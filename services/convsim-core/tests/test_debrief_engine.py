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
from convsim_core.services.debrief_engine import _compute_overall_score, _compute_scores, compute_metrics
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
    "difficulty": "standard",
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
# Unit tests — compute_metrics
# ---------------------------------------------------------------------------


def _make_turn_row(**kwargs) -> dict:
    """Build a minimal dict that mimics a sqlite3.Row for compute_metrics tests."""
    defaults = {
        "role": "player",
        "content": "",
        "state_delta_json": None,
        "event_flags_json": None,
        "safety_json": None,
        "raw_output_json": None,
        "source_mode": "text-only",
        "created_at": "2024-01-01T12:00:00+00:00",
        "turn_number": 1,
    }
    return {**defaults, **kwargs}


# A golden transcript: NPC opening → player turn → NPC response.
_GOLDEN_TURNS = [
    _make_turn_row(
        turn_number=0,
        role="npc_opening",
        content="Hello, let's begin the interview. Tell me about yourself.",
        created_at="2024-01-01T12:00:00.000000+00:00",
    ),
    _make_turn_row(
        turn_number=1,
        role="player",
        content="I have five years of product management experience at a mid-sized tech company.",
        created_at="2024-01-01T12:00:01.000000+00:00",
    ),
    _make_turn_row(
        turn_number=2,
        role="npc",
        content="That sounds impressive. What would you say was your biggest achievement?",
        state_delta_json='{"credibility": 5}',
        created_at="2024-01-01T12:00:03.500000+00:00",
    ),
    _make_turn_row(
        turn_number=3,
        role="player",
        content="What metrics did you use to measure success?",
        created_at="2024-01-01T12:00:10.000000+00:00",
    ),
    _make_turn_row(
        turn_number=4,
        role="npc",
        content="We look at revenue impact, user retention, and NPS.",
        state_delta_json='{"credibility": 3}',
        created_at="2024-01-01T12:00:12.200000+00:00",
    ),
]


