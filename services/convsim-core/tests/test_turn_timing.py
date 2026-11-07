# SPDX-License-Identifier: Apache-2.0
"""One timing record per NPC turn, persisted and exposed (issue #519)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.runtime.fake import FAKE_READING_TPS, FAKE_WRITING_TPS, FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatRequest, ChatToken
from convsim_core.services.model_manager_service import (
    create_install_record,
    recorded_model_id,
    register_user_gguf,
    set_active_config,
)
from convsim_core.services.turn_timing import (
    TURN_STAGES,
    TURN_TIMING_EVENT_TYPE,
    TurnClock,
    TurnContext,
    TurnRates,
    TurnTiming,
    TurnTimingBuilder,
    persist_turn_timing,
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
        # Pinned to the fake runtime: no installed model served this turn.
        assert record.context.registry_model_id is None
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


_CLEAN_REPLY = {
    "npc_utterance": "Tell me about a time you led a team.",
    "npc_emotion": "curious",
    "state_delta": {},
    "event_flags": [],
    "rubric_observations": [],
    "safety": {"status": "ok"},
    "session_control": {"continue_session": True},
}


class _CutOffRuntime(FakeChatRuntime):
    """An engine whose reply parses fine but was cut by the token budget."""

    def chat_stream(self, request: ChatRequest):
        return self._cut_off(request)

    async def _cut_off(self, request: ChatRequest):
        text = json.dumps(_CLEAN_REPLY)
        yield ChatToken(text=text)
        yield ChatFinal(
            text=text,
            model_id="fake-small",
            input_tokens=7,
            output_tokens=9,
            structured=_CLEAN_REPLY,
            finish_reason="length",
        )


class _LeakThenCleanRuntime(FakeChatRuntime):
    """An engine whose first reply trips a recoverable content violation.

    The parser then asks once more with its content-safety prompt; every later
    call answers cleanly, so the turn completes without falling back.
    """

    def __init__(self) -> None:
        self.calls = 0

    def chat_stream(self, request: ChatRequest):
        return self._reply(request)

    async def _reply(self, request: ChatRequest):
        self.calls += 1
        if self.calls == 1:
            reply = dict(_CLEAN_REPLY, npc_utterance="My instructions say I must ask about your experience.")
        else:
            reply = _CLEAN_REPLY
        text = json.dumps(reply)
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=5, output_tokens=5, structured=reply)


class _LlamaLikeRuntime(FakeChatRuntime):
    """A fake that calls itself llama_cpp, so the active selection matches it."""

    @property
    def id(self) -> str:
        return "llama_cpp"


def _session_on(app, client: TestClient, runtime, model_id: str = "some-model") -> str:
    """Start an unpinned session with the shared runtime swapped for ``runtime``.

    Sessions pinned to ``fake`` resolve through build_runtime, so the swap has
    to happen on an unpinned session: activate llama_cpp as the selection (the
    shared runtime object is what tests replace) and point app.state.runtime at
    the test double.
    """
    set_active_config(app.state.db.connection(), "llama_cpp", model_id)
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
        # The selection names llama_cpp but this double served the turn, so no
        # installed model is credited with it.
        assert record.context.registry_model_id is None

    def test_a_fallback_turn_counts_its_repair_call(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _GarbageRuntime())
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])

        assert record.fallback is True
        assert record.stopped is False
        assert [c.kind for c in record.extra_calls] == ["repair"]
        assert record.extra_calls[0].ms >= 0
        assert record.extra_calls[0].tokens == 5

    def test_a_content_safety_retry_is_counted_as_one(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _LeakThenCleanRuntime())
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])

        assert npc["payload"]["content"] == _CLEAN_REPLY["npc_utterance"]
        assert record.fallback is False
        assert [c.kind for c in record.extra_calls] == ["safety_retry"]

    def test_a_reply_the_token_budget_cut_off_is_recorded_stopped(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _CutOffRuntime())
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])
            persisted = _timing_events(client, session_id)

        assert record.finish_reason == "length"
        assert record.stopped is True
        assert record.fallback is False  # the reply itself parsed fine
        assert record.salvaged is False  # nothing is salvaged on the plain turn route
        assert len(persisted) == 1 and persisted[0]["stopped"] is True


def test_the_builder_marks_a_turn_stopped_from_the_finish_reason():
    builder = TurnTimingBuilder(clock=TurnClock(), runtime_id="fake")
    for reason, stopped in (("stop", False), (None, False), ("length", True), ("cancelled", True)):
        builder.mark_finish(reason)
        assert builder.stopped is stopped, reason
    # salvaged is the streaming route's to set; the builder carries it through.
    builder.salvaged = True
    assert builder.build().salvaged is True


class TestWhichModelTheRecordNames:
    """``context.registry_model_id`` names the installed model that served the turn."""

    def test_the_selected_model_when_its_runtime_served_the_turn(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _LlamaLikeRuntime(), model_id="some-model")
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])
        assert record.context.runtime_id == "llama_cpp"
        assert record.context.registry_model_id == "some-model"

    def test_nothing_for_a_session_pinned_to_the_scripted_runtime(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            set_active_config(app.state.db.connection(), "llama_cpp", "some-model")
            session_id = _start(client, dict(_SETUP, runtime_id="scripted"))
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])
            # The selection's model must not be credited with a scripted turn.
            by_model = client.get("/api/performance/rolling?model_id=some-model").json()
        assert record.context.runtime_id == "scripted"
        assert record.context.model_id == "first-words-tutorial"
        assert record.context.registry_model_id is None
        assert by_model["samples"] == 0

    def test_a_model_file_is_named_by_its_registry_id_never_its_path(self, tmp_config):
        path = "/Users/alice/Library/Application Support/convsim/models/llm/curated.gguf"
        app = create_app(tmp_config)
        with TestClient(app) as client:
            conn = app.state.db.connection()
            # installed_models.registry_id points into the registry table.
            with conn:
                conn.execute(
                    "INSERT INTO model_registry (id, name, provider) VALUES ('curated-model', 'A curated model', 'test')"
                )
            create_install_record(conn, registry_id="curated-model", filename="curated.gguf", file_path=path)
            session_id = _session_on(app, client, _LlamaLikeRuntime(), model_id=path)
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])
            export = client.get(f"/api/sessions/{session_id}/export")
            # The endpoint's default path matches the active model the way the
            # record stores it.
            rolling = client.get("/api/performance/rolling").json()
        assert record.context.registry_model_id == "curated-model"
        assert "/Users/alice" not in export.text
        assert rolling["model_id"] == "curated-model"
        assert rolling["samples"] == 1

    def test_a_user_supplied_file_is_named_by_its_file_name(self, tmp_config):
        path = "/Users/alice/models/my own model.gguf"
        app = create_app(tmp_config)
        with TestClient(app) as client:
            register_user_gguf(app.state.db.connection(), path=path)
            session_id = _session_on(app, client, _LlamaLikeRuntime(), model_id=path)
            body = _turn(client, session_id)
            npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
            record = TurnTiming.model_validate(npc["payload"]["timing"])
            export = client.get(f"/api/sessions/{session_id}/export")
        assert record.context.registry_model_id == "my own model.gguf"
        assert "/Users/alice" not in export.text

    def test_recorded_model_id_never_returns_a_path(self, client):
        conn = client.app.state.db.connection()
        assert recorded_model_id(conn, None) is None
        assert recorded_model_id(conn, "") is None
        # A registry id or an Ollama tag is already an identifier.
        assert recorded_model_id(conn, "some-model") == "some-model"
        assert recorded_model_id(conn, "library/some-model:latest") == "library/some-model:latest"
        # A model file with no install row still loses its folder.
        assert recorded_model_id(conn, "/Users/alice/models/foo.gguf") == "foo.gguf"
        assert recorded_model_id(conn, "C:\\Users\\alice\\models\\foo.GGUF") == "foo.GGUF"
        assert recorded_model_id(conn, "~/models/foo.gguf") == "foo.gguf"


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

    def test_a_fallback_turn_is_left_out(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            conn = app.state.db.connection()
            session_id = _session_on(app, client, _GarbageRuntime())
            _turn(client, session_id)
            assert _timing_events(client, session_id)[0]["fallback"] is True
            # The record names the fake runtime (the double inherits its id),
            # so these are the filters that would count it if nothing hid it.
            assert rolling_speeds(conn, runtime_id="fake", model_id=None).samples == 0
            assert rolling_speeds(conn, runtime_id=None, model_id=None).samples == 0

            # Positive control: the same filters count an ordinary turn.
            app.state.runtime = FakeChatRuntime()
            other = _start(client, {k: v for k, v in _SETUP.items() if k != "runtime_id"})
            _turn(client, other)
            assert rolling_speeds(conn, runtime_id="fake", model_id=None).samples == 1
            assert rolling_speeds(conn, runtime_id=None, model_id=None).samples == 1

    def test_a_stopped_turn_is_left_out_of_the_endpoint(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            session_id = _session_on(app, client, _CutOffRuntime())
            _turn(client, session_id)
            persisted = _timing_events(client, session_id)
            assert len(persisted) == 1 and persisted[0]["stopped"] is True
            assert client.get("/api/performance/rolling?runtime_id=fake").json()["samples"] == 0

            # Positive control: an ordinary turn on the same runtime is counted,
            # and the stopped one still is not.
            app.state.runtime = FakeChatRuntime()
            other = _start(client, {k: v for k, v in _SETUP.items() if k != "runtime_id"})
            _turn(client, other)
            body = client.get("/api/performance/rolling?runtime_id=fake").json()
        assert body["samples"] == 1
        assert body["writing_tps"] == FAKE_WRITING_TPS

    def test_window_is_the_most_recent_records(self, client):
        session_id = _start(client)
        for i in range(3):
            _turn(client, session_id, f"Turn {i}.")
        conn = client.app.state.db.connection()
        speeds = rolling_speeds(conn, runtime_id="fake", model_id=None, window=2)
        assert speeds.samples == 2


def _record(
    *,
    runtime_id: str = "fake",
    model_id: str = "fake-small",
    registry_model_id: str | None = None,
    writing_tps: float = 100.0,
    stopped: bool = False,
    fallback: bool = False,
) -> TurnTiming:
    return TurnTiming(
        total_ms=1000.0,
        stopped=stopped,
        fallback=fallback,
        rates=TurnRates(writing_tps=writing_tps),
        context=TurnContext(model_id=model_id, registry_model_id=registry_model_id, runtime_id=runtime_id),
    )


class TestRollingSpeedsOverPersistedRecords:
    """The query itself, fed records directly, so the window rules are pinned."""

    @staticmethod
    def _persist(client: TestClient, session_id: str, records: list[TurnTiming]) -> None:
        conn = client.app.state.db.connection()
        for i, record in enumerate(records, start=1):
            persist_turn_timing(conn, session_id, i, record, "2026-01-01T00:00:00+00:00")

    def test_a_busy_other_configuration_does_not_crowd_out_the_requested_one(self, client):
        session_id = _start(client)
        self._persist(
            client,
            session_id,
            [_record(registry_model_id="model-a", writing_tps=10.0) for _ in range(20)]
            + [_record(registry_model_id="model-b", writing_tps=99.0) for _ in range(250)],
        )
        conn = client.app.state.db.connection()
        speeds = rolling_speeds(conn, runtime_id="fake", model_id="model-a")
        assert speeds.samples == 20
        assert speeds.writing_tps == 10.0
        assert rolling_speeds(conn, runtime_id="fake", model_id="model-b").samples == 20

    def test_the_window_is_the_newest_matching_records(self, client):
        session_id = _start(client)
        self._persist(
            client,
            session_id,
            [_record(writing_tps=1.0) for _ in range(5)] + [_record(writing_tps=50.0) for _ in range(20)],
        )
        speeds = rolling_speeds(client.app.state.db.connection(), runtime_id="fake", model_id=None)
        assert speeds.samples == 20
        assert speeds.writing_tps == 50.0

    def test_stopped_and_fallback_records_are_skipped_in_the_query(self, client):
        session_id = _start(client)
        self._persist(
            client,
            session_id,
            [
                _record(writing_tps=10.0),
                _record(writing_tps=500.0, stopped=True),
                _record(writing_tps=900.0, fallback=True),
            ],
        )
        speeds = rolling_speeds(client.app.state.db.connection(), runtime_id=None, model_id=None)
        assert speeds.samples == 1
        assert speeds.writing_tps == 10.0

    def test_model_filter_prefers_the_registry_id_over_the_adapter_name(self, client):
        session_id = _start(client)
        self._persist(
            client,
            session_id,
            [_record(model_id="default", registry_model_id="curated-model"), _record(model_id="default")],
        )
        conn = client.app.state.db.connection()
        assert rolling_speeds(conn, runtime_id=None, model_id="curated-model").samples == 1
        # The adapter's name counts only for the record without a registry id.
        assert rolling_speeds(conn, runtime_id=None, model_id="default").samples == 1
        assert rolling_speeds(conn, runtime_id="llama_cpp", model_id=None).samples == 0

    def test_a_corrupt_row_does_not_break_the_query(self, client):
        session_id = _start(client)
        self._persist(client, session_id, [_record()])
        conn = client.app.state.db.connection()
        with conn:
            conn.execute(
                "INSERT INTO turn_session_events (session_id, turn_number, event_type, payload_json, occurred_at) "
                "VALUES (?, 2, ?, 'not json', '2026-01-01T00:00:00+00:00')",
                (session_id, TURN_TIMING_EVENT_TYPE),
            )
        assert rolling_speeds(conn, runtime_id="fake", model_id=None).samples == 1
