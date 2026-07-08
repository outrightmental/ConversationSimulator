# SPDX-License-Identifier: Apache-2.0
"""End-to-end text-only player turn pipeline.

Processing steps (SPEC §6):
  1. Normalize player text: strip, reject empty, reject oversized.
  2. Input safety precheck via placeholder policy hook.
  3. Build prompt context: scenario, NPC, state, transcript, rubric, player utterance.
  4. Call ChatRuntime and collect the structured response.
  5. Validate / repair / fallback the model response.
  6. Apply bounded state deltas.
  7. Evaluate scenario event triggers and ending conditions.
  8. Persist player turn, NPC turn, and updated session state atomically.
  9. Return a TurnPipelineResult.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from convsim_prompt import (
    NPC_TURN_OUTPUT_SCHEMA,
    SAFE_FALLBACK_UTTERANCE,
    PromptComposerInput,
    SafetyPolicy,
    SessionState as PromptSessionState,
    TranscriptEntry,
    compose_turn_prompt,
    parse_turn_output,
)
from convsim_prompt.types import ScenarioData

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest, ChatToken
from convsim_core.scenario_state import (
    apply_state_delta,
    build_variable_defs,
    evaluate_ending_condition,
    evaluate_event_triggers,
    initialize_state,
    partition_state_by_visibility,
)

logger = logging.getLogger(__name__)

MAX_TURN_CONTENT_CHARS = 2000

# Default safety policy used when no scenario-specific policy is configured.
_DEFAULT_SAFETY_POLICY = SafetyPolicy(
    policy_id="default_pg",
    content_rating="PG",
    prohibited=[
        "NSFW or sexually explicit content",
        "Real-person impersonation",
        "Medical, legal, or therapeutic advice presented as authoritative",
        "Instructions for illegal activities",
        "Hate speech or targeted harassment",
    ],
    redirects={
        "nsfw": "I'd prefer to keep our conversation professional. Let's refocus.",
        "illegal": "That's not something I can discuss. Let me steer us back on track.",
    },
)


class TurnInputError(ValueError):
    """Raised when player input fails validation before the pipeline runs."""


@dataclass
class TurnPipelineResult:
    player_content: str
    player_event_id: int
    npc_utterance: str
    npc_emotion: str
    npc_event_id: int
    state_delta: Dict[str, int]
    new_state_vars: Dict[str, int]
    visible_state: Dict[str, int]
    event_flags: List[str]
    triggered_scenario_events: List[str]
    safety_status: str
    safety_reason: Optional[str]
    ending_type: Optional[str]
    ending_summary: Optional[str]
    new_flow_state: str
    turn_number: int
    used_fallback: bool


def _normalize_text(text: str) -> str:
    return text.strip()


def _safety_precheck(normalized: str) -> None:
    """Placeholder input safety precheck.

    Validates that the player input does not contain obviously prohibited
    content before forwarding it to the LLM. This hook is intentionally
    minimal — a production implementation would call a safety classifier.
    """
    # Placeholder: accept all input. Replace with a classifier call when ready.
    pass


def _load_recent_turns(session_id: str, conn: sqlite3.Connection, limit: int = 12) -> List[TranscriptEntry]:
    rows = conn.execute(
        "SELECT role, content, turn_number FROM turn_session_turns "
        "WHERE session_id = ? ORDER BY turn_number DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    entries = []
    for row in reversed(rows):
        entries.append(TranscriptEntry(
            speaker=row["role"],
            text=row["content"],
            turn_number=row["turn_number"],
        ))
    return entries


async def _collect_runtime_output(runtime: ChatRuntime, request: ChatRequest) -> str:
    """Stream from the runtime and return the final text."""
    raw_text = ""
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            raw_text = chunk.text
        elif isinstance(chunk, ChatToken):
            raw_text += chunk.text
    return raw_text


async def process_turn(
    session_row: sqlite3.Row,
    player_text: str,
    scenario_data: ScenarioData,
    max_turns: int,
    runtime: ChatRuntime,
    conn: sqlite3.Connection,
) -> TurnPipelineResult:
    """Execute the full player-turn pipeline and persist results.

    ``session_row`` must be a row from the ``turn_sessions`` table.
    ``scenario_data`` is the pre-resolved ScenarioData for this session's
    difficulty level (caller provides it to keep this function stateless about
    scenario lookup).

    Raises TurnInputError if the player text fails validation.
    Never raises for model errors — uses safe fallback instead.
    """
    # 1. Normalize and validate input.
    normalized = _normalize_text(player_text)
    if not normalized:
        raise TurnInputError("Turn content is empty after normalization")
    if len(normalized) > MAX_TURN_CONTENT_CHARS:
        raise TurnInputError(
            f"Turn content is {len(normalized)} characters; maximum is {MAX_TURN_CONTENT_CHARS}"
        )

    # 2. Input safety precheck.
    _safety_precheck(normalized)

    # 3. Load session state.
    session_id: str = session_row["session_id"]
    state_vars: Dict[str, int] = json.loads(session_row["state_vars_json"] or "{}")
    fired_event_ids: Set[str] = set(json.loads(session_row["fired_events_json"] or "[]"))
    turn_number: int = int(session_row["turn_count"]) + 1

    # If state_vars is empty (first turn), initialize from baseline.
    if not state_vars:
        var_defs = build_variable_defs()
        state_vars = initialize_state(var_defs)
    else:
        var_defs = build_variable_defs()

    # 4. Get recent transcript.
    recent_transcript = _load_recent_turns(session_id, conn)

    # 5. Build prompt.
    prompt = compose_turn_prompt(PromptComposerInput(
        scenario=scenario_data,
        session_state=PromptSessionState(
            variables=state_vars,
            turn_number=turn_number,
        ),
        safety_policy=_DEFAULT_SAFETY_POLICY,
        player_utterance=normalized,
        recent_transcript=recent_transcript,
    ))

    # 6. Call runtime.
    messages = [
        ChatMessage(role="system", content=prompt.system_prompt),
        ChatMessage(role="user", content=prompt.user_prompt),
    ]
    request = ChatRequest(
        messages=messages,
        json_schema=NPC_TURN_OUTPUT_SCHEMA,
    )
    logger.debug(
        "Calling runtime %s for session %s turn %d (estimated %d tokens)",
        runtime.id, session_id, turn_number, prompt.estimated_token_count,
    )
    raw_text = await _collect_runtime_output(runtime, request)

    # 7. Validate / repair / fallback.
    turn_output = parse_turn_output(raw_text)
    used_fallback = (turn_output.npc_utterance == SAFE_FALLBACK_UTTERANCE)
    if used_fallback:
        logger.warning("Turn output fell back to safe utterance for session %s turn %d", session_id, turn_number)

    # 8. Handle safety status from model output.
    safety_stopped = turn_output.safety.status == "stop"

    # 9. Apply state delta.
    delta_result = apply_state_delta(state_vars, turn_output.state_delta, var_defs)
    if delta_result.rejected_keys:
        logger.warning("State delta had unknown keys (rejected): %s", delta_result.rejected_keys)

    # 10. Evaluate scenario event triggers.
    triggered_events = evaluate_event_triggers(
        delta_result.new_state,
        turn_number,
        events=[],  # No inline scenario events in hardcoded scenarios yet.
        fired_event_ids=fired_event_ids,
        active_flags=set(turn_output.event_flags),
    )

    # 11. Evaluate ending condition.
    ending_type = evaluate_ending_condition(
        delta_result.new_state,
        turn_number,
        max_turns,
        ending_conditions=None,
        safety_stopped=safety_stopped,
    )

    # Model may also signal session end.
    if ending_type is None and not turn_output.session_control.continue_session:
        sc_ending = turn_output.session_control.ending_type
        if sc_ending and sc_ending != "none":
            ending_type = sc_ending

    new_flow_state = "Ended" if ending_type else "PlayerTurnListening"

    # 12. Persist atomically.
    now = datetime.now(timezone.utc).isoformat()
    player_turn_number = turn_number * 2 - 1
    npc_turn_number = turn_number * 2

    player_cursor = conn.execute(
        "INSERT INTO turn_session_turns "
        "(session_id, turn_number, role, content, created_at) "
        "VALUES (?, ?, 'player', ?, ?)",
        (session_id, player_turn_number, normalized, now),
    )
    npc_cursor = conn.execute(
        "INSERT INTO turn_session_turns "
        "(session_id, turn_number, role, content, emotion, state_delta_json, event_flags_json, safety_json, created_at) "
        "VALUES (?, ?, 'npc', ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            npc_turn_number,
            turn_output.npc_utterance,
            turn_output.npc_emotion,
            json.dumps(dict(delta_result.actual_changes)),
            json.dumps(turn_output.event_flags),
            json.dumps({
                "status": turn_output.safety.status,
                "reason": turn_output.safety.reason,
            }),
            now,
        ),
    )
    conn.execute(
        "UPDATE turn_sessions SET "
        "state_vars_json = ?, fired_events_json = ?, turn_count = ?, "
        "flow_state = ?, ending_type = ? "
        "WHERE session_id = ?",
        (
            json.dumps(delta_result.new_state),
            json.dumps(list(fired_event_ids)),
            turn_number,
            new_flow_state,
            ending_type,
            session_id,
        ),
    )
    conn.commit()

    visible, _ = partition_state_by_visibility(delta_result.new_state, var_defs)

    logger.debug(
        "Turn %d complete for session %s: state=%s ending=%s",
        turn_number, session_id, new_flow_state, ending_type,
    )

    return TurnPipelineResult(
        player_content=normalized,
        player_event_id=player_cursor.lastrowid,
        npc_utterance=turn_output.npc_utterance,
        npc_emotion=turn_output.npc_emotion,
        npc_event_id=npc_cursor.lastrowid,
        state_delta=dict(delta_result.actual_changes),
        new_state_vars=delta_result.new_state,
        visible_state=visible,
        event_flags=turn_output.event_flags,
        triggered_scenario_events=triggered_events,
        safety_status=turn_output.safety.status,
        safety_reason=turn_output.safety.reason,
        ending_type=ending_type,
        ending_summary=turn_output.session_control.ending_summary,
        new_flow_state=new_flow_state,
        turn_number=turn_number,
        used_fallback=used_fallback,
    )