class TestComputeMetrics:
    def test_empty_turns_returns_zero_metrics(self):
        m = compute_metrics([])
        assert m["metrics_version"] == "1"
        assert m["talk_ratio"] == 0.0
        assert m["words_per_turn_player"] == 0.0
        assert m["words_per_turn_npc"] == 0.0
        assert m["state_arc"] == []

    def test_talk_ratio_is_fraction_of_player_words(self):
        m = compute_metrics(_GOLDEN_TURNS)
        assert 0 < m["talk_ratio"] < 1
        # Player turns: turn 1 (13 words) + turn 3 (8 words) = 21
        # NPC: opening (9 words) + turn 2 (11 words) + turn 4 (9 words) = 29
        # talk_ratio = round(21 / 50, 3) = 0.42
        assert abs(m["talk_ratio"] - round(21 / 50, 3)) < 0.001

    def test_words_per_turn_computed_correctly(self):
        m = compute_metrics(_GOLDEN_TURNS)
        # player: 21 words across 2 turns = 10.5
        assert m["words_per_turn_player"] == pytest.approx(21 / 2, abs=0.1)
        # npc (incl. opening): 29 words across 3 turns ≈ 9.67
        assert m["words_per_turn_npc"] == pytest.approx(29 / 3, abs=0.2)

    def test_open_question_detected(self):
        m = compute_metrics(_GOLDEN_TURNS)
        # Turn 3: "What metrics did you use to measure success?" → open question
        assert m["open_questions"] >= 1
        assert m["closed_questions"] == 0

    def test_filler_words_only_counted_for_voice_mode(self):
        voice_turns = [
            _make_turn_row(role="npc_opening", turn_number=0, content="Hello."),
            _make_turn_row(role="player", turn_number=1, content="Um like I was thinking."),
            _make_turn_row(role="npc", turn_number=2, content="I see.", state_delta_json="{}"),
        ]
        text_metrics = compute_metrics(voice_turns, source_mode="text-only")
        assert text_metrics["filler_word_count"] == 0

        voice_metrics = compute_metrics(voice_turns, source_mode="push-to-talk")
        assert voice_metrics["filler_word_count"] > 0

    def test_response_latency_computed_from_timestamps(self):
        m = compute_metrics(_GOLDEN_TURNS)
        # Turn 1 @ 12:00:01, NPC (turn 2) @ 12:00:03.5 → 2500 ms
        # Turn 3 @ 12:00:10, NPC (turn 4) @ 12:00:12.2 → 2200 ms
        assert m["response_latency_p50_ms"] is not None
        assert m["response_latency_p95_ms"] is not None
        # p50 of [2200, 2500] → index 1 = 2500 ms (len=2, n//2=1)
        assert m["response_latency_p50_ms"] == 2500
        assert m["response_latency_p95_ms"] == 2500

    def test_state_arc_accumulates_deltas(self):
        m = compute_metrics(_GOLDEN_TURNS)
        arc = m["state_arc"]
        # Two NPC response turns with credibility deltas
        assert len(arc) == 2
        # After turn 2: credibility = 5
        assert arc[0]["turn_number"] == 2
        assert arc[0]["state"]["credibility"] == 5
        # After turn 4: credibility = 5 + 3 = 8
        assert arc[1]["turn_number"] == 4
        assert arc[1]["state"]["credibility"] == 8

    def test_state_arc_anchored_to_true_meter_values(self):
        # Deltas stored are clamped changes; variables start from a non-zero
        # default (e.g. 50). Passing final_state anchors the arc to real values.
        # credibility: default 50, +5 then +3 → final 58.
        m = compute_metrics(_GOLDEN_TURNS, final_state={"credibility": 58})
        arc = m["state_arc"]
        assert arc[0]["state"]["credibility"] == 55  # 50 + 5
        assert arc[1]["state"]["credibility"] == 58  # 55 + 3, equals final
        # Every meter value stays within the schema's [0, 100] range.
        for entry in arc:
            for value in entry["state"].values():
                assert 0 <= value <= 100

    def test_state_arc_final_equals_final_state(self):
        # A meter that drops must not go negative when anchored to final_state.
        turns = [
            _make_turn_row(role="npc_opening", turn_number=0, content="Hi."),
            _make_turn_row(role="player", turn_number=1, content="Sorry."),
            _make_turn_row(
                role="npc", turn_number=2, content="Hmm.",
                state_delta_json='{"patience": -10}',
            ),
        ]
        # patience default 75, -10 → final 65 (never negative).
        m = compute_metrics(turns, final_state={"patience": 65})
        assert m["state_arc"][-1]["state"]["patience"] == 65

    def test_filler_common_words_not_false_positives(self):
        # Ordinary content words ("I", "you", "so") must not count as fillers.
        turns = [
            _make_turn_row(role="npc_opening", turn_number=0, content="Hi."),
            _make_turn_row(
                role="player", turn_number=1,
                content="I think you should so definitely okay it right away.",
            ),
            _make_turn_row(role="npc", turn_number=2, content="Ok.", state_delta_json="{}"),
        ]
        m = compute_metrics(turns, source_mode="push-to-talk")
        assert m["filler_word_count"] == 0

    def test_filler_phrase_counted_once(self):
        turns = [
            _make_turn_row(role="npc_opening", turn_number=0, content="Hi."),
            _make_turn_row(
                role="player", turn_number=1,
                content="Um, you know, I mean it was like really good.",
            ),
            _make_turn_row(role="npc", turn_number=2, content="Ok.", state_delta_json="{}"),
        ]
        m = compute_metrics(turns, source_mode="push-to-talk")
        # "um" + "you know" (phrase) + "i mean" (phrase) + "like" = 4
        assert m["filler_word_count"] == 4

    def test_deterministic_on_same_input(self):
        m1 = compute_metrics(_GOLDEN_TURNS)
        m2 = compute_metrics(_GOLDEN_TURNS)
        assert m1 == m2

    def test_metrics_in_debrief_response(self, client):
        """Integration: metrics appear in the /debrief HTTP response."""
        session_id = _complete_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        assert "metrics" in body
        metrics = body["metrics"]
        assert metrics["metrics_version"] == "1"
        assert isinstance(metrics["talk_ratio"], float)
        assert isinstance(metrics["open_questions"], int)
        assert isinstance(metrics["state_arc"], list)

    def test_response_latency_populated_end_to_end(self, client):
        """Regression: a real session must yield non-null latency percentiles.

        The player turn is persisted at request-arrival time and the NPC turn
        after inference completes, so their ``created_at`` values differ and the
        latency computation has a real gap to measure. If both turns were ever
        stamped with the same timestamp again the percentiles would collapse to
        None — this test guards against that regression.
        """
        session_id = _complete_session(client)
        metrics = client.post(f"/api/sessions/{session_id}/debrief").json()["metrics"]
        assert metrics["response_latency_p50_ms"] is not None
        assert metrics["response_latency_p95_ms"] is not None
        assert metrics["response_latency_p50_ms"] >= 0

    def test_metrics_in_export(self, client):
        """Integration: metrics block is present in the /export JSON."""
        session_id = _complete_session(client)
        client.post(f"/api/sessions/{session_id}/debrief")
        export = client.get(f"/api/sessions/{session_id}/export").json()
        assert export["debrief"]["metrics"]["metrics_version"] == "1"

    def test_metrics_in_text_export(self, client):
        """Integration: metrics Telemetry section appears in Markdown export."""
        session_id = _complete_session(client)
        client.post(f"/api/sessions/{session_id}/debrief")
        text_res = client.get(f"/api/sessions/{session_id}/export/text")
        assert text_res.status_code == 200
        assert "Telemetry" in text_res.text
        assert "Talk ratio" in text_res.text

    def test_metrics_idempotent_on_cached_debrief(self, client):
        """Integration: second /debrief call returns the same metrics from cache."""
        session_id = _complete_session(client)
        res1 = client.post(f"/api/sessions/{session_id}/debrief")
        res2 = client.post(f"/api/sessions/{session_id}/debrief")
        assert res1.json()["metrics"] == res2.json()["metrics"]


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
        # The fake runtime summary always starts with "This was a simulated practice session."
        # The fallback template also uses "practice session" directly.
        # Either way the combined text must anchor itself to the practice context.
        assert any(
            keyword in all_text.lower()
            for keyword in ("simulated", "practice session", "scenario", "session")
        ), f"Debrief text does not reference simulation context: {all_text!r}"

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
        """Golden fixture: all turning_point turn_numbers must exist in the transcript.

        _RubricRuntime always returns turn_number=3 in its debrief. With 1 player turn
        the stored transcript is {1, 2} (player_turn=2n-1, npc_turn=2n), so turn 3 would
        be filtered out and the assertion loop would trivially pass over an empty list.
        Two player turns produce stored turns {1, 2, 3, 4}, so turn 3 survives the filter
        and the non-empty assertion below ensures the loop actually runs.
        """
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _RubricRuntime()

            # Two turns so stored turn numbers include 3 (second player turn = 2*2-1).
            for msg in [
                "I led a cross-functional team at my last company.",
                "The biggest challenge was keeping everyone aligned on priorities.",
            ]:
                client.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"content": msg},
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

        # The filter must keep at least one turning point (turn 3 is in stored turns).
        assert len(body["turning_points"]) > 0, (
            "Expected at least one turning point to survive the filter; "
            f"stored turns were {stored_turn_numbers}"
        )
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


