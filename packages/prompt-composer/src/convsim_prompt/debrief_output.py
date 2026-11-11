# SPDX-License-Identifier: Apache-2.0
"""Debrief narrative output parser, validator, repair, and fallback.

The LLM is asked to produce only the narrative portions of the debrief
(missed_opportunities, summary, strengths, improvements, turning_points,
replay_suggestions) and, with a rubric, each dimension's band.
Quantitative scores are computed separately from rubric_observations stored
per-turn and are never invented by the LLM.

Language guardrails built into DEBRIEF_SYSTEM_PREAMBLE keep the generated
text away from therapy, clinical diagnosis, legal claims, and real-world
performance guarantees.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence

logger = logging.getLogger(__name__)

# JSON schema passed to the runtime so it can use native JSON-mode if available.
#
# Property order is generation order: llama.cpp's schema-to-grammar writes the
# required properties in the order given, then the optional ones (issue #580).
# The missed opportunities come first and are required, so the model goes
# through the NPC's questions and the player's slips before it judges
# anything; optional, and so written last, they were empty in every debrief
# on the starter model although every player had left a question unanswered.
# The ``maxItems`` keep the reply inside the debrief's output budget
# (debrief_engine._DEBRIEF_MAX_TOKENS): a reply cut off there is invalid JSON,
# and the debrief falls back to the template.
DEBRIEF_NARRATIVE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "missed_opportunities",
        "summary",
        "strengths",
        "improvements",
        "turning_points",
        "replay_suggestions",
    ],
    "additionalProperties": False,
    "properties": {
        "missed_opportunities": {
            "type": "array",
            "description": (
                "Each NPC question the player's next line left unanswered, and each slip in "
                "the player's own words (a wrong fact, a grammar mistake): its turn, what "
                "happened, what to say instead. Empty only if there were none."
            ),
            "items": {"type": "string"},
            "maxItems": 4,
        },
        "summary": {
            "type": "string",
            "description": "2-3 sentence overview of how the practice session went.",
        },
        "strengths": {
            "type": "array",
            "description": (
                "Things the player did well, each citing a turn and quoting the player's "
                "own words from it."
            ),
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
        "improvements": {
            "type": "array",
            "description": (
                "Concrete areas to work on next time, each citing a turn and quoting the "
                "player's own words from it; never something the player already did."
            ),
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
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
            "maxItems": 3,
        },
        "replay_suggestions": {
            "type": "array",
            "description": "Actionable strategies worth trying in a replay.",
            "items": {"type": "string"},
            "maxItems": 2,
        },
    },
}

# The bands a debrief places each rubric dimension in (issue #578). The first
# three are the rubric's own ``scoring.low`` / ``medium`` / ``high``;
# "not_observed" is for a dimension the conversation gave the player no chance
# to show, which is left off the scorecard rather than scored at a guess.
DIMENSION_BANDS = ("low", "medium", "high", "not_observed")

# The property ``dimension_bands`` follows (see build_debrief_narrative_schema).
_BANDS_AFTER = "missed_opportunities"


def build_debrief_narrative_schema(
    *,
    rubric_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """The debrief output schema for one session: a fresh copy of the canonical one.

    With ``rubric_ids``, the schema also requires ``dimension_bands``: an
    object with one property per rubric dimension, each an ``enum`` of
    DIMENSION_BANDS. The keys are fixed and required, so a grammar built from
    the schema leaves the model only the band to choose. It is placed right
    after ``missed_opportunities``: llama.cpp's schema-to-grammar writes
    required properties in the order given, so the bands are judged against
    the rubric once the model has listed the questions the player left
    unanswered and the slips they made (issue #580), and before the summary,
    strengths and improvements, which follow from them. Without ids the
    result equals DEBRIEF_NARRATIVE_SCHEMA.
    """
    schema = copy.deepcopy(DEBRIEF_NARRATIVE_SCHEMA)
    ids = list(dict.fromkeys(i for i in (rubric_ids or ()) if isinstance(i, str) and i))
    if not ids:
        return schema
    bands = {
        "type": "object",
        "description": "Each rubric dimension's band, judged only on what the player said.",
        "properties": {i: {"type": "string", "enum": list(DIMENSION_BANDS)} for i in ids},
        "required": ids,
        "additionalProperties": False,
    }
    properties: Dict[str, Any] = {}
    for key, value in schema["properties"].items():
        properties[key] = value
        if key == _BANDS_AFTER:
            properties["dimension_bands"] = bands
    schema["properties"] = properties
    required = list(schema["required"])
    required.insert(required.index(_BANDS_AFTER) + 1, "dimension_bands")
    schema["required"] = required
    return schema


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
- Credit the player only with the player's own lines: what the NPC said is the \
NPC's, never the player's.
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
    missed_opportunities: List[str] = field(default_factory=list)
    used_fallback: bool = False
    # Rubric dimension id → one of DIMENSION_BANDS, as the model placed it.
    # Empty when the schema asked for none, the model gave none, or the
    # narrative is the template fallback.
    dimension_bands: Dict[str, str] = field(default_factory=dict)


def _make_fallback_narrative(
    outcome: str,
    scores: Dict[str, float],
    key_turns: List[Dict[str, Any]],
    dimension_names: Optional[Dict[str, str]] = None,
    overall_score: Optional[float] = None,
) -> DebriefNarrative:
    """Build a minimal but honest fallback narrative from structured data.

    Uses only data already stored in the database — never invents evidence.
    Dimensions are called by their rubric names when ``dimension_names`` has
    them, and the summary quotes ``overall_score`` (the scorecard's weighted
    figure) when given, else the plain average.
    """
    names = dimension_names or {}
    high_dims = [dim for dim, score in scores.items() if score >= 65]
    low_dims = [dim for dim, score in scores.items() if score < 40]

    summary_parts = [
        f"You completed a practice session that ended with outcome: {outcome}.",
    ]
    if scores:
        if overall_score is not None:
            summary_parts.append(
                f"Your overall score across tracked dimensions was {overall_score:.0f}/100."
            )
        else:
            avg = sum(scores.values()) / len(scores)
            summary_parts.append(
                f"Your overall average score across tracked dimensions was {avg:.0f}/100."
            )

    strengths: List[str] = []
    for dim in high_dims:
        name = names.get(dim, dim)
        strengths.append(f"Strong performance on '{name}' (score: {scores[dim]:.0f}).")
    if not strengths:
        strengths.append("You completed the session — keep practising to build confidence.")

    improvements: List[str] = []
    for dim in low_dims:
        name = names.get(dim, dim)
        improvements.append(f"Focus on '{name}' in your next attempt (score: {scores[dim]:.0f}).")
    if not improvements:
        if scores:
            improvements.append("Continue building on your existing strengths.")
        else:
            improvements.append("Try to engage more deeply with the scenario on your next attempt.")

    missed_opportunities: List[str] = []
    if outcome == "failure":
        missed_opportunities.append(
            "Review the transcript to identify turning points where a different approach might have changed the outcome."
        )
    elif outcome == "timeout":
        missed_opportunities.append(
            "Consider pacing the conversation more efficiently — you may have spent too long on early exchanges."
        )
    elif outcome == "player_exit":
        missed_opportunities.append(
            "Replaying with a different strategy can reveal how the NPC responds to alternative approaches."
        )

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
        missed_opportunities=missed_opportunities,
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

    raw_missed = data.get("missed_opportunities", [])
    if not isinstance(raw_missed, list):
        raise DebriefValidationError("missed_opportunities must be an array")
    missed: List[str] = []
    for i, s in enumerate(raw_missed):
        if not isinstance(s, str):
            raise DebriefValidationError(f"missed_opportunities[{i}] must be a string")
        missed.append(s)

    return DebriefNarrative(
        summary=summary,
        strengths=list(strengths),
        improvements=list(improvements),
        missed_opportunities=missed,
        turning_points=turning_points,
        replay_suggestions=replay,
        used_fallback=False,
        dimension_bands=_valid_bands(data.get("dimension_bands")),
    )


def _valid_bands(raw: Any) -> Dict[str, str]:
    """The well-formed entries of a ``dimension_bands`` object; never raises.

    A band is extra judgement on top of a narrative that is valid without it,
    so a missing or malformed one costs that dimension its band (it is scored
    from the turns alone), not the debrief its narrative.
    """
    if not isinstance(raw, dict):
        return {}
    return {
        k: v for k, v in raw.items()
        if isinstance(k, str) and k and isinstance(v, str) and v in DIMENSION_BANDS
    }


def parse_debrief_narrative(
    raw: str,
    fallback_outcome: str = "player_exit",
    fallback_scores: Optional[Dict[str, float]] = None,
    fallback_key_turns: Optional[List[Dict[str, Any]]] = None,
    runtime: Optional[RuntimeProtocol] = None,
    fallback_dimension_names: Optional[Dict[str, str]] = None,
    fallback_overall_score: Optional[float] = None,
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
        dimension_names=fallback_dimension_names,
        overall_score=fallback_overall_score,
    )
