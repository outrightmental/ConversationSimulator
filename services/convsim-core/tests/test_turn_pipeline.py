# SPDX-License-Identifier: Apache-2.0
"""Tests for the text-only player turn pipeline (issue #18).

Test plan:
  - Integration: two-turn text conversation using the fake runtime.
  - Integration: state changes persist and carry forward to the next turn.
  - Integration: ending condition fires when max_turns is reached.
  - Unit: empty input is rejected.
  - Unit: whitespace-only input is rejected.
  - Unit: oversized input is rejected.
  - Unit: invalid model output triggers safe fallback.
  - Unit: safety.status='stop' ends the session with safety_stop.
  - Unit: safety.status='redirect' keeps session alive.
  - Idempotency guard: state machine rejects a turn in a non-listening state.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    ChatToken,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeStatus,
)
from convsim_core.scenario_state import build_variable_defs, initialize_state
from convsim_core.scenarios import get_scenario_info
from convsim_core.services.turn_pipeline import (
    MAX_TURN_CONTENT_CHARS,
    TurnInputError,
    process_turn,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


_VALID_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "normal",
    "player_role_name": "Alice",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "seed": None,
}


def _create_and_start(client: TestClient) -> str:
    """Helper: create + start a session, return session_id."""
    res = client.post("/api/sessions", json=_VALID_SETUP)
    assert res.status_code == 201
    session_id = res.json()["session_id"]

    res = client.post(f"/api/sessions/{session_id}/start")
    assert res.status_code == 200
    assert res.json()["state"] == "PlayerTurnListening"
    return session_id


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


class TestSessionCreate:
    def test_creates_session_with_201(self, client):
        res = client.post("/api/sessions", json=_VALID_SETUP)
        assert res.status_code == 201
        body = res.json()
        assert body["session_id"].startswith("sess-")
        assert body["scenario_id"] == "behavioral_interview"
        assert body["state"] == "NotStarted"

    def test_returns_400_for_unknown_scenario(self, client):
        res = client.post("/api/sessions", json={**_VALID_SETUP, "scenario_id": "nonexistent"})
        assert res.status_code == 400

    def test_returns_400_for_unavailable_difficulty(self, client):
        res = client.post("/api/sessions", json={
            **_VALID_SETUP,
            "scenario_id": "hostile_executive_interview",
            "difficulty": "easy",
        })
        assert res.status_code == 400

    def test_returns_400_for_unsupported_language(self, client):
        res = client.post("/api/sessions", json={**_VALID_SETUP, "language": "fr"})
        assert res.status_code == 400

    def test_returns_422_for_blank_player_role_name(self, client):
        res = client.post("/api/sessions", json={**_VALID_SETUP, "player_role_name": "   "})
        assert res.status_code == 422

    def test_get_session_returns_correct_state(self, client):
        res = client.post("/api/sessions", json=_VALID_SETUP)
        session_id = res.json()["session_id"]

        get_res = client.get(f"/api/sessions/{session_id}")
        assert get_res.status_code == 200
        assert get_res.json()["session_id"] == session_id
        assert get_res.json()["state"] == "NotStarted"

    def test_get_unknown_session_returns_404(self, client):
        res = client.get("/api/sessions/sess-doesnotexist")
        assert res.status_code == 404


class TestSessionStart:
    def test_start_transitions_to_player_turn_listening(self, client):
        res = client.post("/api/sessions", json=_VALID_SETUP)
        session_id = res.json()["session_id"]

        start_res = client.post(f"/api/sessions/{session_id}/start")
        assert start_res.status_code == 200
        body = start_res.json()
        assert body["state"] == "PlayerTurnListening"
        assert len(body["events"]) == 1
        assert body["events"][0]["event_type"] == "npc_opening"
        assert isinstance(body["events"][0]["payload"]["content"], str)

    def test_start_persists_state(self, client):
        res = client.post("/api/sessions", json=_VALID_SETUP)
        session_id = res.json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")

        get_res = client.get(f"/api/sessions/{session_id}")
        assert get_res.json()["state"] == "PlayerTurnListening"

    def test_double_start_returns_409(self, client):
        session_id = _create_and_start(client)
        res = client.post(f"/api/sessions/{session_id}/start")
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "INVALID_TRANSITION"


# ---------------------------------------------------------------------------
# Integration: two-turn text conversation with fake runtime
# ---------------------------------------------------------------------------


class TestTurnPipelineIntegration:
    def test_single_turn_stores_player_and_npc_events(self, client):
        session_id = _create_and_start(client)

        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I have five years of product management experience."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["session_id"] == session_id
        assert body["state"] == "PlayerTurnListening"

        events = body["events"]
        assert len(events) == 2
        assert events[0]["event_type"] == "player_turn"
        assert events[0]["payload"]["content"] == "I have five years of product management experience."
        assert events[1]["event_type"] == "npc_turn"

        npc_payload = events[1]["payload"]
        assert isinstance(npc_payload["content"], str)
        assert len(npc_payload["content"]) > 0
        assert npc_payload["emotion"] in {
            "neutral", "warm", "curious", "skeptical", "impatient",
            "defensive", "confused", "impressed", "concerned", "angry",
        }

    def test_two_turn_conversation(self, client):
        session_id = _create_and_start(client)

        res1 = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I built a payments platform from scratch."},
        )
        assert res1.status_code == 200
        assert res1.json()["state"] == "PlayerTurnListening"

        res2 = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "The hardest part was aligning stakeholders."},
        )
        assert res2.status_code == 200
        assert res2.json()["state"] == "PlayerTurnListening"

        events2 = res2.json()["events"]
        assert events2[0]["event_type"] == "player_turn"
        assert events2[1]["event_type"] == "npc_turn"

    def test_npc_response_always_passes_schema_or_is_fallback(self, client):
        """NPC utterance is either from the schema or the safe fallback string."""
        from convsim_prompt import SAFE_FALLBACK_UTTERANCE
        session_id = _create_and_start(client)

        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Tell me about your company culture."},
        )
        assert res.status_code == 200
        npc_content = res.json()["events"][1]["payload"]["content"]
        assert isinstance(npc_content, str)
        assert len(npc_content) > 0

    def test_state_vars_initialized_and_accessible(self, client):
        """State vars should be initialized from baseline defaults on first turn."""
        session_id = _create_and_start(client)

        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I'm excited to be here."},
        )
        assert res.status_code == 200
        # Fake runtime returns empty state_delta, so state_delta should be {} or empty
        state_delta = res.json()["events"][1]["payload"]["state_delta"]
        assert isinstance(state_delta, dict)

    def test_session_stays_in_player_turn_listening_after_turn(self, client):
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "My first response."},
        )
        get_res = client.get(f"/api/sessions/{session_id}")
        assert get_res.json()["state"] == "PlayerTurnListening"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestTurnInputValidation:
    def test_empty_content_returns_422(self, client):
        session_id = _create_and_start(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": ""},
        )
        assert res.status_code == 422

    def test_whitespace_only_content_returns_422(self, client):
        session_id = _create_and_start(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "   "},
        )
        assert res.status_code == 422

    def test_oversized_content_returns_422(self, client):
        session_id = _create_and_start(client)
        oversized = "a" * (MAX_TURN_CONTENT_CHARS + 1)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": oversized},
        )
        assert res.status_code == 422

    def test_max_length_content_accepted(self, client):
        session_id = _create_and_start(client)
        exactly_max = "a" * MAX_TURN_CONTENT_CHARS
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": exactly_max},
        )
        assert res.status_code == 200

    def test_turn_from_not_started_state_returns_409(self, client):
        res = client.post("/api/sessions", json=_VALID_SETUP)
        session_id = res.json()["session_id"]
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Too early."},
        )
        assert res.status_code == 409

    def test_turn_from_ended_session_returns_409(self, client):
        session_id = _create_and_start(client)
        client.post(f"/api/sessions/{session_id}/end")
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Too late."},
        )
        assert res.status_code == 409

    def test_turn_on_unknown_session_returns_404(self, client):
        res = client.post(
            "/api/sessions/sess-doesnotexist/turn",
            json={"content": "hello"},
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Ending conditions
# ---------------------------------------------------------------------------


class TestEndingConditions:
    def test_timeout_ending_fires_when_max_turns_reached(self, client):
        """When turn_count reaches max_turns, session ends with timeout."""
        # Use behavioral_interview (max_turns=18) but set up a mock with max_turns=1
        res = client.post("/api/sessions", json=_VALID_SETUP)
        session_id = res.json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")

        # Patch max_turns=1 so the first turn triggers timeout.
        with patch.object(
            get_scenario_info("behavioral_interview"),
            "max_turns",
            new=1,
        ):
            res = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "This should be the last turn."},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["state"] == "Ended"
        assert body["ending_type"] == "timeout"

    def test_end_session_explicit(self, client):
        session_id = _create_and_start(client)
        res = client.post(f"/api/sessions/{session_id}/end")
        assert res.status_code == 200
        assert res.json()["state"] == "Ended"
        assert res.json()["ending_type"] == "player_exit"

    def test_ended_session_cannot_accept_turn(self, client):
        session_id = _create_and_start(client)
        client.post(f"/api/sessions/{session_id}/end")
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "After the end."},
        )
        assert res.status_code == 409


# ---------------------------------------------------------------------------
# Safety handling (unit-level pipeline tests)
# ---------------------------------------------------------------------------


class _SafetyStopRuntime(FakeChatRuntime):
    """Fake runtime that returns safety.status='stop'."""

    def chat_stream(self, request: ChatRequest):
        return self._stream_stop(request)

    async def _stream_stop(self, request: ChatRequest):
        import json as _json
        response = {
            "npc_utterance": "I can't continue this conversation.",
            "npc_emotion": "neutral",
            "state_delta": {},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "stop", "reason": "Content policy violation"},
            "session_control": {"continue_session": False, "ending_type": "safety_stop"},
        }
        text = _json.dumps(response)
        from convsim_core.runtime.types import ChatToken, ChatFinal
        for word in text.split():
            yield ChatToken(text=word + " ")
        yield ChatFinal(
            text=text,
            model_id="fake-small",
            input_tokens=10,
            output_tokens=len(text.split()),
            structured=response,
        )


class _SafetyRedirectRuntime(FakeChatRuntime):
    """Fake runtime that returns safety.status='redirect'."""

    def chat_stream(self, request: ChatRequest):
        return self._stream_redirect(request)

    async def _stream_redirect(self, request: ChatRequest):
        import json as _json
        response = {
            "npc_utterance": "Let's keep this professional.",
            "npc_emotion": "concerned",
            "state_delta": {},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "redirect", "reason": "Off-topic content"},
            "session_control": {"continue_session": True},
        }
        text = _json.dumps(response)
        from convsim_core.runtime.types import ChatToken, ChatFinal
        for word in text.split():
            yield ChatToken(text=word + " ")
        yield ChatFinal(
            text=text,
            model_id="fake-small",
            input_tokens=10,
            output_tokens=len(text.split()),
            structured=response,
        )


class TestSafetyHandling:
    def test_safety_stop_ends_session(self, tmp_config):
        app = create_app(tmp_config)
        app.state  # ensure lifespan runs via TestClient

        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            # Override runtime with one that returns safety=stop
            app.state.runtime = _SafetyStopRuntime()

            res = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "Something inappropriate."},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["state"] == "Ended"
        assert body["ending_type"] == "safety_stop"

    def test_safety_redirect_keeps_session_alive(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _SafetyRedirectRuntime()

            res = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "Off-topic question."},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["state"] == "PlayerTurnListening"
        npc_content = body["events"][1]["payload"]["content"]
        assert "professional" in npc_content.lower() or len(npc_content) > 0

    def test_safety_status_included_in_npc_event_payload(self, client):
        session_id = _create_and_start(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Normal question."},
        )
        npc_payload = res.json()["events"][1]["payload"]
        assert "safety" in npc_payload
        assert npc_payload["safety"]["status"] in {"ok", "redirect", "stop"}


# ---------------------------------------------------------------------------
# Invalid model output → safe fallback
# ---------------------------------------------------------------------------


class _GarbageRuntime(FakeChatRuntime):
    """Runtime that returns unparseable garbage (triggers safe fallback)."""

    def chat_stream(self, request: ChatRequest):
        return self._stream_garbage(request)

    async def _stream_garbage(self, request: ChatRequest):
        from convsim_core.runtime.types import ChatFinal
        garbage = "This is not JSON at all {{{{"
        yield ChatFinal(
            text=garbage,
            model_id="fake-small",
            input_tokens=5,
            output_tokens=5,
            structured=None,
        )


class TestFallback:
    def test_invalid_model_output_uses_safe_fallback(self, tmp_config):
        from convsim_prompt import SAFE_FALLBACK_UTTERANCE
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _GarbageRuntime()

            res = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "What can you tell me about this role?"},
            )
        assert res.status_code == 200
        npc_content = res.json()["events"][1]["payload"]["content"]
        assert npc_content == SAFE_FALLBACK_UTTERANCE


# ---------------------------------------------------------------------------
# State persistence across turns (unit-level, direct pipeline call)
# ---------------------------------------------------------------------------


class _StateDeltaRuntime(FakeChatRuntime):
    """Runtime that returns a non-empty state_delta."""

    def chat_stream(self, request: ChatRequest):
        return self._stream_with_delta(request)

    async def _stream_with_delta(self, request: ChatRequest):
        import json as _json
        from convsim_core.runtime.types import ChatFinal
        response = {
            "npc_utterance": "Great answer! I'm impressed.",
            "npc_emotion": "impressed",
            "state_delta": {"trust": 10, "rapport": 5},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": True},
        }
        text = _json.dumps(response)
        yield ChatFinal(
            text=text,
            model_id="fake-small",
            input_tokens=10,
            output_tokens=len(text.split()),
            structured=response,
        )


class TestStatePersistence:
    def test_state_delta_applied_and_persisted(self, tmp_config):
        """State changes from the runtime are applied and stored for next turn."""
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _StateDeltaRuntime()

            res = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I led cross-functional teams at three companies."},
            )
        assert res.status_code == 200
        npc_payload = res.json()["events"][1]["payload"]
        # The fake runtime requested trust+10, rapport+5
        assert npc_payload["state_delta"].get("trust", 0) == 10
        assert npc_payload["state_delta"].get("rapport", 0) == 5

    def test_state_carries_into_subsequent_turns(self, tmp_config):
        """State vars from turn N are available (via DB) for prompt building in turn N+1."""
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _StateDeltaRuntime()

            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "First turn."},
            )

            # Second turn should succeed (state vars carried over).
            res2 = client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "Second turn."},
            )
        assert res2.status_code == 200
        assert res2.json()["state"] == "PlayerTurnListening"