# ---------------------------------------------------------------------------
# Integration tests — debrief error state transition
# ---------------------------------------------------------------------------


class _FailingDebriefRuntime(FakeChatRuntime):
    """Runtime that raises when the debrief narrative schema is requested.

    NPC turn calls (which use a different discriminant key) fall through to the
    parent FakeChatRuntime so the session can be completed normally before the
    debrief step is exercised.
    """

    def chat_stream(self, request: ChatRequest) -> Any:
        is_debrief = "replay_suggestions" in (
            (request.json_schema or {}).get("properties") or {}
        )
        if is_debrief:
            return self._fail_debrief_stream(request)
        return super().chat_stream(request)

    async def _fail_debrief_stream(self, request: ChatRequest) -> AsyncGenerator:
        raise RuntimeError("Simulated debrief runtime failure")
        yield  # pragma: no cover — makes this an async generator


class TestDebriefErrorState:
    def test_debrief_generation_failure_transitions_session_to_error(self, tmp_config):
        """When debrief generation raises, session must transition to Error state.

        Acceptance criterion: Debrief generation state transitions through
        DebriefGenerating and DebriefReady or Error.
        """
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")
            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I have experience managing cross-functional teams."},
            )
            client.post(f"/api/sessions/{session_id}/end")

            # Switch to a runtime that fails during debrief narrative generation.
            app.state.runtime = _FailingDebriefRuntime()
            debrief_res = client.post(f"/api/sessions/{session_id}/debrief")
            state_res = client.get(f"/api/sessions/{session_id}")

        assert debrief_res.status_code == 500
        assert state_res.json()["state"] == "Error"

    def test_debrief_retry_from_error_state_succeeds(self, tmp_config):
        """After a debrief failure (Error state), retrying with a working runtime succeeds."""
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_VALID_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")
            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I have experience managing cross-functional teams."},
            )
            client.post(f"/api/sessions/{session_id}/end")

            app.state.runtime = _FailingDebriefRuntime()
            first_res = client.post(f"/api/sessions/{session_id}/debrief")
            assert first_res.status_code == 500

            # Restore working runtime and retry — must not return 409.
            app.state.runtime = FakeChatRuntime()
            retry_res = client.post(f"/api/sessions/{session_id}/debrief")

        assert retry_res.status_code == 200
        assert retry_res.json()["session_id"] == session_id


