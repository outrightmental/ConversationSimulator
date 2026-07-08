# SPDX-License-Identifier: Apache-2.0
"""Debrief narrative output parser, validator, repair, and fallback.

The LLM is asked to produce only the narrative portions of the debrief
(summary, strengths, improvements, turning_points, replay_suggestions).
Quantitative scores are computed separately from rubric_observations stored
per-turn and are never invented by the LLM.

Language guardrails built into DEBRIEF_SYSTEM_PREAMBLE keep the generated
text away from therapy, clinical diagnosis, legal claims, and real-world
performance guarantees.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

# JSON schema passed to the runtime so it can use native JSON-mode if available.
DEBRIEF_NARRATIVE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["summary", "strengths", "improvements", "turning_points", "replay_suggestions"],
    "additionalProperties": False,
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentence overview of how the practice session went.",
        },
        "strengths": {
            "type": "array",
            "description": "Specific things the player did well, with transcript evidence.",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "improvements": {
            "type": "array",
            "description": "Concrete areas to work on in the next attempt.",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "turning_points": {
            "type": "array",
            "description": "Key moments that shifted the conversation outcome.",
            "items": {
                "type": "object",
                "required": ["turn_number", "description", "impact"],
                "additionalProperties": False,
                "properties": {
                    "turn_number": {"type": "integer", "minimum": 0},
                    "description": {"type": "string"},
                    "impact": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral"],
                    },
                },
            },
        },
        "replay_suggestions": {
            "type": "array",
            "description": "Actionable strategies worth trying in a replay.",
            "items": {"type": "string"},
        },
    },
}

DEBRIEF_SYSTEM_PREAMBLE = """\
You are a practice-session coach for a conversation simulator. Your role is \
strictly educational: you help players improve communication skills through \
fictional practice scenarios.

HARD RULES — never violate:
- Do not provide therapy, counselling, clinical assessment, or mental-health advice.
- Do not make diagnoses or suggest medical or legal action.
- Do not claim that performance in this simulation predicts real-world outcomes.
- Do not reference the player by their real name; use second-person ("you").
- Cite transcript evidence using turn numbers or short quoted snippets only — \
  do not invent content that does not appear in the transcript.
