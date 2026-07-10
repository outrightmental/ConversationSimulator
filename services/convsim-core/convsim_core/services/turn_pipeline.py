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

import asyncio
import concurrent.futures
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
    TurnEvent,
    compose_turn_prompt,
    parse_turn_output,
)
from convsim_prompt.types import ScenarioData

from convsim_core.input_router import SafetyPolicyConfig
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


def _safety_policy_config_to_prompt_policy(config: SafetyPolicyConfig) -> SafetyPolicy:
    """Convert a SafetyPolicyConfig (input-router) to SafetyPolicy (prompt-composer).

    The prompt-composer SafetyPolicy.prohibited list is shown to the LLM as NPC
    behavior constraints in the SAFETY_POLICY layer.  Category names from
    SafetyPolicyConfig are used directly — they are descriptive enough for the model.
    """
    prohibited = list(config.categories.keys())
    redirects: Dict[str, str] = dict(config.per_category_messages)
    if config.global_redirect_message and "default" not in redirects:
        redirects["default"] = config.global_redirect_message
    return SafetyPolicy(
        policy_id=config.policy_id,
        content_rating=config.content_rating,
        prohibited=prohibited,
        redirects=redirects,
    )


class _SyncRuntimeBridge:
    """Synchronous RuntimeProtocol bridge over ChatRuntime for repair calls.

    parse_turn_output expects a synchronous RuntimeProtocol.call_llm() to request
    structural-repair or content-safety-retry responses from the model.  ChatRuntime
    exposes only an async chat_stream() interface, so this bridge runs each repair
    call in a dedicated thread with its own event loop, isolating it from the
    caller's running asyncio loop.

    If the runtime is event-loop-bound (e.g. uses a per-loop aiohttp session) the
    call will raise from the foreign loop — that exception propagates to
    parse_turn_output's except clause, which logs it and falls back gracefully.
    """

    def __init__(self, runtime: ChatRuntime) -> None:
        self._runtime = runtime

    def call_llm(self, prompt: str) -> str:
        async def _call() -> str:
            request = ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
            )
            return await _collect_runtime_output(self._runtime, request)

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(asyncio.run, _call()).result(timeout=60)
        finally:
            # Never wait on a hung repair call — the 60s timeout above must be
            # the real ceiling. A context manager would call shutdown(wait=True)
            # on exit and block indefinitely if the runtime never returns, so we
            # shut down without waiting and let a stuck thread die on its own.
            pool.shutdown(wait=False)


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
            break  # ChatFinal is authoritative; trailing tokens must not append to it.
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
    *,
    save_transcript: bool = True,
    source_mode: str = "text-only",
    safety_policy_config: Optional[SafetyPolicyConfig] = None,
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
    var_defs = build_variable_defs()
    if not state_vars:
        state_vars = initialize_state(var_defs)

    # 4. Get recent transcript.
    recent_transcript = _load_recent_turns(session_id, conn)

    # 5. Build prompt.
    prompt_safety_policy = (
        _safety_policy_config_to_prompt_policy(safety_policy_config)
        if safety_policy_config is not None
        else _DEFAULT_SAFETY_POLICY
    )
    prompt = compose_turn_prompt(PromptComposerInput(
        scenario=scenario_data,
        session_state=PromptSessionState(
            variables=state_vars,
            turn_number=turn_number,
        ),
        safety_policy=prompt_safety_policy,
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
        "Calling runtime %s for session %s turn %d (estimated %d tokens, truncated=%s)",
        runtime.id, session_id, turn_number, prompt.estimated_token_count, prompt.was_truncated,
    )
    raw_text = await _collect_runtime_output(runtime, request)

    # 7. Validate / repair / fallback.
    # Wrap the runtime so parse_turn_output can make synchronous repair calls.
    # Hidden agenda is forwarded for verbatim-leak detection in the output validator.
    runtime_bridge = _SyncRuntimeBridge(runtime)
    turn_parse_events: List[TurnEvent] = []
    turn_output = parse_turn_output(
        raw_text,
        runtime=runtime_bridge,
        hidden_agenda=scenario_data.npc.private_persona.hidden_agenda,
        turn_events=turn_parse_events,
    )
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

    # 12. Persist atomically. Use `with conn:` so a mid-transaction failure
    # triggers an automatic rollback instead of leaving a dirty open transaction
    # on the singleton connection.
    now = datetime.now(timezone.utc).isoformat()
    player_turn_number = turn_number * 2 - 1
    npc_turn_number = turn_number * 2

    # Prompt metadata stored for debugging. Only non-private fields are kept:
    # token count, truncation flag, and which layers were present. The raw
    # prompt text and NPC private persona content are never written to the log.
    prompt_metadata_payload = json.dumps({
        "estimated_token_count": prompt.estimated_token_count,
        "was_truncated": prompt.was_truncated,
        "layers_present": list(prompt.layer_map.keys()),
    })

    with conn:
        player_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, source_mode, flow_state_after, created_at) "
            "VALUES (?, ?, 'player', ?, ?, ?, ?)",
            (session_id, player_turn_number, normalized, source_mode, new_flow_state, now),
        )
        npc_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, emotion, state_delta_json, event_flags_json, "
            "safety_json, raw_output_json, flow_state_after, created_at) "
            "VALUES (?, ?, 'npc', ?, ?, ?, ?, ?, ?, ?, ?)",
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
                raw_text,
                new_flow_state,
                now,
            ),
        )

        # Persist discrete turn events.
        events_to_insert: List[tuple] = []
        events_to_insert.append((
            session_id,
            turn_number,
            "state_delta",
            json.dumps({
                "actual_changes": dict(delta_result.actual_changes),
                "rejected_keys": delta_result.rejected_keys,
            }),
            now,
        ))
        for event_id in triggered_events:
            events_to_insert.append((
                session_id, turn_number, "scenario_event",
                json.dumps({"event_id": event_id}), now,
            ))
        if turn_output.safety.status == "redirect":
            events_to_insert.append((
                session_id, turn_number, "safety_redirect",
                json.dumps({"reason": turn_output.safety.reason}), now,
            ))
        elif turn_output.safety.status == "stop":
            events_to_insert.append((
                session_id, turn_number, "safety_stop",
                json.dumps({"reason": turn_output.safety.reason}), now,
            ))
        if ending_type:
            events_to_insert.append((
                session_id, turn_number, "session_ending",
                json.dumps({
                    "ending_type": ending_type,
                    "summary": turn_output.session_control.ending_summary,
                }),
                now,
            ))
        events_to_insert.append((
            session_id, turn_number, "prompt_metadata", prompt_metadata_payload, now,
        ))
        events_to_insert.append((
            session_id, turn_number, "debug",
            json.dumps({
                "used_fallback": used_fallback,
                "parse_events": [
                    {
                        "event_type": e.event_type,
                        "category": e.category,
                        "reason": e.reason,
                    }
                    for e in turn_parse_events
                ],
            }), now,
        ))
        conn.executemany(
            "INSERT INTO turn_session_events "
            "(session_id, turn_number, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            events_to_insert,
        )

        # Populate FTS only when transcript saving is enabled for this session.
        if save_transcript:
            conn.executemany(
                "INSERT INTO session_transcript_fts(session_id, turn_number, role, content) "
                "VALUES (?, ?, ?, ?)",
                [
                    (session_id, player_turn_number, "player", normalized),
                    (session_id, npc_turn_number, "npc", turn_output.npc_utterance),
                ],
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
