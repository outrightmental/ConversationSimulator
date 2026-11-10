# SPDX-License-Identifier: Apache-2.0
"""End-to-end text-only player turn pipeline.

Processing steps (SPEC §6):
  1. Normalize player text: strip, reject empty, reject oversized.
  2. Local input safety gate: route player text through deterministic rule
     checks (route_player_input) before the LLM; refuse/stop/redirect as needed.
  3. Evaluate scenario event triggers on the state the previous turn left.
  4. Build prompt context: scenario, NPC, rubric, the scenario's state
     variables, the instructions of the events that fired, transcript,
     player utterance.
  5. Call ChatRuntime and collect the structured response, constrained by the
     session's output schema (its rubric_id an enum of the rubric's ids, its
     state_delta the scenario's variables).
  6. Validate / repair / fallback the model response; retry once a reply that
     repeats one of the NPC's last two lines (issue #580).
  7. Apply bounded state deltas.
  8. Evaluate ending conditions.
  9. Persist player turn, NPC turn, and updated session state atomically.
 10. Return a TurnPipelineResult.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, replace as dataclass_replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Set

from convsim_prompt import (
    SAFE_FALLBACK_UTTERANCE,
    SAFE_REDIRECT_UTTERANCE,
    SAFE_STOP_UTTERANCE,
    PromptComposerInput,
    SafetyPolicy,
    SessionState as PromptSessionState,
    TranscriptEntry,
    TurnEvent,
    TurnOutput,
    compose_repetition_retry_prompt,
    compose_turn_prompt,
    filter_rubric_observations,
    parse_turn_output,
    state_variables_in_schema,
    turn_output_schema_for,
)
from convsim_prompt.output_validator import validate_npc_output
from convsim_prompt.repetition import (
    GUARD_WINDOW,
    RepetitionReport,
    asks_for_repeat,
    check_repetition,
    less_repetitive,
)
from convsim_prompt.turn_output import _extract_json
from convsim_prompt.types import PromptBundle
from convsim_prompt.types import ResponseStyleOverrides, ScenarioData

from convsim_core.input_router import (
    DEFAULT_REDIRECT_MESSAGE,
    RouteAction,
    RouteDecision,
    SafetyPolicyConfig,
    route_player_input,
)
from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatProgress,
    ChatRequest,
    ChatToken,
    SamplingDefaults,
)
from convsim_core.scenario_state import (
    ScenarioEvent,
    apply_state_delta,
    build_variable_defs,
    evaluate_ending_condition,
    evaluate_event_triggers,
    initialize_state,
    partition_state_by_visibility,
)
from convsim_core.services.model_registry_service import active_model_sampling
from convsim_core.services.reply_speed import (
    load_reply_speed,
    profile_for,
    scaled_max_words,
)
from convsim_core.services.turn_salvage import salvage_turn_output
from convsim_core.services.turn_timing import (
    ExtraCallKind,
    StreamObservation,
    TurnClock,
    TurnTimingBuilder,
)
from convsim_core.services.utterance_stream import (
    SentenceGate,
    UtteranceStreamExtractor,
    first_sentence_repeats,
)
from convsim_core.storage.repositories.relationship_repo import get_relationship_recap

logger = logging.getLogger(__name__)


def _apply_reply_speed(scenario_data: ScenarioData, speed: str) -> ScenarioData:
    """Return *scenario_data* with its NPC word cap scaled for *speed*.

    A copy, not a mutation: ``scenario_data`` is resolved once per scenario and
    handed to every session playing it, so writing the current player's pacing
    preference into it would leak across sessions.
    """
    authored = scenario_data.response_style or ResponseStyleOverrides()
    target = scaled_max_words(authored.max_words, speed)
    if target == authored.max_words:
        return scenario_data
    return dataclass_replace(
        scenario_data,
        response_style=dataclass_replace(authored, max_words=target),
    )


MAX_TURN_CONTENT_CHARS = 2000

#: Flow states a session has finished in — the same set as ENDED_FLOW_STATES in
#: routers/sessions.py, which tests/test_turn_pipeline.py holds this to. A turn
#: commits its session state at the end of a model call that can take minutes
#: on a slow machine; a player who ends the session meanwhile (the end button
#: on the in-progress banner, or after the client gave up waiting) must not see
#: it come back. The commit leaves a finished session's state alone.
FINISHED_FLOW_STATES = ("Ended", "DebriefGenerating", "DebriefReady", "Error")
_FINISHED_STATES_SQL = ", ".join(f"'{state}'" for state in FINISHED_FLOW_STATES)


def _commit_session_state(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    turn_number: int,
    flow_state: str,
    ending_type: Optional[str],
    extra_sets: str = "",
    extra_params: tuple = (),
) -> tuple[str, Optional[str]]:
    """Write a turn's outcome to its session row; return the state it holds after.

    ``flow_state`` and ``ending_type`` are written only while the session is
    still in play. Once it has finished, a late turn's transcript rows are still
    kept — the player did say it, and the NPC did answer — but the session stays
    ended, keeps its ending, and its debrief is not reopened. SQLite evaluates
    every SET expression against the row as it was before the update, so the
    CASE tests the state the turn is racing with, not the one it writes.
    """
    conn.execute(
        "UPDATE turn_sessions SET "
        + extra_sets
        + "turn_count = ?, "
        f"flow_state = CASE WHEN flow_state IN ({_FINISHED_STATES_SQL}) THEN flow_state ELSE ? END, "
        f"ending_type = CASE WHEN flow_state IN ({_FINISHED_STATES_SQL}) THEN ending_type ELSE ? END "
        "WHERE session_id = ?",
        (*extra_params, turn_number, flow_state, ending_type, session_id),
    )
    row = conn.execute(
        "SELECT flow_state, ending_type FROM turn_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return flow_state, ending_type
    if row[0] != flow_state:
        logger.info(
            "Turn %d for session %s landed after the session finished (%s); "
            "its transcript is kept and the session stays %s",
            turn_number, session_id, row[0], row[0],
        )
    return row[0], row[1]


def _finished_state(conn: sqlite3.Connection, session_id: str) -> Optional[str]:
    """The state the session already finished in, or None while it is in play.

    Read inside a turn's persist transaction, before anything is written: the
    transaction has no await in it, so this is the state the commit races. A
    turn that lands after the session finished keeps its transcript rows, but
    they record the state the session kept, and it writes no session_ending
    event — the session has an ending already, and the export would otherwise
    report two.
    """
    row = conn.execute(
        "SELECT flow_state FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is not None and row[0] in FINISHED_FLOW_STATES:
        return row[0]
    return None

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

# Default SafetyPolicyConfig for the local input router, used when no pack
# provides a scenario-specific safety YAML.  All nine MVP categories are enabled
# at their standard PG actions.
_DEFAULT_SAFETY_POLICY_CONFIG = SafetyPolicyConfig(
    policy_id="default_pg",
    content_rating="PG",
    categories={
        "nsfw_sexual_content": RouteAction.STOP,
        "minors_romantic_or_sexual": RouteAction.STOP,
        "real_person_impersonation": RouteAction.REFUSE,
        "voice_cloning_request": RouteAction.REFUSE,
        "medical_or_therapy_claim": RouteAction.REDIRECT,
        "legal_claim": RouteAction.REDIRECT,
        "criminal_instruction": RouteAction.REFUSE,
        "harassment_extreme": RouteAction.REDIRECT,
        "self_harm_crisis": RouteAction.STOP_WITH_RESOURCE,
    },
    global_redirect_message=DEFAULT_REDIRECT_MESSAGE,
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


def _output_tokens(final: Optional[ChatFinal]) -> Optional[int]:
    """How many tokens an extra model call wrote, when the engine said (issue #519)."""
    if final is None:
        return None
    if final.timings is not None and final.timings.output_tokens is not None:
        return final.timings.output_tokens
    if final.output_tokens > 0:
        return final.output_tokens
    return None


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

    def __init__(
        self,
        runtime: ChatRuntime,
        timing: Optional[TurnTimingBuilder] = None,
        parse_events: Optional[List[TurnEvent]] = None,
        sampling: Optional[SamplingDefaults] = None,
    ) -> None:
        self._runtime = runtime
        self._timing = timing
        # The turn's registry sampling (issue #580): a repair or retry is the
        # same model answering the same turn, so it samples the same way.
        self._sampling = sampling or SamplingDefaults()
        # The same list the parser appends its events to, read at call time to
        # tell the two kinds of extra call apart (see _call_kind).
        self._parse_events = parse_events if parse_events is not None else []

    def _call_kind(self) -> ExtraCallKind:
        """Which of the parser's two follow-up calls is being made.

        Every extra model call is counted in the turn's record (issue #519).
        The parser makes at most one structural repair and at most one
        content-safety retry, in that order, and reports an
        ``output_violation_detected`` event before the retry and never before
        the repair. So the events it has emitted by the time it calls say which
        call this is, without the core reading the prompt text, which belongs
        to the parser.
        """
        if any(e.event_type == "output_violation_detected" for e in self._parse_events):
            return "safety_retry"
        return "repair"

    def call_llm(self, prompt: str) -> str:
        final_holder: List[ChatFinal] = []

        async def _call() -> str:
            request = ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                **self._sampling.request_fields(),
            )
            text, _, final = await _collect_runtime_output_timed(self._runtime, request)
            if final is not None:
                final_holder.append(final)
            return text

        kind = self._call_kind()
        started = time.perf_counter()
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(asyncio.run, _call()).result(timeout=60)
        finally:
            if self._timing is not None:
                final = final_holder[0] if final_holder else None
                self._timing.record_extra_call(
                    kind, (time.perf_counter() - started) * 1000.0, _output_tokens(final)
                )
            # Never wait on a hung repair call — the 60s timeout above must be
            # the real ceiling. A context manager would call shutdown(wait=True)
            # on exit and block indefinitely if the runtime never returns, so we
            # shut down without waiting and let a stuck thread die on its own.
            pool.shutdown(wait=False)


