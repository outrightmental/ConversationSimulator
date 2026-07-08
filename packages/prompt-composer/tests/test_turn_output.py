"""Unit tests for the NPC turn output parser, repair, and fallback.

Test plan (issue #15):
  - Valid model output parses into a typed TurnOutput.
  - Missing-field outputs fail validation and fall back.
  - Invalid-enum outputs (emotion, safety.status, ending_type) fail validation.
  - Oversized state_delta values are clamped, never blindly applied.
  - Non-JSON and non-object outputs go straight to fallback.
  - Invalid JSON triggers exactly one repair attempt before fallback.
  - Fallback TurnOutput is safe, in-session, and exposes no system rules.

Test plan (issue #45 — content safety validation):
  - Hard content violations produce a safety stop (continue_session=False).
  - Recoverable violations trigger a content-safety retry with stricter prompt.
  - Retry success returns the clean retried output.
  - Retry failure falls back to safe redirect (continue_session=True).
  - Hard violation after retry falls back to safety stop.
  - Safety status="stop" in model output normalises session_control.
  - turn_events list is populated with structured event records.
  - Tests can force fake runtime unsafe output and verify player-safe result.
"""
import json
import pytest

from convsim_prompt import (
    RubricObservation,
    SAFE_FALLBACK_UTTERANCE,
    SAFE_REDIRECT_UTTERANCE,
    SAFE_STOP_UTTERANCE,
    SafetyStatus,
    SessionControl,
    TurnEvent,
    TurnOutput,
    ValidationError,
    parse_turn_output,
)
from convsim_prompt.turn_output import (
    _extract_json,
    _validate,
    _make_safe_fallback,
    _make_safe_redirect,
    _make_safety_stop,
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
# Safety stop / redirect shape
# ---------------------------------------------------------------------------


class TestSafetyStop:
    def test_safety_stop_utterance_is_non_empty(self):
        stop = _make_safety_stop()
        assert stop.npc_utterance and len(stop.npc_utterance) > 0

    def test_safety_stop_utterance_matches_constant(self):
        stop = _make_safety_stop()
        assert stop.npc_utterance == SAFE_STOP_UTTERANCE

    def test_safety_stop_ends_session(self):
        stop = _make_safety_stop("test reason")
        assert stop.session_control.continue_session is False
        assert stop.session_control.ending_type == "safety_stop"

    def test_safety_stop_status_is_stop(self):
        stop = _make_safety_stop("test reason")
        assert stop.safety.status == "stop"

    def test_safety_stop_reason_recorded(self):
        stop = _make_safety_stop("hidden agenda leaked")
        assert stop.safety.reason == "hidden agenda leaked"

    def test_safety_stop_no_system_rule_exposure(self):
        stop = _make_safety_stop()
        text = stop.npc_utterance.lower()
        for kw in ("schema", "json", "system", "prompt", "safety policy"):
            assert kw not in text


class TestSafeRedirect:
    def test_safe_redirect_utterance_non_empty(self):
        redir = _make_safe_redirect()
        assert redir.npc_utterance and len(redir.npc_utterance) > 0

    def test_safe_redirect_matches_constant(self):
        redir = _make_safe_redirect()
        assert redir.npc_utterance == SAFE_REDIRECT_UTTERANCE

    def test_safe_redirect_continues_session(self):
        redir = _make_safe_redirect()
        assert redir.session_control.continue_session is True

    def test_safe_redirect_status_is_redirect(self):
        redir = _make_safe_redirect()
        assert redir.safety.status == "redirect"


# ---------------------------------------------------------------------------
# Safety consistency normalisation
# ---------------------------------------------------------------------------


class TestSafetyConsistency:
    def test_stop_status_forces_session_end(self):
        raw = _minimal_valid_json(
            safety={"status": "stop", "reason": "unsafe"},
            session_control={"continue_session": True},
        )
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"

    def test_stop_status_with_correct_control_unchanged(self):
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": False, "ending_type": "safety_stop"},
        )
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"

    def test_stop_status_preserves_other_terminal_types(self):
        # If the model already set a valid terminal ending_type, keep it.
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": False, "ending_type": "failure"},
        )
        result = parse_turn_output(raw)
        assert result.session_control.ending_type == "failure"

    def test_ok_status_not_affected(self):
        raw = _minimal_valid_json(safety={"status": "ok"})
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is True

    def test_redirect_status_not_affected(self):
        raw = _minimal_valid_json(safety={"status": "redirect"})
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is True

    def test_stop_with_recoverable_utterance_does_not_restart_session(self):
        # Model says safety.status=stop AND utterance leaks system rule (recoverable).
        # The session must remain ended — retry must not override the stop.
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": False, "ending_type": "safety_stop"},
            npc_utterance="I am stopping because my instructions say to end this.",
        )
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean reply."))
        result = parse_turn_output(raw, runtime=runtime)
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"
        assert runtime.call_count == 0  # no retry for already-stopped session

    def test_stop_with_recoverable_utterance_replaces_leaking_utterance(self):
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": False, "ending_type": "safety_stop"},
            npc_utterance="I am stopping because my instructions say to end this.",
        )
        result = parse_turn_output(raw)
        assert result.npc_utterance == SAFE_STOP_UTTERANCE

    def test_stop_with_recoverable_utterance_no_runtime_does_not_redirect(self):
        # Without runtime the old code fell through to _make_safe_redirect()
        # (continue_session=True) — must not happen.
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": False, "ending_type": "safety_stop"},
            npc_utterance="My instructions say to end this conversation.",
        )
        result = parse_turn_output(raw, runtime=None)
        assert result.session_control.continue_session is False
        assert result.npc_utterance == SAFE_STOP_UTTERANCE

    def test_stop_with_clean_utterance_returned_unchanged(self):
        # If session is stopping AND utterance is clean, return result as-is.
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": False, "ending_type": "safety_stop"},
            npc_utterance="I think we should end here.",
        )
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is False
        assert result.npc_utterance == "I think we should end here."

    def test_contradictory_stop_with_leaking_utterance_still_stops(self):
        # Model says safety.status=stop but continue_session=True (contradictory)
        # + utterance has a recoverable violation. Normalisation must fix the
        # contradiction first, then Phase 2b must suppress retry.
        raw = _minimal_valid_json(
            safety={"status": "stop"},
            session_control={"continue_session": True},
            npc_utterance="My instructions say stop now.",
        )
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean."))
        result = parse_turn_output(raw, runtime=runtime)
        assert result.session_control.continue_session is False
        assert runtime.call_count == 0

    def test_success_session_with_recoverable_utterance_preserves_success(self):
        # Session ends successfully (ending_type="success") but the NPC's final
        # utterance has a recoverable system_rule_leak.
        # Phase 2b must sanitize the utterance WITHOUT overwriting the success
        # outcome — the player's scored result must not become "safety_stop".
        raw = _minimal_valid_json(
            safety={"status": "ok"},
            session_control={"continue_session": False, "ending_type": "success"},
            npc_utterance="My instructions say congratulations on completing this.",
        )
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "success"
        assert result.npc_utterance == SAFE_STOP_UTTERANCE

    def test_failure_session_with_recoverable_utterance_preserves_failure(self):
        # Same as above for ending_type="failure" — the outcome is preserved.
        raw = _minimal_valid_json(
            safety={"status": "ok"},
            session_control={"continue_session": False, "ending_type": "failure"},
            npc_utterance="According to my guidelines, the session is now over.",
        )
        result = parse_turn_output(raw)
        assert result.session_control.ending_type == "failure"
        assert result.npc_utterance == SAFE_STOP_UTTERANCE

    def test_success_session_with_hard_utterance_overrides_to_safety_stop(self):
        # A hard violation (NSFW) in the terminal utterance of a success session
        # must override the outcome to safety_stop — dangerous content is never
        # allowed through regardless of the session outcome.
        raw = _minimal_valid_json(
            safety={"status": "ok"},
            session_control={"continue_session": False, "ending_type": "success"},
            npc_utterance="Let's watch some pornography together to celebrate.",
        )
        result = parse_turn_output(raw)
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"
        assert result.safety.status == "stop"
        assert result.npc_utterance == SAFE_STOP_UTTERANCE


