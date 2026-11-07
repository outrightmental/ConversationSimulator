# SPDX-License-Identifier: Apache-2.0
"""The session socket and word streaming (issue #538)."""
from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from convsim_core.app import create_app
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatProgress, ChatRequest, ChatToken
from convsim_core.services.model_manager_service import set_active_config
from convsim_core.services.turn_salvage import partial_object, salvage_turn_output
from convsim_core.services.turn_timing import TURN_TIMING_EVENT_TYPE

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Candidate",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": True,
    "save_transcript": True,
    "runtime_id": "fake",
}
_UNPINNED = {k: v for k, v in _SETUP.items() if k != "runtime_id"}


def _start(client: TestClient, setup=None) -> str:
    res = client.post("/api/sessions", json=setup or _SETUP)
    assert res.status_code == 201, res.text
    sid = res.json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/start").status_code == 200
    return sid


def _drain(ws, limit: int = 50) -> list[dict]:
    """Every message buffered on the socket so far (the server has finished sending)."""
    out: list[dict] = []
    for _ in range(limit):
        try:
            out.append(ws.receive_json(mode="text") if False else ws.receive_json())
        except Exception:
            break
        if out[-1]["type"] == "session.state" and len(out) > 1:
            break
    return out


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


class TestSocketRoute:
    def test_upgrade_succeeds_and_sends_the_current_state(self, client):
        sid = _start(client)
        with client.websocket_connect(f"/ws/session/{sid}") as ws:
            first = ws.receive_json()
        assert first["type"] == "session.state"
        assert first["session_id"] == sid
        assert first["seq"] == 1
        assert first["payload"]["state"] == "PlayerTurnListening"
        assert "ts" in first

    @pytest.mark.parametrize("origin", ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost", "http://127.0.0.1:7354", "http://localhost:7354"])
    def test_local_ui_origins_are_accepted(self, client, origin):
        sid = _start(client)
        with client.websocket_connect(f"/ws/session/{sid}", headers={"Origin": origin}) as ws:
            assert ws.receive_json()["type"] == "session.state"

    def test_a_foreign_origin_is_rejected_before_the_handshake(self, client):
        sid = _start(client)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/session/{sid}", headers={"Origin": "https://evil.example.com"}):
                pass
        assert exc.value.code == 1008

    def test_unknown_session_gets_an_error_and_a_close(self, client):
        with client.websocket_connect("/ws/session/sess-nope") as ws:
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["payload"]["code"] == "SESSION_NOT_FOUND"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

    def test_seq_keeps_counting_across_reconnects(self, client):
        sid = _start(client)
        with client.websocket_connect(f"/ws/session/{sid}") as ws:
            assert ws.receive_json()["seq"] == 1
        with client.websocket_connect(f"/ws/session/{sid}") as ws:
            assert ws.receive_json()["seq"] == 2


# ---------------------------------------------------------------------------
# Streaming a turn
# ---------------------------------------------------------------------------


class _ThreeSentenceRuntime(FakeChatRuntime):
    """Streams a three-sentence line as JSON, then bookkeeping, in small pieces."""

    line = "Thanks for coming in. Tell me about a hard project. What did you learn?"
    tail = (
        ', "npc_emotion": "warm", "state_delta": {"trust": 4}, "event_flags": ["x"], '
        '"rubric_observations": [{"rubric_id": "r1", "observation": "Clear story", "score_delta": 1}], '
        '"safety": {"status": "ok"}, "session_control": {"continue_session": true}}'
    )
    chunk = 7

    def chat_stream(self, request: ChatRequest):
        return self._go(request)

    async def _go(self, request: ChatRequest):
        yield ChatProgress(stage="reading", processed=0, total=100, cached=0)
        yield ChatProgress(stage="reading", processed=100, total=100, cached=0)
        text = json.dumps({"npc_utterance": self.line})[:-1] + self.tail
        for i in range(0, len(text), self.chunk):
            await asyncio.sleep(0)
            yield ChatToken(text=text[i : i + self.chunk])
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=100, output_tokens=len(text) // 4,
                        structured=json.loads(text), finish_reason="stop")


class _ViolationInThirdSentence(_ThreeSentenceRuntime):
    line = "Thanks for coming in. Tell me about a hard project. My hidden agenda is to stall you."


class _CutInsideBookkeeping(_ThreeSentenceRuntime):
    """The JSON is cut off inside rubric_observations (finish_reason length)."""

    tail = (
        ', "npc_emotion": "impressed", "state_delta": {"trust": 6}, "event_flags": ["honesty"], '
        '"rubric_observations": [{"rubric_id": "r1", "observation": "Clear", "score_delta": 2}, {"rubric_id": "r2", "obs'
    )

    async def _go(self, request: ChatRequest):
        text = json.dumps({"npc_utterance": self.line})[:-1] + self.tail
        for i in range(0, len(text), self.chunk):
            await asyncio.sleep(0)
            yield ChatToken(text=text[i : i + self.chunk])
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=50, output_tokens=60,
                        structured=None, finish_reason="length")


