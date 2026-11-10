# SPDX-License-Identifier: Apache-2.0
"""Build a turn from released words and whatever bookkeeping completed (#538).

Once a sentence of the NPC's line has been shown to the player it is committed:
no retry, no retraction (issue #538, design point 4). So when the stream stops
early — a later sentence failed the output check, the token cap cut the JSON,
or the engine went quiet — the turn is built from what is certain: the released
line, plus every field of the model's JSON that closed before the cut. Missing
or malformed fields take the same defaults the parser's safe fallback uses:
no state change, no observations, the session continues. Such a turn is marked
``salvaged``. No model call is made.

This is the slice of #527 that streaming cannot do without; the rest of #527
(repair on the event loop, contextual regeneration) stays there.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from convsim_prompt.turn_output import (
    RubricObservation,
    SafetyStatus,
    SessionControl,
    TurnOutput,
    ValidationError,
    _enforce_safety_consistency,
    _extract_json,
    _validate,
)

logger = logging.getLogger(__name__)

_VALID_EMOTIONS = frozenset({
    "neutral", "warm", "curious", "skeptical", "impatient",
    "defensive", "confused", "impressed", "concerned", "angry",
})
_VALID_SAFETY = frozenset({"ok", "redirect", "stop"})
_VALID_ENDINGS = frozenset({"none", "success", "failure", "timeout", "safety_stop", "player_exit"})
_DELTA_MIN, _DELTA_MAX = -20, 20
_SCORE_MIN, _SCORE_MAX = -3, 3


@dataclass
class SalvageResult:
    output: TurnOutput
    #: True when any field had to be defaulted or the JSON was incomplete.
    salvaged: bool
    #: Which of the model's fields were kept as written.
    kept_fields: List[str] = field(default_factory=list)
    #: Which fields were defaulted, and why.
    defaulted: Dict[str, str] = field(default_factory=dict)


def partial_object(raw: str) -> Optional[Dict[str, Any]]:
    """Parse what closed before the cut in a JSON object that was cut off.

    Walks the text tracking strings and nesting, and remembers every position
    where a value had just closed at the top level or one level down (an
    element of a member that is an array or object), together with the
    brackets still open there. Candidates are tried longest first with those
    brackets closed, so a cut inside ``rubric_observations`` keeps every
    observation that was complete and drops only the one the cut landed in.
    Returns None when not even the first member is whole.
    """
    start = raw.find("{")
    if start == -1:
        return None
    stack: List[str] = []
    in_string = False
    escape = False
    cut_points: List[tuple[int, str]] = []
    closers = {"{": "}", "[": "]"}

    def record(pos: int) -> None:
        if 1 <= len(stack) <= 2:
            cut_points.append((pos, "".join(closers[b] for b in reversed(stack))))

    for i in range(start, len(raw)):
        ch = raw[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
                record(i + 1)
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if not stack:
                try:
                    obj = json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    break
                return obj if isinstance(obj, dict) else None
            record(i + 1)
        elif ch == ",":
            record(i)
    for pos, closing in reversed(cut_points):
        candidate = raw[start:pos].rstrip().rstrip(",") + closing
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _complete_dict(raw_text: str, structured: Optional[Dict[str, Any]]) -> tuple[Optional[Dict[str, Any]], bool]:
    """The model's object, and whether it was whole."""
    if structured is not None:
        return structured, True
    whole = _extract_json(raw_text)
    if whole is not None:
        return whole, True
    return partial_object(raw_text), False


