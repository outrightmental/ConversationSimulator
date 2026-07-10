# SPDX-License-Identifier: Apache-2.0
"""Builds a debrief prompt from session data for the narrative generation step.

The prompt is structured so that:
- The system message contains guardrails, scenario context, rubric definitions,
  and the JSON output schema.
- The user message contains the scored transcript and per-turn rubric observations.

This separation ensures the LLM cannot override the schema or guardrails via
user-turn injection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .debrief_output import DEBRIEF_NARRATIVE_SCHEMA, DEBRIEF_SYSTEM_PREAMBLE
from .types import PromptBundle


@dataclass
class DebriefTurnRecord:
    turn_number: int
    role: str
    content: str
    rubric_observations: List[Dict[str, Any]] = field(default_factory=list)
    state_delta: Dict[str, int] = field(default_factory=dict)
    event_flags: List[str] = field(default_factory=list)


@dataclass
class DebriefComposerInput:
    session_id: str
    scenario_id: str
    scenario_title: str
    player_role_label: str
    outcome: str
    total_turns: int
    final_state: Dict[str, int]
    scores: Dict[str, float]
    turns: List[DebriefTurnRecord]
    rubric_dimension_names: Dict[str, str] = field(default_factory=dict)
    pack_id: Optional[str] = None
    difficulty_preset: Optional[str] = None


def _format_transcript(turns: List[DebriefTurnRecord]) -> str:
    lines: List[str] = []
    for t in turns:
        speaker = t.role.replace("_", " ").title()
        lines.append(f"[Turn {t.turn_number}] {speaker}: {t.content}")
        if t.rubric_observations:
            for obs in t.rubric_observations:
                delta_str = ""
                if obs.get("score_delta") is not None:
                    delta_str = f" (Δ{obs['score_delta']:+d})"
                lines.append(
                    f"  [Rubric '{obs['rubric_id']}'{delta_str}]: {obs['observation']}"
                )
        if t.event_flags:
            lines.append(f"  [Flags]: {', '.join(t.event_flags)}")
    return "\n".join(lines)


def _format_scores(
    scores: Dict[str, float],
    dim_names: Dict[str, str],
) -> str:
    if not scores:
        return "(no rubric dimensions scored)"
    lines: List[str] = []
    for dim_id, score in scores.items():
        name = dim_names.get(dim_id, dim_id)
        lines.append(f"  {name} ({dim_id}): {score:.0f}/100")
    return "\n".join(lines)


def compose_debrief_prompt(inp: DebriefComposerInput) -> PromptBundle:
    """Build a debrief prompt bundle for narrative generation.

    The system prompt contains guardrails + schema. The user prompt contains
    the full scored transcript and final state so the LLM can reference
    real turn numbers and observed behaviour.
    """
    system_parts: List[str] = [
        DEBRIEF_SYSTEM_PREAMBLE.strip(),
        f"SCENARIO: {inp.scenario_title} (id: {inp.scenario_id})",
        f"PLAYER ROLE: {inp.player_role_label}",
        f"OUTCOME: {inp.outcome}",
        *(
            [f"DIFFICULTY PRESET: {inp.difficulty_preset}"]
            if inp.difficulty_preset
            else []
        ),
        "---",
        "DIMENSION SCORES (computed from per-turn rubric observations):",
        _format_scores(inp.scores, inp.rubric_dimension_names),
        "---",
        (
            "OUTPUT SCHEMA — respond with ONLY this JSON object, no markdown fences "
            "or extra text:\n" + json.dumps(DEBRIEF_NARRATIVE_SCHEMA, indent=2)
        ),
    ]
    system_prompt = "\n\n".join(system_parts)

    transcript_text = _format_transcript(inp.turns)
    state_text = (
        "\n".join(f"  {k}: {v}" for k, v in inp.final_state.items())
        if inp.final_state
        else "  (no tracked state)"
    )
    user_parts: List[str] = [
        "SESSION TRANSCRIPT WITH RUBRIC OBSERVATIONS:",
        transcript_text if transcript_text else "(empty transcript)",
        "---",
        "FINAL NPC STATE:",
        state_text,
        "---",
        (
            "Generate a coaching debrief in the JSON format specified above. "
            "Reference specific turn numbers when citing transcript evidence. "
            "Keep language educational and constructive. "
            "This is a simulated practice session — do not make claims about "
            "real-world performance or outcomes."
        ),
    ]
    user_prompt = "\n\n".join(user_parts)

    estimated_tokens = max(1, (len(system_prompt) + len(user_prompt)) // 4)
    layer_map = {
        "DEBRIEF_SYSTEM": system_prompt,
        "DEBRIEF_USER": user_prompt,
    }

    return PromptBundle(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        layer_map=layer_map,
        estimated_token_count=estimated_tokens,
        was_truncated=False,
    )
