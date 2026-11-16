# SPDX-License-Identifier: Apache-2.0
"""A conversation does not end on a question the player cannot answer (#586).

A scenario's ending is decided after the NPC's reply, on the state that reply
produced, so the NPC never knew its line was the last one. When the session
ends on a line that asks the player something, the engine asks the model once
more for a short closing line with no question and adds it to the reply.
"""
from __future__ import annotations

import pytest

from convsim_prompt.layers import PREVIOUS_NPC_LINE_BEGIN
from tests.test_repetition_guard import (
    _ONE_EXCHANGE,
    _Hang,
    _Raw,
    _Replies,
    _Streamer,
    _kinds,
    _play,
    _stored_npc_line,
    _turn,
)

_ASKS = "Good. How would you approach a cross-region dependency like that?"
_STATES = "Good. That is exactly the kind of answer we look for."
_CLOSING = "Thank you, that is all I needed today. We will be in touch soon."


def _ending(line: str, ending_type: str = "success") -> dict:
    """A reply that ends the session, as the model may signal it."""
    return _turn(line, session_control={"continue_session": False, "ending_type": ending_type})


class TestWhenItIsAdded:
    @pytest.mark.asyncio
    async def test_an_ending_on_a_question_gets_a_closing_line(self):
        runtime = _Replies(_ending(_ASKS), _CLOSING)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)

        assert result.ending_type == "success"
        assert result.closing_line == _CLOSING
        assert result.npc_utterance == f"{_ASKS} {_CLOSING}"
        # The transcript the debrief reads holds the whole closing exchange.
        assert _stored_npc_line(conn) == f"{_ASKS} {_CLOSING}"
        assert "closing_line_added" in _kinds(conn)
        assert len(runtime.requests) == 2
        # Recorded as an extra call on the turn's timing.
        assert [c.kind for c in result.timing.extra_calls] == ["closing_line"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ending_type", ["failure", "timeout"])
    async def test_every_scenario_ending_is_closed(self, ending_type):
        runtime = _Replies(_ending(_ASKS, ending_type), _CLOSING)
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.ending_type == ending_type
        assert result.closing_line == _CLOSING

    @pytest.mark.asyncio
    async def test_an_ending_on_a_statement_costs_nothing(self):
        runtime = _Replies(_ending(_STATES))
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.ending_type == "success"
        assert result.closing_line is None
        assert result.npc_utterance == _STATES
        assert len(runtime.requests) == 1
        assert "closing_line_added" not in _kinds(conn)

    @pytest.mark.asyncio
    async def test_a_question_that_does_not_end_the_session_is_left_alone(self):
        runtime = _Replies(_ASKS)
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.ending_type is None
        assert result.closing_line is None
        assert len(runtime.requests) == 1


class TestTheRequest:
    @pytest.mark.asyncio
    async def test_same_system_prompt_with_the_line_quoted_and_the_instruction_last(self):
        runtime = _Replies(_ending(_ASKS), _CLOSING)
        await _play(runtime, *_ONE_EXCHANGE)
        first, closing = runtime.requests
        # The system prompt is the turn's own, so the prompt cache keeps it.
        assert closing.messages[0].content == first.messages[0].content
        assert closing.json_schema == first.json_schema
        user = closing.messages[1].content
        assert PREVIOUS_NPC_LINE_BEGIN in user
        assert f'"{_ASKS}"' in user
        assert "Do not ask a question" in user
        assert "close it warmly" in user
        assert user.rstrip().endswith("this is a simulation.")


class TestWhatIsKept:
    @pytest.mark.asyncio
    async def test_a_question_in_the_closing_line_is_dropped(self):
        runtime = _Replies(_ending(_ASKS), "Thanks for coming in. Any questions for me? Take care.")
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.closing_line == "Thanks for coming in. Take care."

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "closing, why",
        [
            ("Anything else you want to ask me?", "only a question"),
            (_Raw("not json at all"), "output check"),
            (RuntimeError("engine fell over"), "closing call failed"),
            (_ASKS, "repeated the reply"),
            ("Thanks. " * 60, "too long"),
        ],
    )
    async def test_a_bad_closing_line_leaves_the_reply_as_it_was(self, closing, why):
        runtime = _Replies(_ending(_ASKS), closing)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.ending_type == "success"
        assert result.closing_line is None
        assert result.npc_utterance == _ASKS
        assert "closing_line_skipped" in _kinds(conn)

    @pytest.mark.asyncio
    async def test_a_closing_call_that_never_answers_does_not_hold_the_session(self, monkeypatch):
        from convsim_core.services import turn_pipeline

        monkeypatch.setattr(turn_pipeline, "REPETITION_RETRY_MIN_TIMEOUT_S", 0.05)
        monkeypatch.setattr(turn_pipeline, "REPETITION_RETRY_TIMEOUT_FACTOR", 0.0)
        runtime = _Replies(_ending(_ASKS), _Hang)
        result, _ = await _play(runtime, *_ONE_EXCHANGE)
        assert result.ending_type == "success"
        assert result.closing_line is None


class TestStreamed:
    @pytest.mark.asyncio
    async def test_the_streamed_line_stands_and_the_closing_line_follows(self):
        streamer = _Streamer()
        runtime = _Replies(_ending(_ASKS), _CLOSING)
        result, conn = await _play(runtime, *_ONE_EXCHANGE, streamer=streamer)

        # What the player saw stream is the reply as written; the closing line
        # is what the response adds after it.
        assert streamer.finals == [_ASKS]
        assert result.streamed_line == _ASKS
        assert result.closing_line == _CLOSING
        assert _stored_npc_line(conn) == f"{_ASKS} {_CLOSING}"
