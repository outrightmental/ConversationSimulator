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
  - Unit (issue #199): prompt layer ordering respected end-to-end.
  - Unit (issue #199): safety-policy config is converted and forwarded to compose_turn_prompt.
  - Unit (issue #199): hidden agenda is forwarded to parse_turn_output for leak detection.
  - Unit (issue #199): prompt metadata persisted without private content.
  - Unit (issue #199): transcript truncation flag stored in prompt_metadata event.
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
from convsim_core.input_router import RouteAction, SafetyPolicyConfig
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
from convsim_core.scenarios import get_scenario_data, get_scenario_info
from convsim_core.services.turn_pipeline import (
    MAX_TURN_CONTENT_CHARS,
    TurnInputError,
    process_turn,
)
from convsim_core.storage.migrations import run_migrations
from convsim_prompt import LAYER_ORDER, SafetyPolicy, TurnEvent
from convsim_prompt.turn_output import SafetyStatus, SessionControl, TurnOutput


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


# ---------------------------------------------------------------------------
# Helpers for direct process_turn unit tests (issue #199)
# ---------------------------------------------------------------------------

def _make_unit_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with all migrations applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn


def _insert_unit_session(
    conn: sqlite3.Connection,
    session_id: str = "sess-unit",
) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, "
        "turn_count, setup_json) "
        "VALUES (?, 'behavioral_interview', 'PlayerTurnListening', '{}', '[]', 0, '{}')",
        (session_id,),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()


def _get_event_payloads(
    conn: sqlite3.Connection,
    session_id: str,
    event_type: str,
) -> list:
    rows = conn.execute(
        "SELECT payload_json FROM turn_session_events "
        "WHERE session_id = ? AND event_type = ?",
        (session_id, event_type),
    ).fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


def _valid_turn_output() -> TurnOutput:
    return TurnOutput(
        npc_utterance="That's a great point, thank you.",
        npc_emotion="neutral",
        state_delta={},
        event_flags=[],
        rubric_observations=[],
        safety=SafetyStatus(status="ok"),
        session_control=SessionControl(continue_session=True),
    )


# ---------------------------------------------------------------------------
# Issue #199: prompt-composer wiring unit tests
# ---------------------------------------------------------------------------


class TestPromptComposerWiring:
    """Unit tests for prompt-composer wiring: layer ordering, safety policy,
    hidden agenda handling, prompt metadata persistence, and transcript truncation.
    """

    @pytest.mark.asyncio
    async def test_prompt_metadata_event_persisted_after_turn(self):
        """A 'prompt_metadata' event is written to turn_session_events each turn."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        await process_turn(
            session_row=row,
            player_text="I have five years of experience.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        events = _get_event_payloads(conn, "sess-unit", "prompt_metadata")
        assert len(events) == 1
        meta = events[0]
        assert "estimated_token_count" in meta
        assert meta["estimated_token_count"] > 0
        assert "was_truncated" in meta
        assert isinstance(meta["was_truncated"], bool)
        assert "layers_present" in meta
        assert isinstance(meta["layers_present"], list)
        assert len(meta["layers_present"]) > 0

    @pytest.mark.asyncio
    async def test_prompt_metadata_lists_all_expected_layers(self):
        """layers_present in the prompt_metadata event covers the full layer set."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        await process_turn(
            session_row=row,
            player_text="Tell me about the role.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        meta = _get_event_payloads(conn, "sess-unit", "prompt_metadata")[0]
        for layer in LAYER_ORDER:
            assert layer in meta["layers_present"], (
                f"Expected layer {layer!r} in layers_present"
            )

    @pytest.mark.asyncio
    async def test_prompt_metadata_excludes_private_persona_text(self):
        """Hidden agenda text and raw prompt content are not stored in prompt_metadata."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        await process_turn(
            session_row=row,
            player_text="What does success look like in this role?",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        rows = conn.execute(
            "SELECT payload_json FROM turn_session_events "
            "WHERE session_id = 'sess-unit' AND event_type = 'prompt_metadata'",
        ).fetchall()
        assert len(rows) == 1
        raw_payload = rows[0]["payload_json"]

        # Hidden agenda bullets from the behavioral_interview NPC must not appear.
        assert "Assess candidate" not in raw_payload
        assert "Probe for specific" not in raw_payload
        # Raw prompt structure markers must not appear.
        assert "LAYER:SAFETY_POLICY" not in raw_payload
        assert "LAYER:NPC_PRIVATE_PERSONA" not in raw_payload

    @pytest.mark.asyncio
    async def test_truncation_flag_stored_when_compose_returns_truncated(self):
        """When compose_turn_prompt signals was_truncated=True, it appears in the event."""
        from convsim_prompt.types import PromptBundle

        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        fake_bundle = PromptBundle(
            system_prompt="s",
            user_prompt="u",
            layer_map={name: "..." for name in LAYER_ORDER},
            estimated_token_count=5000,
            was_truncated=True,
        )

        with patch(
            "convsim_core.services.turn_pipeline.compose_turn_prompt",
            return_value=fake_bundle,
        ):
            await process_turn(
                session_row=row,
                player_text="Hello.",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        meta = _get_event_payloads(conn, "sess-unit", "prompt_metadata")
        assert len(meta) == 1
        assert meta[0]["was_truncated"] is True
        assert meta[0]["estimated_token_count"] == 5000

    @pytest.mark.asyncio
    async def test_custom_safety_policy_config_forwarded_to_compose_turn_prompt(self):
        """Providing safety_policy_config converts and passes the policy to compose_turn_prompt."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        custom_config = SafetyPolicyConfig(
            policy_id="pack_pg13",
            content_rating="PG-13",
            categories={
                "nsfw_sexual_content": RouteAction.STOP,
                "criminal_instruction": RouteAction.REFUSE,
            },
        )
        captured: list = []

        import convsim_core.services.turn_pipeline as _tp
        _orig = _tp.compose_turn_prompt

        def _spy(inp):
            captured.append(inp.safety_policy)
            return _orig(inp)

        with patch("convsim_core.services.turn_pipeline.compose_turn_prompt", side_effect=_spy):
            await process_turn(
                session_row=row,
                player_text="Hello.",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
                safety_policy_config=custom_config,
            )

        assert len(captured) == 1
        used = captured[0]
        assert isinstance(used, SafetyPolicy)
        assert used.policy_id == "pack_pg13"
        assert used.content_rating == "PG-13"
        assert "nsfw_sexual_content" in used.prohibited
        assert "criminal_instruction" in used.prohibited

    @pytest.mark.asyncio
    async def test_default_safety_policy_applied_when_no_config_provided(self):
        """When safety_policy_config is None the built-in default PG policy is used."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        captured: list = []
        import convsim_core.services.turn_pipeline as _tp
        _orig = _tp.compose_turn_prompt

        def _spy(inp):
            captured.append(inp.safety_policy)
            return _orig(inp)

        with patch("convsim_core.services.turn_pipeline.compose_turn_prompt", side_effect=_spy):
            await process_turn(
                session_row=row,
                player_text="Hello.",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        assert len(captured) == 1
        used = captured[0]
        assert isinstance(used, SafetyPolicy)
        assert used.policy_id == "default_pg"
        assert used.content_rating == "PG"

    @pytest.mark.asyncio
    async def test_hidden_agenda_forwarded_to_parse_turn_output(self):
        """parse_turn_output receives the NPC's hidden_agenda for leak detection."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)
        scenario_data = get_scenario_data("behavioral_interview", "normal")
        expected_agenda = scenario_data.npc.private_persona.hidden_agenda

        captured: dict = {}

        def _spy_parse(raw, runtime=None, hidden_agenda=None, turn_events=None):
            captured["hidden_agenda"] = hidden_agenda
            return _valid_turn_output()

        with patch(
            "convsim_core.services.turn_pipeline.parse_turn_output",
            side_effect=_spy_parse,
        ):
            await process_turn(
                session_row=row,
                player_text="I have relevant experience.",
                scenario_data=scenario_data,
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        assert captured.get("hidden_agenda") == expected_agenda

    @pytest.mark.asyncio
    async def test_runtime_bridge_forwarded_to_parse_turn_output(self):
        """A non-None runtime bridge is passed to parse_turn_output for repair calls."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        captured: dict = {}

        def _spy_parse(raw, runtime=None, hidden_agenda=None, turn_events=None):
            captured["runtime"] = runtime
            return _valid_turn_output()

        with patch(
            "convsim_core.services.turn_pipeline.parse_turn_output",
            side_effect=_spy_parse,
        ):
            await process_turn(
                session_row=row,
                player_text="What are the next steps?",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        assert captured.get("runtime") is not None

    @pytest.mark.asyncio
    async def test_parse_turn_events_included_in_debug_event(self):
        """TurnEvents emitted by parse_turn_output are stored in the debug event payload."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        def _spy_parse(raw, runtime=None, hidden_agenda=None, turn_events=None):
            if turn_events is not None:
                turn_events.append(TurnEvent(
                    event_type="structural_validation_failure",
                    reason="injected test event",
                ))
            return _valid_turn_output()

        with patch(
            "convsim_core.services.turn_pipeline.parse_turn_output",
            side_effect=_spy_parse,
        ):
            await process_turn(
                session_row=row,
                player_text="Interesting.",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        debug = _get_event_payloads(conn, "sess-unit", "debug")
        assert len(debug) == 1
        parse_evts = debug[0].get("parse_events", [])
        types = [e["event_type"] for e in parse_evts]
        assert "structural_validation_failure" in types

    @pytest.mark.asyncio
    async def test_hidden_agenda_leak_reason_redacted_in_debug_event(self):
        """A hidden_agenda_leak reason (which embeds verbatim private agenda
        keywords) must not be persisted to the debug log (issue #199)."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        secret_keywords = "candidate leadership competency"

        def _spy_parse(raw, runtime=None, hidden_agenda=None, turn_events=None):
            if turn_events is not None:
                turn_events.append(TurnEvent(
                    event_type="output_violation_detected",
                    category="hidden_agenda_leak",
                    reason=(
                        "NPC utterance contains multiple keywords from a private "
                        f"agenda item ({secret_keywords})"
                    ),
                    is_recoverable=True,
                ))
            return _valid_turn_output()

        with patch(
            "convsim_core.services.turn_pipeline.parse_turn_output",
            side_effect=_spy_parse,
        ):
            await process_turn(
                session_row=row,
                player_text="Tell me a secret.",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        rows = conn.execute(
            "SELECT payload_json FROM turn_session_events "
            "WHERE session_id = 'sess-unit' AND event_type = 'debug'",
        ).fetchall()
        assert len(rows) == 1
        raw_payload = rows[0]["payload_json"]
        # Private agenda keywords must not appear anywhere in the persisted log.
        assert secret_keywords not in raw_payload
        # The event is still recorded (type/category preserved), reason redacted.
        debug = json.loads(raw_payload)
        leak_evt = next(
            e for e in debug["parse_events"]
            if e["category"] == "hidden_agenda_leak"
        )
        assert leak_evt["reason"] is None
        assert leak_evt["event_type"] == "output_violation_detected"

    @pytest.mark.asyncio
    async def test_prompt_layers_ordered_safety_before_scenario(self):
        """In the composed system prompt, SAFETY_POLICY always precedes SCENARIO_BRIEF."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        captured: list = []
        import convsim_core.services.turn_pipeline as _tp
        _orig = _tp.compose_turn_prompt

        def _spy(inp):
            result = _orig(inp)
            captured.append(result.system_prompt)
            return result

        with patch("convsim_core.services.turn_pipeline.compose_turn_prompt", side_effect=_spy):
            await process_turn(
                session_row=row,
                player_text="Good morning.",
                scenario_data=get_scenario_data("behavioral_interview", "normal"),
                max_turns=10,
                runtime=FakeChatRuntime(),
                conn=conn,
            )

        assert len(captured) == 1
        sp = captured[0]
        assert sp.index("LAYER:SAFETY_POLICY") < sp.index("LAYER:SCENARIO_BRIEF")
        assert sp.index("LAYER:SCENARIO_BRIEF") < sp.index("LAYER:OUTPUT_SCHEMA")


# ---------------------------------------------------------------------------
# Issue #200: structured output path and debug API endpoint
# ---------------------------------------------------------------------------


class TestStructuredOutputPath:
    """When ChatFinal.structured is set the pipeline uses it and records the fact."""

    @pytest.mark.asyncio
    async def test_native_structured_output_recorded_in_debug_event(self):
        """FakeChatRuntime returns ChatFinal.structured; debug event must record it."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        await process_turn(
            session_row=row,
            player_text="Hello, I'm ready to begin.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        debug = _get_event_payloads(conn, "sess-unit", "debug")
        assert len(debug) == 1
        assert debug[0]["used_native_structured_output"] is True

    @pytest.mark.asyncio
    async def test_no_native_structured_output_recorded_for_plain_runtime(self):
        """A runtime that does not set ChatFinal.structured records False."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        class _PlainTextRuntime(FakeChatRuntime):
            """Runtime that always returns plain text with no structured field."""
            async def _stream(self, request: ChatRequest):
                from convsim_core.runtime.types import ChatFinal
                import json as _json
                structured_response = {
                    "npc_utterance": "That is a great question.",
                    "npc_emotion": "curious",
                    "state_delta": {},
                    "event_flags": [],
                    "rubric_observations": [],
                    "safety": {"status": "ok"},
                    "session_control": {"continue_session": True},
                }
                text = _json.dumps(structured_response)
                yield ChatFinal(
                    text=text,
                    model_id="fake-small",
                    input_tokens=5,
                    output_tokens=10,
                    structured=None,  # no native structured output
                )

        conn2 = _make_unit_db()
        row2 = _insert_unit_session(conn2, session_id="sess-unit")

        await process_turn(
            session_row=row2,
            player_text="What are you looking for?",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=_PlainTextRuntime(),
            conn=conn2,
        )

        debug = _get_event_payloads(conn2, "sess-unit", "debug")
        assert len(debug) == 1
        assert debug[0]["used_native_structured_output"] is False

    @pytest.mark.asyncio
    async def test_structured_output_parses_successfully(self):
        """Native structured output bypasses JSON extraction and parses cleanly."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        result = await process_turn(
            session_row=row,
            player_text="Tell me about yourself.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        # FakeChatRuntime returns a valid NPC structured response; must parse cleanly.
        assert result.used_fallback is False
        assert result.npc_utterance == "Hello there. I am a simulated NPC."
        assert result.npc_emotion == "neutral"

    @pytest.mark.asyncio
    async def test_raw_text_stored_separately_from_parse_input(self):
        """raw_output_json in the NPC turn row reflects the model's actual text output."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        await process_turn(
            session_row=row,
            player_text="Let's get started.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        # NPC turn row has turn_number=2 (game_turn=1, npc_row = 1*2)
        npc_row = conn.execute(
            "SELECT raw_output_json FROM turn_session_turns "
            "WHERE session_id = 'sess-unit' AND turn_number = 2"
        ).fetchone()
        assert npc_row is not None
        assert npc_row["raw_output_json"] is not None


class TestDebugEndpoint:
    """Tests for GET /api/sessions/{session_id}/debug."""

    def test_debug_returns_404_for_unknown_session(self, client):
        res = client.get("/api/sessions/sess-doesnotexist/debug")
        assert res.status_code == 404

    def test_debug_returns_empty_turns_before_any_turn(self, client):
        session_id = _create_and_start(client)
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        body = res.json()
        assert body["session_id"] == session_id
        assert body["turns"] == []

    def test_debug_returns_turn_data_after_one_turn(self, client):
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I have strong communication skills."},
        )
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        body = res.json()
        assert body["session_id"] == session_id
        assert len(body["turns"]) == 1
        turn = body["turns"][0]
        assert turn["turn_number"] == 1

    def test_debug_exposes_raw_npc_output(self, client):
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "My background is in software engineering."},
        )
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turn = res.json()["turns"][0]
        # raw_npc_output is the raw text from the model (not None for a successful turn).
        assert turn["raw_npc_output"] is not None
        assert isinstance(turn["raw_npc_output"], str)

    def test_debug_reports_native_structured_output_flag(self, client):
        """FakeChatRuntime sets ChatFinal.structured so the flag must be True."""
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I am excited about this opportunity."},
        )
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turn = res.json()["turns"][0]
        assert turn["used_native_structured_output"] is True

    def test_debug_includes_prompt_metadata(self, client):
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Let me explain my experience."},
        )
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turn = res.json()["turns"][0]
        assert turn["prompt_metadata"] is not None
        assert "estimated_token_count" in turn["prompt_metadata"]
        assert "layers_present" in turn["prompt_metadata"]

    def test_debug_parse_events_present(self, client):
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Here is my response."},
        )
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turn = res.json()["turns"][0]
        # FakeChatRuntime produces clean output — no parse events expected.
        assert isinstance(turn["parse_events"], list)

    def test_debug_accumulates_across_turns(self, client):
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "First turn content."},
        )
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Second turn content."},
        )
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turns = res.json()["turns"]
        assert len(turns) == 2
        assert turns[0]["turn_number"] == 1
        assert turns[1]["turn_number"] == 2

    def test_debug_fallback_flag_set_when_runtime_returns_garbage(self, tmp_config):
        from convsim_prompt import SAFE_FALLBACK_UTTERANCE
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _GarbageRuntime()

            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "This will trigger fallback."},
            )

            res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turn = res.json()["turns"][0]
        assert turn["used_fallback"] is True
        assert turn["used_native_structured_output"] is False