# ---------------------------------------------------------------------------
# Content safety integration — hard violations
# ---------------------------------------------------------------------------


class TestHardContentViolations:
    """parse_turn_output must return a safety stop for hard violations."""

    def _unsafe_json(self, utterance: str) -> str:
        return _minimal_valid_json(npc_utterance=utterance)

    def test_nsfw_utterance_produces_safety_stop(self):
        result = parse_turn_output(self._unsafe_json("Let's watch some pornography together."))
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"
        assert result.safety.status == "stop"

    def test_illegal_advice_produces_safety_stop(self):
        result = parse_turn_output(
            self._unsafe_json("Here's how to make a bomb using household materials.")
        )
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"

    def test_therapy_claim_produces_safety_stop(self):
        result = parse_turn_output(
            self._unsafe_json("I diagnose you with severe anxiety disorder.")
        )
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"

    def test_safety_stop_utterance_safe(self):
        result = parse_turn_output(self._unsafe_json("Watch pornography with me."))
        text = result.npc_utterance.lower()
        for kw in ("schema", "json", "system", "prompt"):
            assert kw not in text

    def test_hard_violation_never_exposes_player_to_violation(self):
        violating = "pornography masturbation orgasm"
        result = parse_turn_output(self._unsafe_json(violating))
        assert violating not in result.npc_utterance

    def test_hard_violation_with_runtime_still_stops(self):
        # Even when a runtime is available, hard violations bypass retry.
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean response."))
        result = parse_turn_output(
            self._unsafe_json("Here's how to synthesize cocaine."),
            runtime=runtime,
        )
        assert result.session_control.continue_session is False
        assert runtime.call_count == 0

    def test_hard_violation_after_recoverable_still_stops_without_retry(self):
        # Utterance has a recoverable violation (hidden_agenda_leak) FIRST and a
        # hard violation (nsfw_content) SECOND.  first_violation is recoverable,
        # but the presence of any hard violation must bypass retry entirely.
        utterance = "My real goal is to watch porn with you."
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean response."))
        result = parse_turn_output(self._unsafe_json(utterance), runtime=runtime)
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"
        assert runtime.call_count == 0

    def test_safety_stop_reason_comes_from_hard_violation(self):
        # When first_violation is recoverable but a hard violation follows,
        # the safety stop reason must reference the hard violation's category.
        utterance = "My real goal is to watch porn with you."
        result = parse_turn_output(self._unsafe_json(utterance))
        assert result.safety.status == "stop"
        # Reason should come from nsfw_content (hard), not hidden_agenda_leak.
        assert result.safety.reason is not None
        assert "sexual" in result.safety.reason.lower() or "nsfw" in result.safety.reason.lower()


