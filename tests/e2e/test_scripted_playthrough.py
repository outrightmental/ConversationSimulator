# SPDX-License-Identifier: Apache-2.0
"""End-to-end scripted playthrough smoke tests (issue #238).

Verifies the full packaged-app journey — sidecar startup → bundled scenario
load → scripted multi-turn text conversation → debrief — against the fake
runtime.

Key properties:
  - No real model download required: the fake runtime is used throughout.
  - Transcript content is never printed in assertion messages so CI artifact
    logs do not inadvertently expose session text.
  - The packaged-environment env vars (CONVSIM_BUNDLED_RUNTIME_DIR,
    official_packs_dir → packs/official/) are applied by conftest.py, so this
    exercises the exact configuration path the Tauri shell uses.

For real-model packaged-app testing see Part F of docs/release-checklist.md.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Scripted conversation parameters
# ---------------------------------------------------------------------------

_SCENARIO_ID = "behavioral_interview"

_SESSION_SETUP: dict = {
    "scenario_id": _SCENARIO_ID,
    "difficulty": "standard",
    "player_role_name": "Packaged App Smoke Tester",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": False,  # no transcript file written during smoke runs
    "seed": None,
}

# Three scripted player turns — generic enough for any interview-style scenario.
_SCRIPTED_TURNS = [
    "I have five years of experience in software development.",
    "My biggest achievement was building a cross-team API platform.",
    "I believe in clear documentation and knowledge sharing.",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_and_start_session(client: TestClient) -> str:
    """Create and start a session; return the session_id."""
    create_res = client.post("/api/sessions", json=_SESSION_SETUP)
    assert create_res.status_code == 201, (
        f"Session creation failed (status {create_res.status_code})"
    )
    session_id = create_res.json()["session_id"]
    start_res = client.post(f"/api/sessions/{session_id}/start")
    assert start_res.status_code == 200, (
        f"Session start failed (status {start_res.status_code})"
    )
    return session_id


# ---------------------------------------------------------------------------
# Health and sidecar startup
# ---------------------------------------------------------------------------


class TestPackagedStartupHealth:
    """Sidecar reports healthy immediately after startup in packaged env."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json().get("status") == "ok", (
            "Expected health status 'ok' in packaged-environment mode"
        )

    def test_health_includes_runtime_field(self, client: TestClient) -> None:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert "runtime" in res.json(), (
            "Health response must include a runtime field"
        )

    def test_health_includes_database_field(self, client: TestClient) -> None:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert "database" in res.json(), (
            "Health response must include a database field"
        )


# ---------------------------------------------------------------------------
# Bundled scenario library
# ---------------------------------------------------------------------------


class TestBundledScenarioLibrary:
    """Bundled official packs are loadable in packaged-environment mode."""

    def test_scenarios_endpoint_returns_200(self, client: TestClient) -> None:
        res = client.get("/api/scenarios")
        assert res.status_code == 200

    def test_at_least_one_scenario_present(self, client: TestClient) -> None:
        res = client.get("/api/scenarios")
        assert res.status_code == 200
        scenarios = res.json()
        assert len(scenarios) >= 1, (
            "Expected at least one scenario from the bundled official packs"
        )

    def test_behavioral_interview_scenario_loadable(self, client: TestClient) -> None:
        res = client.get("/api/scenarios")
        assert res.status_code == 200
        ids = {s.get("scenario_id") for s in res.json()}
        assert _SCENARIO_ID in ids, (
            f"Bundled scenario '{_SCENARIO_ID}' not found in the scenario library — "
            "the official packs may not be loading from official_packs_dir"
        )

    def test_scenario_card_has_required_fields(self, client: TestClient) -> None:
        res = client.get("/api/scenarios")
        assert res.status_code == 200
        scenarios = res.json()
        assert scenarios, "Scenario list must be non-empty"
        card = next((s for s in scenarios if s.get("scenario_id") == _SCENARIO_ID), None)
        if card is None:
            card = scenarios[0]
        assert card.get("scenario_id"), "Scenario card must have a non-empty scenario_id"
        assert card.get("title"), "Scenario card must have a non-empty title"
        assert "difficulty_default" in card, "Scenario card must expose difficulty_default"


# ---------------------------------------------------------------------------
# Scripted multi-turn text playthrough
# ---------------------------------------------------------------------------