class TurnStreamer(Protocol):
    """Where the pipeline sends what the player may see while a turn runs (#538).

    The sessions router passes a WebSocket-backed implementation when a client
    is listening; with none, the pipeline streams nothing and behaves as it
    always has. ``output_tokens`` is read by ``progress`` so the panel can show
    how much has been written.
    """

    output_tokens: int

    async def progress(self, stage: str, prompt: Optional[Dict[str, Optional[int]]] = None) -> None: ...

    async def token(self, text: str) -> None: ...

    async def final(self, content: str) -> None: ...


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
    rubric_observations: List[Dict[str, Any]]
    safety_status: str
    safety_reason: Optional[str]
    ending_type: Optional[str]
    ending_summary: Optional[str]
    new_flow_state: str
    turn_number: int
    used_fallback: bool
    # What the turn cost so far (issue #519): the builder the pipeline filled,
    # for the caller to add what it alone can see (voice, the whole request)
    # and build the record once. None only for turns that never reached the
    # model: an input safety stop answers from a canned line.
    timing: Optional[TurnTimingBuilder] = None
    # True when the turn was built from released words plus whatever
    # bookkeeping completed, with the rest defaulted (issue #538).
    salvaged: bool = False
    # The spoken line as it was streamed to the player, when it was. The REST
    # response always equals what was streamed.
    streamed_line: Optional[str] = None


def _normalize_text(text: str) -> str:
    return text.strip()