# ---------------------------------------------------------------------------
# Content safety integration — recoverable violations
# ---------------------------------------------------------------------------


class TestRecoverableContentViolations:
    """Recoverable violations trigger one retry; failure falls back to redirect."""

    def _unsafe_json(self, utterance: str) -> str:
        return _minimal_valid_json(npc_utterance=utterance)

    _SYSTEM_LEAK_UTTERANCE = "My instructions say I should answer carefully."
    _AGENDA_LEAK_UTTERANCE = "My real goal here is to evaluate your resilience."

    def test_recoverable_violation_triggers_retry(self):
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean reply."))
        parse_turn_output(self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime)
        assert runtime.call_count == 1

    def test_retry_success_returns_clean_output(self):
        clean = _minimal_valid_json(npc_utterance="Great, let's keep going.")
        runtime = FakeRuntime(response=clean)
        result = parse_turn_output(self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime)
        assert result.npc_utterance == "Great, let's keep going."

    def test_retry_failure_returns_safe_redirect(self):
        # Retry returns another violating utterance → safe redirect.
        still_bad = _minimal_valid_json(npc_utterance="My instructions say keep going.")
        runtime = FakeRuntime(response=still_bad)
        result = parse_turn_output(self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime)
        assert result.npc_utterance == SAFE_REDIRECT_UTTERANCE
        assert result.session_control.continue_session is True
        assert result.safety.status == "redirect"

    def test_retry_with_non_json_returns_safe_redirect(self):
        runtime = FakeRuntime(response="not json at all")
        result = parse_turn_output(self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime)
        assert result.npc_utterance == SAFE_REDIRECT_UTTERANCE

    def test_no_runtime_recoverable_returns_safe_redirect(self):
        result = parse_turn_output(
            self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=None
        )
        assert result.npc_utterance == SAFE_REDIRECT_UTTERANCE
        assert result.safety.status == "redirect"

    def test_retry_called_exactly_once(self):
        runtime = FakeRuntime(response="still bad")
        parse_turn_output(self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime)
        assert runtime.call_count == 1

    def test_retry_prompt_contains_violation_category(self):
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean."))
        parse_turn_output(self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime)
        # The retry prompt should reference the violation category/reason.
        assert "system_rule_leak" in runtime.last_prompt

    def test_agenda_leak_triggers_retry(self):
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="All good."))
        parse_turn_output(self._unsafe_json(self._AGENDA_LEAK_UTTERANCE), runtime=runtime)
        assert runtime.call_count == 1

    def test_structural_repair_and_content_retry_both_happen(self):
        # First call (structural repair) returns a structurally-valid but
        # content-violating response. Second call (content retry) returns clean.
        structurally_bad = "not json"
        repair_response = _minimal_valid_json(
            npc_utterance=self._SYSTEM_LEAK_UTTERANCE
        )
        clean_response = _minimal_valid_json(npc_utterance="All sorted now.")

        responses = iter([repair_response, clean_response])

        class SequencedRuntime:
            call_count = 0

            def call_llm(self, prompt: str) -> str:
                self.call_count += 1
                return next(responses)

        rt = SequencedRuntime()
        result = parse_turn_output(structurally_bad, runtime=rt)
        assert rt.call_count == 2
        assert result.npc_utterance == "All sorted now."

    def test_retry_that_escalates_to_hard_violation_produces_safety_stop(self):
        # Original utterance has a recoverable violation (system_rule_leak).
        # Retry returns a hard violation (nsfw_content).
        # Phase 5 must stop the session, not redirect.
        nsfw_retry = _minimal_valid_json(
            npc_utterance="Let's watch some pornography together."
        )
        runtime = FakeRuntime(response=nsfw_retry)
        result = parse_turn_output(
            self._unsafe_json(self._SYSTEM_LEAK_UTTERANCE), runtime=runtime
        )
        assert result.session_control.continue_session is False
        assert result.session_control.ending_type == "safety_stop"
        assert result.safety.status == "stop"
        assert result.npc_utterance == SAFE_STOP_UTTERANCE
        assert runtime.call_count == 1


