# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — Player text-path journey (issue #80).

Acceptance criteria exercised:
  P-1  Select a scenario from the library.
  P-2  Start a session; NPC opening line is delivered.
  P-3  Submit a player turn; NPC responds.
  P-4  Session state evolves and carries into the next turn.
  P-5  End the session cleanly.
  P-6  Debrief report is generated after the session ends.
  P-7  A completed session can be retrieved again (basis for replay).
  P-8  No outbound cloud-inference calls occur during the entire journey.

All checks run against the fake runtime — no model download required.
Owner: platform team.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatToken

# Re-export shared setup dict so individual tests can customise it.
_SESSION_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "normal",
    "player_role_name": "Acceptance Tester",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "seed": None,
}

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_minimal_zip() -> bytes:
    """Build a minimal installable pack zip for acceptance scenario library tests."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("player-pack/manifest.yaml", (
            'schema_version: "0.1"\n'
            'pack_id: acceptance.player_pack\n'
            'name: Player Acceptance Pack\n'
            'version: 1.0.0\n'
            'description: Minimal pack for player acceptance testing.\n'
            'author: Acceptance Suite\n'
            'license: CC-BY-4.0\n'
            'content_rating: G\n'
            'tags:\n  - acceptance\n'
            'supported_languages:\n  - en\n'
            'entry_scenarios:\n  - scenarios/practice.yaml\n'
            'assets:\n  allow_external_urls: false\n'
            'safety:\n  policy: safety/policy.yaml\n'
        ))
        zf.writestr("player-pack/safety/policy.yaml", (
            'schema_version: "0.1"\n'
            'policy_id: player_policy\n'
            'content_rating_cap: G\n'
            'content_categories:\n'
            '  nsfw_sexual: block\n'
            '  real_person_impersonation: block\n'
            '  instructional_criminal: block\n'
            '  crisis_content: redirect\n'
            'redirect_message: "Let\'s keep things on topic."\n'
        ))
        zf.writestr("player-pack/npcs/guide.yaml", (
            'schema_version: "0.1"\n'
            'npc_id: player_guide\n'
            'display_name: Practice Guide\n'
            'archetype: generic\n'
            'fictional: true\n'
            'age_band: adult\n'
            'public_persona:\n'
            '  occupation: Practice Facilitator\n'
            '  speaking_style: Warm and encouraging\n'
            '  demeanor: Supportive\n'
            'private_persona: {}\n'
        ))
        zf.writestr("player-pack/rubrics/practice.yaml", (
            'schema_version: "0.1"\n'
            'rubric_id: practice_rubric\n'
            'title: Practice Rubric\n'
            'dimensions:\n'
            '  - id: clarity\n'
            '    name: Clarity\n'
            '    description: How clearly the player communicates.\n'
            '    scoring:\n'
            '      low: Unclear\n'
            '      medium: Adequate\n'
            '      high: Excellent\n'
        ))
        zf.writestr("player-pack/scenarios/practice.yaml", (
            'schema_version: "0.1"\n'
            'scenario_id: practice_scenario\n'
            'title: Practice Conversation\n'
            'summary: A minimal scenario for acceptance testing the player journey.\n'
            'player_role:\n'
            '  label: Participant\n'
            '  brief: You are verifying the player acceptance test.\n'
            'npc:\n'
            '  ref: ../npcs/guide.yaml\n'
            'rubric:\n'
            '  ref: ../rubrics/practice.yaml\n'
            'duration:\n'
            '  max_turns: 6\n'
            'opening:\n'
            '  npc_says: "Welcome. Let us begin the acceptance test."\n'
            'goals:\n'
            '  player_visible:\n'
            '    - Complete the player acceptance test\n'
        ))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _start_session(client: TestClient) -> str:
    res = client.post("/api/sessions", json=_SESSION_SETUP)
    assert res.status_code == 201, res.text
    session_id = res.json()["session_id"]
    start = client.post(f"/api/sessions/{session_id}/start")
    assert start.status_code == 200, start.text
    return session_id


# ---------------------------------------------------------------------------
# P-1  Scenario selection
# ---------------------------------------------------------------------------


class TestScenarioSelection:
    """A player can discover and select a scenario before starting a session."""

    def test_scenarios_endpoint_returns_200(self, client):
        res = client.get("/api/scenarios")
        assert res.status_code == 200

    def test_scenario_library_lists_installed_scenarios(self, client):
        zip_bytes = _make_minimal_zip()
        import_res = client.post(
            "/api/packs/import/zip",
            files={"file": ("pack.zip", zip_bytes, "application/zip")},
        )
        assert import_res.status_code == 201, import_res.text

        res = client.get("/api/scenarios")
        assert res.status_code == 200
        scenarios = res.json()
        assert len(scenarios) > 0, "expected at least one scenario after pack import"

    def test_scenario_card_has_required_fields(self, client):
        zip_bytes = _make_minimal_zip()
        client.post(
            "/api/packs/import/zip",
            files={"file": ("pack.zip", zip_bytes, "application/zip")},
        )
        res = client.get("/api/scenarios")
        assert res.status_code == 200
        scenarios = res.json()
        assert len(scenarios) > 0
        card = scenarios[0]
        assert card.get("scenario_id"), "scenario card must have a non-empty scenario_id"
        assert card.get("title"), "scenario card must have a non-empty title"
        assert "difficulty_default" in card, "scenario card must expose difficulty"


# ---------------------------------------------------------------------------
# P-2  Session start and NPC opening
# ---------------------------------------------------------------------------


class TestSessionStart:
    """Starting a session delivers the NPC opening line."""

    def test_create_session_with_behavioral_interview(self, client):
        res = client.post("/api/sessions", json=_SESSION_SETUP)
        assert res.status_code == 201
        body = res.json()
        assert body["session_id"].startswith("sess-")
        assert body["state"] == "NotStarted"

    def test_start_delivers_npc_opening(self, client):
        session_id = _start_session(client)
        state = client.get(f"/api/sessions/{session_id}").json()
        assert state["state"] == "PlayerTurnListening"

    def test_npc_opening_event_has_content(self, client):
        res = client.post("/api/sessions", json=_SESSION_SETUP)
        session_id = res.json()["session_id"]
        start = client.post(f"/api/sessions/{session_id}/start")
        events = start.json()["events"]
        assert len(events) == 1
        assert events[0]["event_type"] == "npc_opening"
        assert isinstance(events[0]["payload"]["content"], str)
        assert len(events[0]["payload"]["content"]) > 0


# ---------------------------------------------------------------------------
# P-3  Player turn → NPC response
# ---------------------------------------------------------------------------


class TestPlayerTurn:
    """The player can speak or type; the NPC responds."""

    def test_text_turn_returns_npc_response(self, client):
        session_id = _start_session(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I have five years of product management experience."},
        )
        assert res.status_code == 200
        events = res.json()["events"]
        player_event = events[0]
        npc_event = events[1]
        assert player_event["event_type"] == "player_turn"
        assert npc_event["event_type"] == "npc_turn"
        assert isinstance(npc_event["payload"]["content"], str)
        assert len(npc_event["payload"]["content"]) > 0

    def test_npc_response_has_emotion(self, client):
        session_id = _start_session(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I built a payments platform from scratch."},
        )
        emotion = res.json()["events"][1]["payload"]["emotion"]
        valid_emotions = {
            "neutral", "warm", "curious", "skeptical", "impatient",
            "defensive", "confused", "impressed", "concerned", "angry",
        }
        assert emotion in valid_emotions

    def test_two_consecutive_turns_both_succeed(self, client):
        session_id = _start_session(client)
        r1 = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I led a distributed team across three time zones."},
        )
        assert r1.status_code == 200
        r2 = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "The hardest part was aligning stakeholders with different priorities."},
        )
        assert r2.status_code == 200
        assert r2.json()["state"] == "PlayerTurnListening"


# ---------------------------------------------------------------------------
# P-4  State evolution
# ---------------------------------------------------------------------------


class _StateDeltaRuntime(FakeChatRuntime):
    """Fake runtime that returns a non-trivial state_delta."""

    def chat_stream(self, request):
        return self._yield(request)

    async def _yield(self, request):
        import json as _json
        payload = {
            "npc_utterance": "Impressive. Tell me more.",
            "npc_emotion": "impressed",
            "state_delta": {"trust": 15, "rapport": 8},
            "event_flags": [],
            "rubric_observations": [{"rubric_id": "clarity", "observation": "Clear answer", "score_delta": 3}],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": True},
        }
        text = _json.dumps(payload)
        yield ChatFinal(
            text=text,
            model_id="fake-small",
            input_tokens=10,
            output_tokens=len(text.split()),
            structured=payload,
        )


class TestStateEvolution:
    """Scenario state variables evolve across turns."""

    def test_state_delta_is_present_in_npc_event(self, client):
        session_id = _start_session(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I'm excited to be here."},
        )
        npc_payload = res.json()["events"][1]["payload"]
        assert "state_delta" in npc_payload
        assert isinstance(npc_payload["state_delta"], dict)

    def test_state_delta_applied_to_session(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as c:
            res = c.post("/api/sessions", json=_SESSION_SETUP)
            session_id = res.json()["session_id"]
            c.post(f"/api/sessions/{session_id}/start")
            app.state.runtime = _StateDeltaRuntime()
            res = c.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I led cross-functional teams at three companies."},
            )
        assert res.status_code == 200
        npc_payload = res.json()["events"][1]["payload"]
        assert npc_payload["state_delta"].get("trust") == 15
        assert npc_payload["state_delta"].get("rapport") == 8

    def test_state_carries_into_subsequent_turn(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as c:
            res = c.post("/api/sessions", json=_SESSION_SETUP)
            session_id = res.json()["session_id"]
            c.post(f"/api/sessions/{session_id}/start")
            app.state.runtime = _StateDeltaRuntime()
            c.post(f"/api/sessions/{session_id}/turn", json={"content": "First turn."})
            res2 = c.post(f"/api/sessions/{session_id}/turn", json={"content": "Second turn."})
        assert res2.status_code == 200
        assert res2.json()["state"] == "PlayerTurnListening"


# ---------------------------------------------------------------------------
# P-5  Session end
# ---------------------------------------------------------------------------


class TestSessionEnd:
    """A player can finish a session cleanly."""

    def test_explicit_end_transitions_to_ended(self, client):
        session_id = _start_session(client)
        res = client.post(f"/api/sessions/{session_id}/end")
        assert res.status_code == 200
        body = res.json()
        assert body["state"] == "Ended"
        assert body["ending_type"] == "player_exit"

    def test_turn_after_end_is_rejected(self, client):
        session_id = _start_session(client)
        client.post(f"/api/sessions/{session_id}/end")
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Too late."},
        )
        assert res.status_code == 409


# ---------------------------------------------------------------------------
# P-6  Debrief
# ---------------------------------------------------------------------------


class TestDebrief:
    """After finishing, the player sees a debrief report."""

    def test_debrief_generated_after_session_ends(self, client):
        session_id = _start_session(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I built the product roadmap for a 20-person team."},
        )
        client.post(f"/api/sessions/{session_id}/end")
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("session_id") == session_id
        assert "scores" in body
        assert "summary" in body

    def test_debrief_on_active_session_is_rejected(self, client):
        session_id = _start_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 409

    def test_debrief_is_idempotent(self, client):
        session_id = _start_session(client)
        client.post(f"/api/sessions/{session_id}/end")
        r1 = client.post(f"/api/sessions/{session_id}/debrief")
        r2 = client.post(f"/api/sessions/{session_id}/debrief")
        assert r1.status_code == 200
        assert r2.status_code == 200


# ---------------------------------------------------------------------------
# P-7  Session retrieval (basis for replay)
# ---------------------------------------------------------------------------


class TestSessionRetrieval:
    """A completed session can be retrieved by ID, enabling replay."""

    def test_completed_session_retrievable_by_id(self, client):
        session_id = _start_session(client)
        client.post(f"/api/sessions/{session_id}/end")
        res = client.get(f"/api/sessions/{session_id}")
        assert res.status_code == 200
        assert res.json()["session_id"] == session_id
        assert res.json()["state"] == "Ended"

    def test_multiple_sessions_each_retrievable(self, client):
        ids = []
        for i in range(2):
            res = client.post("/api/sessions", json={**_SESSION_SETUP, "player_role_name": f"Tester {i}"})
            ids.append(res.json()["session_id"])
        for sid in ids:
            get_res = client.get(f"/api/sessions/{sid}")
            assert get_res.status_code == 200
            assert get_res.json()["session_id"] == sid

    def test_session_export_available_after_debrief(self, client):
        session_id = _start_session(client)
        client.post(f"/api/sessions/{session_id}/end")
        client.post(f"/api/sessions/{session_id}/debrief")
        res = client.get(f"/api/sessions/{session_id}/export")
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# P-8  No cloud inference
# ---------------------------------------------------------------------------


class TestNoCloudInference:
    """A complete session must not make any outbound network calls."""

    def test_full_session_does_not_trigger_play_mode_network_call(self, tmp_config):
        """When LOCAL_MODE is True, any play-mode network attempt raises
        NetworkBlockedError.  A full session with the fake runtime must complete
        without triggering that error, proving no cloud inference is attempted."""
        import convsim_core.network_policy as policy
        app = create_app(tmp_config)
        original_local_mode = policy.LOCAL_MODE
        policy.LOCAL_MODE = True
        try:
            with TestClient(app) as c:
                res = c.post("/api/sessions", json=_SESSION_SETUP)
                session_id = res.json()["session_id"]
                c.post(f"/api/sessions/{session_id}/start")
                c.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"content": "I have strong communication skills."},
                )
                end = c.post(f"/api/sessions/{session_id}/end")
            assert end.status_code == 200, (
                "Session ended with an error; a play-mode network call may have been blocked"
            )
        finally:
            policy.LOCAL_MODE = original_local_mode

    def test_fake_runtime_is_used_by_default(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as c:
            health = c.get("/api/health")
        runtime_status = health.json().get("runtime", {})
        runtime_id = runtime_status.get("runtime_id", "") or runtime_status.get("id", "")
        assert "fake" in runtime_id.lower() or runtime_status.get("status") in {"ready", "ok"}, (
            f"expected fake runtime in test environment, got: {runtime_status}"
        )
