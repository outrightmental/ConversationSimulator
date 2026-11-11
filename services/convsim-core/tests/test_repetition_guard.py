# SPDX-License-Identifier: Apache-2.0
"""The repetition guard and its one retry (issue #580, P2).

On the starter model Ray ended two turns running with the same question, word
for word, and Diane's first question came back two turns later. After a reply
validates, the pipeline compares it with the NPC's last two lines (the
authored opening counts) and, on a repeat, generates it once more with the
repeated line quoted and the temperature a step higher, keeping whichever
repeats less. These tests pin:

  * which lines are compared, and that a fresh reply costs no extra call;
  * the retry request: same schema and system prompt, the repeated line
    quoted in the user turn, the temperature +0.1, recorded as a
    ``repetition_retry`` extra call;
  * which reply is kept, and that any failure keeps the first reply; a kept
    retry's raw output is what the turn row stores, so the debrief scores the
    reply the player got;
  * a player who asks for the line again gets the repeat, unretried;
  * streaming (#538): released text is committed text. A first sentence that
    would repeat is never shown, so the line can still be retried, and is,
    even when the whole line ends otherwise; a repeat
    after the first sentence streams with the line and is noted, never cut
    (a cut left the player an answer without its question), and the rest of
    the line is still held to the output check.
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from typing import Any, List, Optional

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatRequest, ChatToken, SamplingDefaults
from convsim_core.scenarios import get_scenario_data
from convsim_core.services import debrief_engine, turn_pipeline
from convsim_core.services.model_manager_service import set_active_config
from convsim_core.services.turn_pipeline import process_turn
from convsim_core.storage.migrations import run_migrations
from convsim_prompt.layers import PREVIOUS_NPC_LINE_BEGIN, REPEATED_LINE_BEGIN

_OPENING = "Welcome in. Thanks for making the time to come and see us today."
_PLAYER_1 = "Happy to be here. I have been looking forward to it."
# Ray's T3 closing question, verbatim from issue #580.
_NPC_1 = (
    "That's a solid offer, and I see your point. "
    "What's the smallest you'd be open to for the car?"
)
_PLAYER_2 = "I could do eleven thousand, cash."
_NPC_2 = "Eleven is low for this one. It has new brakes and one owner."
_PLAYER = "Twelve thousand is my limit."

# Ray's T4: a new first sentence, then T3's question again.
_REPEAT_AT_END = "I hear you, and I respect that. What's the smallest you'd be open to for the car?"
# Starts by repeating _NPC_1's first sentence.
_REPEAT_AT_START = "That's a solid offer, and I see your point. Twelve is close, though."
_FRESH = "Twelve is close. Sign today and I can throw in floor mats."

# A reply that opens with the previous line's closing question, then moves on.
_GREETING = "Good to hear it. What brings you here?"
_ASKS_BACK = "What brings you here? Twelve is close and I can work with it."


def _turn(line: str, **fields: Any) -> dict:
    body = {
        "npc_utterance": line,
        "npc_emotion": "neutral",
        "state_delta": {},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    }
    body.update(fields)
    return body


class _Raw(str):
    """A reply that is not JSON at all."""


class _Hang:
    """A reply that never comes."""


class _Replies(FakeChatRuntime):
    """Answers each request with the next scripted reply, streamed in small chunks.

    A reply is a line (wrapped in a whole turn object), a turn dict, a
    ``_Raw`` string, an exception to raise, or ``_Hang``. Every request is
    kept in ``requests``.
    """

    def __init__(self, *replies: Any, chunk: int = 6) -> None:
        self.replies = list(replies)
        self.requests: List[ChatRequest] = []
        self.chunk = chunk

    def chat_stream(self, request: ChatRequest):
        self.requests.append(request)
        reply = self.replies.pop(0) if self.replies else _FRESH
        return self._go(reply)

    async def _go(self, reply: Any):
        if isinstance(reply, BaseException):
            raise reply
        if reply is _Hang:
            await asyncio.sleep(30)
        if isinstance(reply, _Raw):
            text, structured = str(reply), None
        else:
            structured = reply if isinstance(reply, dict) else _turn(reply)
            text = json.dumps(structured)
        for i in range(0, len(text), self.chunk):
            await asyncio.sleep(0)
            yield ChatToken(text=text[i : i + self.chunk])
        yield ChatFinal(
            text=text, model_id="fake-small", input_tokens=100, output_tokens=20,
            structured=structured, finish_reason="stop",
        )


class _Streamer:
    """Collects what the pipeline would send to the session socket."""

    def __init__(self) -> None:
        self.output_tokens = 0
        self.tokens: List[str] = []
        self.finals: List[str] = []
        self.stages: List[str] = []

    async def progress(self, stage: str, prompt: Optional[dict] = None) -> None:
        self.stages.append(stage)

    async def token(self, text: str) -> None:
        self.tokens.append(text)

    async def final(self, content: str) -> None:
        self.finals.append(content)


def _session(*history: tuple[str, str]) -> tuple[sqlite3.Connection, sqlite3.Row]:
    """An in-memory session whose transcript holds ``history`` (role, text)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    turns = sum(1 for role, _ in history if role == "npc")
    conn.execute(
        "INSERT INTO turn_sessions (session_id, scenario_id, flow_state, state_vars_json, "
        "fired_events_json, turn_count, setup_json) "
        "VALUES ('s', 'behavioral_interview', 'PlayerTurnListening', '{}', '[]', ?, '{}')",
        (turns,),
    )
    for number, (role, text) in enumerate(history):
        conn.execute(
            "INSERT INTO turn_session_turns (session_id, turn_number, role, content) VALUES ('s', ?, ?, ?)",
            (number, role, text),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM turn_sessions WHERE session_id = 's'").fetchone()
    return conn, row


_ONE_EXCHANGE = (("npc_opening", _OPENING), ("player", _PLAYER_1), ("npc", _NPC_1))
_TWO_EXCHANGES = _ONE_EXCHANGE + (("player", _PLAYER_2), ("npc", _NPC_2))


async def _play(runtime, *history, streamer=None, player=_PLAYER, **kwargs):
    conn, row = _session(*history)
    result = await process_turn(
        session_row=row,
        player_text=player,
        scenario_data=get_scenario_data("behavioral_interview", "standard"),
        max_turns=10,
        runtime=runtime,
        conn=conn,
        streamer=streamer,
        **kwargs,
    )
    return result, conn


def _parse_events(conn: sqlite3.Connection) -> List[dict]:
    return _debug_payload(conn)["parse_events"]


def _kinds(conn: sqlite3.Connection) -> List[str]:
    return [e["event_type"] for e in _parse_events(conn)]


def _stored_npc_line(conn: sqlite3.Connection) -> str:
    return _stored_npc_row(conn)["content"]


def _stored_npc_row(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute(
        "SELECT * FROM turn_session_turns WHERE role = 'npc' ORDER BY turn_number DESC LIMIT 1"
    ).fetchone()


def _event_payload(conn: sqlite3.Connection, event_type: str) -> Any:
    row = conn.execute(
        "SELECT payload_json FROM turn_session_events WHERE event_type = ? ORDER BY id DESC LIMIT 1",
        (event_type,),
    ).fetchone()
    return json.loads(row["payload_json"]) if row is not None else None


def _debug_payload(conn: sqlite3.Connection) -> dict:
    return _event_payload(conn, "debug")


# ---------------------------------------------------------------------------
# What is compared, and what a fresh reply costs
# ---------------------------------------------------------------------------


class TestWhatIsCompared:
    @pytest.mark.asyncio
    async def test_a_fresh_reply_costs_no_extra_call(self):
        runtime = _Replies(_FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert len(runtime.requests) == 1
        assert result.npc_utterance == _FRESH
        assert result.timing.extra_calls == []
        assert not any(k.startswith("repetition") for k in _kinds(conn))

    @pytest.mark.asyncio
    async def test_a_repeat_of_the_previous_line_is_retried(self):
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert len(runtime.requests) == 2
        assert result.npc_utterance == _FRESH
        assert _stored_npc_line(conn) == _FRESH

    @pytest.mark.asyncio
    async def test_the_opening_counts(self):
        runtime = _Replies("Sure. Thanks for making the time to come and see us today.", _FRESH)
        result, _ = await _play(runtime, ("npc_opening", _OPENING), player=_PLAYER_1)
        assert len(runtime.requests) == 2
        assert result.npc_utterance == _FRESH

    @pytest.mark.asyncio
    async def test_the_line_before_the_previous_one_counts(self):
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        result, _ = await _play(runtime, *_TWO_EXCHANGES)
        assert len(runtime.requests) == 2
        assert result.npc_utterance == _FRESH
        # The retry quotes the line repeated, and keeps the quote of the
        # previous line, which is a different one.
        user = runtime.requests[1].messages[1].content
        assert REPEATED_LINE_BEGIN in user and f'"{_NPC_1}"' in user
        assert PREVIOUS_NPC_LINE_BEGIN in user and f'"{_NPC_2}"' in user

    @pytest.mark.asyncio
    async def test_three_lines_back_is_not_compared(self):
        runtime = _Replies("Sure. Thanks for making the time to come and see us today.")
        result, _ = await _play(runtime, *_TWO_EXCHANGES)
        assert len(runtime.requests) == 1
        assert result.timing.extra_calls == []

    @pytest.mark.asyncio
    async def test_a_redirect_is_not_retried(self):
        runtime = _Replies(_turn(_REPEAT_AT_END, safety={"status": "redirect", "reason": "x"}))
        await _play(runtime, *_ONE_EXCHANGE)
        assert len(runtime.requests) == 1

    @pytest.mark.asyncio
    async def test_the_canned_fallback_line_is_not_retried(self):
        # Garbage, then garbage from the parser's structural repair: the
        # canned line is spoken, and it is no NPC loop.
        runtime = _Replies(_Raw("not json"), _Raw("still not json"))
        result, _ = await _play(runtime, ("npc_opening", turn_pipeline.SAFE_FALLBACK_UTTERANCE))
        assert result.used_fallback
        assert len(runtime.requests) == 2
        assert [c.kind for c in result.timing.extra_calls] == ["repair"]


# ---------------------------------------------------------------------------
# The retry request
# ---------------------------------------------------------------------------


class TestRetryRequest:
    @pytest.mark.asyncio
    async def test_same_schema_and_system_prompt_with_the_line_quoted_and_a_hotter_temperature(self):
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        await _play(runtime, *_ONE_EXCHANGE)
        first, retry = runtime.requests
        assert retry.json_schema == first.json_schema
        assert retry.max_tokens == first.max_tokens
        assert retry.scripted_turn_index == first.scripted_turn_index
        assert retry.temperature == pytest.approx(first.temperature + 0.1)
        # The system prompt is the turn's own, so the prompt cache keeps it (#524).
        assert retry.messages[0].role == "system"
        assert retry.messages[0].content == first.messages[0].content
        user = retry.messages[1].content
        assert user != first.messages[1].content
        assert REPEATED_LINE_BEGIN in user
        assert user.count(f'"{_NPC_1}"') == 1  # quoted once, not twice
        assert PREVIOUS_NPC_LINE_BEGIN not in user
        assert "Do not repeat this" in user
        # The player's line stays last.
        assert user.rstrip().endswith("=== END PLAYER INPUT ===")
        assert user.index("Do not repeat this") < user.index(_PLAYER)

    @pytest.mark.asyncio
    async def test_llama_cpp_sends_the_retry_with_the_turns_schema_constraint(self):
        """The retry builds no schema of its own: llama-server constrains it with
        the grammar it already converts for every turn, from the same schema."""
        from convsim_core.runtime.llama_cpp import LlamaCppConfig, LlamaCppRuntime
        from convsim_prompt import NPC_TURN_OUTPUT_SCHEMA

        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        await _play(runtime, *_ONE_EXCHANGE)
        adapter = LlamaCppRuntime(LlamaCppConfig(base_url="http://127.0.0.1:1"))
        first, retry = (
            adapter._build_payload(r, "m", with_extras=True) for r in runtime.requests
        )
        assert retry["response_format"] == first["response_format"] == {
            "type": "json_object", "schema": NPC_TURN_OUTPUT_SCHEMA,
        }
        assert retry["temperature"] == pytest.approx(first["temperature"] + 0.1)
        assert retry["top_p"] == first["top_p"]
        assert retry["max_tokens"] == first["max_tokens"]
        assert retry["messages"][0] == first["messages"][0]
        assert [m["role"] for m in retry["messages"]] == ["system", "user"]

    @pytest.mark.asyncio
    async def test_the_registry_temperature_is_raised_one_step(self, monkeypatch):
        monkeypatch.setattr(
            turn_pipeline, "active_model_sampling",
            lambda conn, runtime_id, config=None: SamplingDefaults(temperature=0.7, top_p=0.8),
        )
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        await _play(runtime, *_ONE_EXCHANGE)
        first, retry = runtime.requests
        assert first.temperature == pytest.approx(0.7)
        assert retry.temperature == pytest.approx(0.8)
        assert retry.top_p == first.top_p == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_the_retry_is_recorded_as_an_extra_call(self):
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert [c.kind for c in result.timing.extra_calls] == ["repetition_retry"]
        assert result.timing.extra_calls[0].tokens == 20
        assert result.timing.extra_calls[0].ms >= 0
        record = result.timing.build()
        assert [c.kind for c in record.extra_calls] == ["repetition_retry"]
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_kept"]
        detected = _parse_events(conn)[0]
        assert detected["category"] == "repetition"
        assert "previous NPC line" in detected["reason"]


    @pytest.mark.asyncio
    async def test_the_retry_is_parsed_by_the_turns_own_parse_step(self, monkeypatch):
        """One helper parses both replies, so a step added to the turn's parse
        (a filter, a schema to check against) cannot skip a kept retry."""
        calls: list = []
        real = turn_pipeline._parse_reply

        def spy(parse_input, **kw):
            calls.append(kw)
            return real(parse_input, **kw)

        monkeypatch.setattr(turn_pipeline, "_parse_reply", spy)
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _FRESH
        turn, retry = calls
        assert turn["request"].messages == runtime.requests[0].messages
        assert retry["request"].messages == runtime.requests[1].messages
        assert retry["request"].json_schema == turn["request"].json_schema
        # The turn's parse may repair; the retry's gets no model call of its own.
        assert turn["runtime"] is not None and retry["runtime"] is None
        assert turn["hidden_agenda"] == retry["hidden_agenda"]


# ---------------------------------------------------------------------------
# Which reply is kept
# ---------------------------------------------------------------------------


class TestWhichReplyIsKept:
    @pytest.mark.asyncio
    async def test_a_retry_that_repeats_as_much_keeps_the_first_reply(self):
        runtime = _Replies(_REPEAT_AT_END, _REPEAT_AT_END)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_discarded"]
        assert [c.kind for c in result.timing.extra_calls] == ["repetition_retry"]

    @pytest.mark.asyncio
    async def test_a_retry_that_repeats_less_is_kept(self):
        # Run and same closing question first; only a shorter run second.
        less = "I hear you. That's a solid offer, and I see your point here."
        runtime = _Replies(_REPEAT_AT_END, less)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == less
        kept = _parse_events(conn)[-1]
        assert kept["event_type"] == "repetition_retry_kept"
        assert kept["reason"].startswith("the retry repeats less")

    @pytest.mark.asyncio
    async def test_the_retrys_bookkeeping_comes_with_its_line(self):
        runtime = _Replies(
            _turn(_REPEAT_AT_END, state_delta={"trust": -5}),
            _turn(_FRESH, state_delta={"trust": 4}, npc_emotion="warm"),
        )
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _FRESH
        assert result.state_delta == {"trust": 4}
        assert result.npc_emotion == "warm"

    @pytest.mark.asyncio
    async def test_a_kept_retry_is_the_output_the_turn_row_and_the_debrief_read(self):
        """The NPC row's raw output is what the debrief tallies rubric notes
        from, what GET /debug returns as raw_npc_output and what the D-05
        replay's check (g) reads the proposed state_delta from. After a kept
        retry it must be the retry's, the reply the player got, and agree with
        the row's state_delta and the turn's rubric_observations event. The
        first reply, which nobody saw, stays in the kept event for the drawer."""
        first = _turn(
            _REPEAT_AT_END,
            state_delta={"trust": 6},
            rubric_observations=[{"rubric_id": "clarity", "observation": "Crisp.", "score_delta": 3}],
        )
        retry = _turn(
            _FRESH,
            state_delta={"trust": -5},
            rubric_observations=[{"rubric_id": "clarity", "observation": "Vague.", "score_delta": -3}],
        )
        runtime = _Replies(first, retry)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _FRESH
        row = _stored_npc_row(conn)
        assert json.loads(row["raw_output_json"]) == retry
        assert json.loads(row["state_delta_json"]) == {"trust": -5}
        assert _event_payload(conn, "rubric_observations") == retry["rubric_observations"]
        tallies = debrief_engine._tally_observations([row])
        assert (tallies["clarity"].notes, tallies["clarity"].net) == (1, -3)
        records = debrief_engine._build_debrief_turn_records([row])
        assert [o["score_delta"] for o in records[0].rubric_observations] == [-3]
        kept = _parse_events(conn)[-1]
        assert kept["event_type"] == "repetition_retry_kept"
        assert json.loads(kept["discarded_raw_output"]) == first

    @pytest.mark.asyncio
    async def test_a_kept_retry_brings_its_own_structured_output_flag(self):
        """used_native_structured_output describes the stored output: here the
        first reply came as plain text, the kept retry pre-parsed."""
        runtime = _Replies(_Raw(json.dumps(_turn(_REPEAT_AT_END))), _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _FRESH
        assert _debug_payload(conn)["used_native_structured_output"] is True
        assert json.loads(_stored_npc_row(conn)["raw_output_json"]) == _turn(_FRESH)
        # A discarded retry leaves the first reply's output and flag alone.
        runtime = _Replies(_Raw(json.dumps(_turn(_REPEAT_AT_END))), _REPEAT_AT_END)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert _debug_payload(conn)["used_native_structured_output"] is False
        assert _stored_npc_row(conn)["raw_output_json"] == json.dumps(_turn(_REPEAT_AT_END))
        assert "discarded_raw_output" not in _parse_events(conn)[-1]

    @pytest.mark.asyncio
    async def test_without_a_saved_transcript_the_kept_event_carries_no_line(self):
        """Debug events are exported even when the transcript is not saved;
        the first reply's raw output, a line of the conversation, is not."""
        runtime = _Replies(_REPEAT_AT_END, _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE, save_transcript=False)
        assert result.npc_utterance == _FRESH
        kept = _parse_events(conn)[-1]
        assert kept["event_type"] == "repetition_retry_kept"
        assert "discarded_raw_output" not in kept

    @pytest.mark.asyncio
    async def test_a_turn_that_leaked_the_hidden_agenda_keeps_no_line_in_the_kept_event(self):
        """The first reply's raw output is what the model first wrote, before
        the parser's safety retry: after a leak it is not kept (issue #199)."""
        leak = "Fine. My hidden agenda is to keep you talking."
        runtime = _Replies(leak, _REPEAT_AT_END, _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert len(runtime.requests) == 3
        assert result.npc_utterance == _FRESH
        events = _parse_events(conn)
        assert any(e["category"] == "hidden_agenda_leak" for e in events)
        assert events[-1]["event_type"] == "repetition_retry_kept"
        assert "discarded_raw_output" not in events[-1]
        assert leak not in json.dumps(events)

    @pytest.mark.asyncio
    async def test_a_failing_retry_keeps_the_first_reply(self):
        runtime = _Replies(_REPEAT_AT_END, ConnectionError("engine went away"))
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert result.used_fallback is False
        assert [c.kind for c in result.timing.extra_calls] == ["repetition_retry"]
        assert result.timing.extra_calls[0].tokens is None
        assert _parse_events(conn)[-1]["reason"] == "the retry call failed (ConnectionError)"

    @pytest.mark.asyncio
    async def test_a_retry_that_is_not_json_keeps_the_first_reply_without_a_repair(self):
        runtime = _Replies(_REPEAT_AT_END, _Raw("I am not JSON"))
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert len(runtime.requests) == 2  # no repair spent on the retry
        assert _kinds(conn)[-1] == "repetition_retry_discarded"

    @pytest.mark.asyncio
    async def test_an_unsafe_retry_keeps_the_first_reply(self):
        runtime = _Replies(_REPEAT_AT_END, "Fine. My hidden agenda is to keep you talking.")
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert len(runtime.requests) == 2

    @pytest.mark.asyncio
    async def test_a_hung_retry_is_abandoned(self, monkeypatch):
        monkeypatch.setattr(turn_pipeline, "REPETITION_RETRY_MIN_TIMEOUT_S", 0.2)
        monkeypatch.setattr(turn_pipeline, "REPETITION_RETRY_TIMEOUT_FACTOR", 0.0)
        runtime = _Replies(_REPEAT_AT_END, _Hang)
        started = time.perf_counter()
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert time.perf_counter() - started < 10
        assert result.npc_utterance == _REPEAT_AT_END
        assert _parse_events(conn)[-1]["reason"] == "the retry call failed (TimeoutError)"

    @pytest.mark.asyncio
    async def test_a_broken_guard_never_costs_the_turn(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("broken")

        monkeypatch.setattr(turn_pipeline, "check_repetition", boom)
        runtime = _Replies(_REPEAT_AT_END)
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert len(runtime.requests) == 1


# ---------------------------------------------------------------------------
# Streaming: released text is committed text (#538)
# ---------------------------------------------------------------------------


class TestStreamedLines:
    @pytest.mark.asyncio
    async def test_a_repeating_first_sentence_is_never_shown_and_the_line_is_retried(self):
        streamer = _Streamer()
        runtime = _Replies(_REPEAT_AT_START, _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE, streamer=streamer)
        assert streamer.tokens == []
        assert streamer.finals == []
        assert "checking" in streamer.stages
        assert len(runtime.requests) == 2
        assert result.npc_utterance == _FRESH
        assert result.streamed_line is None
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_kept"]

    @pytest.mark.asyncio
    async def test_a_first_sentence_held_for_its_question_alone_is_retried(self):
        """The gate holds "What brings you here?": as a whole line it ends with
        the previous line's closing question. The whole reply ends otherwise,
        so only the held first sentence makes it a repeat, and the guard must
        still retry it: nothing else would ever commit the held line."""
        streamer = _Streamer()
        runtime = _Replies(_ASKS_BACK, _FRESH)
        result, conn = await _play(runtime, ("npc_opening", _GREETING), streamer=streamer, player="Hello!")
        assert streamer.tokens == [] and streamer.finals == []
        assert "checking" in streamer.stages
        assert len(runtime.requests) == 2
        assert f'"{_GREETING}"' in runtime.requests[1].messages[1].content
        assert [c.kind for c in result.timing.extra_calls] == ["repetition_retry"]
        assert result.npc_utterance == _stored_npc_line(conn) == _FRESH
        assert result.streamed_line is None
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_kept"]
        detected = _parse_events(conn)[0]
        assert detected["reason"].startswith("its first sentence, held back from the stream,")
        assert "the same 4-word question as the previous NPC line" in detected["reason"]

    @pytest.mark.asyncio
    async def test_a_retry_whose_first_sentence_would_be_held_too_keeps_the_first_reply(self):
        """The retry is judged as the held line was: its first sentence would
        be held for the same question, so it repeats as much."""
        streamer = _Streamer()
        again = "What brings you here? I can do twelve, and not a dollar more."
        runtime = _Replies(_ASKS_BACK, again)
        result, conn = await _play(runtime, ("npc_opening", _GREETING), streamer=streamer, player="Hello!")
        assert streamer.tokens == [] and streamer.finals == []
        assert len(runtime.requests) == 2
        assert result.npc_utterance == _stored_npc_line(conn) == _ASKS_BACK
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_discarded"]
        assert "question" in _parse_events(conn)[1]["reason"]

    @pytest.mark.asyncio
    async def test_a_held_line_the_safety_retry_replaced_is_not_retried_for_the_hold(self):
        """The gate held the first reply's opening question, but the parser's
        safety retry then replaced the whole line with one that does not open
        with it. The guard judges the line it is guarding, so the hold costs
        no third generation and leaves no repetition event."""
        streamer = _Streamer()
        replaced = "Twelve is close and I can work with it."
        runtime = _Replies("What brings you here? My hidden agenda is to keep you talking.", replaced)
        result, conn = await _play(runtime, ("npc_opening", _GREETING), streamer=streamer, player="Hello!")
        assert streamer.tokens == []
        assert len(runtime.requests) == 2
        assert [c.kind for c in result.timing.extra_calls] == ["safety_retry"]
        assert result.npc_utterance == _stored_npc_line(conn) == replaced
        assert not any(k.startswith("repetition") for k in _kinds(conn))

    @pytest.mark.asyncio
    async def test_the_same_reply_unstreamed_is_not_a_repeat(self):
        """Without a streamer nothing is held, and the whole line ends with
        its own sentence, not the previous question: no retry."""
        runtime = _Replies(_ASKS_BACK)
        result, conn = await _play(runtime, ("npc_opening", _GREETING), player="Hello!")
        assert len(runtime.requests) == 1
        assert result.npc_utterance == _ASKS_BACK
        assert not any(k.startswith("repetition") for k in _kinds(conn))

    @pytest.mark.asyncio
    async def test_a_repeat_after_the_first_sentence_streams_whole_and_is_noted(self):
        """Ray's T4: a new first sentence, then T3's closing question. Cutting
        the question would leave him no question at all; the line streams."""
        streamer = _Streamer()
        runtime = _Replies(_turn(_REPEAT_AT_END, state_delta={"trust": 3}, npc_emotion="warm"))
        result, conn = await _play(runtime, *_ONE_EXCHANGE, streamer=streamer)
        assert streamer.tokens == [
            "I hear you, and I respect that.", " What's the smallest you'd be open to for the car?",
        ]
        assert streamer.finals == [_REPEAT_AT_END]
        # What the player saw is what is committed, and nothing replaced it.
        assert result.npc_utterance == _stored_npc_line(conn) == "".join(streamer.tokens) == _REPEAT_AT_END
        assert result.streamed_line == _REPEAT_AT_END
        assert len(runtime.requests) == 1
        assert result.timing.extra_calls == []
        assert result.state_delta == {"trust": 3}
        assert result.npc_emotion == "warm"
        assert result.salvaged is False
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_skipped"]
        assert "the same 10-word question" in _parse_events(conn)[0]["reason"]

    @pytest.mark.asyncio
    async def test_after_a_streamed_repeat_an_unsafe_sentence_still_defaults_the_bookkeeping(self):
        """The rest of the line is still held to the output check. A sentence
        that fails it stops the stream, and the bookkeeping, which describes
        the withheld text too, is defaulted, as for any unsafe tail."""
        streamer = _Streamer()
        line = _REPEAT_AT_END + " Between us, my real goal is to fill the role fast."
        runtime = _Replies(_turn(
            line,
            state_delta={"trust": 3},
            npc_emotion="warm",
            event_flags=["deal_signalled"],
            session_control={"continue_session": False, "ending_type": "success"},
        ))
        result, conn = await _play(runtime, *_ONE_EXCHANGE, streamer=streamer)
        assert "".join(streamer.tokens) == result.npc_utterance == _REPEAT_AT_END
        assert result.salvaged is True
        assert result.state_delta == {}
        assert result.event_flags == []
        assert result.ending_type is None
        kinds = _kinds(conn)
        assert kinds[:2] == ["output_violation_detected", "stream_salvaged"]
        assert kinds[2:] == ["repetition_detected", "repetition_retry_skipped"]
        assert len(runtime.requests) == 1

    @pytest.mark.asyncio
    async def test_a_repeat_only_the_whole_line_shows_is_noted_once_part_is_out(self):
        streamer = _Streamer()
        runtime = _Replies("The brakes are fresh too. We have new tires.")
        result, conn = await _play(
            runtime, ("npc_opening", "We have new tires. The brakes are fresh too."),
            streamer=streamer, player="Hello!",
        )
        assert streamer.tokens == ["The brakes are fresh too.", " We have new tires."]
        assert result.npc_utterance == "The brakes are fresh too. We have new tires."
        assert len(runtime.requests) == 1
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_skipped"]

    @pytest.mark.asyncio
    async def test_a_fresh_streamed_line_is_untouched(self):
        streamer = _Streamer()
        runtime = _Replies(_FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE, streamer=streamer)
        assert "".join(streamer.tokens) == streamer.finals[0] == result.npc_utterance == _FRESH
        assert len(runtime.requests) == 1
        assert not any(k.startswith("repetition") for k in _kinds(conn))


# ---------------------------------------------------------------------------
# A player who asks for the line again
# ---------------------------------------------------------------------------

# spanish_coffee: asking for a repeat is a repair strategy the rubric rewards.
_ROSA = "¡Claro! Un café con leche. ¿Quieres algo para comer?"
_ROSA_AGAIN = "¡Claro! Te lo repito más despacio: un café con leche. ¿Quieres algo para comer?"
_ASKS_AGAIN = "Perdón, ¿puede repetir más despacio?"
_ROSA_HISTORY = (
    ("npc_opening", "¡Hola! Buenos días. ¿Qué vas a tomar hoy?"),
    ("player", "Quisiera un café con leche, por favor."),
    ("npc", _ROSA),
)
# A line whose first sentence repeats Rosa's previous one word for word.
_ROSA_TOTAL = "Un café con leche y un cruasán, ¿verdad? Son cuatro euros con cincuenta."
_ROSA_TOTAL_HISTORY = (
    ("npc_opening", "¡Hola! Buenos días. ¿Qué vas a tomar hoy?"),
    ("player", "Un café con leche y un cruasán. ¿Cuánto es?"),
    ("npc", _ROSA_TOTAL),
)


class TestRepeatRequested:
    @pytest.mark.asyncio
    async def test_the_repeat_the_player_asked_for_is_kept_without_a_retry(self):
        runtime = _Replies(_ROSA_AGAIN)
        result, conn = await _play(runtime, *_ROSA_HISTORY, player=_ASKS_AGAIN)
        assert result.npc_utterance == _ROSA_AGAIN
        assert len(runtime.requests) == 1
        assert result.timing.extra_calls == []
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_skipped"]
        assert _parse_events(conn)[1]["reason"] == "the player asked for the line again"

    @pytest.mark.asyncio
    async def test_the_same_reply_to_any_other_line_is_retried(self):
        runtime = _Replies(_ROSA_AGAIN, "Tenemos cruasanes recién hechos.")
        result, conn = await _play(runtime, *_ROSA_HISTORY, player="Gracias. ¿Algo más?")
        assert len(runtime.requests) == 2
        assert result.npc_utterance == "Tenemos cruasanes recién hechos."

    @pytest.mark.asyncio
    async def test_a_repeated_first_sentence_streams_when_the_player_asked(self):
        streamer = _Streamer()
        runtime = _Replies(_ROSA_TOTAL)
        result, conn = await _play(
            runtime, *_ROSA_TOTAL_HISTORY, streamer=streamer, player="Perdón, ¿otra vez, más despacio?",
        )
        assert "".join(streamer.tokens) == streamer.finals[0] == result.npc_utterance == _ROSA_TOTAL
        assert len(runtime.requests) == 1
        assert _kinds(conn) == ["repetition_detected", "repetition_retry_skipped"]
        assert _parse_events(conn)[1]["reason"] == "the player asked for the line again"
        # Asked anything else, the same first sentence is held for the guard.
        held = _Streamer()
        runtime = _Replies(_ROSA_TOTAL, "Son cuatro euros con cincuenta, gracias.")
        result, _ = await _play(runtime, *_ROSA_TOTAL_HISTORY, streamer=held, player="Vale. ¿Algo más?")
        assert held.tokens == [] and held.finals == []
        assert len(runtime.requests) == 2

    @pytest.mark.asyncio
    async def test_a_broken_request_check_guards_the_turn_as_usual(self, monkeypatch):
        def boom(_line):
            raise RuntimeError("broken")

        monkeypatch.setattr(turn_pipeline, "asks_for_repeat", boom)
        runtime = _Replies(_ROSA_AGAIN, "Tenemos cruasanes recién hechos.")
        result, _ = await _play(runtime, *_ROSA_HISTORY, player=_ASKS_AGAIN)
        assert len(runtime.requests) == 2


# ---------------------------------------------------------------------------
# End to end, over the session socket
# ---------------------------------------------------------------------------

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Candidate",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": True,
    "save_transcript": True,
}


def _turn_over_socket(app, client: TestClient, runtime) -> tuple[dict, list]:
    set_active_config(app.state.db.connection(), "llama_cpp", "some-model")
    app.state.runtime = runtime
    res = client.post("/api/sessions", json=_SETUP)
    assert res.status_code == 201, res.text
    sid = res.json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/start").status_code == 200
    opening = client.get(f"/api/sessions/{sid}/transcript").json()["turns"][0]["content"]
    runtime.opening = opening
    with client.websocket_connect(f"/ws/session/{sid}") as ws:
        assert ws.receive_json()["type"] == "session.state"
        res = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hello."})
        assert res.status_code == 200, res.text
        events = []
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "session.state":
                break
    return res.json(), events


class _EchoesTheOpening(_Replies):
    """First reply: part of the authored opening again, word for word. Then a fresh line.

    behavioral_interview opens "Thanks for coming in today. I'm Alex Chen from
    HR. Tell me a little about yourself and why you're interested in this
    role." ``sentences`` picks which of its sentences the reply echoes.
    """

    def __init__(self, sentences: slice) -> None:
        super().__init__()
        self.sentences = sentences
        self.opening = ""

    def chat_stream(self, request: ChatRequest):
        if not self.requests:
            echoed = " ".join(re.split(r"(?<=[.!?])\s+", self.opening)[self.sentences])
            self.replies = [echoed, _FRESH]
        return super().chat_stream(request)


class TestOverTheSocket:
    def test_an_echo_in_the_first_sentence_is_never_streamed_and_the_retry_is_committed(self, tmp_config):
        app = create_app(tmp_config)
        runtime = _EchoesTheOpening(slice(2, None))
        with TestClient(app) as client:
            body, events = _turn_over_socket(app, client, runtime)
        assert runtime.opening.startswith("Thanks for coming in today.")
        assert not any(e["type"] in ("npc.token", "npc.final") for e in events)
        stages = [e["payload"]["stage"] for e in events if e["type"] == "turn.progress"]
        assert "checking" in stages
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert npc["payload"]["content"] == _FRESH
        assert [c["kind"] for c in npc["payload"]["timing"]["extra_calls"]] == ["repetition_retry"]

    def test_an_echo_after_a_released_sentence_streams_whole_and_is_committed(self, tmp_config):
        """The whole opening again: its 5-word first sentence repeats nothing
        on its own and goes out, so the rest of the line follows it. The player
        gets the whole line, never a cut one, and no retry replaces it."""
        app = create_app(tmp_config)
        runtime = _EchoesTheOpening(slice(None))
        with TestClient(app) as client:
            body, events = _turn_over_socket(app, client, runtime)
        tokens = [e["payload"]["text"] for e in events if e["type"] == "npc.token"]
        finals = [e["payload"]["content"] for e in events if e["type"] == "npc.final"]
        npc = next(e for e in body["events"] if e["event_type"] == "npc_turn")
        assert tokens[0] == "Thanks for coming in today."
        assert "".join(tokens) == runtime.opening
        assert finals == [runtime.opening]
        assert npc["payload"]["content"] == runtime.opening
        assert npc["payload"]["timing"]["extra_calls"] == []
        assert len(runtime.requests) == 1