def _persist_input_safety_stop(
    session_row: sqlite3.Row,
    normalized: str,
    decision: RouteDecision,
    conn: sqlite3.Connection,
    source_mode: str,
    save_transcript: bool,
    barged_in: bool = False,
) -> "TurnPipelineResult":
    """Short-circuit persist for a STOP / STOP_WITH_RESOURCE from the input router.

    Writes the player turn, a synthetic NPC stop/crisis response, and a
    sanitised safety event (category + action only, no raw player text) to the
    DB, then marks the session as Ended.  The LLM is never called.
    """
    session_id: str = session_row["session_id"]
    turn_number: int = int(session_row["turn_count"]) + 1
    player_turn_number = turn_number * 2 - 1
    npc_turn_number = turn_number * 2
    now = datetime.now(timezone.utc).isoformat()
    ending_type = "safety_stop"
    new_flow_state = "Ended"

    npc_utterance = (
        decision.message
        or "This conversation has been stopped for safety reasons."
    )
    safety_status = (
        "stop_with_resource_message"
        if decision.action == RouteAction.STOP_WITH_RESOURCE
        else "stop"
    )

    logger.warning(
        "Input safety gate: session=%s turn=%d category=%s action=%s",
        session_id, turn_number, decision.category, decision.action.value,
    )

    # Snapshot the simulation state at this turn boundary (state unchanged by safety stop).
    current_state_vars: Dict[str, int] = json.loads(session_row["state_vars_json"] or "{}")
    current_fired_events: List[str] = json.loads(session_row["fired_events_json"] or "[]")
    safety_stop_snapshot_json = json.dumps({
        "state_vars": current_state_vars,
        "fired_events": current_fired_events,
    })

    with conn:
        kept_state = _finished_state(conn, session_id)
        rows_state = kept_state or new_flow_state
        player_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, source_mode, barged_in, flow_state_after, created_at) "
            "VALUES (?, ?, 'player', ?, ?, ?, ?, ?)",
            (session_id, player_turn_number, normalized, source_mode, int(barged_in), rows_state, now),
        )
        npc_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, emotion, state_delta_json, event_flags_json, "
            "safety_json, raw_output_json, flow_state_after, state_snapshot_json, created_at) "
            "VALUES (?, ?, 'npc', ?, 'neutral', '{}', '[]', ?, NULL, ?, ?, ?)",
            (
                session_id,
                npc_turn_number,
                npc_utterance,
                json.dumps({"status": safety_status, "reason": decision.category}),
                rows_state,
                safety_stop_snapshot_json,
                now,
            ),
        )
        # Sanitised event log: category and action only — never the raw player text.
        safety_events = [
            (
                session_id, turn_number, "input_safety_stop",
                json.dumps({
                    "category": decision.category,
                    "action": decision.action.value,
                }),
                now,
            ),
        ]
        if not kept_state:
            safety_events.append((
                session_id, turn_number, "session_ending",
                json.dumps({"ending_type": ending_type, "summary": None}),
                now,
            ))
        conn.executemany(
            "INSERT INTO turn_session_events "
            "(session_id, turn_number, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            safety_events,
        )
        if save_transcript:
            conn.executemany(
                "INSERT INTO session_transcript_fts(session_id, turn_number, role, content) "
                "VALUES (?, ?, ?, ?)",
                [
                    (session_id, player_turn_number, "player", normalized),
                    (session_id, npc_turn_number, "npc", npc_utterance),
                ],
            )
        new_flow_state, ending_type = _commit_session_state(
            conn,
            session_id,
            turn_number=turn_number,
            flow_state=new_flow_state,
            ending_type=ending_type,
        )

    return TurnPipelineResult(
        player_content=normalized,
        player_event_id=player_cursor.lastrowid,
        npc_utterance=npc_utterance,
        npc_emotion="neutral",
        npc_event_id=npc_cursor.lastrowid,
        state_delta={},
        new_state_vars={},
        visible_state={},
        event_flags=[],
        triggered_scenario_events=[],
        rubric_observations=[],
        safety_status=safety_status,
        safety_reason=decision.category,
        ending_type=ending_type,
        ending_summary=None,
        new_flow_state=new_flow_state,
        turn_number=turn_number,
        used_fallback=False,
    )


