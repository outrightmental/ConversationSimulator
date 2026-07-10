# SPDX-License-Identifier: Apache-2.0
"""Transcript export utilities: local JSON structure and human-readable Markdown."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def format_transcript_as_markdown(
    session_id: str,
    scenario_id: str,
    turns: List[Dict[str, Any]],
    debrief: Optional[Dict[str, Any]] = None,
    transcript_saved: bool = True,
) -> str:
    """Render a session transcript as human-readable Markdown.

    Arguments:
        session_id: The session identifier.
        scenario_id: The scenario identifier.
        turns: Ordered list of turn dicts (turn_number, role, content, emotion).
        debrief: Optional persisted debrief document to include in the export.
        transcript_saved: Whether transcript saving was enabled for this session.

    Returns:
        A Markdown-formatted string suitable for saving as a .md file.
    """
    lines: List[str] = []

    lines.append("# Session Transcript")
    lines.append("")
    lines.append(f"**Session ID**: `{session_id}`")
    lines.append(f"**Scenario**: {scenario_id}")
    lines.append("")

    if debrief:
        outcome = debrief.get("outcome", "unknown")
        total_turns = debrief.get("total_turns", 0)
        overall_score = debrief.get("overall_score")

        lines.append("## Debrief Summary")
        lines.append("")
        lines.append(f"**Outcome**: {outcome.replace('_', ' ').title()}")
        lines.append(f"**Total turns**: {total_turns}")
        if overall_score is not None:
            lines.append(f"**Overall score**: {round(overall_score)}/100")
        lines.append("")

        summary = debrief.get("summary", "")
        if summary:
            lines.append(summary)
            lines.append("")

        strengths = debrief.get("strengths", [])
        if strengths:
            lines.append("### Strengths")
            lines.append("")
            for item in strengths:
                lines.append(f"- {item}")
            lines.append("")

        improvements = debrief.get("improvements", [])
        if improvements:
            lines.append("### Areas for improvement")
            lines.append("")
            for item in improvements:
                lines.append(f"- {item}")
            lines.append("")

        missed = debrief.get("missed_opportunities", [])
        if missed:
            lines.append("### Missed opportunities")
            lines.append("")
            for item in missed:
                lines.append(f"- {item}")
            lines.append("")

        turning_points = debrief.get("turning_points", [])
        if turning_points:
            lines.append("### Key moments")
            lines.append("")
            for tp in turning_points:
                impact = tp.get("impact", "neutral")
                tn = tp.get("turn_number", "?")
                desc = tp.get("description", "")
                impact_icon = {"positive": "▲", "negative": "▼"}.get(impact, "–")
                lines.append(f"- **Turn {tn}** {impact_icon} {impact}: {desc}")
            lines.append("")

        replay = debrief.get("replay_suggestions", [])
        if replay:
            lines.append("### Try next time")
            lines.append("")
            for item in replay:
                lines.append(f"- {item}")
            lines.append("")

    lines.append("## Transcript")
    lines.append("")

    if not transcript_saved:
        lines.append("*Transcript saving was disabled for this session. Turn content is not available.*")
        lines.append("")
        return "\n".join(lines)

    if not turns:
        lines.append("*No turns recorded for this session.*")
        lines.append("")
        return "\n".join(lines)

    _ROLE_LABELS: Dict[str, str] = {
        "player": "You",
        "npc": "NPC",
        "npc_opening": "NPC (Opening)",
    }

    for turn in turns:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        turn_number = turn.get("turn_number", "?")
        emotion = turn.get("emotion")

        speaker = _ROLE_LABELS.get(role, role.replace("_", " ").title())
        header = f"### Turn {turn_number} — {speaker}"
        if emotion and emotion != "neutral":
            header += f" *(feeling: {emotion})*"

        lines.append(header)
        lines.append("")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)
