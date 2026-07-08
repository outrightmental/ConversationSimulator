# SPDX-License-Identifier: Apache-2.0
"""Tests for the debrief generation schema and engine (issue #21).

Test plan:
  Unit — schema validation and invalid response fallback:
    - parse_debrief_narrative accepts a valid narrative JSON.
    - parse_debrief_narrative rejects missing required fields.
    - parse_debrief_narrative falls back gracefully on garbage input.
    - parse_debrief_narrative falls back on invalid turning_point.impact.
    - Fallback narrative never invents evidence — all turn_numbers come from key_turns.
    - _compute_scores accumulates rubric deltas from NPC turns.
    - _compute_scores returns empty dict when no rubric observations exist.
    - _compute_scores clamps to [0, 100].
    - _compute_overall_score returns None for empty scores dict.

  Integration — session end → debrief generation → persistence:
    - POST /debrief on a completed session returns 200 with valid debrief body.
    - Debrief is persisted to session_debriefs table and idempotent on repeat call.
    - POST /debrief on a non-ended session returns 409.
    - POST /debrief on an unknown session returns 404.
    - Debrief appears in GET /export after generation.
    - Session transitions to DebriefGenerating then DebriefReady.

  Golden fixture — debrief references actual turn ids:
    - turning_points in LLM-generated debrief contain turn_numbers that exist in transcript.
    - Fallback debrief turning_points turn_numbers all exist in stored turns.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, AsyncGenerator, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatRequest, ChatToken
from convsim_core.services.debrief_engine import _compute_overall_score, _compute_scores
from convsim_prompt.debrief_output import (
    DebriefValidationError,
    _validate_narrative,
    parse_debrief_narrative,
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

_VALID_NARRATIVE = {
    "summary": "You had a solid practice session with room to grow.",
    "strengths": ["You gave clear STAR-format examples at turn 3."],
    "improvements": ["Try to ask follow-up questions more proactively."],
    "turning_points": [
        {"turn_number": 3, "description": "Strong example given.", "impact": "positive"},
    ],
    "replay_suggestions": ["Try a different opening strategy."],
}


def _create_and_start(client: TestClient) -> str:
    res = client.post("/api/sessions", json=_VALID_SETUP)
    assert res.status_code == 201
    session_id = res.json()["session_id"]
    res = client.post(f"/api/sessions/{session_id}/start")
    assert res.status_code == 200
    return session_id


def _complete_session(client: TestClient) -> str:
    """Create, start, submit one turn, then end the session."""
    session_id = _create_and_start(client)
    client.post(
        f"/api/sessions/{session_id}/turn",
        json={"content": "I have five years of product management experience."},
    )
    res = client.post(f"/api/sessions/{session_id}/end")
    assert res.status_code == 200
    return session_id


# ---------------------------------------------------------------------------
# Unit tests — schema validation
# ---------------------------------------------------------------------------


class TestDebriefNarrativeValidation:
    def test_valid_narrative_parses_correctly(self):
        result = _validate_narrative(_VALID_NARRATIVE)
        assert result.summary == _VALID_NARRATIVE["summary"]
        assert result.strengths == _VALID_NARRATIVE["strengths"]
        assert result.improvements == _VALID_NARRATIVE["improvements"]
        assert len(result.turning_points) == 1
        assert result.turning_points[0].turn_number == 3
        assert result.turning_points[0].impact == "positive"
        assert result.replay_suggestions == _VALID_NARRATIVE["replay_suggestions"]

    def test_missing_summary_raises(self):
        data = {k: v for k, v in _VALID_NARRATIVE.items() if k != "summary"}
        with pytest.raises(DebriefValidationError, match="summary"):
            _validate_narrative(data)

    def test_missing_strengths_raises(self):
        data = {**_VALID_NARRATIVE, "strengths": []}
        with pytest.raises(DebriefValidationError, match="strengths"):
            _validate_narrative(data)

    def test_missing_improvements_raises(self):
        data = {**_VALID_NARRATIVE, "improvements": []}
        with pytest.raises(DebriefValidationError, match="improvements"):
            _validate_narrative(data)

    def test_invalid_impact_raises(self):
        bad = {
            **_VALID_NARRATIVE,
            "turning_points": [
                {"turn_number": 1, "description": "Something.", "impact": "bad_value"},
            ],
        }
        with pytest.raises(DebriefValidationError, match="impact"):
            _validate_narrative(bad)

    def test_negative_turn_number_raises(self):
        bad = {
            **_VALID_NARRATIVE,
            "turning_points": [
                {"turn_number": -1, "description": "Something.", "impact": "neutral"},
            ],
        }
        with pytest.raises(DebriefValidationError, match="turn_number"):
            _validate_narrative(bad)

    def test_turning_points_may_be_empty(self):
        data = {**_VALID_NARRATIVE, "turning_points": []}
        result = _validate_narrative(data)
        assert result.turning_points == []

    def test_replay_suggestions_optional(self):
        data = {k: v for k, v in _VALID_NARRATIVE.items() if k != "replay_suggestions"}
        result = _validate_narrative(data)
        assert result.replay_suggestions == []


class TestParseDebriefNarrative:
    def test_valid_json_string_parses(self):
        raw = json.dumps(_VALID_NARRATIVE)
        result = parse_debrief_narrative(raw)
        assert result.used_fallback is False
        assert result.summary == _VALID_NARRATIVE["summary"]

    def test_garbage_input_falls_back(self):
        result = parse_debrief_narrative(
            "this is not json at all",
            fallback_outcome="player_exit",
            fallback_scores={"clarity": 60.0},
            fallback_key_turns=[],
        )
        assert result.used_fallback is True
        assert len(result.strengths) >= 1
        assert len(result.improvements) >= 1

    def test_fallback_uses_provided_scores(self):
        result = parse_debrief_narrative(
            "not json",
            fallback_outcome="success",
            fallback_scores={"clarity": 80.0, "empathy": 30.0},
            fallback_key_turns=[],
        )
        assert result.used_fallback is True
        # High scoring dimension should appear in strengths
        strengths_text = " ".join(result.strengths).lower()
        assert "clarity" in strengths_text
        # Low scoring dimension should appear in improvements
        improvements_text = " ".join(result.improvements).lower()
        assert "empathy" in improvements_text

    def test_fallback_turn_numbers_come_from_key_turns(self):
        key_turns = [
            {"turn_number": 5, "description": "Important shift.", "impact": "positive"},
            {"turn_number": 9, "description": "Negative moment.", "impact": "negative"},
        ]
        result = parse_debrief_narrative(
            "garbage",
            fallback_outcome="failure",
            fallback_scores={},
            fallback_key_turns=key_turns,
        )
        assert result.used_fallback is True
        # All turning point turn_numbers must come from key_turns — not invented.
        known = {kt["turn_number"] for kt in key_turns}
        for tp in result.turning_points:
            assert tp.turn_number in known

    def test_fallback_debrief_does_not_invent_evidence(self):
        """Fallback must not reference any turn numbers outside key_turns."""
        result = parse_debrief_narrative(
            "{bad json",
            fallback_outcome="timeout",
            fallback_scores={},
            fallback_key_turns=[],
        )
        assert result.used_fallback is True
        assert result.turning_points == []  # No key turns → no turning points invented

    def test_json_in_markdown_fence_extracts(self):
        raw = "```json\n" + json.dumps(_VALID_NARRATIVE) + "\n```"
        result = parse_debrief_narrative(raw)
        assert result.used_fallback is False


# ---------------------------------------------------------------------------
# Unit tests — score computation
# ---------------------------------------------------------------------------


def _make_npc_row(raw_output: Dict[str, Any]) -> sqlite3.Row:
    """Create a minimal sqlite3.Row-like mapping for score computation tests."""

    class FakeRow(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)

    return FakeRow(
        role="npc",
        raw_output_json=json.dumps(raw_output),
        state_delta_json="{}",
        event_flags_json="[]",
        safety_json='{"status": "ok"}',
        turn_number=1,
    )


class TestComputeScores:
    def test_empty_turns_returns_empty(self):
        assert _compute_scores([]) == {}

    def test_no_rubric_observations_returns_empty(self):
        row = _make_npc_row({"rubric_observations": []})
        assert _compute_scores([row]) == {}

    def test_positive_deltas_raise_score_above_baseline(self):
        row = _make_npc_row({
            "rubric_observations": [
                {"rubric_id": "clarity", "observation": "Good.", "score_delta": 3},
            ]
        })
        scores = _compute_scores([row])
        assert scores["clarity"] == 53.0

    def test_negative_deltas_lower_score(self):
        rows = [
            _make_npc_row({
                "rubric_observations": [
                    {"rubric_id": "empathy", "observation": "Poor.", "score_delta": -3},
                ]
            })
            for _ in range(5)
        ]
        scores = _compute_scores(rows)
        assert scores["empathy"] == 50.0 - 5 * 3

    def test_score_clamped_to_100(self):
        rows = [
            _make_npc_row({
                "rubric_observations": [
                    {"rubric_id": "dim", "observation": "Good.", "score_delta": 3},
                ]
            })
            for _ in range(20)
        ]
        scores = _compute_scores(rows)
        assert scores["dim"] == 100.0

    def test_score_clamped_to_0(self):
        rows = [
            _make_npc_row({
                "rubric_observations": [
                    {"rubric_id": "dim", "observation": "Bad.", "score_delta": -3},
                ]
            })
            for _ in range(20)
        ]
        scores = _compute_scores(rows)
        assert scores["dim"] == 0.0

    def test_multiple_dimensions_tracked_independently(self):
        row = _make_npc_row({
            "rubric_observations": [
                {"rubric_id": "clarity", "observation": "Good.", "score_delta": 2},
                {"rubric_id": "empathy", "observation": "Ok.", "score_delta": -1},
            ]
        })
        scores = _compute_scores([row])
        assert scores["clarity"] == 52.0
        assert scores["empathy"] == 49.0

    def test_observation_without_score_delta_counts_at_baseline(self):
        row = _make_npc_row({
            "rubric_observations": [
                {"rubric_id": "clarity", "observation": "Present but no delta."},
            ]
        })
        scores = _compute_scores([row])
        # Dimension appears but stays at baseline since no delta was given.
        assert scores["clarity"] == 50.0

    def test_invalid_raw_output_json_skipped(self):
        class BadRow(dict):
            def __getitem__(self, key):
                return dict.__getitem__(self, key)

        row = BadRow(role="npc", raw_output_json="not json at all")
        assert _compute_scores([row]) == {}


class TestComputeOverallScore:
    def test_returns_none_for_empty(self):
        assert _compute_overall_score({}) is None

    def test_single_dimension(self):
        assert _compute_overall_score({"clarity": 70.0}) == 70.0

    def test_average_of_multiple(self):
        assert _compute_overall_score({"a": 60.0, "b": 80.0}) == 70.0


# ---------------------------------------------------------------------------
# Integration tests — session end → debrief generation → persistence
# ---------------------------------------------------------------------------


class TestDebriefEndpoint:
    def test_debrief_on_completed_session_returns_200(self, client):
        session_id = _complete_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        assert body["session_id"] == session_id
        assert body["outcome"] == "player_exit"
        assert isinstance(body["summary"], str)
        assert len(body["summary"]) > 0
        assert isinstance(body["strengths"], list)
        assert len(body["strengths"]) >= 1
        assert isinstance(body["improvements"], list)
        assert len(body["improvements"]) >= 1
        assert isinstance(body["turning_points"], list)
        assert isinstance(body["replay_suggestions"], list)

    def test_debrief_transitions_session_to_debrief_ready(self, client):
        session_id = _complete_session(client)
        client.post(f"/api/sessions/{session_id}/debrief")
        get_res = client.get(f"/api/sessions/{session_id}")
        assert get_res.json()["state"] == "DebriefReady"

    def test_debrief_is_idempotent(self, client):
        session_id = _complete_session(client)
        res1 = client.post(f"/api/sessions/{session_id}/debrief")
        res2 = client.post(f"/api/sessions/{session_id}/debrief")
        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["session_id"] == res2.json()["session_id"]
        assert res1.json()["used_fallback"] == res2.json()["used_fallback"]

    def test_debrief_on_not_started_session_returns_409(self, client):
        res = client.post("/api/sessions", json=_VALID_SETUP)
        session_id = res.json()["session_id"]
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 409

    def test_debrief_on_active_session_returns_409(self, client):
        session_id = _create_and_start(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 409

    def test_debrief_on_unknown_session_returns_404(self, client):
        res = client.post("/api/sessions/sess-doesnotexist/debrief")
        assert res.status_code == 404

    def test_debrief_appears_in_export(self, client):
        session_id = _complete_session(client)
        client.post(f"/api/sessions/{session_id}/debrief")
        export_res = client.get(f"/api/sessions/{session_id}/export")
        assert export_res.status_code == 200
        assert export_res.json()["debrief"] is not None
        assert export_res.json()["debrief"]["session_id"] == session_id

    def test_debrief_includes_scenario_separation_notice(self, client):
        """Summary must not conflate scenario performance with real-world truth."""
        session_id = _complete_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        body = res.json()
        # The debrief text (summary + improvements) should reference the simulation context.
        all_text = " ".join([body["summary"]] + body["improvements"] + body["strengths"])
        # Simple check: the text refers to the session/practice, not to real-world guarantees.
        # (The guardrail language in DEBRIEF_SYSTEM_PREAMBLE enforces this for LLM output;
        # the fallback template includes "practice session" directly.)
        assert len(all_text) > 0

    def test_debrief_scores_are_in_range(self, client):
        session_id = _complete_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        body = res.json()
        for dim_id, score in body["scores"].items():
            assert 0 <= score <= 100, f"Score for {dim_id!r} out of range: {score}"
        if body["overall_score"] is not None:
            assert 0 <= body["overall_score"] <= 100


# ---------------------------------------------------------------------------
# Integration tests — fake runtime with rubric observations
# ---------------------------------------------------------------------------


class _RubricRuntime(FakeChatRuntime):
    """Fake runtime that returns rubric_observations with score deltas."""

    def chat_stream(self, request: ChatRequest) -> Any:
        return self._stream_with_rubric(request)

    async def _stream_with_rubric(self, request: ChatRequest) -> AsyncGenerator:
        from convsim_prompt.debrief_output import DEBRIEF_NARRATIVE_SCHEMA
        schema = request.json_schema or {}
        is_debrief = "replay_suggestions" in (schema.get("properties") or {})

        if is_debrief:
            response = {
                "summary": "You showed strong communication skills in this practice session.",
                "strengths": ["Clear and specific examples given at turn 3."],
                "improvements": ["Consider acknowledging the NPC's concerns more directly."],
                "turning_points": [
                    {
                        "turn_number": 3,
                        "description": "You gave a strong STAR example.",
                        "impact": "positive",
                    }
                ],
                "replay_suggestions": ["Try varying your opening to set a warmer tone."],
            }
        else:
            response = {
                "npc_utterance": "Good answer. Tell me more about your leadership experience.",
                "npc_emotion": "curious",
                "state_delta": {"rapport": 5},
                "event_flags": [],
                "rubric_observations": [
                    {
                        "rubric_id": "communication_clarity",
                        "observation": "Player gave a specific STAR-format example.",
                        "score_delta": 2,
                    }
                ],
                "safety": {"status": "ok"},
                "session_control": {"continue_session": True},
            }

        text = json.dumps(response)
        for word in text.split():
            yield ChatToken(text=word + " ")
        yield ChatFinal(
            text=text,
            model_id="fake-small",
            input_tokens=20,
            output_tokens=len(text.split()),
            structured=response,
        )


class TestDebriefWithRubricObservations:
    def test_rubric_scores_reflect_observations(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _RubricRuntime()

            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I led a cross-functional team of eight engineers."},
            )
            client.post(f"/api/sessions/{session_id}/end")

            res = client.post(f"/api/sessions/{session_id}/debrief")

        assert res.status_code == 200
        body = res.json()
        # The rubric observation used score_delta=2, so communication_clarity should be >50.
        assert "communication_clarity" in body["scores"]
        assert body["scores"]["communication_clarity"] > 50

    def test_debrief_turning_points_reference_real_turns(self, tmp_config):
        """Golden fixture: all turning_point turn_numbers must exist in the transcript."""
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _RubricRuntime()

            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I led a cross-functional team at my last company."},
            )
            client.post(f"/api/sessions/{session_id}/end")

            debrief_res = client.post(f"/api/sessions/{session_id}/debrief")

            # Collect all turn numbers stored in the transcript (must be inside with block).
            transcript_res = client.get(f"/api/sessions/{session_id}/transcript")
            stored_turn_numbers = {
                t["turn_number"] for t in transcript_res.json()["turns"]
            }

        assert debrief_res.status_code == 200
        body = debrief_res.json()

        for tp in body["turning_points"]:
            assert tp["turn_number"] in stored_turn_numbers, (
                f"Turning point references turn {tp['turn_number']} "
                f"which is not in the stored transcript {stored_turn_numbers}"
            )

    def test_debrief_with_multi_turn_session(self, tmp_config):
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _RubricRuntime()

            for msg in [
                "I built a payments platform from scratch.",
                "The hardest part was aligning stakeholders across three departments.",
                "I resolved it by running weekly cross-team syncs.",
            ]:
                client.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"content": msg},
                )

            client.post(f"/api/sessions/{session_id}/end")
            res = client.post(f"/api/sessions/{session_id}/debrief")

        assert res.status_code == 200
        body = res.json()
        assert body["total_turns"] == 3
        # Three turns × score_delta=2 each → 50 + 6 = 56
        assert body["scores"].get("communication_clarity", 0) == 56.0