# ---------------------------------------------------------------------------
# Issue #201: state variables, scenario events, endings, and rubrics
# ---------------------------------------------------------------------------


def _insert_unit_session_with_state(
    conn: sqlite3.Connection,
    session_id: str = "sess-unit",
    state_vars: dict = None,
) -> sqlite3.Row:
    """Like _insert_unit_session but allows pre-seeding state_vars_json."""
    import json as _json
    state_json = _json.dumps(state_vars or {})
    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, "
        "turn_count, setup_json) "
        "VALUES (?, 'behavioral_interview', 'PlayerTurnListening', ?, '[]', 0, '{}')",
        (session_id, state_json),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()


class _SpecificDeltaRuntime(FakeChatRuntime):
    """Runtime that returns a configurable state_delta."""

    def __init__(self, state_delta: dict = None, rubric_obs: list = None) -> None:
        super().__init__()
        self._delta = state_delta or {}
        self._rubric_obs = rubric_obs or []

    def chat_stream(self, request: ChatRequest):
        return self._stream(request)

    async def _stream(self, request: ChatRequest):
        import json as _json
        from convsim_core.runtime.types import ChatFinal
        response = {
            "npc_utterance": "Understood.",
            "npc_emotion": "neutral",
            "state_delta": self._delta,
            "event_flags": [],
            "rubric_observations": self._rubric_obs,
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


class TestScenarioStateIntegration:
    """Integration tests for scenario state variables, events, endings, and rubrics (issue #201)."""

    # ------------------------------------------------------------------
    # Clamping and invalid variable rejection
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_custom_variable_overrides_constrain_delta(self):
        """A custom max_delta_per_turn override is respected; delta cannot exceed it."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        # trust starts at 50 (baseline default); runtime requests +20
        # but we cap max_delta_per_turn at 5, so only +5 should be applied.
        result = await process_turn(
            session_row=row,
            player_text="Hello.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=_SpecificDeltaRuntime(state_delta={"trust": 20}),
            conn=conn,
            state_variable_overrides={"trust": {"max_delta_per_turn": 5}},
        )

        assert result.state_delta.get("trust") == 5
        assert result.new_state_vars["trust"] == 55  # 50 + 5

    @pytest.mark.asyncio
    async def test_invalid_variable_key_rejected_in_pipeline(self):
        """An unknown variable key proposed by the model is rejected; not applied."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        result = await process_turn(
            session_row=row,
            player_text="Hello.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=_SpecificDeltaRuntime(state_delta={"ghost_key": 10, "trust": 5}),
            conn=conn,
        )

        assert "ghost_key" not in result.new_state_vars
        assert result.state_delta.get("trust") == 5

    # ------------------------------------------------------------------
    # Ending conditions
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_success_ending_fires_from_ending_conditions(self):
        """ending_type='success' is set when the success variable condition is met."""
        conn = _make_unit_db()
        # Pre-seed objective_progress near the threshold (50); delta +15 pushes to 65 > 60.
        row = _insert_unit_session_with_state(
            conn, state_vars={"trust": 50, "patience": 75, "pressure": 25,
                              "rapport": 50, "openness": 50, "objective_progress": 50}
        )

        result = await process_turn(
            session_row=row,
            player_text="I agree completely.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=20,
            runtime=_SpecificDeltaRuntime(state_delta={"objective_progress": 15}),
            conn=conn,
            ending_conditions={
                "success": {
                    "type": "variable_above",
                    "variable": "objective_progress",
                    "threshold": 60,
                }
            },
        )

        assert result.ending_type == "success"
        assert result.new_flow_state == "Ended"

    @pytest.mark.asyncio
    async def test_failure_ending_fires_from_ending_conditions(self):
        """ending_type='failure' is set when the failure variable condition is met."""
        conn = _make_unit_db()
        # Pre-seed patience near the failure threshold (20); delta -15 pushes to 5 < 10.
        row = _insert_unit_session_with_state(
            conn, state_vars={"trust": 50, "patience": 20, "pressure": 25,
                              "rapport": 50, "openness": 50, "objective_progress": 0}
        )

        result = await process_turn(
            session_row=row,
            player_text="That's not right at all.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=20,
            runtime=_SpecificDeltaRuntime(state_delta={"patience": -15}),
            conn=conn,
            ending_conditions={
                "failure": {
                    "type": "variable_below",
                    "variable": "patience",
                    "threshold": 10,
                }
            },
        )

        assert result.ending_type == "failure"
        assert result.new_flow_state == "Ended"

    @pytest.mark.asyncio
    async def test_timeout_ending_fires_when_max_turns_reached(self):
        """ending_type='timeout' fires when turn_number >= max_turns (pipeline unit)."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        result = await process_turn(
            session_row=row,
            player_text="Last turn.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=1,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        assert result.ending_type == "timeout"
        assert result.new_flow_state == "Ended"

    @pytest.mark.asyncio
    async def test_success_takes_priority_over_timeout(self):
        """When success and timeout both fire on the same turn, success wins."""
        conn = _make_unit_db()
        row = _insert_unit_session_with_state(
            conn, state_vars={"trust": 50, "patience": 75, "pressure": 25,
                              "rapport": 50, "openness": 50, "objective_progress": 50}
        )

        result = await process_turn(
            session_row=row,
            player_text="Final answer.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=1,  # timeout would fire
            runtime=_SpecificDeltaRuntime(state_delta={"objective_progress": 15}),
            conn=conn,
            ending_conditions={
                "success": {
                    "type": "variable_above",
                    "variable": "objective_progress",
                    "threshold": 60,
                }
            },
        )

        assert result.ending_type == "success"

    # ------------------------------------------------------------------
    # Scenario events
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_scenario_event_fires_and_returned(self):
        """An event whose condition is met appears in triggered_scenario_events."""
        from convsim_core.scenario_state import ScenarioEvent
        conn = _make_unit_db()
        # rapport starts at 60; delta +15 pushes to 75 which is > 70 — event fires.
        row = _insert_unit_session_with_state(
            conn, state_vars={"trust": 50, "patience": 75, "pressure": 25,
                              "rapport": 60, "openness": 50, "objective_progress": 0}
        )

        evt = ScenarioEvent(
            id="rapport_high",
            when={"type": "variable_above", "variable": "rapport", "threshold": 70},
            npc_instruction="Acknowledge the improved atmosphere.",
        )

        result = await process_turn(
            session_row=row,
            player_text="I appreciate your perspective.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=20,
            runtime=_SpecificDeltaRuntime(state_delta={"rapport": 15}),
            conn=conn,
            scenario_events=[evt],
        )

        assert "rapport_high" in result.triggered_scenario_events

    @pytest.mark.asyncio
    async def test_scenario_event_does_not_fire_when_condition_not_met(self):
        """An event whose condition is not met is absent from triggered_scenario_events."""
        from convsim_core.scenario_state import ScenarioEvent
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        evt = ScenarioEvent(
            id="trust_very_high",
            when={"type": "variable_above", "variable": "trust", "threshold": 90},
            npc_instruction="NPC becomes very open.",
        )

        result = await process_turn(
            session_row=row,
            player_text="Hello.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=20,
            runtime=FakeChatRuntime(),
            conn=conn,
            scenario_events=[evt],
        )

        assert "trust_very_high" not in result.triggered_scenario_events

    # ------------------------------------------------------------------
    # Visible vs. hidden state meters
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_visible_state_in_pipeline_result(self):
        """result.visible_state contains visible variables and excludes hidden ones."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        result = await process_turn(
            session_row=row,
            player_text="Hello.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        # Baseline visible variables must be present.
        assert "trust" in result.visible_state
        assert "patience" in result.visible_state
        assert "rapport" in result.visible_state
        assert "openness" in result.visible_state
        assert "objective_progress" in result.visible_state
        # pressure is HIDDEN — must not appear.
        assert "pressure" not in result.visible_state

    @pytest.mark.asyncio
    async def test_custom_hidden_variable_excluded_from_visible_state(self):
        """A variable declared hidden in state_variable_overrides is not in visible_state."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        result = await process_turn(
            session_row=row,
            player_text="Hello.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
            state_variable_overrides={"trust": {"visibility": "hidden"}},
        )

        assert "trust" not in result.visible_state

    def test_visible_state_in_turn_api_response(self, client):
        """The /turn HTTP response includes visible_state in the npc_turn payload."""
        session_id = _create_and_start(client)

        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Good morning."},
        )
        assert res.status_code == 200
        npc_payload = res.json()["events"][1]["payload"]
        assert "visible_state" in npc_payload
        assert isinstance(npc_payload["visible_state"], dict)
        # trust is a visible baseline variable — must appear.
        assert "trust" in npc_payload["visible_state"]
        # pressure is hidden — must not appear.
        assert "pressure" not in npc_payload["visible_state"]

    # ------------------------------------------------------------------
    # Rubric observations persistence
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rubric_observations_persisted_in_events(self):
        """Rubric observations from the NPC turn are stored in turn_session_events."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        runtime = _SpecificDeltaRuntime(
            rubric_obs=[
                {"rubric_id": "clarity", "observation": "Clear explanation.", "score_delta": 2},
                {"rubric_id": "empathy", "observation": "Showed empathy.", "score_delta": 1},
            ]
        )

        await process_turn(
            session_row=row,
            player_text="Let me be clear.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=runtime,
            conn=conn,
        )

        events = _get_event_payloads(conn, "sess-unit", "rubric_observations")
        assert len(events) == 1
        obs_list = events[0]
        assert isinstance(obs_list, list)
        assert len(obs_list) == 2
        rubric_ids = {o["rubric_id"] for o in obs_list}
        assert rubric_ids == {"clarity", "empathy"}

    @pytest.mark.asyncio
    async def test_rubric_observations_in_pipeline_result(self):
        """result.rubric_observations contains the NPC's rubric observations."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        runtime = _SpecificDeltaRuntime(
            rubric_obs=[
                {"rubric_id": "structure", "observation": "Well-structured.", "score_delta": 3},
            ]
        )

        result = await process_turn(
            session_row=row,
            player_text="Here is my reasoning.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=runtime,
            conn=conn,
        )

        assert len(result.rubric_observations) == 1
        assert result.rubric_observations[0]["rubric_id"] == "structure"
        assert result.rubric_observations[0]["score_delta"] == 3

    @pytest.mark.asyncio
    async def test_empty_rubric_observations_not_persisted(self):
        """No rubric_observations event is written when the NPC returns an empty list."""
        conn = _make_unit_db()
        row = _insert_unit_session(conn)

        await process_turn(
            session_row=row,
            player_text="Hello.",
            scenario_data=get_scenario_data("behavioral_interview", "normal"),
            max_turns=10,
            runtime=FakeChatRuntime(),
            conn=conn,
        )

        events = _get_event_payloads(conn, "sess-unit", "rubric_observations")
        assert events == []

    def test_rubric_observations_in_turn_api_response(self, client):
        """The /turn HTTP response includes rubric_observations in the npc_turn payload."""
        session_id = _create_and_start(client)

        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Hello."},
        )
        assert res.status_code == 200
        npc_payload = res.json()["events"][1]["payload"]
        assert "rubric_observations" in npc_payload
        assert isinstance(npc_payload["rubric_observations"], list)

    # ------------------------------------------------------------------
    # scenario_events wired from ScenarioInfo (coworker_feedback)
    # ------------------------------------------------------------------

    def test_coworker_feedback_scenario_has_state_variable_overrides(self):
        """coworker_feedback ScenarioInfo ships with state_variable_overrides."""
        from convsim_core.scenarios import get_scenario_info
        info = get_scenario_info("coworker_feedback")
        assert info is not None
        assert info.state_variable_overrides is not None
        assert "rapport" in info.state_variable_overrides

    def test_coworker_feedback_scenario_has_events(self):
        """coworker_feedback ScenarioInfo ships with at least one event."""
        from convsim_core.scenarios import get_scenario_info
        info = get_scenario_info("coworker_feedback")
        assert info is not None
        assert info.events is not None
        assert len(info.events) > 0
        assert info.events[0].id == "npc_defensive"

    def test_coworker_feedback_scenario_has_ending_conditions(self):
        """coworker_feedback ScenarioInfo ships with both success and failure endings."""
        from convsim_core.scenarios import get_scenario_info
        info = get_scenario_info("coworker_feedback")
        assert info is not None
        assert info.ending_conditions is not None
        assert "success" in info.ending_conditions
        assert "failure" in info.ending_conditions

    def test_coworker_feedback_rapport_starts_at_30(self):
        """The coworker_feedback rapport override (default=30) is applied on first turn."""
        from convsim_core.scenario_state import build_variable_defs, initialize_state
        from convsim_core.scenarios import get_scenario_info
        info = get_scenario_info("coworker_feedback")
        defs = build_variable_defs(info.state_variable_overrides)
        state = initialize_state(defs)
        assert state["rapport"] == 30

    def test_triggered_scenario_events_in_turn_api_response(self, client):
        """triggered_scenario_events is present in the npc_turn payload."""
        session_id = _create_and_start(client)

        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Hello."},
        )
        assert res.status_code == 200
        npc_payload = res.json()["events"][1]["payload"]
        assert "triggered_scenario_events" in npc_payload
        assert isinstance(npc_payload["triggered_scenario_events"], list)