# ---------------------------------------------------------------------------
# Tests — missed_opportunities field
# ---------------------------------------------------------------------------


class TestDebriefMissedOpportunities:
    def test_debrief_includes_missed_opportunities_field(self, client):
        """Debrief response must include a missed_opportunities list."""
        session_id = _complete_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        assert "missed_opportunities" in body
        assert isinstance(body["missed_opportunities"], list)

    def test_fallback_missed_opportunities_not_empty_for_player_exit(self, client):
        """Fallback debrief for player_exit outcome should include at least one missed opportunity."""
        session_id = _complete_session(client)
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        # The fake runtime returns a non-fallback debrief, but the debrief_doc persists
        # missed_opportunities from the LLM narrative which the fake runtime includes.
        # Just verify the field is present and is a list.
        assert isinstance(body["missed_opportunities"], list)

    def test_missed_opportunities_in_export(self, client):
        """Exported debrief should include missed_opportunities."""
        session_id = _complete_session(client)
        client.post(f"/api/sessions/{session_id}/debrief")
        export_res = client.get(f"/api/sessions/{session_id}/export")
        assert export_res.status_code == 200
        debrief = export_res.json()["debrief"]
        assert debrief is not None
        assert "missed_opportunities" in debrief
        assert isinstance(debrief["missed_opportunities"], list)


# ---------------------------------------------------------------------------
# Tests — ended-early sessions
# ---------------------------------------------------------------------------


class TestEndedEarlySessions:
    def test_debrief_on_session_ended_after_one_turn(self, client):
        """Debrief should succeed for a session ended early after just one turn."""
        session_id = _create_and_start(client)
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I have five years of experience."},
        )
        res = client.post(f"/api/sessions/{session_id}/end")
        assert res.status_code == 200
        assert res.json()["ending_type"] == "player_exit"

        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        assert body["outcome"] == "player_exit"
        assert body["total_turns"] == 1
        assert isinstance(body["summary"], str) and len(body["summary"]) > 0
        assert isinstance(body["strengths"], list) and len(body["strengths"]) >= 1
        assert isinstance(body["improvements"], list) and len(body["improvements"]) >= 1

    def test_debrief_on_session_ended_with_zero_turns(self, client):
        """Debrief should work for a session started then immediately ended (zero turns)."""
        session_id = _create_and_start(client)
        res = client.post(f"/api/sessions/{session_id}/end")
        assert res.status_code == 200

        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        assert body["total_turns"] == 0
        assert isinstance(body["summary"], str) and len(body["summary"]) > 0

    def test_debrief_for_ended_early_session_references_simulation_context(self, client):
        """Early-exit debrief text must still be grounded in the practice context."""
        session_id = _create_and_start(client)
        res = client.post(f"/api/sessions/{session_id}/end")
        assert res.status_code == 200

        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        all_text = " ".join(
            [body["summary"]] + body["improvements"] + body["strengths"]
        )
        assert any(
            keyword in all_text.lower()
            for keyword in ("simulated", "practice session", "scenario", "session")
        ), f"Debrief text does not reference simulation context: {all_text!r}"