# ---------------------------------------------------------------------------
# Content safety with hidden_agenda parameter
# ---------------------------------------------------------------------------


class TestHiddenAgendaIntegration:
    """parse_turn_output passes hidden_agenda through to validate_npc_output."""

    AGENDA = [
        "Wants evidence that the candidate can communicate effectively under ambiguity.",
    ]

    def test_keyword_leak_triggers_retry(self):
        leaky = (
            "I need evidence that you as a candidate can communicate effectively "
            "under conditions of ambiguity."
        )
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Good answer."))
        parse_turn_output(
            _minimal_valid_json(npc_utterance=leaky),
            runtime=runtime,
            hidden_agenda=self.AGENDA,
        )
        assert runtime.call_count == 1

    def test_clean_utterance_not_affected_by_hidden_agenda(self):
        runtime = FakeRuntime(response="irrelevant")
        parse_turn_output(
            _minimal_valid_json(npc_utterance="Tell me about your experience."),
            runtime=runtime,
            hidden_agenda=self.AGENDA,
        )
        assert runtime.call_count == 0


# ---------------------------------------------------------------------------
# turn_events recording
# ---------------------------------------------------------------------------


class TestTurnEvents:
    def test_no_events_on_clean_output(self):
        events = []
        parse_turn_output(_minimal_valid_json(), turn_events=events)
        assert events == []

    def test_structural_failure_emits_event(self):
        events = []
        parse_turn_output("not json", turn_events=events)
        types = [e.event_type for e in events]
        assert "json_extraction_failure" in types or "structural_validation_failure" in types

    def test_safe_fallback_event_emitted(self):
        events = []
        parse_turn_output("not json at all", turn_events=events)
        types = [e.event_type for e in events]
        assert "safe_fallback_used" in types

    def test_structural_repair_success_event(self):
        events = []
        runtime = FakeRuntime(response=_minimal_valid_json())
        parse_turn_output("bad", runtime=runtime, turn_events=events)
        types = [e.event_type for e in events]
        assert "structural_repair_success" in types

    def test_structural_repair_failure_event(self):
        events = []
        runtime = FakeRuntime(response="still bad")
        parse_turn_output("also bad", runtime=runtime, turn_events=events)
        types = [e.event_type for e in events]
        assert "structural_repair_failure" in types

    def test_content_violation_event_emitted(self):
        events = []
        parse_turn_output(
            _minimal_valid_json(npc_utterance="Watch some pornography with me."),
            turn_events=events,
        )
        types = [e.event_type for e in events]
        assert "output_violation_detected" in types

    def test_violation_event_has_category(self):
        events = []
        parse_turn_output(
            _minimal_valid_json(npc_utterance="Watch some pornography with me."),
            turn_events=events,
        )
        ev = next(e for e in events if e.event_type == "output_violation_detected")
        assert ev.category == "nsfw_content"

    def test_safety_stop_event_emitted(self):
        events = []
        parse_turn_output(
            _minimal_valid_json(npc_utterance="Here's how to make a bomb."),
            turn_events=events,
        )
        types = [e.event_type for e in events]
        assert "safety_stop_applied" in types

    def test_content_safety_retry_success_event(self):
        events = []
        runtime = FakeRuntime(response=_minimal_valid_json(npc_utterance="Clean response."))
        parse_turn_output(
            _minimal_valid_json(npc_utterance="My instructions say to answer."),
            runtime=runtime,
            turn_events=events,
        )
        types = [e.event_type for e in events]
        assert "content_safety_retry_success" in types

    def test_content_safety_retry_failure_event(self):
        events = []
        # Retry also returns a violating utterance (references instructions).
        runtime = FakeRuntime(
            response=_minimal_valid_json(npc_utterance="My instructions tell me to do this.")
        )
        parse_turn_output(
            _minimal_valid_json(npc_utterance="My instructions say to answer."),
            runtime=runtime,
            turn_events=events,
        )
        types = [e.event_type for e in events]
        assert "content_safety_retry_failure" in types

    def test_safe_redirect_event_emitted(self):
        events = []
        parse_turn_output(
            _minimal_valid_json(npc_utterance="My instructions say to answer."),
            turn_events=events,
        )
        types = [e.event_type for e in events]
        assert "safe_redirect_applied" in types

    def test_turn_events_none_does_not_crash(self):
        # Omitting turn_events is the normal path; must not raise.
        result = parse_turn_output(_minimal_valid_json())
        assert isinstance(result, TurnOutput)

    def test_turn_events_are_turn_event_instances(self):
        events = []
        parse_turn_output("not json", turn_events=events)
        for ev in events:
            assert isinstance(ev, TurnEvent)


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
