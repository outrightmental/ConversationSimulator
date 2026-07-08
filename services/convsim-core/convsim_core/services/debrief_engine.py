# SPDX-License-Identifier: Apache-2.0
"""Debrief generation engine.

Processing steps:
  1. Load all turns + raw LLM output for the session from the database.
  2. Compute per-rubric-dimension scores from accumulated rubric_observations.
  3. Compute overall weighted score.
  4. Identify key turning points from state changes, event flags, safety events.
  5. Build a debrief prompt with scenario context, transcript, and observed scores.
  6. Call the ChatRuntime and parse/repair/fallback the debrief narrative JSON.
  7. Assemble and persist the full debrief document.
  8. Transition session flow_state to DebriefReady (or Error on failure).

Language rules (enforced via DEBRIEF_SYSTEM_PREAMBLE):
  - No therapy, clinical assessment, or mental-health advice.
  - No real-world performance guarantees.
  - Evidence cited by turn number only — no invented quotes.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from convsim_prompt import (
    DEBRIEF_NARRATIVE_SCHEMA,
    DebriefNarrative,
    DebriefTurnRecord,
    compose_debrief_prompt,
    parse_debrief_narrative,
)
from convsim_prompt.debrief_composer import DebriefComposerInput
from convsim_prompt.types import ScenarioData

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest, ChatToken

logger = logging.getLogger(__name__)

# Neutral baseline for rubric dimension scores (0–100 scale).
_SCORE_BASELINE = 50.0
_SCORE_MIN = 0.0
_SCORE_MAX = 100.0


@dataclass
class DebriefResult:
    session_id: str
    scenario_id: str
    pack_id: Optional[str]
    outcome: str
    total_turns: int
    scores: Dict[str, float]
    overall_score: Optional[float]
    summary: str
    strengths: List[str]
    improvements: List[str]
    turning_points: List[Dict[str, Any]]
    replay_suggestions: List[str]
    npc_final_state: Dict[str, int]
    generated_at: str
    used_fallback: bool = False


def _parse_rubric_observations(raw_output_json: Optional[str]) -> List[Dict[str, Any]]:
    """Extract rubric_observations list from a stored raw LLM output string."""
    if not raw_output_json:
        return []
    try:
        data = json.loads(raw_output_json)
        obs = data.get("rubric_observations")
        if isinstance(obs, list):
            return obs
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


def _compute_scores(
    npc_turns: List[sqlite3.Row],
) -> Dict[str, float]:
    """Accumulate rubric dimension scores from per-turn rubric_observations.

    Each NPC turn may contain rubric observations with optional score_deltas
    in the range [-3, 3]. Starting from a baseline of 50, deltas are summed and
    the final value is clamped to [0, 100].

    Only dimensions that appear in at least one observation are scored.
    """
    accumulators: Dict[str, float] = {}

    for turn in npc_turns:
        observations = _parse_rubric_observations(turn["raw_output_json"])
        for obs in observations:
            rubric_id = obs.get("rubric_id")
            score_delta = obs.get("score_delta")
            if not isinstance(rubric_id, str) or not rubric_id:
                continue
            if rubric_id not in accumulators:
                accumulators[rubric_id] = _SCORE_BASELINE
            if isinstance(score_delta, int) and not isinstance(score_delta, bool):
                # score_delta already validated/clamped by the turn pipeline
                accumulators[rubric_id] += score_delta

    return {
        dim_id: max(_SCORE_MIN, min(_SCORE_MAX, score))
        for dim_id, score in accumulators.items()
    }


def _compute_overall_score(scores: Dict[str, float]) -> Optional[float]:
    """Compute overall score as simple average (or None if no dimensions scored)."""
    if not scores:
        return None
    return round(sum(scores.values()) / len(scores), 1)


def _identify_key_turns(
    npc_turns: List[sqlite3.Row],
) -> List[Dict[str, Any]]:
    """Identify turns with significant state changes or notable events.

    Returns a list of dicts ready for fallback narrative generation,
    each containing turn_number, description, and impact.
    """
    key: List[Dict[str, Any]] = []

    for turn in npc_turns:
        turn_number = turn["turn_number"]
        state_delta: Dict[str, int] = {}
        if turn["state_delta_json"]:
            try:
                state_delta = json.loads(turn["state_delta_json"])
            except json.JSONDecodeError:
                pass

        event_flags: List[str] = []
        if turn["event_flags_json"]:
            try:
                event_flags = json.loads(turn["event_flags_json"])
            except json.JSONDecodeError:
                pass

        safety_status = "ok"
        if turn["safety_json"]:
            try:
                safety_status = json.loads(turn["safety_json"]).get("status", "ok")
            except (json.JSONDecodeError, AttributeError):
                pass

        # Significant state change: any single variable changed by ≥8 points.
        big_changes = {k: v for k, v in state_delta.items() if abs(v) >= 8}
        if big_changes:
            direction = "positive" if sum(big_changes.values()) > 0 else "negative"
            vars_str = ", ".join(
                f"{k} {v:+d}" for k, v in sorted(big_changes.items())
            )
            key.append({
                "turn_number": turn_number,
                "description": f"Significant state shift at turn {turn_number}: {vars_str}.",
                "impact": direction,
            })
        elif safety_status in ("redirect", "stop"):
            key.append({
                "turn_number": turn_number,
                "description": f"Safety {safety_status} triggered at turn {turn_number}.",
                "impact": "negative",
            })
        elif event_flags:
            key.append({
                "turn_number": turn_number,
                "description": (
                    f"Event flags raised at turn {turn_number}: {', '.join(event_flags)}."
                ),
                "impact": "neutral",
            })

    return key


def _build_debrief_turn_records(
    all_turns: List[sqlite3.Row],
) -> List[DebriefTurnRecord]:
    """Convert DB rows into DebriefTurnRecord objects for the prompt composer."""
    records: List[DebriefTurnRecord] = []
    for turn in all_turns:
        obs = _parse_rubric_observations(turn["raw_output_json"])
        state_delta: Dict[str, int] = {}
        if turn["state_delta_json"]:
            try:
                state_delta = json.loads(turn["state_delta_json"])
            except json.JSONDecodeError:
                pass
        event_flags: List[str] = []
        if turn["event_flags_json"]:
            try:
                event_flags = json.loads(turn["event_flags_json"])
            except json.JSONDecodeError:
                pass
        records.append(DebriefTurnRecord(
            turn_number=turn["turn_number"],
            role=turn["role"],
            content=turn["content"],
            rubric_observations=obs,
            state_delta=state_delta,
            event_flags=event_flags,
        ))
    return records


async def _collect_runtime_output(runtime: ChatRuntime, request: ChatRequest) -> str:
    raw_text = ""
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            raw_text = chunk.text
            break
        elif isinstance(chunk, ChatToken):
            raw_text += chunk.text
    return raw_text


async def generate_debrief(
    session_row: sqlite3.Row,
    conn: sqlite3.Connection,
    runtime: ChatRuntime,
    scenario_data: ScenarioData,
) -> DebriefResult:
    """Generate, persist, and return a debrief for a completed session.

    Transitions the session through DebriefGenerating → DebriefReady/Error.
    Always returns a DebriefResult (falls back to template narrative on LLM error).
    """
    session_id: str = session_row["session_id"]
    scenario_id: str = session_row["scenario_id"]
    setup: Dict[str, Any] = json.loads(session_row["setup_json"] or "{}")
    pack_id: Optional[str] = setup.get("pack_id")
    outcome: str = session_row["ending_type"] or "player_exit"
    final_state: Dict[str, int] = json.loads(session_row["state_vars_json"] or "{}")
    total_turns: int = int(session_row["turn_count"])
    now = datetime.now(timezone.utc).isoformat()

    # Transition to DebriefGenerating.
    conn.execute(
        "UPDATE turn_sessions SET flow_state = 'DebriefGenerating' WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()

    try:
        # Load all turns for transcript.
        all_turn_rows = conn.execute(
            "SELECT turn_number, role, content, emotion, state_delta_json, "
            "event_flags_json, safety_json, raw_output_json "
            "FROM turn_session_turns WHERE session_id = ? ORDER BY turn_number ASC",
            (session_id,),
        ).fetchall()

        # NPC turns hold raw_output_json with rubric_observations.
        npc_turn_rows = [r for r in all_turn_rows if r["role"] == "npc"]

        # Compute scores.
        scores = _compute_scores(npc_turn_rows)
        overall_score = _compute_overall_score(scores)

        # Identify key turning points for fallback and for the LLM.
        key_turns = _identify_key_turns(npc_turn_rows)

        # Build prompt.
        turn_records = _build_debrief_turn_records(all_turn_rows)
        composer_input = DebriefComposerInput(
            session_id=session_id,
            scenario_id=scenario_id,
            scenario_title=scenario_data.title,
            player_role_label=scenario_data.player_role_label,
            outcome=outcome,
            total_turns=total_turns,
            final_state=final_state,
            scores=scores,
            turns=turn_records,
            pack_id=pack_id,
        )
        prompt = compose_debrief_prompt(composer_input)

        # Call runtime.
        messages = [
            ChatMessage(role="system", content=prompt.system_prompt),
            ChatMessage(role="user", content=prompt.user_prompt),
        ]
        request = ChatRequest(
            messages=messages,
            json_schema=DEBRIEF_NARRATIVE_SCHEMA,
        )
        logger.debug(
            "Calling runtime %s for debrief of session %s (~%d tokens)",
            runtime.id, session_id, prompt.estimated_token_count,
        )
        raw_text = await _collect_runtime_output(runtime, request)

        # Build set of turn numbers actually stored for this session.
        stored_turn_numbers = {r["turn_number"] for r in all_turn_rows}

        # Validate / repair / fallback.
        narrative: DebriefNarrative = parse_debrief_narrative(
            raw_text,
            fallback_outcome=outcome,
            fallback_scores=scores,
            fallback_key_turns=key_turns,
        )

        # Drop any turning points that reference turn numbers not in the transcript.
        # This prevents invented evidence regardless of whether we got LLM or fallback output.
        valid_turning_points = [
            tp for tp in narrative.turning_points
            if tp.turn_number in stored_turn_numbers
        ]
        if len(valid_turning_points) < len(narrative.turning_points):
            dropped = len(narrative.turning_points) - len(valid_turning_points)
            logger.warning(
                "Dropped %d turning point(s) with invalid turn numbers for session %s",
                dropped, session_id,
            )
            narrative.turning_points = valid_turning_points

        if narrative.used_fallback:
            logger.warning("Debrief for session %s used fallback narrative", session_id)

        # Assemble full debrief document.
        debrief_doc: Dict[str, Any] = {
            "schema_version": "0.1",
            "session_id": session_id,
            "scenario_id": scenario_id,
            "outcome": outcome,
            "total_turns": total_turns,
            "scores": {k: round(v, 1) for k, v in scores.items()},
            "overall_score": overall_score,
            "summary": narrative.summary,
            "strengths": narrative.strengths,
            "improvements": narrative.improvements,
            "turning_points": [
                {
                    "turn_number": tp.turn_number,
                    "description": tp.description,
                    "impact": tp.impact,
                }
                for tp in narrative.turning_points
            ],
            "replay_suggestions": narrative.replay_suggestions,
            "npc_final_state": final_state,
            "generated_at": now,
            "used_fallback": narrative.used_fallback,
        }
        if pack_id:
            debrief_doc["pack_id"] = pack_id

        # Persist and transition to DebriefReady.
        with conn:
            conn.execute(
                "INSERT INTO session_debriefs (session_id, content_json, generated_at) "
                "VALUES (?, ?, ?)",
                (session_id, json.dumps(debrief_doc), now),
            )
            conn.execute(
                "UPDATE turn_sessions SET flow_state = 'DebriefReady' WHERE session_id = ?",
                (session_id,),
            )

        logger.debug("Debrief persisted for session %s (fallback=%s)", session_id, narrative.used_fallback)

        return DebriefResult(
            session_id=session_id,
            scenario_id=scenario_id,
            pack_id=pack_id,
            outcome=outcome,
            total_turns=total_turns,
            scores={k: round(v, 1) for k, v in scores.items()},
            overall_score=overall_score,
            summary=narrative.summary,
            strengths=narrative.strengths,
            improvements=narrative.improvements,
            turning_points=debrief_doc["turning_points"],
            replay_suggestions=narrative.replay_suggestions,
            npc_final_state=final_state,
            generated_at=now,
            used_fallback=narrative.used_fallback,
        )

    except Exception as exc:
        logger.error("Debrief generation failed for session %s: %s", session_id, exc)
        conn.execute(
            "UPDATE turn_sessions SET flow_state = 'Error' WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        raise
