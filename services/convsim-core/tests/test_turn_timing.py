# SPDX-License-Identifier: Apache-2.0
"""One timing record per NPC turn, persisted and exposed (issue #519)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.runtime.fake import FAKE_READING_TPS, FAKE_WRITING_TPS, FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatRequest, ChatToken
from convsim_core.services.model_manager_service import set_active_config
from convsim_core.services.turn_timing import (
    TURN_STAGES,
    TURN_TIMING_EVENT_TYPE,
    TurnTiming,
    rolling_speeds,
)

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Candidate",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "runtime_id": "fake",
}


def _start(client: TestClient, setup: dict | None = None) -> str:
    res = client.post("/api/sessions", json=setup or _SETUP)
    assert res.status_code == 201, res.text
    session_id = res.json()["session_id"]
    assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
    return session_id


def _turn(client: TestClient, session_id: str, text: str = "I have five years of experience.") -> dict:
    res = client.post(f"/api/sessions/{session_id}/turn", json={"content": text})
    assert res.status_code == 200, res.text
    return res.json()


def _timing_events(client: TestClient, session_id: str) -> list[dict]:
    conn = client.app.state.db.connection()
    rows = conn.execute(
        "SELECT turn_number, payload_json FROM turn_session_events "
        "WHERE session_id = ? AND event_type = ? ORDER BY id",
        (session_id, TURN_TIMING_EVENT_TYPE),
    ).fetchall()
    return [{"turn_number": r["turn_number"], **json.loads(r["payload_json"])} for r in rows]


def test_the_stage_list_is_defined_once():
    assert TURN_STAGES == ("waiting", "reading", "writing", "finishing", "checking", "voice")


class TestRecordOnTheTurnResponse:
    def test_npc_turn_carries_a_complete_record_from_the_fake_engine(self, client):
        session_id = _start(client)
        body = _turn(client, session_id)
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        record = TurnTiming.model_validate(npc["payload"]["timing"])

        assert record.total_ms > 0
        assert record.first_token_ms is not None and 0 <= record.first_token_ms <= record.total_ms
        # The fake engine reports one millisecond per prompt token read and two
        # per token written, and the record repeats what it said.
        assert record.tokens.prompt is not None and record.tokens.prompt > 0
        assert record.tokens.evaluated == record.tokens.prompt
        assert record.tokens.cached == 0
        assert record.tokens.output is not None and record.tokens.output > 0
        assert record.reading_ms == float(record.tokens.prompt)
        assert record.writing_ms == record.tokens.output * 2.0
        assert record.rates.reading_tps == FAKE_READING_TPS
        assert record.rates.writing_tps == FAKE_WRITING_TPS
        assert record.waiting_ms is not None and record.waiting_ms >= 0
        assert record.finish_reason == "stop"
        assert record.fallback is False
        assert record.salvaged is False
        assert record.stopped is False
        assert record.extra_calls == []
        assert record.voice is None
        # Not yet measurable: words do not stream until #538.
        assert record.first_words_ms is None and record.reply_done_ms is None
        assert record.tokens.spoken is None
        assert record.context.runtime_id == "fake"
        assert record.context.model_id == "fake-small"
        assert record.context.cold is True  # nothing came from cache
        assert record.other_ms >= 0

    def test_record_is_persisted_as_a_turn_timing_event_per_npc_turn(self, client):
        session_id = _start(client)
        _turn(client, session_id, "First.")
        _turn(client, session_id, "Second.")
        events = _timing_events(client, session_id)
        assert [e["turn_number"] for e in events] == [1, 2]
        assert all(e["context"]["runtime_id"] == "fake" for e in events)

    def test_an_input_safety_stop_never_reached_the_model_and_has_no_record(self, client):
        session_id = _start(client)
        res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I want to hurt myself and I don't see a way out."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["state"] == "Ended"
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert "timing" not in npc["payload"]
        assert _timing_events(client, session_id) == []


class TestRecordOnTheOtherEndpoints:
    def test_debug_endpoint_carries_the_record(self, client):
        session_id = _start(client)
        _turn(client, session_id)
        res = client.get(f"/api/sessions/{session_id}/debug")
        assert res.status_code == 200
        turns = res.json()["turns"]
        assert len(turns) == 1
        assert turns[0]["turn_number"] == 1
        assert turns[0]["timing"]["context"]["runtime_id"] == "fake"
        assert turns[0]["timing"]["rates"]["writing_tps"] == FAKE_WRITING_TPS

    def test_transcript_endpoint_carries_the_record_on_npc_rows_only(self, client):
        session_id = _start(client)
        _turn(client, session_id)
        res = client.get(f"/api/sessions/{session_id}/transcript")
        assert res.status_code == 200
        turns = res.json()["turns"]
        by_role = {t["role"]: t for t in turns}
        assert by_role["npc_opening"]["timing"] is None
        assert by_role["player"]["timing"] is None
        assert by_role["npc"]["turn_number"] == 2
        assert by_role["npc"]["timing"]["total_ms"] > 0

    def test_export_includes_the_event(self, client):
        session_id = _start(client)
        _turn(client, session_id)
        res = client.get(f"/api/sessions/{session_id}/export")
        assert res.status_code == 200
        events = [e for e in res.json()["events"] if e["event_type"] == TURN_TIMING_EVENT_TYPE]
        assert len(events) == 1
        assert events[0]["turn_number"] == 1
        assert events[0]["payload"]["context"]["runtime_id"] == "fake"

    def test_deleting_the_session_removes_the_record(self, client):
        session_id = _start(client)
        _turn(client, session_id)
        assert len(_timing_events(client, session_id)) == 1
        assert client.delete(f"/api/sessions/{session_id}").status_code == 204
        assert _timing_events(client, session_id) == []

    def test_clear_all_local_data_removes_the_record(self, client):
        session_id = _start(client)
        _turn(client, session_id)
        assert client.post("/api/privacy/clear").status_code == 200
        assert _timing_events(client, session_id) == []


class _SilentRuntime(FakeChatRuntime):
    """An engine that streams text and reports nothing about the cost."""

    def chat_stream(self, request: ChatRequest):
        return self._silent(request)

    async def _silent(self, request: ChatRequest):
        response = {
            "npc_utterance": "Hello there.",
            "npc_emotion": "neutral",
            "state_delta": {},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": True},
        }
        text = json.dumps(response)
        for word in text.split():
            yield ChatToken(text=word + " ")
        yield ChatFinal(text=text, model_id="silent", input_tokens=0, output_tokens=0, structured=response)


class _GarbageRuntime(FakeChatRuntime):
    """An engine whose every answer is unparseable, so the turn falls back."""

    def chat_stream(self, request: ChatRequest):
        return self._garbage(request)

    async def _garbage(self, request: ChatRequest):
        yield ChatFinal(text="not json {{{{", model_id="fake-small", input_tokens=5, output_tokens=5)


def _session_on(app, client: TestClient, runtime) -> str:
    """Start a fake-pinned session, then swap the shared runtime underneath it.

    Sessions pinned to ``fake`` resolve through build_runtime, so the swap has
    to happen on an unpinned session: activate llama_cpp as the selection (the
    shared runtime object is what tests replace) and point app.state.runtime at
    the test double.
    """
    set_active_config(app.state.db.connection(), "llama_cpp", "some-model")
    app.state.runtime = runtime
    setup = {k: v for k, v in _SETUP.items() if k != "runtime_id"}
    return _start(client, setup)


class TestRecordWithOtherEngines:
    def test_an_engine_that_reports_nothing_yields_nulls_not_guesses(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _SilentRuntime())
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])

        assert record.total_ms > 0
        assert record.first_token_ms is not None
        assert record.writing_ms is not None  # observed: first token → final
        assert record.waiting_ms is None and record.reading_ms is None
        assert record.tokens.prompt is None and record.tokens.cached is None
        assert record.tokens.evaluated is None and record.tokens.output is None
        assert record.rates.reading_tps is None and record.rates.writing_tps is None
        assert record.finish_reason is None
        assert record.context.cold is None
        assert record.context.model_id == "silent"
        # The runtime names itself; the test double is a fake-runtime subclass.
        assert record.context.runtime_id == "fake"
        # The registry id comes from the active selection at the time.
        assert record.context.registry_model_id == "some-model"

    def test_a_fallback_turn_counts_its_repair_call(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _GarbageRuntime())
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])

        assert record.fallback is True
        assert [c.kind for c in record.extra_calls] == ["repair"]
        assert record.extra_calls[0].ms >= 0
        assert record.extra_calls[0].tokens == 5


class TestRollingSpeeds:
    def test_empty_before_any_turn(self, client):
        res = client.get("/api/performance/rolling")
        assert res.status_code == 200
        body = res.json()
        assert body["samples"] == 0
        assert body["reading_tps"] is None
        assert body["writing_tps"] is None
        assert body["first_token_ms"] is None
        assert body["first_words_ms"] is None
        assert body["total_ms"] is None

    def test_medians_over_recorded_turns(self, client):
        session_id = _start(client)
        _turn(client, session_id, "One.")
        _turn(client, session_id, "Two.")
        _turn(client, session_id, "Three.")
        res = client.get("/api/performance/rolling")
        assert res.status_code == 200
        body = res.json()
        assert body["samples"] == 3
        assert body["reading_tps"] == FAKE_READING_TPS
        assert body["writing_tps"] == FAKE_WRITING_TPS
        assert body["first_token_ms"] is not None and body["first_token_ms"] >= 0
        assert body["total_ms"] is not None and body["total_ms"] > 0
        # Nothing streams yet, so the median of an all-null column is null.
        assert body["first_words_ms"] is None

    def test_filters_by_runtime_and_model(self, client):
        session_id = _start(client)
        _turn(client, session_id)
        assert client.get("/api/performance/rolling?runtime_id=fake").json()["samples"] == 1
        assert client.get("/api/performance/rolling?runtime_id=llama_cpp").json()["samples"] == 0
        assert client.get("/api/performance/rolling?runtime_id=fake&model_id=other").json()["samples"] == 0

    def test_fallback_and_stopped_turns_are_left_out(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _GarbageRuntime())
            _turn(client, session_id)
            conn = app.state.db.connection()
            speeds = rolling_speeds(conn, runtime_id="llama_cpp", model_id=None)
        assert speeds.samples == 0

    def test_window_is_the_most_recent_records(self, client):
        session_id = _start(client)
        for i in range(3):
            _turn(client, session_id, f"Turn {i}.")
        conn = client.app.state.db.connection()
        speeds = rolling_speeds(conn, runtime_id="fake", model_id=None, window=2)
        assert speeds.samples == 2