def _previous_event_flags(session_id: str, conn: sqlite3.Connection) -> Set[str]:
    """The event flags the NPC's last reply raised, for this turn's ``flag`` events.

    Events are evaluated before the turn (issue #580), so a ``flag`` condition
    reads the flags of the reply before it, as a variable condition reads the
    state that reply left. None before the first reply.
    """
    row = conn.execute(
        "SELECT event_flags_json FROM turn_session_turns "
        "WHERE session_id = ? AND role = 'npc' ORDER BY turn_number DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return set()
    try:
        flags = json.loads(row["event_flags_json"] or "[]")
    except (TypeError, ValueError):
        return set()
    return {f for f in flags if isinstance(f, str)} if isinstance(flags, list) else set()


def _fired_event_instructions(
    events: List[ScenarioEvent], triggered_ids: List[str]
) -> List[str]:
    """The ``npc_instruction`` of each triggered event, once each, in the scenario's order."""
    wanted = set(triggered_ids)
    instructions: List[str] = []
    seen: Set[str] = set()
    for event in events:
        if event.id in wanted and event.id not in seen:
            seen.add(event.id)
            instructions.append(event.npc_instruction)
    return instructions


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


OnChunk = Callable[[Any], Awaitable[bool]]


async def _collect_runtime_output_timed(
    runtime: ChatRuntime,
    request: ChatRequest,
    observation: Optional[StreamObservation] = None,
    on_chunk: Optional[OnChunk] = None,
) -> tuple[str, Optional[Dict[str, Any]], Optional[ChatFinal]]:
    """Stream from the runtime and return (raw_text, structured, final).

    ``structured`` is the pre-parsed JSON dict from ``ChatFinal.structured``
    when the runtime used native JSON-schema constraints.  The caller should
    prefer ``structured`` over re-parsing ``raw_text`` when it is not None,
    because grammar-constrained output is always valid JSON.

    When an ``observation`` is given, the moments the engine's signals arrived
    — first progress chunk, first token, final — are stamped on it with a
    monotonic clock, which is how the turn's stages are timed (issue #519).

    ``on_chunk`` sees every chunk as it arrives and may return True to stop
    consuming the stream (issue #538: a released sentence's successor failed
    the output check). Stopping closes the runtime's generator, which closes
    the engine connection; ``final`` is then None and ``raw_text`` is what had
    arrived.
    """
    raw_text = ""
    structured: Optional[Dict[str, Any]] = None
    final: Optional[ChatFinal] = None
    stream = runtime.chat_stream(request)
    stopped = False
    try:
        async for chunk in stream:
            if isinstance(chunk, ChatFinal):
                raw_text = chunk.text
                structured = chunk.structured
                final = chunk
                if observation is not None:
                    observation.saw_final(chunk, time.perf_counter())
                if on_chunk is not None:
                    await on_chunk(chunk)
                break  # ChatFinal is authoritative; trailing tokens must not append to it.
            elif isinstance(chunk, ChatToken):
                if observation is not None:
                    observation.saw_token(time.perf_counter())
                raw_text += chunk.text
            elif isinstance(chunk, ChatProgress):
                if observation is not None:
                    observation.saw_progress(chunk, time.perf_counter())
            if on_chunk is not None and await on_chunk(chunk):
                stopped = True
                break
    finally:
        if stopped:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001 — closing a stopped stream is best effort
                    pass
    return raw_text, structured, final


async def _collect_runtime_output(
    runtime: ChatRuntime, request: ChatRequest
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Stream from the runtime and return (raw_text, structured).

    The untimed form of :func:`_collect_runtime_output_timed`, kept for callers
    that only want the text.
    """
    raw_text, structured, _ = await _collect_runtime_output_timed(runtime, request)
    return raw_text, structured


def _parse_input(raw_text: str, structured: Optional[Dict[str, Any]]) -> str:
    """The text the parser reads for one model reply.

    When the runtime returned a pre-parsed structured dict (native JSON-schema
    or grammar constraints), it is serialised back to a clean JSON string so
    the JSON-extraction step always succeeds on the first try. The raw text is
    what the debug drawer keeps either way.
    """
    return json.dumps(structured) if structured is not None else raw_text


def _parse_reply(
    parse_input: str,
    *,
    request: ChatRequest,
    runtime: Optional[Any],
    hidden_agenda: Optional[List[str]],
    events: List[TurnEvent],
) -> TurnOutput:
    """One model reply as a TurnOutput: the turn's own, and the repetition retry's.

    Every step from the reply's text to a validated turn runs here, so a retry
    the repetition guard keeps has been through exactly what the turn's own
    reply went through; a step added to one cannot skip the other. ``request``
    is the request the reply answers: the retry's is a copy of the turn's with
    only its messages and temperature changed, so a step that reads the
    request (its output schema, say) treats both alike. ``runtime`` is what
    parse_turn_output makes its structural repair and content-safety retry
    calls on; the repetition retry passes None and gets neither.
    """
    return parse_turn_output(
        parse_input,
        runtime=runtime,
        hidden_agenda=hidden_agenda,
        turn_events=events,
        output_schema=request.json_schema,
    )


def _repair_is_coming(parse_input: str, hidden_agenda: Optional[List[str]]) -> bool:
    """Whether parse_turn_output will have to call the model again.

    The parser's structural repair and content-safety retry run synchronously
    on the event loop (see #527), so the ``checking`` stage can only be shown
    by predicting them: the output is not a JSON object, or its line fails the
    output check in a recoverable way.
    """
    data = _extract_json(parse_input)
    if data is None:
        return True
    utterance = data.get("npc_utterance")
    if not isinstance(utterance, str) or not utterance:
        return True
    result = validate_npc_output(utterance=utterance, hidden_agenda=hidden_agenda)
    return (not result.is_safe) and not result.has_hard_violation


# ---------------------------------------------------------------------------
# Repetition guard (issue #580, P2)
# ---------------------------------------------------------------------------
#
# A reply that repeats one of the NPC's last two lines (the authored opening
# counts) is generated once more, with the line it repeated quoted as "do not
# repeat this" and the temperature a step higher, and whichever of the two
# repeats less is kept. What counts as a repeat is convsim_prompt.repetition,
# which the D-05 pre-check's check (a) shares.
#
# Released text is committed text (#538), so the retry may only replace a line
# nobody has seen. The sentence gate holds back a streamed first sentence that
# would make the line a repeat: nothing has been released, so the whole line is
# still the engine's to replace and comes here. Once a sentence is out, the
# rest of the line streams as usual (only the safety check can hold it back),
# and a repeat in it is noted, not retried: cutting the line there would leave
# the player a stub, an answer without its question (see process_turn).

#: How much hotter the retry samples than the turn did.
REPETITION_RETRY_TEMPERATURE_STEP = 0.1
#: The highest temperature the retry asks for.
_MAX_RETRY_TEMPERATURE = 2.0
#: The retry may take this many times as long as the first reply did, and at
#: least the floor: a retry that hangs must not hold the turn.
REPETITION_RETRY_TIMEOUT_FACTOR = 2.0
REPETITION_RETRY_MIN_TIMEOUT_S = 30.0

#: The engine's own canned lines: never the NPC repeating itself.
_CANNED_UTTERANCES = frozenset({SAFE_FALLBACK_UTTERANCE, SAFE_REDIRECT_UTTERANCE, SAFE_STOP_UTTERANCE})


def _previous_npc_lines(transcript: List[TranscriptEntry]) -> List[str]:
    """The NPC's last ``GUARD_WINDOW`` lines, newest first; the opening counts."""
    lines = [e.text for e in reversed(transcript) if e.speaker != "player" and (e.text or "").strip()]
    return lines[:GUARD_WINDOW]


def _is_model_line(output: TurnOutput) -> bool:
    """Whether the turn's line is the model's own words in an ordinary turn.

    Not a canned engine line (fallback, redirect, stop), and not a line the
    model itself marked as a safety redirect or stop.
    """
    return output.safety.status == "ok" and output.npc_utterance not in _CANNED_UTTERANCES


def _repetition_event(event_type: str, reason: str) -> TurnEvent:
    return TurnEvent(event_type=event_type, category="repetition", reason=reason)


@dataclass
class _RetryKeptEvent(TurnEvent):
    """``repetition_retry_kept``, with the raw output of the first reply.

    A kept retry is the turn: its raw output is what the NPC row stores, and
    what the debrief and the debug drawer read. The first reply, which the
    player never got, is kept here so the drawer can still show it.
    """

    discarded_raw_output: str = ""


@dataclass(frozen=True)
class _RetryReply:
    """The repetition retry's reply: the turn parsed from it, and the output it came as.

    ``raw_text`` is the text the turn was parsed from (the runtime's
    pre-parsed object serialised, when it gave one), and ``structured`` that
    object, or None. A kept retry replaces the first reply's output with
    these before the turn is stored.
    """

    output: TurnOutput
    raw_text: str
    structured: Optional[Dict[str, Any]]


def _debug_parse_events(events: List[TurnEvent], *, save_transcript: bool) -> List[Dict[str, Any]]:
    """The turn's parse events as the ``debug`` event stores them.

    A hidden_agenda_leak reason embeds verbatim keywords copied from the NPC's
    private hidden agenda. It is redacted so private content is never written
    to the debug log (issue #199: no hidden/private content in logs by
    default); event_type + category still identify the leak. The first reply
    a kept repetition retry replaced is a line of the conversation, and the
    session export carries every event: it is kept only when the transcript
    is saved, and never from a turn that leaked the hidden agenda.
    """
    leaked = any(e.category == "hidden_agenda_leak" for e in events)
    out: List[Dict[str, Any]] = []
    for e in events:
        entry: Dict[str, Any] = {
            "event_type": e.event_type,
            "category": e.category,
            "reason": None if e.category == "hidden_agenda_leak" else e.reason,
            "is_recoverable": e.is_recoverable,
        }
        if isinstance(e, _RetryKeptEvent) and save_transcript and not leaked:
            entry["discarded_raw_output"] = e.discarded_raw_output
        out.append(entry)
    return out


#: Why a repeat was kept without a retry, for the debug drawer.
_ALREADY_RELEASED = "the line had already been released to the player"
_REPEAT_REQUESTED = "the player asked for the line again"
#: What repeated, when only a streamed line's first sentence did.
_FIRST_SENTENCE = "its first sentence "
_HELD_FIRST_SENTENCE = "its first sentence, held back from the stream, "


def _player_asked_for_repeat(player_line: str) -> bool:
    """Whether the player asked the NPC to say it again (see ``asks_for_repeat``).

    In spanish_coffee that is a repair strategy the rubric rewards; the NPC's
    answer is meant to repeat its line, and retrying it with "do not repeat
    this" would contradict the request. A broken check means no exemption.
    """
    try:
        return asks_for_repeat(player_line)
    except Exception:  # noqa: BLE001 — the guard must never cost the player a turn
        logger.exception("Repeat-request check failed; guarding the turn as usual")
        return False


def _note_repetition(
    line: str,
    previous_lines: List[str],
    events: List[TurnEvent],
    why_kept: str,
) -> None:
    """Record a line that repeats an earlier one but is kept without a retry.

    A streamed line: the gate judges only the first release, so a repeat later
    in the line, or one only the whole line's similarity shows, is on screen
    by the time the line is complete, and committed text. Or a line answering
    a player who asked for the line again. Either way it is noted for the
    debug drawer, not retried.
    """
    try:
        report = check_repetition(line, previous_lines) if previous_lines else RepetitionReport()
    except Exception:  # noqa: BLE001 — a note is never worth a turn
        logger.exception("Repetition check failed on a kept line")
        return
    if report.flagged:
        events.append(_repetition_event("repetition_detected", report.describe()))
        events.append(_repetition_event("repetition_retry_skipped", why_kept))


async def _retry_repetitive_reply(
    runtime: ChatRuntime,
    request: ChatRequest,
    prompt: PromptBundle,
    repeated_lines: List[str],
    hidden_agenda: Optional[List[str]],
    timing: TurnTimingBuilder,
    timeout_s: float,
) -> tuple[Optional[_RetryReply], str]:
    """Generate the turn once more; return the reply, or None and why not.

    The same request, schema and sampling, with the system prompt untouched so
    the engine's prompt cache serves all of it, the repeated line(s) quoted in
    the user turn, and the temperature one step higher. The call is recorded
    as a ``repetition_retry`` extra call whether or not it succeeds. The reply
    is accepted only if it parses and passes the output check as written: no
    repair or safety retry is spent on it, the first reply is there instead.
    """
    retry_prompt = compose_repetition_retry_prompt(prompt, repeated_lines)
    retry_request = request.model_copy(update={
        "messages": [
            ChatMessage(role="system", content=retry_prompt.system_prompt),
            ChatMessage(role="user", content=retry_prompt.user_prompt),
        ],
        "temperature": round(
            min(_MAX_RETRY_TEMPERATURE, request.temperature + REPETITION_RETRY_TEMPERATURE_STEP), 3
        ),
    })
    final: Optional[ChatFinal] = None
    started = time.perf_counter()
    try:
        raw_text, structured, final = await asyncio.wait_for(
            _collect_runtime_output_timed(runtime, retry_request), timeout=timeout_s
        )
    except Exception as exc:  # noqa: BLE001 — the first reply stands
        logger.warning("Repetition retry failed (%s): keeping the first reply", type(exc).__name__)
        return None, f"the retry call failed ({type(exc).__name__})"
    finally:
        timing.record_extra_call(
            "repetition_retry", (time.perf_counter() - started) * 1000.0, _output_tokens(final)
        )
    retry_events: List[TurnEvent] = []
    parse_input = _parse_input(raw_text, structured)
    output = _parse_reply(
        parse_input,
        request=retry_request,
        runtime=None,
        hidden_agenda=hidden_agenda,
        events=retry_events,
    )
    if not _is_model_line(output) or any(
        e.event_type == "output_violation_detected" for e in retry_events
    ):
        return None, "the retry's reply did not pass the output check as written"
    return _RetryReply(output=output, raw_text=parse_input, structured=structured), ""


async def _guard_repetition(
    turn_output: TurnOutput,
    previous_lines: List[str],
    *,
    raw_text: str,
    runtime: ChatRuntime,
    request: ChatRequest,
    prompt: PromptBundle,
    hidden_agenda: Optional[List[str]],
    timing: TurnTimingBuilder,
    events: List[TurnEvent],
    streamer: Optional[TurnStreamer],
    first_call_s: float,
    held: Optional[RepetitionReport] = None,
) -> Optional[_RetryReply]:
    """The repetition guard on a line nobody has seen yet.

    Returns the retry to keep in place of the first reply, whose raw output
    is ``raw_text``, or None to keep the first reply. Cheap when the reply is
    not a repeat: a word comparison with two lines and no model call. On a
    repeat, one retry (see ``_retry_repetitive_reply``); the retry is kept
    only if it repeats strictly less. Never raises: on any error the first
    reply is kept.

    ``held`` is why the sentence gate held the streamed line's first sentence
    back, when it did. A first sentence that ends with the previous line's
    closing question is held even when the whole line ends otherwise and is
    no repeat; nothing but this guard will ever commit a held line, so it
    counts as one and is retried. The retry is then judged the same way, by
    its whole line and then by its first sentence as the gate would have.
    """
    try:
        if not previous_lines or not _is_model_line(turn_output):
            return None
        report = check_repetition(turn_output.npc_utterance, previous_lines)
        why = report.describe()
        if not report.flagged and held is not None:
            report, why = held, _HELD_FIRST_SENTENCE + held.describe()
        if not report.flagged:
            return None
        events.append(_repetition_event("repetition_detected", why))
        if streamer is not None:
            await streamer.progress("checking")
        retry, why_not = await _retry_repetitive_reply(
            runtime,
            request,
            prompt,
            [previous_lines[i] for i in report.against],
            hidden_agenda,
            timing,
            max(REPETITION_RETRY_MIN_TIMEOUT_S, REPETITION_RETRY_TIMEOUT_FACTOR * first_call_s),
        )
        if retry is None:
            events.append(_repetition_event("repetition_retry_discarded", why_not))
            return None
        retry_report = check_repetition(retry.output.npc_utterance, previous_lines)
        retry_why = retry_report.describe()
        if not retry_report.flagged and held is not None:
            retry_report = first_sentence_repeats(retry.output.npc_utterance, previous_lines)
            retry_why = _FIRST_SENTENCE + retry_report.describe()
        if less_repetitive(retry_report, report):
            events.append(_RetryKeptEvent(
                event_type="repetition_retry_kept",
                category="repetition",
                reason=(
                    f"the retry repeats less: {retry_why}" if retry_report.flagged
                    else "the retry does not repeat an earlier line"
                ),
                discarded_raw_output=raw_text,
            ))
            return retry
        events.append(_repetition_event(
            "repetition_retry_discarded",
            f"the retry repeats as much or more: {retry_why}",
        ))
        return None
    except Exception as exc:  # noqa: BLE001 — the guard must never cost the player a turn
        logger.exception("Repetition guard failed; keeping the first reply")
        events.append(_repetition_event(
            "repetition_retry_discarded", f"the guard failed ({type(exc).__name__})",
        ))
        return None


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
    barged_in: bool = False,
    safety_policy_config: Optional[SafetyPolicyConfig] = None,
    state_variable_overrides: Optional[Dict[str, Any]] = None,
    scenario_events: Optional[List[ScenarioEvent]] = None,
    ending_conditions: Optional[Dict[str, Any]] = None,
    timing: Optional[TurnTimingBuilder] = None,
    streamer: Optional[TurnStreamer] = None,
    config: Any = None,
) -> TurnPipelineResult:
    """Execute the full player-turn pipeline and persist results.

    ``session_row`` must be a row from the ``turn_sessions`` table.
    ``scenario_data`` is the pre-resolved ScenarioData for this session's
    difficulty level (caller provides it to keep this function stateless about
    scenario lookup).

    ``timing`` is the record of what this turn cost (issue #519). The router
    starts its clock when the request arrives and passes the builder in; a
    caller that passes none gets a builder started here, so the record is never
    missing for a turn that reached the model.

    ``streamer`` receives the turn as it happens (issue #538): stage changes,
    each sentence of the NPC's line once it has passed the output check, and
    the complete line. Released text is committed text: once a sentence has
    been sent, the turn is never regenerated, and a later sentence that fails
    the check stops generation and the turn is built from what was released.
    A first sentence that would repeat one of the NPC's last two lines is held
    back too, with generation running on: nothing has been shown, so the
    repetition guard may still retry the turn (issue #580). A repeat after the
    first sentence streams and is noted. With no streamer the turn behaves as
    before.

    ``config`` is the service config. It decides which installed model the
    turn's registry sampling is read for (``active_model_sampling``): in the
    demo edition that is the demo model's own install, the file its engine
    runs. Without it the full edition's rule applies.

    Raises TurnInputError if the player text fails validation.
    Never raises for model errors — uses safe fallback instead.
    """
    if timing is None:
        timing = TurnTimingBuilder(clock=TurnClock(), runtime_id=runtime.id)
    # Capture the moment the player's turn arrived, before any LLM work. The
    # player turn is persisted with this timestamp while the NPC turn is stamped
    # after inference completes, so their gap reflects real response latency
    # (see compute_metrics). If both were stamped at persist time the latency
    # would always be zero.
    received_at = datetime.now(timezone.utc).isoformat()

    # 1. Normalize and validate input.
    normalized = _normalize_text(player_text)
    if not normalized:
        raise TurnInputError("Turn content is empty after normalization")
    if len(normalized) > MAX_TURN_CONTENT_CHARS:
        raise TurnInputError(
            f"Turn content is {len(normalized)} characters; maximum is {MAX_TURN_CONTENT_CHARS}"
        )

    # 2. Local input safety gate — deterministic rule checks before the LLM.
    #    Global non-overridable rules (minors, self-harm) always fire.
    #    Pack-specific or default policy rules fire for all other categories.
    effective_policy_config = (
        safety_policy_config if safety_policy_config is not None
        else _DEFAULT_SAFETY_POLICY_CONFIG
    )
    decision = route_player_input(normalized, effective_policy_config)
    if decision.action == RouteAction.REFUSE:
        raise TurnInputError(decision.message or "Input refused by safety policy")
    if decision.action in (RouteAction.STOP, RouteAction.STOP_WITH_RESOURCE):
        return _persist_input_safety_stop(
            session_row=session_row,
            normalized=normalized,
            decision=decision,
            conn=conn,
            source_mode=source_mode,
            save_transcript=save_transcript,
            barged_in=barged_in,
        )
    # REDIRECT: safety policy is already injected into the LLM prompt; continue.
    # OK: proceed normally.

    compose_started = time.perf_counter()

    # 3. Load session state.
    session_id: str = session_row["session_id"]
    state_vars: Dict[str, int] = json.loads(session_row["state_vars_json"] or "{}")
    fired_event_ids: Set[str] = set(json.loads(session_row["fired_events_json"] or "[]"))
    turn_number: int = int(session_row["turn_count"]) + 1

    # If state_vars is empty (first turn), initialize from scenario variable defs.
    var_defs = build_variable_defs(state_variable_overrides)
    if not state_vars:
        state_vars = initialize_state(var_defs)

    # 3b. Scenario events (issue #580), on the state the previous turn left
    #     and the flags its reply raised. Each event that fires puts its
    #     npc_instruction into this turn's prompt, once for an event that fires
    #     once and on every turn its condition holds for a repeating one, and
    #     is recorded on this turn. Evaluated after the reply, as they were, no
    #     instruction ever reached a prompt: the session had moved on.
    events = scenario_events or []
    triggered_events = evaluate_event_triggers(
        state_vars,
        turn_number,
        events=events,
        fired_event_ids=fired_event_ids,
        active_flags=_previous_event_flags(session_id, conn),
    )
    event_instructions = _fired_event_instructions(events, triggered_events)

    # 4. Get recent transcript.
    recent_transcript = _load_recent_turns(session_id, conn)

    # 5. Load cross-session relationship recap for this NPC (may be None on
    #    the first session or when the feature is not yet populated).
    #    pack_id falls back to scenario_id so builtin scenarios partition
    #    their NPCs without requiring a pack row in the database.
    npc_id: str = scenario_data.npc.npc_id
    setup: Dict[str, Any] = json.loads(session_row["setup_json"] or "{}")
    pack_id: str = setup.get("pack_id") or scenario_data.scenario_id
    relationship_recap = get_relationship_recap(conn, npc_id, pack_id)

    # 6. Build prompt. The player's reply-speed preference (issue #501) scales
    #    the NPC's word budget here and its token budget at step 7, so a choice
    #    made in Settings mid-scenario applies to this very turn.
    reply_speed = load_reply_speed(conn)
    scenario_data = _apply_reply_speed(scenario_data, reply_speed)
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
        relationship_recap=relationship_recap,
        scenario_event_instructions=event_instructions,
    ))

    # 7. Call runtime. The model's registry entry sets the temperature and
    #    top_p when it declares them (issue #580); otherwise the request keeps
    #    ChatRequest's temperature and the adapter's top_p, as before.
    sampling = active_model_sampling(conn, runtime.id, config)
    messages = [
        ChatMessage(role="system", content=prompt.system_prompt),
        ChatMessage(role="user", content=prompt.user_prompt),
    ]
    # The session's schema, the one the prompt's OUTPUT_SCHEMA layer quotes:
    # with a rubric, rubric_id is an enum of its dimension ids (issue #578),
    # which the engine's schema-to-grammar conversion enforces.
    output_schema = turn_output_schema_for(scenario_data)
    request = ChatRequest(
        messages=messages,
        json_schema=output_schema,
        scripted_turn_index=turn_number,
        # Structured turn output (utterance + deltas + rubric observations)
        # regularly lands in the 300-600 token range; the 512 default left no
        # headroom and a truncated JSON object degrades to the fallback
        # utterance. Reasoning is disabled at the engine level, so the extra
        # budget costs nothing when unused. "balanced" keeps the 1024 this was
        # hardcoded to before reply speed became a setting.
        max_tokens=profile_for(reply_speed).max_tokens,
        **sampling.request_fields(),
    )
    logger.debug(
        "Calling runtime %s for session %s turn %d (estimated %d tokens, truncated=%s)",
        runtime.id, session_id, turn_number, prompt.estimated_token_count, prompt.was_truncated,
    )
    timing.compose_ms = (time.perf_counter() - compose_started) * 1000.0
    hidden_agenda = scenario_data.npc.private_persona.hidden_agenda

    # Streaming (issue #538): decode the spoken line out of the model's JSON as
    # it arrives, release it sentence by sentence once each sentence has passed
    # the output check, and tell the client which stage the turn is in. The
    # gate also holds back a first sentence that would make the line a repeat
    # of one of the NPC's last two lines (issue #580), so the repetition
    # guard's retry only ever replaces a line nobody has seen.
    # A player who asked for the line again gets it: neither the gate nor the
    # guard holds a repeat back on that turn, and one is only noted.
    previous_npc_lines = _previous_npc_lines(recent_transcript)
    repeat_requested = _player_asked_for_repeat(normalized)
    guarded_lines = [] if repeat_requested else previous_npc_lines
    extractor = UtteranceStreamExtractor() if streamer is not None else None
    gate = SentenceGate(hidden_agenda=hidden_agenda, previous_lines=guarded_lines)
    stream_state = {"writing_announced": False, "finishing_announced": False}

    async def _on_chunk(chunk: Any) -> bool:
        assert streamer is not None and extractor is not None
        if isinstance(chunk, ChatProgress):
            prompt = None
            if chunk.total is not None or chunk.processed is not None:
                prompt = {"processed": chunk.processed, "total": chunk.total, "cached": chunk.cached}
            await streamer.progress(chunk.stage, prompt)
            return False
        if isinstance(chunk, ChatToken):
            streamer.output_tokens += 1
            if not stream_state["writing_announced"]:
                stream_state["writing_announced"] = True
                await streamer.progress("writing")
            if not extractor.active:
                return False
            grew = extractor.feed(chunk.text)
            if not grew and not extractor.done:
                return False
            for piece in gate.feed(extractor.text, extractor.done):
                if timing.first_words_ms is None:
                    timing.first_words_ms = timing.clock.elapsed_ms()
                await streamer.token(piece)
            if gate.blocked is not None:
                # A sentence failed the check. Nothing released is withdrawn;
                # if anything was released, the line is committed as it stands
                # and generation stops here. If nothing was released yet, the
                # whole output is still collected so the normal validate /
                # retry path can run on it.
                return bool(gate.released)
            if extractor.done:
                if gate.repeated is not None:
                    # The first sentence would have repeated an earlier line,
                    # so the whole line is held for the repetition guard: the
                    # player has seen none of it and the line is not final.
                    return False
                timing.reply_done_ms = timing.clock.elapsed_ms()
                await streamer.final(gate.released_text)
                if not stream_state["finishing_announced"]:
                    stream_state["finishing_announced"] = True
                    await streamer.progress("finishing")
            return False
        return False

    if streamer is not None:
        await streamer.progress("waiting")
    observation = StreamObservation(sent_at=time.perf_counter())
    timing.observation = observation
    raw_text, native_structured, final = await _collect_runtime_output_timed(
        runtime, request, observation, on_chunk=_on_chunk if streamer is not None else None
    )
    # A reply the token budget cut off, or one the caller cancelled, is
    # recorded as stopped so the rolling medians leave it out (issue #519).
    # A stream this pipeline closed itself, after a released sentence's
    # successor failed the output check, has no final: that turn is not
    # stopped but salvaged, below.
    timing.mark_finish(final.finish_reason if final is not None else None)
    parse_started = time.perf_counter()

    released_line = gate.released_text if extractor is not None else ""
    turn_parse_events: List[TurnEvent] = []
    salvaged = False

    if released_line:
        # 8a. Released text is committed text (issue #538): build the turn from
        # the words the player has seen plus whatever bookkeeping the model
        # completed. No repair, no retry, no second model call.
        blocked = gate.blocked is not None
        salvage = salvage_turn_output(
            raw_text, native_structured, released_line, force_defaults=blocked
        )
        turn_output = salvage.output
        turn_output.rubric_observations = filter_rubric_observations(
            turn_output.rubric_observations, output_schema
        )
        salvaged = salvage.salvaged
        if blocked:
            violation = gate.blocked.first_violation
            turn_parse_events.append(TurnEvent(
                event_type="output_violation_detected",
                category=violation.category if violation else None,
                reason=violation.reason if violation else None,
                is_recoverable=violation.is_recoverable if violation else None,
            ))
            turn_parse_events.append(TurnEvent(
                event_type="stream_salvaged",
                reason="a later sentence failed the output check; the released sentences stand",
            ))
        elif salvaged:
            turn_parse_events.append(TurnEvent(
                event_type="stream_salvaged",
                reason="; ".join(f"{k}: {v}" for k, v in salvage.defaulted.items()) or "fields defaulted",
            ))
        # The gate let the first sentence out, so nothing it held back was for
        # repetition; a repeat later in the line is noted (issue #580).
        _note_repetition(
            released_line,
            previous_npc_lines,
            turn_parse_events,
            _REPEAT_REQUESTED if repeat_requested else _ALREADY_RELEASED,
        )
        used_fallback = False
    else:
        # 8b. Validate / repair / fallback, exactly as before streaming existed.
        # The original raw_text is preserved in the DB for the debug drawer,
        # unless the repetition guard keeps its retry (8c): then the retry's.
        parse_input = _parse_input(raw_text, native_structured)

        if streamer is not None and _repair_is_coming(parse_input, hidden_agenda):
            # The parser's repair runs synchronously, so the stage has to be
            # announced before it starts (#527 moves it onto the event loop).
            await streamer.progress("checking")

        # Wrap the runtime so parse_turn_output can make synchronous repair calls.
        # Hidden agenda is forwarded for verbatim-leak detection in the output validator.
        runtime_bridge = _SyncRuntimeBridge(runtime, timing, turn_parse_events, sampling)
        turn_output = _parse_reply(
            parse_input,
            request=request,
            runtime=runtime_bridge,
            hidden_agenda=hidden_agenda,
            events=turn_parse_events,
        )
        used_fallback = (turn_output.npc_utterance == SAFE_FALLBACK_UTTERANCE)
        if used_fallback:
            logger.warning("Turn output fell back to safe utterance for session %s turn %d", session_id, turn_number)
        # 8c. Repetition guard (issue #580): nothing of this line has been
        # shown, so a reply that repeats one of the NPC's last two lines may
        # still be replaced by one retry; unless the player asked for it.
        if repeat_requested and _is_model_line(turn_output):
            _note_repetition(
                turn_output.npc_utterance, previous_npc_lines, turn_parse_events, _REPEAT_REQUESTED,
            )
        # A first sentence the gate held back makes the line a repeat even
        # when the whole line, which ends otherwise, does not. The gate judged
        # the streamed reply; the parser's repair or safety retry may since
        # have replaced it, so the line being guarded is judged again the same
        # way, and a replacement that no longer opens with the repeat is not
        # retried for it.
        held: Optional[RepetitionReport] = None
        if gate.repeated is not None and _is_model_line(turn_output):
            again = first_sentence_repeats(turn_output.npc_utterance, guarded_lines)
            held = again if again.flagged else None
        kept_retry = await _guard_repetition(
            turn_output,
            guarded_lines,
            raw_text=raw_text,
            runtime=runtime,
            request=request,
            prompt=prompt,
            hidden_agenda=hidden_agenda,
            timing=timing,
            events=turn_parse_events,
            streamer=streamer,
            first_call_s=(observation.final_at or time.perf_counter()) - observation.sent_at,
            held=held,
        )
        if kept_retry is not None:
            # The retry is the turn: the row stores its output, which the
            # debrief scores and the debug drawer shows, not the first reply's.
            turn_output = kept_retry.output
            raw_text = kept_retry.raw_text
            native_structured = kept_retry.structured
    timing.fallback = used_fallback
    timing.salvaged = salvaged
    # The repair calls run inside parse_turn_output, so their wall time is
    # subtracted here: they are reported as extra_calls, not as "other".
    timing.parse_ms = max(
        0.0,
        (time.perf_counter() - parse_started) * 1000.0 - sum(c.ms for c in timing.extra_calls),
    )

    # 9. Handle safety status from model output.
    safety_stopped = turn_output.safety.status == "stop"

    # 10. Apply state delta. With state of the scenario's own, only the
    #     variables the session's schema names may move (issue #580): a runtime
    #     that ignores the schema, or a repair call sent without it, can still
    #     write a baseline the scenario never reads.
    played = state_variables_in_schema(output_schema)
    delta_result = apply_state_delta(
        state_vars,
        turn_output.state_delta,
        var_defs,
        allowed=played,
    )
    if delta_result.rejected_keys:
        logger.warning("State delta had unknown keys (rejected): %s", delta_result.rejected_keys)

    # 11. Scenario events were evaluated before the prompt (step 3b).

    # 12. Evaluate ending condition.
    ending_type = evaluate_ending_condition(
        delta_result.new_state,
        turn_number,
        max_turns,
        ending_conditions=ending_conditions,
        safety_stopped=safety_stopped,
    )

    # Model may also signal session end.
    if ending_type is None and not turn_output.session_control.continue_session:
        sc_ending = turn_output.session_control.ending_type
        if sc_ending and sc_ending != "none":
            ending_type = sc_ending

    new_flow_state = "Ended" if ending_type else "PlayerTurnListening"

    # 13. Persist atomically. Use `with conn:` so a mid-transaction failure
    # triggers an automatic rollback instead of leaving a dirty open transaction
    # on the singleton connection.
    now = datetime.now(timezone.utc).isoformat()
    player_turn_number = turn_number * 2 - 1
    npc_turn_number = turn_number * 2

    # State snapshot stored on the NPC turn row so any completed game turn can
    # serve as a fork point for branch sessions (see branch_service.py).
    state_snapshot_json = json.dumps({
        "state_vars": delta_result.new_state,
        "fired_events": list(fired_event_ids),
    })

    # Prompt metadata stored for debugging. Only non-private fields are kept:
    # token count, truncation flag, and which layers were present. The raw
    # prompt text and NPC private persona content are never written to the log.
    prompt_metadata_payload = json.dumps({
        "estimated_token_count": prompt.estimated_token_count,
        "was_truncated": prompt.was_truncated,
        "layers_present": list(prompt.layer_map.keys()),
    })

    persist_started = time.perf_counter()
    with conn:
        kept_state = _finished_state(conn, session_id)
        rows_state = kept_state or new_flow_state
        player_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, source_mode, barged_in, flow_state_after, created_at) "
            "VALUES (?, ?, 'player', ?, ?, ?, ?, ?)",
            (session_id, player_turn_number, normalized, source_mode, int(barged_in), rows_state, received_at),
        )
        npc_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, emotion, state_delta_json, event_flags_json, "
            "safety_json, raw_output_json, flow_state_after, state_snapshot_json, created_at) "
            "VALUES (?, ?, 'npc', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                rows_state,
                state_snapshot_json,
                now,
            ),
        )

        # Persist discrete turn events.
        events_to_insert: List[tuple] = []
        if barged_in:
            events_to_insert.append((
                session_id, turn_number, "barge_in",
                json.dumps({"turn_number": turn_number}), now,
            ))
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
        if turn_output.rubric_observations:
            events_to_insert.append((
                session_id, turn_number, "rubric_observations",
                json.dumps([
                    {
                        "rubric_id": obs.rubric_id,
                        "observation": obs.observation,
                        "score_delta": obs.score_delta,
                    }
                    for obs in turn_output.rubric_observations
                ]), now,
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
        if ending_type and not kept_state:
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
                "salvaged": salvaged,
                "streamed": bool(released_line),
                "used_native_structured_output": native_structured is not None,
                "parse_events": _debug_parse_events(turn_parse_events, save_transcript=save_transcript),
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

        new_flow_state, ending_type = _commit_session_state(
            conn,
            session_id,
            turn_number=turn_number,
            flow_state=new_flow_state,
            ending_type=ending_type,
            extra_sets="state_vars_json = ?, fired_events_json = ?, ",
            extra_params=(
                json.dumps(delta_result.new_state),
                json.dumps(list(fired_event_ids)),
            ),
        )

    timing.persist_ms = (time.perf_counter() - persist_started) * 1000.0

    # The meters: the visible variables, and with state of the scenario's own
    # only those it plays, the ones that can move (issue #580).
    visible, _ = partition_state_by_visibility(delta_result.new_state, var_defs, played)

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
        rubric_observations=[
            {
                "rubric_id": obs.rubric_id,
                "observation": obs.observation,
                "score_delta": obs.score_delta,
            }
            for obs in turn_output.rubric_observations
        ],
        safety_status=turn_output.safety.status,
        safety_reason=turn_output.safety.reason,
        ending_type=ending_type,
        ending_summary=turn_output.session_control.ending_summary,
        new_flow_state=new_flow_state,
        turn_number=turn_number,
        used_fallback=used_fallback,
        timing=timing,
        salvaged=salvaged,
        streamed_line=released_line or None,
    )
