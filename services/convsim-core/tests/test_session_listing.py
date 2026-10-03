# SPDX-License-Identifier: Apache-2.0
"""GET /api/sessions — the list the resume entry point is built on (issue #501).

The web client already called this endpoint (``api.listSessions``) and the
shared ``SessionCreateResponse`` type already documented it ("Included in list
responses (GET /api/sessions)"), but the route was never registered: the
request answered 405, so Settings' "Your sessions" list only ever showed an
error and nothing in the app could find a conversation to resume.
"""

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
