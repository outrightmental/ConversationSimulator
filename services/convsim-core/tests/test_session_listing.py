# SPDX-License-Identifier: Apache-2.0
"""GET /api/sessions — the list the resume entry point is built on (issue #501).

The web client already called this endpoint (``api.listSessions``) and the
shared ``SessionCreateResponse`` type already documented it ("Included in list
responses (GET /api/sessions)"), but the route was never registered: the
request answered 405, so Settings' "Your sessions" list only ever showed an
error and nothing in the app could find a conversation to resume.
"""
import json

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app

# The Creator Workbench fixtures build a profile with a loadable local pack,
# which is what makes a preview session possible at all.
from tests.test_workbench_api import ts_client  # noqa: F401

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Test Player",
    "save_transcript": True,
    # Explicit model-free pin (issue #473) so no model install is needed.
    "runtime_id": "fake",
}


def _create(client, **overrides) -> str:
    resp = client.post("/api/sessions", json={**_SETUP, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def test_list_sessions_returns_200(client):
    assert client.get("/api/sessions").status_code == 200


def test_list_sessions_empty_profile(client):
    assert client.get("/api/sessions").json() == {"sessions": []}


def test_list_sessions_includes_created_session(client):
    session_id = _create(client)
    sessions = client.get("/api/sessions").json()["sessions"]
    assert [s["session_id"] for s in sessions] == [session_id]
    entry = sessions[0]
    assert entry["scenario_id"] == "behavioral_interview"
    assert entry["state"] == "NotStarted"
    assert entry["turn_count"] == 0
    assert entry["ending_type"] is None
    assert entry["ended_at"] is None
    # The setup is what lets the Conversation screen rehydrate a resumed
    # session without the route state it was originally launched with.
    assert entry["setup"]["player_role_name"] == "Test Player"


def test_list_sessions_newest_first(client):
    first = _create(client)
    second = _create(client)
    ids = [s["session_id"] for s in client.get("/api/sessions").json()["sessions"]]
    # created_at has one-second resolution, so ordering must not depend on the
    # two inserts landing in different seconds.
    assert ids == [second, first]


def test_in_progress_excludes_unstarted_sessions(client):
    """A NotStarted session has nothing to go back to, so it is not resumable."""
    _create(client)
    body = client.get("/api/sessions", params={"status": "in_progress"}).json()
    assert body["sessions"] == []


def test_in_progress_includes_started_session(client):
    session_id = _create(client)
    assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
    sessions = client.get("/api/sessions", params={"status": "in_progress"}).json()["sessions"]
    assert [s["session_id"] for s in sessions] == [session_id]
    assert sessions[0]["state"] == "PlayerTurnListening"


def test_in_progress_excludes_ended_session(client):
    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/start")
    assert client.post(f"/api/sessions/{session_id}/end").status_code == 200

    in_progress = client.get("/api/sessions", params={"status": "in_progress"}).json()
    assert in_progress["sessions"] == []

    ended = client.get("/api/sessions", params={"status": "ended"}).json()["sessions"]
    assert [s["session_id"] for s in ended] == [session_id]
    assert ended[0]["ending_type"] == "player_exit"
    assert ended[0]["ended_at"] is not None


def test_turn_count_reflects_whole_turns(client):
    """turn_count counts player+NPC exchanges, not transcript rows (issue #501 §4)."""
    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/start")
    client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello there."})

    sessions = client.get("/api/sessions").json()["sessions"]
    assert sessions[0]["turn_count"] == 1

    rows = client.get(f"/api/sessions/{session_id}/transcript").json()["turns"]
    # One opening + one player row + one NPC row = three rows for one turn.
    assert len(rows) == 3


def test_limit_caps_the_result(client):
    for _ in range(3):
        _create(client)
    sessions = client.get("/api/sessions", params={"limit": 2}).json()["sessions"]
    assert len(sessions) == 2


def test_limit_out_of_range_is_rejected(client):
    assert client.get("/api/sessions", params={"limit": 0}).status_code == 400
    assert client.get("/api/sessions", params={"limit": 501}).status_code == 400


def test_unknown_status_is_rejected(client):
    assert client.get("/api/sessions", params={"status": "nonsense"}).status_code == 422


def test_get_single_session_still_carries_setup(client):
    """Resume after a relaunch reads the setup back from this endpoint."""
    session_id = _create(client, show_state_meters=True, language="en")
    body = client.get(f"/api/sessions/{session_id}").json()
    assert body["setup"]["show_state_meters"] is True
    assert body["setup"]["language"] == "en"


def test_ended_includes_a_session_whose_debrief_was_generated(client):
    """`Ended` is only the first state a finished session passes through.

    Generating the debrief moves the row to DebriefReady, so a session the
    player actually played to the end is almost never still `Ended` by the time
    anything lists it. Matching only `Ended` left those sessions in neither
    filter.
    """
    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/start")
    client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello there."})
    client.post(f"/api/sessions/{session_id}/end")
    assert client.post(f"/api/sessions/{session_id}/debrief").status_code == 200
    assert client.get(f"/api/sessions/{session_id}").json()["state"] == "DebriefReady"

    ended = client.get("/api/sessions", params={"status": "ended"}).json()["sessions"]
    assert [s["session_id"] for s in ended] == [session_id]
    # And it is still not offered as something to pick back up.
    in_progress = client.get("/api/sessions", params={"status": "in_progress"}).json()
    assert in_progress["sessions"] == []


def test_single_session_reports_the_visible_meters(client):
    """A resuming conversation screen reads its meters back from here.

    Meter values only ever arrived with a turn, so without this a player who
    stepped out to Settings came back to a conversation with no meters at all
    until they sent another message (issue #501 §1 and §3).
    """
    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/start")
    client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello there."})

    body = client.get(f"/api/sessions/{session_id}").json()
    assert body["visible_state"], "expected the scenario's meter values"
    assert all(isinstance(v, int) for v in body["visible_state"].values())


def test_visible_meters_are_reported_before_the_first_turn(client):
    """Resume between the opening and the first reply keeps the meters (issue #501).

    start_session only flips flow_state; the variables are first persisted by
    the first turn. The opening event has already shown the player the
    scenario's initial meters by then, so a player who reads the opening, steps
    out to Settings and clicks Resume must get those same values back — not an
    empty object that makes the meters panel vanish until they send a message.
    """
    session_id = _create(client)
    start = client.post(f"/api/sessions/{session_id}/start").json()
    opening = next(e for e in start["events"] if e["event_type"] == "npc_opening")
    assert opening["payload"]["visible_state"], "the opening should carry meters"

    body = client.get(f"/api/sessions/{session_id}").json()
    assert body["state"] == "PlayerTurnListening"
    assert body["visible_state"] == opening["payload"]["visible_state"]


def test_unstarted_session_reports_no_meters(client):
    """Before the opening nothing has been shown, so there is nothing to restore."""
    session_id = _create(client)
    assert client.get(f"/api/sessions/{session_id}").json()["visible_state"] == {}


def test_visible_meters_exclude_hidden_variables(client):
    """Hidden state variables are hidden from the player, resume included."""
    from convsim_core.scenario_state import build_variable_defs
    from convsim_core.scenario_state import VariableVisibility

    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/start")
    client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello there."})

    hidden = {
        name
        for name, defn in build_variable_defs().items()
        if defn.visibility == VariableVisibility.HIDDEN
    }
    reported = set(client.get(f"/api/sessions/{session_id}").json()["visible_state"])
    assert reported.isdisjoint(hidden)


def test_workbench_preview_is_never_offered_for_resume(ts_client):
    """A pack author's preview session is not the player's conversation.

    Workbench previews are written straight into `turn_sessions` under a
    dynamic `__wbtest__<hex>` scenario id and nothing ever ends them, so left
    in this listing one would sit at the top of the resumable set forever and
    offer to resume a scenario that only ever existed in memory.
    """
    assert ts_client.post(
        "/api/workbench/packs/local-dev/ts-pack/test-session"
    ).status_code == 200

    assert ts_client.get(
        "/api/sessions", params={"status": "in_progress"}
    ).json()["sessions"] == []
    assert ts_client.get("/api/sessions").json()["sessions"] == []


# ── Demo edition ─────────────────────────────────────────────────────────────
# The demo shares its data folder with the full app (issue #495), so the table
# this endpoint reads can hold sessions of scenarios the demo never offers.


@pytest.fixture()
def demo_client(tmp_config):
    app = create_app(tmp_config.model_copy(update={"edition": "demo"}))
    with TestClient(app) as c:
        yield c


def _insert_started_row(client, session_id: str, scenario_id: str) -> None:
    """A started session, written the way the full app leaves one behind.

    The demo's create route refuses these scenario ids, so the only way such a
    row reaches a demo build is through the shared data folder.
    """
    conn = client.app.state.db.connection()
    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, "
        "turn_count, setup_json, created_at) "
        "VALUES (?, ?, 'PlayerTurnListening', '{}', '[]', 0, ?, ?)",
        (
            session_id,
            scenario_id,
            json.dumps({**_SETUP, "scenario_id": scenario_id}),
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()


def test_demo_lists_only_the_demo_conversations(demo_client):
    """A full-app session in the shared folder is never offered to the demo.

    create_session already refuses the non-demo ids and the scenario routes
    404 them, but the resumed turn route plays whatever this list offers: left
    unfiltered, a demo build showed "Resume your conversation —
    first_words_tutorial" and then played a scenario it can neither create nor
    describe. Applies to every status, so Settings' list is gated too.
    """
    demo_id = _create(demo_client)  # behavioral_interview is one of the five
    assert demo_client.post(f"/api/sessions/{demo_id}/start").status_code == 200
    _insert_started_row(demo_client, "sess-full-library", "hostile_executive_interview")
    _insert_started_row(demo_client, "sess-tutorial", "first_words_tutorial")

    in_progress = demo_client.get("/api/sessions", params={"status": "in_progress"}).json()
    assert [s["session_id"] for s in in_progress["sessions"]] == [demo_id]
    everything = demo_client.get("/api/sessions").json()
    assert [s["session_id"] for s in everything["sessions"]] == [demo_id]


def test_full_edition_lists_every_scenario(client):
    """The gate is the demo's: the full app shows the player all of their sessions."""
    _insert_started_row(client, "sess-full-library", "hostile_executive_interview")
    _insert_started_row(client, "sess-tutorial", "first_words_tutorial")
    body = client.get("/api/sessions", params={"status": "in_progress"}).json()
    assert {s["session_id"] for s in body["sessions"]} == {"sess-full-library", "sess-tutorial"}


# ── The copy in TypeScript must agree with this one ──────────────────────────
# `status=in_progress` is the filter, but it is not the only place the resumable
# set is decided: Settings lists every unfinished conversation with its own
# Resume button and picks them out client-side. That copy lives in
# packages/shared so the web app and the TypeScript proxy share one list — but
# nothing can make it import this one, and a flow state added here without being
# added there silently loses its Resume button on the screen the lost player of
# issue #501 was standing on.


def _typescript_state_list(name: str) -> list[str]:
    """The string literals in a `const <name> = [...]` block in shared's types."""
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "packages" / "shared" / "src" / "types" / "session.ts"
    ).read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = \[(.*?)\]", source, re.DOTALL)
    assert match is not None, f"{name} not found in packages/shared/src/types/session.ts"
    return re.findall(r"'([^']+)'", match.group(1))


def test_resumable_states_match_the_typescript_copy():
    from convsim_core.routers.sessions import RESUMABLE_FLOW_STATES

    assert _typescript_state_list("RESUMABLE_SESSION_STATES") == list(
        RESUMABLE_FLOW_STATES
    )


def test_ended_states_match_the_typescript_copy():
    from convsim_core.routers.sessions import ENDED_FLOW_STATES

    assert _typescript_state_list("ENDED_SESSION_STATES") == list(ENDED_FLOW_STATES)
