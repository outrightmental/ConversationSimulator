"""Unit tests for the NPC turn output parser, repair, and fallback.

Test plan (issue #15):
  - Valid model output parses into a typed TurnOutput.
  - Missing-field outputs fail validation and fall back.
  - Invalid-enum outputs (emotion, safety.status, ending_type) fail validation.
  - Oversized state_delta values are clamped, never blindly applied.
  - Non-JSON and non-object outputs go straight to fallback.
  - Invalid JSON triggers exactly one repair attempt before fallback.
  - Fallback TurnOutput is safe, in-session, and exposes no system rules.
"""
import json
import pytest

from convsim_prompt import (
    RubricObservation,
    SAFE_FALLBACK_UTTERANCE,
    SafetyStatus,
    SessionControl,
    TurnOutput,
    ValidationError,
    parse_turn_output,
)
from convsim_prompt.turn_output import (
    _extract_json,
    _validate,
    _make_safe_fallback,
    _REPAIR_PROMPT,
    _STATE_DELTA_MIN,
    _STATE_DELTA_MAX,
    _RUBRIC_SCORE_DELTA_MIN,
    _RUBRIC_SCORE_DELTA_MAX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_valid_dict(**overrides):
    """Minimal valid turn output dict; overrides replace top-level keys."""
    base = {
        "npc_utterance": "Hello there.",
        "npc_emotion": "neutral",
        "state_delta": {},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    }
    base.update(overrides)
    return base


def _minimal_valid_json(**overrides) -> str:
    return json.dumps(_minimal_valid_dict(**overrides))


class FakeRuntime:
    """Fake runtime adapter that returns a pre-set string for every call_llm()."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0
        self.last_prompt: str | None = None

    def call_llm(self, prompt: str) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        return self._response


class FailingRuntime:
    """Runtime that always raises."""

    def __init__(self) -> None:
        self.call_count = 0

    def call_llm(self, prompt: str) -> str:
        self.call_count += 1
        raise RuntimeError("LLM unavailable")


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json_object(self):
        raw = '{"a": 1}'
        result = _extract_json(raw)
        assert result == {"a": 1}

    def test_json_with_leading_text(self):
        raw = 'Here is the output:\n{"a": 1}'
        result = _extract_json(raw)
        assert result == {"a": 1}

    def test_json_with_trailing_text(self):
        raw = '{"a": 1}\nThat is my answer.'
        result = _extract_json(raw)
        assert result == {"a": 1}

    def test_json_in_fenced_code_block(self):
        raw = '```\n{"a": 1}\n```'
        result = _extract_json(raw)
        assert result == {"a": 1}

    def test_json_in_json_fenced_code_block(self):
        raw = '```json\n{"a": 1}\n```'
        result = _extract_json(raw)
        assert result == {"a": 1}

    def test_non_json_returns_none(self):
        assert _extract_json("plain text, no JSON") is None

    def test_json_array_not_returned_as_dict(self):
        assert _extract_json("[1, 2, 3]") is None

    def test_empty_string_returns_none(self):
        assert _extract_json("") is None

    def test_whitespace_only_returns_none(self):
        assert _extract_json("   \n\t  ") is None

    def test_fenced_block_when_brace_scan_fails(self):
        # A stray opening brace before the fence makes the brace-scan span invalid;
        # the fence-regex path must pick up the correct JSON.
        raw = "Use { this schema:\n```json\n{\"a\": 1}\n```"
        result = _extract_json(raw)
        assert result == {"a": 1}


# ---------------------------------------------------------------------------
# Validation — valid inputs
# ---------------------------------------------------------------------------


class TestValidateValid:
    def test_minimal_valid_turn(self):
        result = _validate(_minimal_valid_dict())
        assert isinstance(result, TurnOutput)
        assert result.npc_utterance == "Hello there."
        assert result.npc_emotion == "neutral"
        assert result.state_delta == {}
        assert result.event_flags == []
        assert result.rubric_observations == []
        assert result.safety.status == "ok"
        assert result.session_control.continue_session is True

    def test_all_valid_emotions_accepted(self):
        emotions = [
            "neutral", "warm", "curious", "skeptical", "impatient",
            "defensive", "confused", "impressed", "concerned", "angry",
        ]
        for emotion in emotions:
            result = _validate(_minimal_valid_dict(npc_emotion=emotion))
            assert result.npc_emotion == emotion

    def test_full_turn_with_optional_fields(self):
        data = _minimal_valid_dict(
            state_delta={"trust": 5, "patience": -3},
            event_flags=["greeting_received"],
            rubric_observations=[
                {"rubric_id": "clarity", "observation": "Spoke clearly.", "score_delta": 2}
            ],
            safety={"status": "ok", "reason": None},
            session_control={
                "continue_session": True,
                "ending_type": "none",
                "ending_summary": None,
            },
        )
        result = _validate(data)
        assert result.state_delta == {"trust": 5, "patience": -3}
        assert result.event_flags == ["greeting_received"]
        assert len(result.rubric_observations) == 1
        assert result.rubric_observations[0].rubric_id == "clarity"
        assert result.rubric_observations[0].score_delta == 2

    def test_safety_redirect_status(self):
        result = _validate(_minimal_valid_dict(safety={"status": "redirect", "reason": "Off topic."}))
        assert result.safety.status == "redirect"
        assert result.safety.reason == "Off topic."

    def test_safety_stop_status(self):
        result = _validate(_minimal_valid_dict(safety={"status": "stop"}))
        assert result.safety.status == "stop"

    def test_session_control_ending_types(self):
        for etype in ["none", "success", "failure", "timeout", "safety_stop", "player_exit"]:
            sc = {"continue_session": False, "ending_type": etype}
            result = _validate(_minimal_valid_dict(session_control=sc))
            assert result.session_control.ending_type == etype

    def test_rubric_observation_without_score_delta(self):
        data = _minimal_valid_dict(
            rubric_observations=[{"rubric_id": "r1", "observation": "Good."}]
        )
        result = _validate(data)
        assert result.rubric_observations[0].score_delta is None


# ---------------------------------------------------------------------------
# Validation — missing required fields
# ---------------------------------------------------------------------------


class TestValidateMissingFields:
    def _assert_missing(self, key: str, **nested):
        """Verify ValidationError is raised when a required field is absent."""
        data = _minimal_valid_dict()
        if nested:
            data.update(nested)
        else:
            del data[key]
        with pytest.raises(ValidationError, match=key):
            _validate(data)

    def test_missing_npc_utterance(self):
        self._assert_missing("npc_utterance")

    def test_missing_npc_emotion(self):
        self._assert_missing("npc_emotion")

    def test_missing_state_delta(self):
        self._assert_missing("state_delta")

    def test_missing_event_flags(self):
        self._assert_missing("event_flags")

    def test_missing_rubric_observations(self):
        self._assert_missing("rubric_observations")

    def test_missing_safety(self):
        self._assert_missing("safety")

    def test_missing_safety_status(self):
        data = _minimal_valid_dict(safety={"reason": "no status here"})
        with pytest.raises(ValidationError, match="safety.status"):
            _validate(data)

    def test_missing_session_control(self):
        self._assert_missing("session_control")

    def test_missing_session_control_continue_session(self):
        data = _minimal_valid_dict(session_control={"ending_type": "none"})
        with pytest.raises(ValidationError, match="continue_session"):
            _validate(data)

    def test_empty_npc_utterance(self):
        data = _minimal_valid_dict(npc_utterance="")
        with pytest.raises(ValidationError, match="npc_utterance"):
            _validate(data)

    def test_missing_rubric_observation_rubric_id(self):
        data = _minimal_valid_dict(
            rubric_observations=[{"observation": "no id"}]
        )
        with pytest.raises(ValidationError, match="rubric_id"):
            _validate(data)

    def test_missing_rubric_observation_observation(self):
        data = _minimal_valid_dict(
            rubric_observations=[{"rubric_id": "r1"}]
        )
        with pytest.raises(ValidationError, match="observation"):
            _validate(data)


# ---------------------------------------------------------------------------
# Validation — invalid enum values
# ---------------------------------------------------------------------------


class TestValidateInvalidEnums:
    def test_unknown_npc_emotion(self):
        data = _minimal_valid_dict(npc_emotion="happy")
        with pytest.raises(ValidationError, match="npc_emotion"):
            _validate(data)

    def test_unknown_safety_status(self):
        data = _minimal_valid_dict(safety={"status": "warn"})
        with pytest.raises(ValidationError, match="safety.status"):
            _validate(data)

    def test_unknown_ending_type(self):
        data = _minimal_valid_dict(
            session_control={"continue_session": False, "ending_type": "crash"}
        )
        with pytest.raises(ValidationError, match="ending_type"):
            _validate(data)


# ---------------------------------------------------------------------------
# Validation — state delta bounds
# ---------------------------------------------------------------------------


class TestStateDeltaBounds:
    def test_in_bounds_values_pass_unchanged(self):
        data = _minimal_valid_dict(state_delta={"trust": 20, "patience": -20})
        result = _validate(data)
        assert result.state_delta == {"trust": 20, "patience": -20}

    def test_oversized_positive_delta_clamped(self):
        data = _minimal_valid_dict(state_delta={"trust": 99})
        result = _validate(data)
        assert result.state_delta["trust"] == _STATE_DELTA_MAX

    def test_oversized_negative_delta_clamped(self):
        data = _minimal_valid_dict(state_delta={"patience": -99})
        result = _validate(data)
        assert result.state_delta["patience"] == _STATE_DELTA_MIN

    def test_clamped_values_never_exceed_bounds(self):
        data = _minimal_valid_dict(state_delta={"a": 1000, "b": -1000, "c": 0})
        result = _validate(data)
        for v in result.state_delta.values():
            assert _STATE_DELTA_MIN <= v <= _STATE_DELTA_MAX

    def test_non_integer_delta_value_raises(self):
        data = _minimal_valid_dict(state_delta={"trust": 1.5})
        with pytest.raises(ValidationError, match="integer"):
            _validate(data)

    def test_state_delta_must_be_object(self):
        data = _minimal_valid_dict(state_delta=[1, 2, 3])
        with pytest.raises(ValidationError, match="state_delta"):
            _validate(data)

    def test_state_delta_bool_value_raises(self):
        # Python bool is a subclass of int; JSON `true`/`false` must be rejected.
        for v in (True, False):
            data = _minimal_valid_dict(state_delta={"trust": v})
            with pytest.raises(ValidationError, match="integer"):
                _validate(data)


# ---------------------------------------------------------------------------
# Validation — rubric score_delta bounds
# ---------------------------------------------------------------------------


class TestRubricScoreDeltaBounds:
    def _obs(self, score_delta):
        return [{"rubric_id": "r1", "observation": "ok", "score_delta": score_delta}]

    def test_in_bounds_score_delta_unchanged(self):
        for v in (_RUBRIC_SCORE_DELTA_MIN, 0, _RUBRIC_SCORE_DELTA_MAX):
            result = _validate(_minimal_valid_dict(rubric_observations=self._obs(v)))
            assert result.rubric_observations[0].score_delta == v

    def test_oversized_positive_score_delta_clamped(self):
        result = _validate(_minimal_valid_dict(rubric_observations=self._obs(99)))
        assert result.rubric_observations[0].score_delta == _RUBRIC_SCORE_DELTA_MAX

    def test_oversized_negative_score_delta_clamped(self):
        result = _validate(_minimal_valid_dict(rubric_observations=self._obs(-99)))
        assert result.rubric_observations[0].score_delta == _RUBRIC_SCORE_DELTA_MIN

    def test_score_delta_bool_raises(self):
        for v in (True, False):
            data = _minimal_valid_dict(rubric_observations=self._obs(v))
            with pytest.raises(ValidationError, match="integer"):
                _validate(data)


# ---------------------------------------------------------------------------
# parse_turn_output — happy path
# ---------------------------------------------------------------------------


class TestParseTurnOutputValid:
    def test_valid_json_string_returns_turn_output(self):
        raw = _minimal_valid_json()
        result = parse_turn_output(raw)
        assert isinstance(result, TurnOutput)
        assert result.npc_utterance == "Hello there."

    def test_valid_json_with_prose_returns_turn_output(self):
        raw = "Here is my response:\n" + _minimal_valid_json()
        result = parse_turn_output(raw)
        assert isinstance(result, TurnOutput)

    def test_valid_json_in_code_fence_returns_turn_output(self):
        raw = "```json\n" + _minimal_valid_json() + "\n```"
        result = parse_turn_output(raw)
        assert isinstance(result, TurnOutput)

    def test_state_delta_clamped_in_valid_parse(self):
        raw = _minimal_valid_json(state_delta={"trust": 50})
        result = parse_turn_output(raw)
        assert result.state_delta["trust"] == _STATE_DELTA_MAX


# ---------------------------------------------------------------------------
# parse_turn_output — fallback cases (no runtime)
# ---------------------------------------------------------------------------


class TestParseTurnOutputFallback:
    def test_non_json_returns_fallback(self):
        result = parse_turn_output("This is just some text.")
        _assert_is_safe_fallback(result)

    def test_empty_string_returns_fallback(self):
        result = parse_turn_output("")
        _assert_is_safe_fallback(result)

    def test_missing_field_returns_fallback(self):
        data = _minimal_valid_dict()
        del data["safety"]
        result = parse_turn_output(json.dumps(data))
        _assert_is_safe_fallback(result)

    def test_invalid_emotion_returns_fallback(self):
        result = parse_turn_output(_minimal_valid_json(npc_emotion="happy"))
        _assert_is_safe_fallback(result)

    def test_invalid_safety_status_returns_fallback(self):
        result = parse_turn_output(_minimal_valid_json(safety={"status": "warn"}))
        _assert_is_safe_fallback(result)

    def test_invalid_ending_type_returns_fallback(self):
        raw = _minimal_valid_json(
            session_control={"continue_session": False, "ending_type": "boom"}
        )
        result = parse_turn_output(raw)
        _assert_is_safe_fallback(result)

    def test_json_array_not_accepted(self):
        result = parse_turn_output("[1, 2, 3]")
        _assert_is_safe_fallback(result)

    def test_parse_never_raises(self):
        for raw in ["", "not json", "{broken", "null", "42", '["list"]']:
            result = parse_turn_output(raw)
            assert isinstance(result, TurnOutput)


# ---------------------------------------------------------------------------
# parse_turn_output — repair retry
# ---------------------------------------------------------------------------


class TestRepairRetry:
    def test_repair_called_when_initial_parse_fails(self):
        runtime = FakeRuntime(response=_minimal_valid_json())
        parse_turn_output("not valid json", runtime=runtime)
        assert runtime.call_count == 1

    def test_repair_not_called_when_initial_parse_succeeds(self):
        runtime = FakeRuntime(response="irrelevant")
        parse_turn_output(_minimal_valid_json(), runtime=runtime)
        assert runtime.call_count == 0

    def test_repair_returns_valid_turn_output(self):
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Repaired."))
        result = parse_turn_output("garbage input", runtime=runtime)
        assert result.npc_utterance == "Repaired."

    def test_repair_called_exactly_once_not_more(self):
        runtime = FakeRuntime(response="still bad json")
        parse_turn_output("also bad", runtime=runtime)
        assert runtime.call_count == 1

    def test_fallback_when_repair_also_fails(self):
        runtime = FakeRuntime(response="still not json")
        result = parse_turn_output("bad input", runtime=runtime)
        _assert_is_safe_fallback(result)

    def test_fallback_when_repair_returns_invalid_schema(self):
        bad_schema = json.dumps({"npc_utterance": "hi"})  # missing fields
        runtime = FakeRuntime(response=bad_schema)
        result = parse_turn_output("bad input", runtime=runtime)
        _assert_is_safe_fallback(result)

    def test_fallback_when_runtime_raises(self):
        runtime = FailingRuntime()
        result = parse_turn_output("bad input", runtime=runtime)
        _assert_is_safe_fallback(result)
        assert runtime.call_count == 1

    def test_repair_prompt_contains_schema(self):
        runtime = FakeRuntime(response="irrelevant")
        parse_turn_output("bad", runtime=runtime)
        assert "npc_utterance" in runtime.last_prompt
        assert "npc_emotion" in runtime.last_prompt
        assert "session_control" in runtime.last_prompt

    def test_no_runtime_no_repair_returns_fallback(self):
        result = parse_turn_output("not json", runtime=None)
        _assert_is_safe_fallback(result)

    def test_repair_with_fenced_valid_json_succeeds(self):
        fenced = "```json\n" + _minimal_valid_json(npc_utterance="Fenced repair.") + "\n```"
        runtime = FakeRuntime(response=fenced)
        result = parse_turn_output("initial garbage", runtime=runtime)
        assert result.npc_utterance == "Fenced repair."


# ---------------------------------------------------------------------------
# Fallback shape
# ---------------------------------------------------------------------------


class TestSafeFallback:
    def test_fallback_utterance_is_non_empty(self):
        fb = _make_safe_fallback()
        assert fb.npc_utterance and len(fb.npc_utterance) > 0

    def test_fallback_utterance_constant_matches_instance(self):
        fb = _make_safe_fallback()
        assert fb.npc_utterance == SAFE_FALLBACK_UTTERANCE

    def test_fallback_session_continues(self):
        fb = _make_safe_fallback()
        assert fb.session_control.continue_session is True

    def test_fallback_safety_status_is_ok(self):
        fb = _make_safe_fallback()
        assert fb.safety.status == "ok"

    def test_fallback_emotion_is_neutral(self):
        fb = _make_safe_fallback()
        assert fb.npc_emotion == "neutral"

    def test_fallback_state_delta_is_empty(self):
        fb = _make_safe_fallback()
        assert fb.state_delta == {}

    def test_fallback_event_flags_empty(self):
        fb = _make_safe_fallback()
        assert fb.event_flags == []

    def test_fallback_no_system_rule_exposure(self):
        fb = _make_safe_fallback()
        text = fb.npc_utterance.lower()
        for keyword in ("schema", "json", "system", "rule", "layer", "safety policy", "prompt"):
            assert keyword not in text, f"Fallback utterance exposes: {keyword!r}"

    def test_fallback_instances_are_independent(self):
        fb1 = _make_safe_fallback()
        fb2 = _make_safe_fallback()
        fb1.state_delta["x"] = 1
        assert "x" not in fb2.state_delta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_is_safe_fallback(result: TurnOutput) -> None:
    """Assert a TurnOutput matches the safe fallback contract."""
    assert isinstance(result, TurnOutput)
    assert result.session_control.continue_session is True
    assert result.safety.status == "ok"
    assert result.npc_emotion == "neutral"
    assert result.state_delta == {}