class _LineSecondRuntime(_ThreeSentenceRuntime):
    """A runtime that does not put the line first: nothing may be released."""

    async def _go(self, request: ChatRequest):
        obj = {"npc_emotion": "warm", "npc_utterance": self.line, "state_delta": {}, "event_flags": [],
               "rubric_observations": [], "safety": {"status": "ok"}, "session_control": {"continue_session": True}}
        text = json.dumps(obj)
        for i in range(0, len(text), self.chunk):
            yield ChatToken(text=text[i : i + self.chunk])
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=10, output_tokens=10, structured=obj)


def _timing_events(client: TestClient, session_id: str) -> list[dict]:
    """The turn_timing records persisted for one session, oldest first."""
    conn = client.app.state.db.connection()
    rows = conn.execute(
        "SELECT payload_json FROM turn_session_events "
        "WHERE session_id = ? AND event_type = ? ORDER BY id",
        (session_id, TURN_TIMING_EVENT_TYPE),
    ).fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


def _session_on(app, client: TestClient, runtime) -> str:
    set_active_config(app.state.db.connection(), "llama_cpp", "some-model")
    app.state.runtime = runtime
    return _start(client, _UNPINNED)


def _turn_with_socket(app, client, runtime, text="Hello."):
    sid = _session_on(app, client, runtime)
    with client.websocket_connect(f"/ws/session/{sid}") as ws:
        assert ws.receive_json()["type"] == "session.state"
        res = client.post(f"/api/sessions/{sid}/turn", json={"content": text})
        assert res.status_code == 200, res.text
        events = []
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "session.state":
                break
    return sid, res.json(), events