def salvage_turn_output(
    raw_text: str,
    structured: Optional[Dict[str, Any]],
    released_line: str,
    *,
    force_defaults: bool = False,
) -> SalvageResult:
    """Make a TurnOutput whose spoken line is exactly ``released_line``.

    With ``force_defaults`` every bookkeeping field is defaulted regardless of
    what the model wrote — used when a later sentence of the line failed the
    output check, where the model's state changes described a line the player
    did not get.
    """
    data, whole = _complete_dict(raw_text, structured)
    kept: List[str] = []
    defaulted: Dict[str, str] = {}

    if whole and not force_defaults and data is not None:
        try:
            output = _validate(dict(data, npc_utterance=released_line))
            _enforce_safety_consistency(output)
            return SalvageResult(output=output, salvaged=False, kept_fields=sorted(k for k in data if k != "npc_utterance"))
        except ValidationError as exc:
            defaulted["_validation"] = str(exc)

    data = {} if (data is None or force_defaults) else data
    if force_defaults:
        defaulted["_all"] = "a later sentence failed the output check; bookkeeping defaulted"
    elif not whole:
        defaulted["_json"] = "the model's JSON was cut off before it closed"

    emotion = data.get("npc_emotion")
    if isinstance(emotion, str) and emotion in _VALID_EMOTIONS:
        kept.append("npc_emotion")
    else:
        if "npc_emotion" in data:
            defaulted["npc_emotion"] = f"invalid: {emotion!r}"
        emotion = "neutral"

    state_delta: Dict[str, int] = {}
    raw_delta = data.get("state_delta")
    if isinstance(raw_delta, dict) and all(
        isinstance(v, int) and not isinstance(v, bool) for v in raw_delta.values()
    ):
        state_delta = {k: max(_DELTA_MIN, min(_DELTA_MAX, int(v))) for k, v in raw_delta.items()}
        kept.append("state_delta")
    elif "state_delta" in data:
        defaulted["state_delta"] = "not an object of integers"

    event_flags: List[str] = []
    raw_flags = data.get("event_flags")
    if isinstance(raw_flags, list) and all(isinstance(f, str) for f in raw_flags):
        event_flags = list(raw_flags)
        kept.append("event_flags")
    elif "event_flags" in data:
        defaulted["event_flags"] = "not a list of strings"

    observations: List[RubricObservation] = []
    raw_obs = data.get("rubric_observations")
    if isinstance(raw_obs, list):
        complete = 0
        for obs in raw_obs:
            if not isinstance(obs, dict):
                continue
            rid, text = obs.get("rubric_id"), obs.get("observation")
            if not (isinstance(rid, str) and rid and isinstance(text, str) and text):
                continue
            score = obs.get("score_delta")
            if isinstance(score, bool) or not isinstance(score, int):
                score = None
            else:
                score = max(_SCORE_MIN, min(_SCORE_MAX, score))
            observations.append(RubricObservation(rubric_id=rid, observation=text, score_delta=score))
            complete += 1
        if complete:
            kept.append("rubric_observations")
    elif "rubric_observations" in data:
        defaulted["rubric_observations"] = "not a list"

    safety = SafetyStatus(status="ok")
    raw_safety = data.get("safety")
    if isinstance(raw_safety, dict) and raw_safety.get("status") in _VALID_SAFETY:
        safety = SafetyStatus(status=raw_safety["status"], reason=raw_safety.get("reason"))
        kept.append("safety")
    elif "safety" in data:
        defaulted["safety"] = "missing or invalid status"

    control = SessionControl(continue_session=True)
    raw_control = data.get("session_control")
    if isinstance(raw_control, dict) and isinstance(raw_control.get("continue_session"), bool):
        ending = raw_control.get("ending_type")
        if ending is not None and ending not in _VALID_ENDINGS:
            ending = None
        control = SessionControl(
            continue_session=raw_control["continue_session"],
            ending_type=ending,
            ending_summary=raw_control.get("ending_summary"),
        )
        kept.append("session_control")
    elif "session_control" in data:
        defaulted["session_control"] = "missing or invalid continue_session"

    output = TurnOutput(
        npc_utterance=released_line,
        npc_emotion=emotion,
        state_delta=state_delta,
        event_flags=event_flags,
        rubric_observations=observations,
        safety=safety,
        session_control=control,
    )
    _enforce_safety_consistency(output)
    return SalvageResult(output=output, salvaged=True, kept_fields=kept, defaulted=defaulted)
