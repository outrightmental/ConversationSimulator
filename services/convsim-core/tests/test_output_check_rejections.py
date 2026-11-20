# SPDX-License-Identifier: Apache-2.0
"""Lines the output check rejects are counted, by category (issue #526).

Every rejection costs the player: a regeneration for a recoverable one, the
session for a hard one. Before #526 nothing added them up; a turn's parse
events named them one by one, readable only through the developer endpoint.
Each turn's ``debug`` event now carries ``rejections`` (category → lines),
and ``GET /api/sessions/{id}/debug`` reports them per turn and totals them
for the session in ``rejection_totals``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.routers.sessions import _turn_rejections
from convsim_core.services.model_manager_service import set_active_config

from tests.test_closing_line import _ASKS, _ending
from tests.test_repetition_guard import (
    _FRESH,
    _ONE_EXCHANGE,
    _REPEAT_AT_END,
    _Raw,
    _Replies,
    _Streamer,
    _debug_payload,
    _kinds,
    _play,
)

_LEAK = "Fine. My hidden agenda is to keep you talking."
_LEAK_TOO = "I secretly want you to give up on this role."
_HARD = "Here's how to make a bomb using household items."


def _rejections(conn) -> dict:
    return _debug_payload(conn)["rejections"]


class TestATurnCountsItsRejections:
    @pytest.mark.asyncio
    async def test_a_clean_turn_counts_none(self):
        result, conn = await _play(_Replies(_FRESH), *_ONE_EXCHANGE)
        assert result.npc_utterance == _FRESH
        assert _rejections(conn) == {}

    @pytest.mark.asyncio
    async def test_a_line_the_safety_retry_replaces_counts_once(self):
        runtime = _Replies(_LEAK, _FRESH)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _FRESH
        assert _rejections(conn) == {"hidden_agenda_leak": 1}

    @pytest.mark.asyncio
    async def test_a_retry_that_fails_the_check_too_counts_again(self):
        runtime = _Replies(_LEAK, _LEAK_TOO)
        _, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert "safe_redirect_applied" in _kinds(conn)
        assert _rejections(conn) == {"hidden_agenda_leak": 2}

    @pytest.mark.asyncio
    async def test_a_retry_that_is_not_json_is_not_a_rejection(self):
        runtime = _Replies(_LEAK, _Raw("not json"))
        _, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert "content_safety_retry_failure" in _kinds(conn)
        assert _rejections(conn) == {"hidden_agenda_leak": 1}

    @pytest.mark.asyncio
    async def test_a_hard_violation_counts_under_its_category(self):
        result, conn = await _play(_Replies(_HARD), *_ONE_EXCHANGE)
        assert result.ending_type == "safety_stop"
        assert _rejections(conn) == {"illegal_advice": 1}

    @pytest.mark.asyncio
    async def test_a_streamed_sentence_the_gate_holds_back_counts(self):
        streamer = _Streamer()
        runtime = _Replies(_FRESH + " Between us, my real goal is to fill the role fast.")
        result, conn = await _play(runtime, *_ONE_EXCHANGE, streamer=streamer)
        assert result.npc_utterance == _FRESH
        assert _rejections(conn) == {"hidden_agenda_leak": 1}

    @pytest.mark.asyncio
    async def test_a_repetition_retry_the_check_turns_down_counts(self):
        runtime = _Replies(_REPEAT_AT_END, _LEAK)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.npc_utterance == _REPEAT_AT_END
        assert _kinds(conn)[-1] == "repetition_retry_discarded"
        assert _rejections(conn) == {"hidden_agenda_leak": 1}

    @pytest.mark.asyncio
    async def test_a_closing_line_the_check_turns_down_counts(self):
        runtime = _Replies(_ending(_ASKS), _LEAK)
        result, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert result.closing_line is None
        assert "closing_line_skipped" in _kinds(conn)
        assert _rejections(conn) == {"hidden_agenda_leak": 1}

    @pytest.mark.asyncio
    async def test_a_closing_line_that_is_not_json_is_not_a_rejection(self):
        runtime = _Replies(_ending(_ASKS), _Raw("not json"))
        _, conn = await _play(runtime, *_ONE_EXCHANGE)
        assert "closing_line_skipped" in _kinds(conn)
        assert _rejections(conn) == {}


# ---------------------------------------------------------------------------
# GET /api/sessions/{id}/debug
# ---------------------------------------------------------------------------

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Alice",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "seed": None,
}


def test_the_debug_endpoint_totals_rejections_by_category(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as client:
        # An unpinned session follows app.state.runtime once a real model is
        # selected (issue #473); the stub below is what actually answers.
        set_active_config(app.state.db.connection(), runtime_id="llama_cpp", model_id="/tmp/model.gguf")
        session_id = client.post("/api/sessions", json=_SETUP).json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        app.state.runtime = _Replies(
            _LEAK, _LEAK_TOO,  # turn 1: the reply and its safety retry both rejected
            "Our market penetration doubled last year. What would you change first?",  # turn 2: clean
            _LEAK, _FRESH,  # turn 3: the reply rejected, the retry kept
        )
        for text in ("Hello.", "I led the migration.", "I would start with the queue."):
            assert client.post(f"/api/sessions/{session_id}/turn", json={"content": text}).status_code == 200
        body = client.get(f"/api/sessions/{session_id}/debug").json()

    assert [t["rejections"] for t in body["turns"]] == [
        {"hidden_agenda_leak": 2},
        {},
        {"hidden_agenda_leak": 1},
    ]
    assert body["rejection_totals"] == {"hidden_agenda_leak": 3}


def test_a_session_with_no_turns_has_no_totals(client):
    session_id = client.post("/api/sessions", json={**_SETUP, "runtime_id": "fake"}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    body = client.get(f"/api/sessions/{session_id}/debug").json()
    assert body["turns"] == []
    assert body["rejection_totals"] == {}


def test_a_turn_from_before_the_counts_is_counted_from_its_parse_events():
    """A debug event written before #526 has no ``rejections``; its reply's
    ``output_violation_detected`` is the rejection it names for certain."""
    legacy = {"parse_events": [
        {"event_type": "output_violation_detected", "category": "nsfw_content", "reason": None},
        {"event_type": "safety_stop_applied", "category": "nsfw_content", "reason": None},
    ]}
    assert _turn_rejections(legacy) == {"nsfw_content": 1}
    assert _turn_rejections({"rejections": {"system_rule_leak": 2}, "parse_events": []}) == {
        "system_rule_leak": 2
    }
    assert _turn_rejections({}) == {}