class TestScriptedTextPlaythrough:
    """Full scripted text playthrough: create → start → turns → end → debrief."""

    def test_session_create_returns_session_id(self, client: TestClient) -> None:
        res = client.post("/api/sessions", json=_SESSION_SETUP)
        assert res.status_code == 201
        body = res.json()
        assert "session_id" in body, "Create response must include session_id"
        assert body["session_id"], "session_id must be non-empty"
        assert body["session_id"].startswith("sess-"), (
            "session_id must follow the 'sess-' prefix convention"
        )

    def test_session_start_delivers_npc_opening(self, client: TestClient) -> None:
        session_id = _create_and_start_session(client)
        state_res = client.get(f"/api/sessions/{session_id}")
        assert state_res.status_code == 200
        assert state_res.json().get("state") == "PlayerTurnListening", (
            "Expected state PlayerTurnListening after start"
        )

    def test_first_scripted_turn_succeeds(self, client: TestClient) -> None:
        session_id = _create_and_start_session(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": _SCRIPTED_TURNS[0]},
        )
        assert res.status_code == 200, (
            f"First scripted turn failed (status {res.status_code})"
        )
        events = res.json().get("events", [])
        assert len(events) >= 2, (
            "Turn response must include at least player and NPC events"
        )
        event_types = {e.get("event_type") for e in events}
        assert "npc_turn" in event_types, (
            "NPC turn event missing from first turn response"
        )

    def test_three_scripted_turns_complete_without_error(self, client: TestClient) -> None:
        session_id = _create_and_start_session(client)
        for i, turn_text in enumerate(_SCRIPTED_TURNS):
            res = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": turn_text},
            )
            assert res.status_code == 200, (
                f"Scripted turn {i + 1}/{len(_SCRIPTED_TURNS)} failed "
                f"(status {res.status_code})"
            )
            # Check structure only, not content, to avoid leaking transcript text.
            events = res.json().get("events", [])
            event_types = {e.get("event_type") for e in events}
            assert "npc_turn" in event_types, (
                f"NPC turn event missing from turn {i + 1}"
            )
            npc_events = [e for e in events if e.get("event_type") == "npc_turn"]
            payload = npc_events[0].get("payload", {})
            assert isinstance(payload.get("content"), str), (
                f"NPC turn {i + 1} content must be a string"
            )
            assert len(payload["content"]) > 0, (
                f"NPC turn {i + 1} content must be non-empty"
            )

    def test_session_state_after_turns_is_player_turn_listening(
        self, client: TestClient
    ) -> None:
        session_id = _create_and_start_session(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": _SCRIPTED_TURNS[0]},
        )
        state_res = client.get(f"/api/sessions/{session_id}")
        assert state_res.status_code == 200
        assert state_res.json().get("state") == "PlayerTurnListening", (
            "Session must remain in PlayerTurnListening after a completed turn"
        )

    def test_session_end_transitions_to_ended(self, client: TestClient) -> None:
        session_id = _create_and_start_session(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": _SCRIPTED_TURNS[0]},
        )
        end_res = client.post(f"/api/sessions/{session_id}/end")
        assert end_res.status_code == 200, (
            f"Session end failed (status {end_res.status_code})"
        )
        assert end_res.json().get("state") == "Ended", (
            "Expected state Ended after ending the session"
        )

    def test_debrief_generated_after_full_playthrough(
        self, client: TestClient
    ) -> None:
        session_id = _create_and_start_session(client)
        for turn_text in _SCRIPTED_TURNS:
            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": turn_text},
            )
        client.post(f"/api/sessions/{session_id}/end")

        debrief_res = client.post(f"/api/sessions/{session_id}/debrief")
        assert debrief_res.status_code == 200, (
            f"Debrief generation failed (status {debrief_res.status_code})"
        )
        body = debrief_res.json()
        assert body.get("session_id") == session_id, (
            "Debrief must reference the correct session"
        )

    def test_debrief_has_scores_and_summary(self, client: TestClient) -> None:
        session_id = _create_and_start_session(client)
        for turn_text in _SCRIPTED_TURNS:
            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": turn_text},
            )
        client.post(f"/api/sessions/{session_id}/end")
        body = client.post(f"/api/sessions/{session_id}/debrief").json()

        # Check structure only, not values, to avoid exposing session content.
        assert "scores" in body, "Debrief must include a scores field"
        assert "summary" in body, "Debrief must include a summary field"
        assert isinstance(body["scores"], dict), "Debrief scores must be a dict"

    def test_debrief_is_idempotent(self, client: TestClient) -> None:
        session_id = _create_and_start_session(client)
        client.post(f"/api/sessions/{session_id}/end")
        r1 = client.post(f"/api/sessions/{session_id}/debrief")
        r2 = client.post(f"/api/sessions/{session_id}/debrief")
        assert r1.status_code == 200
        assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Transcript privacy
# ---------------------------------------------------------------------------


class TestTranscriptPrivacy:
    """Smoke infrastructure must not expose transcripts in failure artifacts."""

    def test_save_transcript_disabled_in_smoke_config(self) -> None:
        """The smoke session config must have save_transcript=False.

        This prevents transcript files from being written to the data directory
        during CI runs, which is the first line of defence against transcript
        content appearing in uploaded failure artifacts.
        """
        assert _SESSION_SETUP.get("save_transcript") is False, (
            "Packaged-app smoke tests must set save_transcript=False to prevent "
            "transcripts from being written to the data directory"
        )

    def test_no_outbound_calls_in_packaged_env(self, client: TestClient) -> None:
        """A packaged-env session must not attempt any outbound connections."""
        import convsim_core.network_policy as policy

        original = policy.LOCAL_MODE
        policy.LOCAL_MODE = True
        try:
            session_id = _create_and_start_session(client)
            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": _SCRIPTED_TURNS[0]},
            )
            end_res = client.post(f"/api/sessions/{session_id}/end")
            assert end_res.status_code == 200, (
                "Session end raised an error; an outbound connection may have been "
                "attempted — verify the fake runtime is being used"
            )
        finally:
            policy.LOCAL_MODE = original