- Keep language constructive, specific, and grounded in what happened in this session.
"""

_REPAIR_PROMPT = (
    "Your previous response did not produce valid debrief JSON. "
    "Return ONLY a valid JSON object matching this schema — no markdown fences, "
    "no explanation, no text outside the JSON object itself:\n"
    + json.dumps(DEBRIEF_NARRATIVE_SCHEMA, indent=2)
)

_VALID_IMPACTS = frozenset({"positive", "negative", "neutral"})


class DebriefValidationError(ValueError):
    """Raised when a debrief narrative fails schema or semantic validation."""


class RuntimeProtocol(Protocol):
    def call_llm(self, prompt: str) -> str: ...


@dataclass
class TurningPoint:
    turn_number: int
    description: str
    impact: str = "neutral"


@dataclass
class DebriefNarrative:
    summary: str
    strengths: List[str]
    improvements: List[str]
    turning_points: List[TurningPoint]
    replay_suggestions: List[str] = field(default_factory=list)
    used_fallback: bool = False


def _make_fallback_narrative(
    outcome: str,
    scores: Dict[str, float],
    key_turns: List[Dict[str, Any]],
) -> DebriefNarrative:
    """Build a minimal but honest fallback narrative from structured data.

    Uses only data already stored in the database — never invents evidence.
    """
    high_dims = [dim for dim, score in scores.items() if score >= 65]
    low_dims = [dim for dim, score in scores.items() if score < 40]

    summary_parts = [
        f"You completed a practice session that ended with outcome: {outcome}.",
    ]
    if scores:
        avg = sum(scores.values()) / len(scores)
        summary_parts.append(f"Your overall average score across tracked dimensions was {avg:.0f}/100.")

    strengths: List[str] = []
    for dim in high_dims:
        strengths.append(f"Strong performance on '{dim}' (score: {scores[dim]:.0f}).")
    if not strengths:
        strengths.append("You completed the session — keep practising to build confidence.")

    improvements: List[str] = []
    for dim in low_dims:
        improvements.append(f"Focus on '{dim}' in your next attempt (score: {scores[dim]:.0f}).")
    if not improvements:
        if scores:
            improvements.append("Continue building on your existing strengths.")
        else:
            improvements.append("Try to engage more deeply with the scenario on your next attempt.")

    turning_points: List[TurningPoint] = []
    for kt in key_turns[:3]:
        turning_points.append(TurningPoint(
            turn_number=kt["turn_number"],
            description=kt.get("description", "A notable moment in the conversation."),
            impact=kt.get("impact", "neutral"),
        ))

    replay_suggestions = [
        "Review the transcript to identify moments where the NPC's response shifted.",
        "Try adjusting your opening approach to set a different tone.",
    ]

    return DebriefNarrative(
        summary=" ".join(summary_parts),
        strengths=strengths,
        improvements=improvements,
        turning_points=turning_points,
        replay_suggestions=replay_suggestions,
        used_fallback=True,
    )


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
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
            obj = json.loads(text[start: end + 1])
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


def _validate_narrative(data: Dict[str, Any]) -> DebriefNarrative:
    def _req(key: str) -> Any:
        if key not in data:
            raise DebriefValidationError(f"Missing required field: {key}")
        return data[key]

    summary = _req("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise DebriefValidationError("summary must be a non-empty string")

    strengths = _req("strengths")
    if not isinstance(strengths, list) or not strengths:
        raise DebriefValidationError("strengths must be a non-empty array")
    for i, s in enumerate(strengths):
        if not isinstance(s, str):
            raise DebriefValidationError(f"strengths[{i}] must be a string")

    improvements = _req("improvements")
    if not isinstance(improvements, list) or not improvements:
        raise DebriefValidationError("improvements must be a non-empty array")
    for i, s in enumerate(improvements):
        if not isinstance(s, str):
            raise DebriefValidationError(f"improvements[{i}] must be a string")

    raw_tps = _req("turning_points")
    if not isinstance(raw_tps, list):
        raise DebriefValidationError("turning_points must be an array")
    turning_points: List[TurningPoint] = []
    for i, tp in enumerate(raw_tps):
        if not isinstance(tp, dict):
            raise DebriefValidationError(f"turning_points[{i}] must be an object")
        tn = tp.get("turn_number")
        desc = tp.get("description")
        impact = tp.get("impact", "neutral")
        if not isinstance(tn, int) or tn < 0:
            raise DebriefValidationError(
                f"turning_points[{i}].turn_number must be a non-negative integer"
            )
        if not isinstance(desc, str) or not desc.strip():
            raise DebriefValidationError(
                f"turning_points[{i}].description must be a non-empty string"
            )
        if impact not in _VALID_IMPACTS:
            raise DebriefValidationError(
                f"turning_points[{i}].impact must be one of {sorted(_VALID_IMPACTS)}"
            )
        turning_points.append(TurningPoint(turn_number=tn, description=desc, impact=impact))

    raw_replay = data.get("replay_suggestions", [])
    if not isinstance(raw_replay, list):
        raise DebriefValidationError("replay_suggestions must be an array")
    replay: List[str] = []
    for i, s in enumerate(raw_replay):
        if not isinstance(s, str):
            raise DebriefValidationError(f"replay_suggestions[{i}] must be a string")
        replay.append(s)

    return DebriefNarrative(
        summary=summary,
        strengths=list(strengths),
        improvements=list(improvements),
        turning_points=turning_points,
        replay_suggestions=replay,
        used_fallback=False,
    )


def parse_debrief_narrative(
    raw: str,
    fallback_outcome: str = "player_exit",
    fallback_scores: Optional[Dict[str, float]] = None,
    fallback_key_turns: Optional[List[Dict[str, Any]]] = None,
    runtime: Optional[RuntimeProtocol] = None,
) -> DebriefNarrative:
    """Parse raw LLM output into a DebriefNarrative.

    Falls back to a template-based narrative built from structured data so the
    debrief is always useful and never invents transcript evidence.
    """
    data = _extract_json(raw)
    if data is not None:
        try:
            return _validate_narrative(data)
        except DebriefValidationError as exc:
            logger.warning("Debrief narrative validation failed (will attempt repair): %s", exc)

    if runtime is not None:
        logger.debug("Requesting repaired debrief narrative from runtime")
        try:
            repaired_raw = runtime.call_llm(_REPAIR_PROMPT)
            repaired_data = _extract_json(repaired_raw)
            if repaired_data is not None:
                return _validate_narrative(repaired_data)
            logger.warning("Debrief repair attempt returned non-JSON output")
        except DebriefValidationError as exc:
            logger.warning("Debrief repair attempt produced invalid output: %s", exc)
        except Exception as exc:
            logger.warning("Debrief repair runtime call raised: %s", exc)

    logger.debug("Returning fallback debrief narrative")
    return _make_fallback_narrative(
        outcome=fallback_outcome,
        scores=fallback_scores or {},
        key_turns=fallback_key_turns or [],
    )