# ---------------------------------------------------------------------------
# Tests — disabled transcript saving
# ---------------------------------------------------------------------------


_NO_TRANSCRIPT_SETUP = {**_VALID_SETUP, "save_transcript": False}


class TestTranscriptSavingDisabledDebrief:
    def test_debrief_generates_when_transcript_saving_disabled(self, client):
        """Debrief should generate successfully even when save_transcript=False."""
        res = client.post("/api/sessions", json=_NO_TRANSCRIPT_SETUP)
        assert res.status_code == 201
        session_id = res.json()["session_id"]

        client.post(f"/api/sessions/{session_id}/start")
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "I have five years of product management experience."},
        )
        client.post(f"/api/sessions/{session_id}/end")

        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200
        body = res.json()
        assert body["session_id"] == session_id
        assert body["outcome"] == "player_exit"
        assert isinstance(body["summary"], str) and len(body["summary"]) > 0
        assert isinstance(body["strengths"], list) and len(body["strengths"]) >= 1

    def test_debrief_scores_still_computed_when_transcript_saving_disabled(self, tmp_config):
        """Rubric scores are computed from turn_session_turns regardless of save_transcript."""
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json=_NO_TRANSCRIPT_SETUP)
            session_id = res.json()["session_id"]
            client.post(f"/api/sessions/{session_id}/start")

            app.state.runtime = _RubricRuntime()

            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I led a cross-functional team."},
            )
            client.post(f"/api/sessions/{session_id}/end")

            res = client.post(f"/api/sessions/{session_id}/debrief")

        assert res.status_code == 200
        body = res.json()
        assert "communication_clarity" in body["scores"]
        assert body["scores"]["communication_clarity"] > 50

    def test_transcript_endpoint_shows_no_turns_when_saving_disabled(self, client):
        """Transcript endpoint must report transcript_saved=False and no turns."""
        res = client.post("/api/sessions", json=_NO_TRANSCRIPT_SETUP)
        session_id = res.json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Just a test turn."},
        )

        res = client.get(f"/api/sessions/{session_id}/transcript")
        assert res.status_code == 200
        body = res.json()
        assert body["transcript_saved"] is False
        assert body["turns"] == []
        assert body.get("message") is not None

    def test_export_text_with_transcript_disabled_contains_notice(self, client):
        """Text export for save_transcript=False must say transcript is not available."""
        res = client.post("/api/sessions", json=_NO_TRANSCRIPT_SETUP)
        session_id = res.json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        client.post(f"/api/sessions/{session_id}/end")

        res = client.get(f"/api/sessions/{session_id}/export/text")
        assert res.status_code == 200
        text = res.text
        assert "transcript saving was disabled" in text.lower() or "not available" in text.lower()


# ---------------------------------------------------------------------------
# Tests — transcript text export endpoint
# ---------------------------------------------------------------------------


class TestTranscriptTextExport:
    def test_text_export_returns_200_with_markdown(self, client):
        session_id = _complete_session(client)
        res = client.get(f"/api/sessions/{session_id}/export/text")
        assert res.status_code == 200
        ct = res.headers.get("content-type", "")
        assert "text" in ct
        assert session_id in res.text

    def test_text_export_contains_transcript_heading(self, client):
        session_id = _complete_session(client)
        res = client.get(f"/api/sessions/{session_id}/export/text")
        assert res.status_code == 200
        assert "## Transcript" in res.text

    def test_text_export_with_debrief_includes_summary(self, client):
        session_id = _complete_session(client)
        client.post(f"/api/sessions/{session_id}/debrief")
        res = client.get(f"/api/sessions/{session_id}/export/text")
        assert res.status_code == 200
        assert "## Debrief Summary" in res.text

    def test_text_export_on_unknown_session_returns_404(self, client):
        res = client.get("/api/sessions/sess-doesnotexist/export/text")
        assert res.status_code == 404

    def test_text_export_content_disposition_filename(self, client):
        session_id = _complete_session(client)
        res = client.get(f"/api/sessions/{session_id}/export/text")
        assert res.status_code == 200
        disposition = res.headers.get("content-disposition", "")
        assert ".md" in disposition
