"""NPC turn output parser, validator, repair, and fallback.

Parsing pipeline:
  1. Extract JSON from raw model text (handles markdown fences, leading prose).
  2. Validate required fields, enum values, and field types.
  3. If validation fails: make exactly one repair call to the runtime (if given).
  4. If repair also fails or no runtime is available: return SAFE_FALLBACK.

State delta values are clamped to [-20, 20] per-turn before they can reach the
state engine — dangerously large values are never applied blindly.

Validation errors are logged at WARNING level so they appear in dev logs and the
debug drawer without crashing the session.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from .types import NPC_TURN_OUTPUT_SCHEMA

logger = logging.getLogger(__name__)

_VALID_EMOTIONS = frozenset({
    "neutral", "warm", "curious", "skeptical", "impatient",
    "defensive", "confused", "impressed", "concerned", "angry",
})
_VALID_SAFETY_STATUSES = frozenset({"ok", "redirect", "stop"})
_VALID_ENDING_TYPES = frozenset({
    "none", "success", "failure", "timeout", "safety_stop", "player_exit",
})

_STATE_DELTA_MIN = -20
_STATE_DELTA_MAX = 20
_RUBRIC_SCORE_DELTA_MIN = -3
_RUBRIC_SCORE_DELTA_MAX = 3

_REPAIR_PROMPT = (
    "Your previous response did not produce a valid structured JSON response. "
    "Return ONLY a valid JSON object matching this schema — no markdown fences, "
    "no explanation, no text outside the JSON object itself:\n"
    + json.dumps(NPC_TURN_OUTPUT_SCHEMA, indent=2)
)


class ValidationError(ValueError):
    """Raised when a turn output fails schema or semantic validation."""


class RuntimeProtocol(Protocol):
    """Minimal interface the parser uses for a single repair LLM call."""

    def call_llm(self, prompt: str) -> str: ...


@dataclass
class RubricObservation:
    rubric_id: str
    observation: str
    score_delta: Optional[int] = None


@dataclass
class SafetyStatus:
    status: str
    reason: Optional[str] = None


@dataclass
class SessionControl:
    continue_session: bool
    ending_type: Optional[str] = None
    ending_summary: Optional[str] = None


@dataclass
class TurnOutput:
    npc_utterance: str
    npc_emotion: str
    state_delta: Dict[str, int]
    event_flags: List[str]
    rubric_observations: List[RubricObservation]
    safety: SafetyStatus
    session_control: SessionControl


# Canonical safe fallback: keeps the player in-session, exposes no system rules.
SAFE_FALLBACK_UTTERANCE = "I'm not sure what to say right now. Could you repeat that?"


def _make_safe_fallback() -> TurnOutput:
    return TurnOutput(
        npc_utterance=SAFE_FALLBACK_UTTERANCE,
        npc_emotion="neutral",
        state_delta={},
        event_flags=[],
        rubric_observations=[],
        safety=SafetyStatus(status="ok"),
        session_control=SessionControl(continue_session=True),
    )


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """Try to find and parse a JSON object in raw model text.

    Attempts in order:
      1. Entire stripped string as JSON.
      2. First '{' … last '}' span (handles leading/trailing prose).
      3. First ```json … ``` or ``` … ``` fenced code block.
    """
    text = raw.strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    return None


def _validate(data: Dict[str, Any]) -> TurnOutput:
    """Validate a parsed dict and convert it to a TurnOutput.

    Raises ValidationError for missing required fields, wrong types, or invalid
    enum values. State delta values outside [-20, 20] are clamped and logged.
    """

    def _req(key: str, parent: Dict[str, Any] = data, ctx: str = "") -> Any:
        if key not in parent:
            prefix = f"{ctx}." if ctx else ""
            raise ValidationError(f"Missing required field: {prefix}{key}")
        return parent[key]

    utterance = _req("npc_utterance")
    if not isinstance(utterance, str) or not utterance:
        raise ValidationError("npc_utterance must be a non-empty string")

    emotion = _req("npc_emotion")
    if emotion not in _VALID_EMOTIONS:
        raise ValidationError(
            f"Unknown npc_emotion: {emotion!r}. "
            f"Valid values: {sorted(_VALID_EMOTIONS)}"
        )

    raw_delta = _req("state_delta")
    if not isinstance(raw_delta, dict):
        raise ValidationError("state_delta must be an object")
    state_delta: Dict[str, int] = {}
    for k, v in raw_delta.items():
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValidationError(
                f"state_delta[{k!r}] must be an integer, got {type(v).__name__}"
            )
        clamped = max(_STATE_DELTA_MIN, min(_STATE_DELTA_MAX, v))
        if clamped != v:
            logger.warning("state_delta[%r] clamped %d → %d", k, v, clamped)
        state_delta[k] = clamped

    raw_flags = _req("event_flags")
    if not isinstance(raw_flags, list):
        raise ValidationError("event_flags must be an array")
    for i, flag in enumerate(raw_flags):
        if not isinstance(flag, str):
            raise ValidationError(f"event_flags[{i}] must be a string")
    event_flags: List[str] = list(raw_flags)

    raw_obs = _req("rubric_observations")
    if not isinstance(raw_obs, list):
        raise ValidationError("rubric_observations must be an array")
    observations: List[RubricObservation] = []
    for i, obs in enumerate(raw_obs):
        if not isinstance(obs, dict):
            raise ValidationError(f"rubric_observations[{i}] must be an object")
        r_id = obs.get("rubric_id")
        r_text = obs.get("observation")
        if not isinstance(r_id, str) or not r_id:
            raise ValidationError(
                f"rubric_observations[{i}].rubric_id missing or not a string"
            )
        if not isinstance(r_text, str) or not r_text:
            raise ValidationError(
                f"rubric_observations[{i}].observation missing or not a string"
            )
        score_delta = obs.get("score_delta")
        if score_delta is not None:
            if not isinstance(score_delta, int) or isinstance(score_delta, bool):
                raise ValidationError(
                    f"rubric_observations[{i}].score_delta must be an integer"
                )
            clamped_sd = max(_RUBRIC_SCORE_DELTA_MIN, min(_RUBRIC_SCORE_DELTA_MAX, score_delta))
            if clamped_sd != score_delta:
                logger.warning(
                    "rubric_observations[%d].score_delta clamped %d → %d",
                    i, score_delta, clamped_sd,
                )
            score_delta = clamped_sd
        observations.append(
            RubricObservation(rubric_id=r_id, observation=r_text, score_delta=score_delta)
        )

    raw_safety = _req("safety")
    if not isinstance(raw_safety, dict):
        raise ValidationError("safety must be an object")
    safety_status = raw_safety.get("status")
    if safety_status not in _VALID_SAFETY_STATUSES:
        raise ValidationError(
            f"safety.status missing or invalid: {safety_status!r}. "
            f"Valid values: {sorted(_VALID_SAFETY_STATUSES)}"
        )
    safety = SafetyStatus(status=safety_status, reason=raw_safety.get("reason"))

    raw_sc = _req("session_control")
    if not isinstance(raw_sc, dict):
        raise ValidationError("session_control must be an object")
    if "continue_session" not in raw_sc:
        raise ValidationError("session_control.continue_session is required")
    continue_session = raw_sc["continue_session"]
    if not isinstance(continue_session, bool):
        raise ValidationError("session_control.continue_session must be a boolean")
    ending_type = raw_sc.get("ending_type")
    if ending_type is not None and ending_type not in _VALID_ENDING_TYPES:
        raise ValidationError(
            f"session_control.ending_type invalid: {ending_type!r}. "
            f"Valid values: {sorted(_VALID_ENDING_TYPES)}"
        )
    session_control = SessionControl(
        continue_session=continue_session,
        ending_type=ending_type,
        ending_summary=raw_sc.get("ending_summary"),
    )

    return TurnOutput(
        npc_utterance=utterance,
        npc_emotion=emotion,
        state_delta=state_delta,
        event_flags=event_flags,
        rubric_observations=observations,
        safety=safety,
        session_control=session_control,
    )


def parse_turn_output(
    raw: str,
    runtime: Optional[RuntimeProtocol] = None,
) -> TurnOutput:
    """Parse raw LLM output into a TurnOutput.

    Parsing pipeline:
      1. Extract JSON from ``raw`` and validate it.
      2. If that fails and ``runtime`` is given: make exactly one repair call.
      3. If repair also fails or no runtime: return a safe fallback TurnOutput.

    This function never raises — it always returns a TurnOutput so sessions
    survive model drift or malformed output.
    """
    data = _extract_json(raw)
    if data is not None:
        try:
            return _validate(data)
        except ValidationError as exc:
            logger.warning("Turn output validation failed (will attempt repair): %s", exc)

    if runtime is not None:
        logger.debug("Requesting repaired turn output from runtime")
        try:
            repaired_raw = runtime.call_llm(_REPAIR_PROMPT)
            repaired_data = _extract_json(repaired_raw)
            if repaired_data is not None:
                return _validate(repaired_data)
            logger.warning("Repair attempt returned non-JSON output")
        except ValidationError as exc:
            logger.warning("Repair attempt produced invalid output: %s", exc)
        except Exception as exc:
            logger.warning("Repair runtime call raised: %s", exc)

    logger.debug("Returning SAFE_FALLBACK for turn output")
    return _make_safe_fallback()