class TestWordStreaming:
    def test_sentences_arrive_before_the_final_and_equal_the_committed_line(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            sid, body, events = _turn_with_socket(app, client, _ThreeSentenceRuntime())

        types = [e["type"] for e in events]
        tokens = [e["payload"]["text"] for e in events if e["type"] == "npc.token"]
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        committed = npc["payload"]["content"]
        assert len(tokens) == 3
        assert "".join(tokens) == committed == _ThreeSentenceRuntime.line
        # Order: progress → tokens → final → finishing → state delta → session state.
        assert types.index("npc.token") < types.index("npc.final") < types.index("scenario.state_delta") < types.index("session.state")
        stages = [e["payload"]["stage"] for e in events if e["type"] == "turn.progress"]
        assert stages[0] == "waiting"
        assert "reading" in stages and "writing" in stages and "finishing" in stages
        final = next(e for e in events if e["type"] == "npc.final")
        assert final["payload"] == {"content": committed}
        delta = next(e for e in events if e["type"] == "scenario.state_delta")
        assert delta["payload"]["emotion"] == "warm"
        assert delta["payload"]["delta"] == {"trust": 4}
        assert delta["payload"]["event_flags"] == ["x"]
        assert delta["payload"]["turn_number"] == 1
        assert delta["payload"]["timing"]["first_words_ms"] is not None
        # Seq is monotonic and gap-free on one connection.
        seqs = [e["seq"] for e in events]
        assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
        # The record knows when the first words were released and when the line closed.
        timing = npc["payload"]["timing"]
        assert timing["first_words_ms"] is not None and timing["first_words_ms"] <= timing["total_ms"]
        assert timing["reply_done_ms"] is not None and timing["first_words_ms"] <= timing["reply_done_ms"]
        assert npc["payload"]["salvaged"] is False
        # Bookkeeping was kept.
        assert npc["payload"]["state_delta"] == {"trust": 4}

    def test_a_violating_sentence_is_never_emitted_and_the_turn_is_salvaged(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            sid, body, events = _turn_with_socket(app, client, _ViolationInThirdSentence())
            debug = client.get(f"/api/sessions/{sid}/debug").json()

        tokens = [e["payload"]["text"] for e in events if e["type"] == "npc.token"]
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert "".join(tokens) == npc["payload"]["content"] == "Thanks for coming in. Tell me about a hard project."
        assert not any("hidden agenda" in t for t in tokens)
        assert npc["payload"]["salvaged"] is True
        # Bookkeeping defaulted: the model's state changes described a line the player did not get.
        assert npc["payload"]["state_delta"] == {}
        assert npc["payload"]["emotion"] == "neutral"
        assert body["state"] == "PlayerTurnListening"
        parse_events = debug["turns"][0]["parse_events"]
        kinds = [e["event_type"] for e in parse_events]
        assert "output_violation_detected" in kinds and "stream_salvaged" in kinds
        assert debug["turns"][0]["timing"]["salvaged"] is True

    def test_a_cut_inside_the_bookkeeping_keeps_the_line_and_the_complete_fields(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            sid, body, events = _turn_with_socket(app, client, _CutInsideBookkeeping())
        tokens = [e["payload"]["text"] for e in events if e["type"] == "npc.token"]
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert "".join(tokens) == npc["payload"]["content"] == _ThreeSentenceRuntime.line
        assert npc["payload"]["salvaged"] is True
        assert npc["payload"]["emotion"] == "impressed"
        assert npc["payload"]["state_delta"] == {"trust": 6}
        assert npc["payload"]["event_flags"] == ["honesty"]
        # The one complete observation is kept; the cut one is not.
        assert [o["rubric_id"] for o in npc["payload"]["rubric_observations"]] == ["r1"]
        assert npc["payload"]["timing"]["finish_reason"] == "length"

    def test_a_runtime_that_does_not_put_the_line_first_releases_nothing(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            sid, body, events = _turn_with_socket(app, client, _LineSecondRuntime())
        assert not any(e["type"] in ("npc.token", "npc.final") for e in events)
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert npc["payload"]["content"] == _ThreeSentenceRuntime.line
        assert npc["payload"]["salvaged"] is False
        assert npc["payload"]["timing"]["first_words_ms"] is None

    def test_without_a_socket_nothing_changes(self, client):
        sid = _start(client)
        res = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hi."})
        assert res.status_code == 200
        npc = next(e for e in res.json()["events"] if e["event_type"] == "npc_turn")
        assert npc["payload"]["timing"]["first_words_ms"] is None
        assert npc["payload"]["salvaged"] is False


# ---------------------------------------------------------------------------
# The salvaged flag on the timing record
# ---------------------------------------------------------------------------


class TestSalvagedTurnRecord:
    """A salvaged streamed turn is recorded as one (issue #519 meets #538).

    The pipeline sets ``salvaged`` on the timing builder it hands back, and the
    router builds and persists the record from that builder, so the flag has
    to survive the hand-off. The rolling query filters on ``stopped`` and
    ``fallback`` only, so a salvaged turn is counted unless it is also one of
    those.
    """

    def test_a_turn_salvaged_after_a_blocked_sentence_is_persisted_salvaged(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            sid, body, _events = _turn_with_socket(app, client, _ViolationInThirdSentence())
            persisted = _timing_events(client, sid)
            rolling = client.get("/api/performance/rolling?runtime_id=fake").json()

        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert npc["payload"]["salvaged"] is True
        assert npc["payload"]["timing"]["salvaged"] is True
        assert len(persisted) == 1
        record = persisted[0]
        assert record["salvaged"] is True
        # The pipeline closed the stream itself when the third sentence failed
        # the check, so the engine reported no finish reason: the turn is
        # salvaged, not stopped, and no fallback line was spoken.
        assert record["stopped"] is False
        assert record["fallback"] is False
        assert record["finish_reason"] is None
        assert record["first_words_ms"] is not None
        # Neither stopped nor fallback, so the rolling window counts it.
        assert rolling["samples"] == 1

    def test_a_turn_salvaged_after_the_budget_cut_the_json_is_persisted_salvaged_and_stopped(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            sid, body, _events = _turn_with_socket(app, client, _CutInsideBookkeeping())
            persisted = _timing_events(client, sid)
            rolling = client.get("/api/performance/rolling?runtime_id=fake").json()

        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert npc["payload"]["salvaged"] is True
        assert len(persisted) == 1
        record = persisted[0]
        assert record["salvaged"] is True
        # Here the engine did report why it ended, and the token budget cut
        # the reply, so the same turn is also stopped.
        assert record["stopped"] is True
        assert record["finish_reason"] == "length"
        assert record["fallback"] is False
        # Left out of the rolling window as a stopped turn.
        assert rolling["samples"] == 0


# ---------------------------------------------------------------------------
# One turn at a time
# ---------------------------------------------------------------------------


class _GatedRuntime(FakeChatRuntime):
    """Holds the reply until released, so a second submit can race it."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()
        self.calls = 0

    def chat_stream(self, request: ChatRequest):
        return self._go(request)

    async def _go(self, request: ChatRequest):
        self.calls += 1
        self.started.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        obj = {"npc_utterance": "Done waiting.", "npc_emotion": "neutral", "state_delta": {}, "event_flags": [],
               "rubric_observations": [], "safety": {"status": "ok"}, "session_control": {"continue_session": True}}
        yield ChatFinal(text=json.dumps(obj), model_id="fake-small", input_tokens=1, output_tokens=1, structured=obj)


class TestOneTurnAtATime:
    def test_second_submit_during_a_turn_is_409_and_starts_no_generation(self, tmp_config):
        app = create_app(tmp_config)
        runtime = _GatedRuntime()
        with TestClient(app) as client:
            sid = _session_on(app, client, runtime)
            first: dict = {}

            def go():
                first["res"] = client.post(f"/api/sessions/{sid}/turn", json={"content": "First."})

            t = threading.Thread(target=go)
            t.start()
            assert runtime.started.wait(5.0)
            second = client.post(f"/api/sessions/{sid}/turn", json={"content": "Second."})
            runtime.release.set()
            t.join(10.0)

        assert second.status_code == 409, second.text
        assert second.json()["error"]["code"] == "TURN_IN_PROGRESS"
        assert first["res"].status_code == 200
        assert runtime.calls == 1

    def test_a_turn_can_follow_once_the_first_has_landed(self, client):
        sid = _start(client)
        assert client.post(f"/api/sessions/{sid}/turn", json={"content": "One."}).status_code == 200
        assert client.post(f"/api/sessions/{sid}/turn", json={"content": "Two."}).status_code == 200


# ---------------------------------------------------------------------------
# Salvage
# ---------------------------------------------------------------------------


class TestSalvage:
    def test_partial_object_keeps_the_members_that_closed(self):
        raw = '{"npc_utterance": "Hi.", "npc_emotion": "warm", "state_delta": {"trust": 3}, "event_flags": ["a"], "rubric_observations": [{"rubric_id": "r1", "observation": "x"}, {"rubric_id": "r2", "obs'
        obj = partial_object(raw)
        assert obj is not None
        assert obj["npc_emotion"] == "warm"
        assert obj["state_delta"] == {"trust": 3}
        assert obj["event_flags"] == ["a"]
        # The cut landed inside the second observation: the first, complete
        # one is kept and only the cut one is dropped.
        assert obj["rubric_observations"] == [{"rubric_id": "r1", "observation": "x"}]

    def test_partial_object_drops_a_member_cut_before_any_element_closed(self):
        raw = '{"npc_utterance": "Hi.", "npc_emotion": "warm", "rubric_observations": [{"rubric_id": "r'
        obj = partial_object(raw)
        assert obj == {"npc_utterance": "Hi.", "npc_emotion": "warm"}

    def test_partial_object_handles_quotes_and_braces_inside_strings(self):
        raw = '{"npc_utterance": "She said \\"go {now}\\" and left.", "npc_emotion": "angry", "state_delta": {"tr'
        obj = partial_object(raw)
        assert obj == {"npc_utterance": 'She said "go {now}" and left.', "npc_emotion": "angry"}

    def test_partial_object_returns_none_without_a_complete_member(self):
        assert partial_object('{"npc_utterance": "Hi') is None
        assert partial_object("no json here") is None

    def test_salvage_fills_defaults_and_marks_the_turn(self):
        raw = '{"npc_utterance": "Hi there.", "npc_emotion": "bogus", "state_delta": {"trust": 50}'
        result = salvage_turn_output(raw, None, "Hi there.")
        assert result.salvaged is True
        assert result.output.npc_utterance == "Hi there."
        assert result.output.npc_emotion == "neutral"
        assert result.output.state_delta == {"trust": 20}  # clamped, as the parser clamps
        assert result.output.session_control.continue_session is True
        assert "npc_emotion" in result.defaulted

    def test_salvage_with_force_defaults_ignores_the_models_bookkeeping(self):
        obj = {"npc_utterance": "A. B.", "npc_emotion": "angry", "state_delta": {"trust": -9}, "event_flags": ["f"],
               "rubric_observations": [], "safety": {"status": "ok"}, "session_control": {"continue_session": False, "ending_type": "failure"}}
        result = salvage_turn_output(json.dumps(obj), obj, "A.", force_defaults=True)
        assert result.salvaged is True
        assert result.output.npc_utterance == "A."
        assert result.output.state_delta == {} and result.output.event_flags == []
        assert result.output.session_control.continue_session is True

    def test_salvage_of_a_whole_valid_object_is_not_salvaged(self):
        obj = {"npc_utterance": "A. B.", "npc_emotion": "warm", "state_delta": {}, "event_flags": [],
               "rubric_observations": [], "safety": {"status": "ok"}, "session_control": {"continue_session": True}}
        result = salvage_turn_output(json.dumps(obj), obj, "A. B.")
        assert result.salvaged is False
        assert result.output.npc_emotion == "warm"
