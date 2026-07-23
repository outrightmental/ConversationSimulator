# SPDX-License-Identifier: Apache-2.0
"""Session management HTTP routes for the text-only turn pipeline.

Routes:
  POST   /api/sessions                    — create session
  GET    /api/sessions/{session_id}       — get session state
  POST   /api/sessions/{session_id}/start — start session (NPC opening)
  POST   /api/sessions/{session_id}/turn  — submit player turn (full pipeline)
  POST   /api/sessions/{session_id}/end   — end session

NOTE: Turn processing is not idempotent. Clients should check session state
(GET /api/sessions/{id}) before retrying after a network error to avoid
duplicate turns.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, field_validator

from convsim_core.runtime import build_runtime
from convsim_core.runtime.base import ChatRuntime
from convsim_core.scenario_state import build_variable_defs, partition_state_by_visibility
from convsim_core.scenarios import get_scenario_info
from convsim_core.services.branch_service import fork_session
from convsim_core.services.debrief_engine import generate_debrief
from convsim_core.services.model_manager_service import get_active_config
from convsim_core.services.relationship_memory import update_relationship_memory
from convsim_core.services.timing import thinking_pause_ms_for_difficulty
from convsim_core.services.transcript_export import format_transcript_as_markdown
from convsim_core.services.tts_queue import synthesize_utterance
from convsim_core.services.turn_pipeline import MAX_TURN_CONTENT_CHARS, TurnInputError, process_turn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_VALID_STATES_FOR_TURN = {"PlayerTurnListening"}


def _generate_session_id() -> str:
    return f"sess-{secrets.token_hex(8)}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conflict(detail: str, current_state: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"message": detail, "code": "INVALID_TRANSITION", "current_state": current_state},
    )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


_DEFAULT_TTS_VOICE_ID = "af_heart"


class SessionCreateRequest(BaseModel):
    scenario_id: str
    difficulty: Literal["warm", "standard", "hard", "adversarial"] = "standard"
    player_role_name: str
    language: str = "en"
    input_mode: Literal["text-only", "push-to-talk", "hands-free"] = "text-only"
    tts_enabled: bool = False
    tts_voice_id: str = _DEFAULT_TTS_VOICE_ID
    # Conversational timing features (issue #308)
    npc_thinking_pause_enabled: bool = True
    backchannel_enabled: bool = False
    barge_in_enabled: bool = True
    show_state_meters: bool = False
    save_transcript: bool = True
    seed: Optional[int] = None
    # Pins the session to a model-free runtime for its whole lifetime (issue #427).
    # Restricted to the runtimes that need no model and reach nothing off-box, so a
    # client can never point a session at a sidecar-backed runtime this way.
    runtime_id: Optional[Literal["scripted", "fake"]] = None

    @field_validator("player_role_name")
    @classmethod
    def player_role_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("player_role_name cannot be blank")
        return v

    @field_validator("tts_voice_id")
    @classmethod
    def tts_voice_id_must_be_approved(cls, v: str) -> str:
        from convsim_core.tts.voices import validate_voice_id
        from convsim_core.tts.types import TtsVoiceValidationError
        try:
            validate_voice_id(v)
        except TtsVoiceValidationError as exc:
            raise ValueError(str(exc)) from exc
        return v


class SessionResponse(BaseModel):
    session_id: str
    scenario_id: str
    state: str
    created_at: str
    setup: Dict[str, Any]


class SessionEventPayload(BaseModel):
    event_id: int
    session_id: str
    event_type: str
    payload: Dict[str, Any]
    created_at: str


class SessionStartResponse(BaseModel):
    session_id: str
    state: str
    events: List[SessionEventPayload]


class TurnSubmitRequest(BaseModel):
    content: str
    barged_in: bool = False

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Turn content cannot be blank")
        if len(v.strip()) > MAX_TURN_CONTENT_CHARS:
            raise ValueError(f"Turn content exceeds {MAX_TURN_CONTENT_CHARS} characters")
        return v


class TurnResponse(BaseModel):
    session_id: str
    state: str
    events: List[SessionEventPayload]
    ending_type: Optional[str] = None


class SessionEndResponse(BaseModel):
    session_id: str
    state: str
    ending_type: str


class TurnEntry(BaseModel):
    turn_number: int
    role: str
    content: str
    source_mode: Optional[str] = None
    emotion: Optional[str] = None
    flow_state_after: Optional[str] = None
    created_at: str


class TranscriptResponse(BaseModel):
    session_id: str
    scenario_id: str
    transcript_saved: bool
    message: Optional[str] = None
    turns: List[TurnEntry]


class EventEntry(BaseModel):
    id: int
    turn_number: Optional[int] = None
    event_type: str
    payload: Dict[str, Any]
    occurred_at: str


class SessionExportResponse(BaseModel):
    session_id: str
    exported_at: str
    scenario: Dict[str, Any]
    setup: Dict[str, Any]
    state: str
    ending_type: Optional[str] = None
    turn_count: int
    created_at: str
    transcript_saved: bool
    visible_state: Dict[str, int]
    turns: List[TurnEntry]
    events: List[EventEntry]
    debrief: Optional[Dict[str, Any]] = None


class TurnDebugDetail(BaseModel):
    turn_number: int
    raw_npc_output: Optional[str]
    used_native_structured_output: bool
    used_fallback: bool
    parse_events: List[Dict[str, Any]]
    prompt_metadata: Optional[Dict[str, Any]]


class SessionDebugResponse(BaseModel):
    session_id: str
    turns: List[TurnDebugDetail]


class DebriefTurningPoint(BaseModel):
    turn_number: int
    description: str
    impact: str


class DebriefResponse(BaseModel):
    session_id: str
    scenario_id: str
    pack_id: Optional[str] = None
    outcome: str
    total_turns: int
    scores: Dict[str, float]
    overall_score: Optional[float] = None
    summary: str
    strengths: List[str]
    improvements: List[str]
    missed_opportunities: List[str] = []
    turning_points: List[DebriefTurningPoint]
    replay_suggestions: List[str]
    npc_final_state: Dict[str, int]
    generated_at: str
    used_fallback: bool
    metrics: Optional[Dict[str, Any]] = None


class BranchSessionRequest(BaseModel):
    fork_turn_number: int


class BranchSessionResponse(BaseModel):
    branch_session_id: str
    parent_session_id: str
    fork_turn_number: int
    state: str
    created_at: str


class SessionCompareSummary(BaseModel):
    session_id: str
    outcome: Optional[str] = None
    total_turns: int
    overall_score: Optional[float] = None
    headline_metrics: Optional[Dict[str, Any]] = None


class SessionCompareResponse(BaseModel):
    parent_session_id: str
    branch_session_id: str
    fork_turn_number: int
    parent: SessionCompareSummary
    branch: SessionCompareSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_tts_for_utterance(
    utterance: str,
    session_id: str,
    turn_number: int,
    voice_id: str,
    tts_worker: Any,
    conn: Any,
    now: str,
    thinking_pause_ms: int = 0,
) -> List[SessionEventPayload]:
    """Synthesize *utterance* sentence-by-sentence and persist tts_audio_chunk events.

    Returns an ordered list of SessionEventPayload for the caller to include in
    the HTTP response.  Any TTS failure is captured per-chunk and does not raise.

    ``thinking_pause_ms`` is embedded in the first chunk's payload so the client
    can delay playback start to simulate the NPC "thinking" before speaking.
    """
    try:
        chunks = await synthesize_utterance(
            utterance=utterance,
            voice_id=voice_id,
            tts_worker=tts_worker,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("TTS queue failed for session %s: %s", session_id, exc, exc_info=True)
        return []

    events: List[SessionEventPayload] = []
    for i, chunk in enumerate(chunks):
        payload: Dict[str, Any] = {
            "chunk_index": chunk.chunk_index,
            "total_chunks": chunk.total_chunks,
            "text": chunk.text,
            "voice_id": chunk.voice_id,
            "cache_path": chunk.audio_path,
            "error": chunk.error,
        }
        # Attach thinking pause only to the first chunk so the client waits
        # before starting playback, then streams subsequent chunks normally.
        if i == 0 and thinking_pause_ms > 0:
            payload["thinking_pause_ms"] = thinking_pause_ms
        cursor = conn.execute(
            "INSERT INTO turn_session_events "
            "(session_id, turn_number, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, 'tts_audio_chunk', ?, ?)",
            (session_id, turn_number, json.dumps(payload), now),
        )
        conn.commit()
        events.append(SessionEventPayload(
            event_id=cursor.lastrowid,
            session_id=session_id,
            event_type="tts_audio_chunk",
            payload=payload,
            created_at=now,
        ))
    return events


def _row_to_response(row: Any) -> SessionResponse:
    return SessionResponse(
        session_id=row["session_id"],
        scenario_id=row["scenario_id"],
        state=row["flow_state"],
        created_at=row["created_at"],
        setup=json.loads(row["setup_json"]),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


#: Runtimes that are stateless, model-free and cheap to instantiate per request.
#: A session that starts on one of these keeps it for its whole lifetime, so a
#: scripted tutorial cannot be hijacked by a model install that finishes mid-play.
_SESSION_PINNED_RUNTIME_IDS = ("scripted", "fake")


def _pinned_runtime_id(requested: str | None, conn: Any) -> str | None:
    """Return the runtime id to pin this session to, or None to follow the global one.

    An explicit ``runtime_id`` on the create request wins: the scripted tutorial
    asks for its runtime by name, so it cannot land on the fake runtime just
    because the preceding ``use_model`` call failed, or because a background
    model install flipped the global selection in the window between the two
    requests. Otherwise fall back to the active selection, which pins demo-mode
    and scripted sessions created through the ordinary setup form.
    """
    if requested in _SESSION_PINNED_RUNTIME_IDS:
        return requested
    runtime_id = get_active_config(conn).get("runtime_id")
    return runtime_id if runtime_id in _SESSION_PINNED_RUNTIME_IDS else None


def _resolve_runtime(request: Request, setup: Dict[str, Any]) -> ChatRuntime:
    """Return the runtime this session was pinned to, else the shared runtime.

    ``setup["runtime_id"]`` is snapshotted at session creation (see
    ``create_session``) when the session asked for a scripted/fake runtime or the
    active selection was one of those, so a tutorial keeps answering from its
    authored script even after a background model install flips the global active
    runtime to llama.cpp.

    For sidecar-based runtimes (llama.cpp, Ollama) — and for sessions created
    before this snapshot existed — the shared ``app.state.runtime`` is returned
    to preserve connection-pool state and support test-injected runtimes.
    """
    runtime_id = setup.get("runtime_id")
    if runtime_id in _SESSION_PINNED_RUNTIME_IDS:
        return build_runtime(runtime_id)
    return request.app.state.runtime


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session(body: SessionCreateRequest, request: Request) -> SessionResponse:
    info = get_scenario_info(body.scenario_id)
    if info is None:
        raise HTTPException(status_code=400, detail=f"Unknown scenario_id: {body.scenario_id!r}")

    diff_options = info.difficulty_options
    if body.difficulty not in diff_options:
        raise HTTPException(
            status_code=400,
            detail=f"Difficulty {body.difficulty!r} is not available for scenario {body.scenario_id!r}",
        )

    if body.language not in info.supported_languages:
        raise HTTPException(
            status_code=400,
            detail=f"Language {body.language!r} is not supported by scenario {body.scenario_id!r}",
        )

    db = request.app.state.db
    conn = db.connection()
    session_id = _generate_session_id()
    now = _now_iso()
    setup_dict = body.model_dump()
    # Pin scripted/fake sessions to their runtime for the whole session. Without
    # this the tutorial would follow the global active runtime, which flips to
    # llama.cpp the moment a background model install finishes — mid-conversation,
    # or before the tutorial's authored debrief is generated.
    pinned_runtime_id = _pinned_runtime_id(body.runtime_id, conn)
    if pinned_runtime_id is None:
        # Leave no key at all rather than a null one, so _resolve_runtime's
        # membership test reads the same for old and new sessions.
        setup_dict.pop("runtime_id", None)
    else:
        setup_dict["runtime_id"] = pinned_runtime_id

    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, turn_count, setup_json, created_at) "
        "VALUES (?, ?, 'NotStarted', '{}', '[]', 0, ?, ?)",
        (session_id, body.scenario_id, json.dumps(setup_dict), now),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    return _row_to_response(row)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return _row_to_response(row)


@router.post("/{session_id}/start", response_model=SessionStartResponse)
async def start_session(session_id: str, request: Request) -> SessionStartResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    current_state = row["flow_state"]
    if current_state != "NotStarted":
        raise _conflict(
            f"Cannot start session from state {current_state!r}. Session must be in NotStarted state.",
            current_state,
        )

    info = get_scenario_info(row["scenario_id"])
    opening_text = (
        info.opening_npc_says if info else "Hello! I am ready to begin. Please go ahead."
    )
    setup = json.loads(row["setup_json"])
    save_transcript = setup.get("save_transcript", True)

    now = _now_iso()
    with conn:
        conn.execute(
            "UPDATE turn_sessions SET flow_state = 'PlayerTurnListening' WHERE session_id = ?",
            (session_id,),
        )
        cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, flow_state_after, created_at) "
            "VALUES (?, 0, 'npc_opening', ?, 'PlayerTurnListening', ?)",
            (session_id, opening_text, now),
        )
        if save_transcript:
            conn.execute(
                "INSERT INTO session_transcript_fts(session_id, turn_number, role, content) "
                "VALUES (?, ?, ?, ?)",
                (session_id, 0, "npc_opening", opening_text),
            )

    opening_event = SessionEventPayload(
        event_id=cursor.lastrowid,
        session_id=session_id,
        event_type="npc_opening",
        payload={"content": opening_text},
        created_at=now,
    )

    tts_enabled = setup.get("tts_enabled", False)
    tts_events: List[SessionEventPayload] = []
    if tts_enabled:
        voice_id = setup.get("tts_voice_id", _DEFAULT_TTS_VOICE_ID)
        tts_events = await _run_tts_for_utterance(
            utterance=opening_text,
            session_id=session_id,
            turn_number=0,
            voice_id=voice_id,
            tts_worker=request.app.state.tts_worker,
            conn=conn,
            now=now,
        )

    return SessionStartResponse(
        session_id=session_id,
        state="PlayerTurnListening",
        events=[opening_event] + tts_events,
    )


@router.post("/{session_id}/turn", response_model=TurnResponse)
async def submit_turn(session_id: str, body: TurnSubmitRequest, request: Request) -> TurnResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    current_state = row["flow_state"]
    if current_state not in _VALID_STATES_FOR_TURN:
        raise _conflict(
            f"Cannot submit turn from state {current_state!r}. Session must be in PlayerTurnListening state.",
            current_state,
        )

    setup = json.loads(row["setup_json"])
    scenario_id = row["scenario_id"]
    difficulty = setup.get("difficulty", "standard")
    info = get_scenario_info(scenario_id)
    if info is None:
        raise HTTPException(status_code=500, detail=f"Scenario {scenario_id!r} not found in registry")

    scenario_data = info.get_scenario_data(difficulty)
    max_turns = info.max_turns

    runtime = _resolve_runtime(request, setup)
    save_transcript = setup.get("save_transcript", True)
    source_mode = setup.get("input_mode", "text-only")

    try:
        result = await process_turn(
            session_row=row,
            player_text=body.content,
            scenario_data=scenario_data,
            max_turns=max_turns,
            runtime=runtime,
            conn=conn,
            save_transcript=save_transcript,
            source_mode=source_mode,
            barged_in=body.barged_in,
            state_variable_overrides=info.state_variable_overrides,
            scenario_events=info.events,
            ending_conditions=info.ending_conditions,
        )
    except TurnInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = _now_iso()
    player_event = SessionEventPayload(
        event_id=result.player_event_id,
        session_id=session_id,
        event_type="player_turn",
        payload={"content": result.player_content, "barged_in": body.barged_in},
        created_at=now,
    )
    npc_event = SessionEventPayload(
        event_id=result.npc_event_id,
        session_id=session_id,
        event_type="npc_turn",
        payload={
            "content": result.npc_utterance,
            "emotion": result.npc_emotion,
            "state_delta": result.state_delta,
            "visible_state": result.visible_state,
            "event_flags": result.event_flags,
            "triggered_scenario_events": result.triggered_scenario_events,
            "rubric_observations": result.rubric_observations,
            "safety": {
                "status": result.safety_status,
                "reason": result.safety_reason,
            },
            "ending_type": result.ending_type,
        },
        created_at=now,
    )

    tts_events: List[SessionEventPayload] = []
    tts_enabled = setup.get("tts_enabled", False)
    if tts_enabled and not result.used_fallback:
        voice_id = setup.get("tts_voice_id", _DEFAULT_TTS_VOICE_ID)
        npc_thinking_pause_enabled = setup.get("npc_thinking_pause_enabled", True)
        diff_settings = scenario_data.difficulty_settings
        pause_ms = thinking_pause_ms_for_difficulty(
            difficulty_settings_patience=diff_settings.patience if diff_settings else 50,
            enabled=bool(npc_thinking_pause_enabled),
        )
        tts_events = await _run_tts_for_utterance(
            utterance=result.npc_utterance,
            session_id=session_id,
            turn_number=result.turn_number,
            voice_id=voice_id,
            tts_worker=request.app.state.tts_worker,
            conn=conn,
            now=now,
            thinking_pause_ms=pause_ms,
        )

    return TurnResponse(
        session_id=session_id,
        state=result.new_flow_state,
        events=[player_event, npc_event] + tts_events,
        ending_type=result.ending_type,
    )


@router.post("/{session_id}/end", response_model=SessionEndResponse)
async def end_session(session_id: str, request: Request) -> SessionEndResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    current_state = row["flow_state"]
    if current_state == "Ended":
        raise _conflict(
            f"Session is already in terminal state {current_state!r}.",
            current_state,
        )

    ending_type: str = row["ending_type"] or "player_exit"
    conn.execute(
        "UPDATE turn_sessions SET flow_state = 'Ended', ending_type = ?, "
        "ended_at = COALESCE(ended_at, datetime('now')) WHERE session_id = ?",
        (ending_type, session_id),
    )
    conn.commit()

    return SessionEndResponse(
        session_id=session_id,
        state="Ended",
        ending_type=ending_type,
    )


@router.get("/{session_id}/debug", response_model=SessionDebugResponse)
async def get_session_debug(session_id: str, request: Request) -> SessionDebugResponse:
    """Dev-only: return raw NPC output and validation events for every turn.

    Exposes the raw model output text, parse/validation events, prompt metadata,
    and structured-output flags for each turn.  This data is stored locally and
    never sent to any remote service.  Do not surface this endpoint in the normal
    player UI.
    """
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT session_id FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    # NPC turn rows store the raw model output.  turn_number for NPC rows is
    # game_turn * 2 (player is game_turn * 2 - 1), so we divide by 2 to map
    # back to the game turn used in turn_session_events.
    npc_rows = conn.execute(
        "SELECT turn_number, raw_output_json FROM turn_session_turns "
        "WHERE session_id = ? AND role = 'npc' ORDER BY turn_number ASC",
        (session_id,),
    ).fetchall()
    raw_by_game_turn: Dict[int, Optional[str]] = {
        t["turn_number"] // 2: t["raw_output_json"] for t in npc_rows
    }

    # Debug and prompt_metadata events share the same game turn number.
    event_rows = conn.execute(
        "SELECT turn_number, event_type, payload_json FROM turn_session_events "
        "WHERE session_id = ? AND event_type IN ('debug', 'prompt_metadata') "
        "ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    debug_by_turn: Dict[int, Dict[str, Any]] = {}
    prompt_by_turn: Dict[int, Dict[str, Any]] = {}
    for e in event_rows:
        tn = e["turn_number"]
        if tn is None:
            continue
        payload = json.loads(e["payload_json"])
        if e["event_type"] == "debug":
            debug_by_turn[tn] = payload
        else:
            prompt_by_turn[tn] = payload

    all_game_turns = sorted(set(raw_by_game_turn) | set(debug_by_turn))
    turns: List[TurnDebugDetail] = []
    for game_turn in all_game_turns:
        debug = debug_by_turn.get(game_turn, {})
        turns.append(TurnDebugDetail(
            turn_number=game_turn,
            raw_npc_output=raw_by_game_turn.get(game_turn),
            used_native_structured_output=debug.get("used_native_structured_output", False),
            used_fallback=debug.get("used_fallback", False),
            parse_events=debug.get("parse_events", []),
            prompt_metadata=prompt_by_turn.get(game_turn),
        ))

    return SessionDebugResponse(session_id=session_id, turns=turns)


@router.post("/{session_id}/debrief", response_model=DebriefResponse)
async def create_debrief(session_id: str, request: Request) -> DebriefResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    current_state = row["flow_state"]

    # If debrief already exists, return it.
    if current_state == "DebriefReady":
        existing = conn.execute(
            "SELECT content_json FROM session_debriefs "
            "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if existing:
            doc = json.loads(existing["content_json"])
            return DebriefResponse(
                session_id=doc["session_id"],
                scenario_id=doc["scenario_id"],
                pack_id=doc.get("pack_id"),
                outcome=doc["outcome"],
                total_turns=doc.get("total_turns", 0),
                scores=doc.get("scores", {}),
                overall_score=doc.get("overall_score"),
                summary=doc.get("summary", ""),
                strengths=doc.get("strengths", []),
                improvements=doc.get("improvements", []),
                missed_opportunities=doc.get("missed_opportunities", []),
                turning_points=[
                    DebriefTurningPoint(**tp) for tp in doc.get("turning_points", [])
                ],
                replay_suggestions=doc.get("replay_suggestions", []),
                npc_final_state=doc.get("npc_final_state", {}),
                generated_at=doc.get("generated_at", _now_iso()),
                used_fallback=doc.get("used_fallback", False),
                metrics=doc.get("metrics"),
            )
        # DebriefReady state with no persisted row — data inconsistency.
        raise HTTPException(
            status_code=500,
            detail=f"Debrief record missing for session {session_id!r} in DebriefReady state",
        )

    # Must be in Ended, DebriefGenerating (retry), or Error (retry after failure) to generate.
    if current_state not in ("Ended", "DebriefGenerating", "Error"):
        raise _conflict(
            f"Cannot generate debrief from state {current_state!r}. "
            "Session must be in Ended state.",
            current_state,
        )

    scenario_id = row["scenario_id"]
    setup = json.loads(row["setup_json"])
    difficulty = setup.get("difficulty", "standard")
    info = get_scenario_info(scenario_id)
    if info is None:
        raise HTTPException(status_code=500, detail=f"Scenario {scenario_id!r} not found in registry")

    scenario_data = info.get_scenario_data(difficulty)
    runtime = _resolve_runtime(request, setup)

    try:
        result = await generate_debrief(
            session_row=row,
            conn=conn,
            runtime=runtime,
            scenario_data=scenario_data,
        )
    except Exception as exc:
        logger.error("Debrief generation failed for session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Debrief generation failed") from exc

    # Update the NPC relationship recap with this session's debrief data.
    # pack_id falls back to scenario_id for built-in scenarios that have no pack.
    npc_id = scenario_data.npc.npc_id
    pack_id = result.pack_id or scenario_id
    update_relationship_memory(
        conn,
        npc_id=npc_id,
        pack_id=pack_id,
        outcome=result.outcome,
        scores=result.scores,
        improvements=result.improvements,
        generated_at=result.generated_at,
    )

    return DebriefResponse(
        session_id=result.session_id,
        scenario_id=result.scenario_id,
        pack_id=result.pack_id,
        outcome=result.outcome,
        total_turns=result.total_turns,
        scores=result.scores,
        overall_score=result.overall_score,
        summary=result.summary,
        strengths=result.strengths,
        improvements=result.improvements,
        missed_opportunities=result.missed_opportunities,
        turning_points=[
            DebriefTurningPoint(**tp) for tp in result.turning_points
        ],
        replay_suggestions=result.replay_suggestions,
        npc_final_state=result.npc_final_state,
        generated_at=result.generated_at,
        used_fallback=result.used_fallback,
        metrics=result.metrics if result.metrics else None,
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT session_id FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    with conn:
        # FTS shadow tables have no foreign-key cascade, so delete entries explicitly.
        conn.execute("DELETE FROM session_transcript_fts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM turn_sessions WHERE session_id = ?", (session_id,))


def _turns_from_rows(rows: list) -> List[TurnEntry]:
    return [
        TurnEntry(
            turn_number=t["turn_number"],
            role=t["role"],
            content=t["content"],
            source_mode=t["source_mode"],
            emotion=t["emotion"],
            flow_state_after=t["flow_state_after"],
            created_at=t["created_at"],
        )
        for t in rows
    ]


@router.get("/{session_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(session_id: str, request: Request) -> TranscriptResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    setup = json.loads(row["setup_json"])
    save_transcript = setup.get("save_transcript", True)

    if not save_transcript:
        return TranscriptResponse(
            session_id=session_id,
            scenario_id=row["scenario_id"],
            transcript_saved=False,
            message="Transcript saving is disabled for this session.",
            turns=[],
        )

    turn_rows = conn.execute(
        "SELECT turn_number, role, content, source_mode, emotion, flow_state_after, created_at "
        "FROM turn_session_turns WHERE session_id = ? ORDER BY turn_number ASC",
        (session_id,),
    ).fetchall()

    return TranscriptResponse(
        session_id=session_id,
        scenario_id=row["scenario_id"],
        transcript_saved=True,
        turns=_turns_from_rows(turn_rows),
    )


@router.get("/{session_id}/export/text", response_class=PlainTextResponse)
async def export_session_text(session_id: str, request: Request) -> PlainTextResponse:
    """Export a session transcript and debrief as human-readable Markdown text.

    Returns a UTF-8 text/markdown response with Content-Disposition set for
    file download.  All data is sourced locally from the session database.
    """
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    setup = json.loads(row["setup_json"])
    save_transcript = setup.get("save_transcript", True)
    scenario_id = row["scenario_id"]

    turn_rows = (
        conn.execute(
            "SELECT turn_number, role, content, emotion "
            "FROM turn_session_turns WHERE session_id = ? ORDER BY turn_number ASC",
            (session_id,),
        ).fetchall()
        if save_transcript
        else []
    )

    debrief_row = conn.execute(
        "SELECT content_json FROM session_debriefs "
        "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    debrief_doc = json.loads(debrief_row["content_json"]) if debrief_row else None

    turns = [dict(r) for r in turn_rows]
    markdown = format_transcript_as_markdown(
        session_id=session_id,
        scenario_id=scenario_id,
        turns=turns,
        debrief=debrief_doc,
        transcript_saved=save_transcript,
    )
    filename = f"session-{session_id}-transcript.md"
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{session_id}/branch", status_code=201, response_model=BranchSessionResponse)
async def create_branch_session(
    session_id: str, body: BranchSessionRequest, request: Request
) -> BranchSessionResponse:
    """Fork the session at the start of game turn *fork_turn_number*.

    Creates a new branch session that inherits the parent's state and transcript
    up to turn N-1, then resumes in PlayerTurnListening so the player can try a
    different approach at turn N.  The branch session is fully independent and
    supports its own debrief.  Use GET /{branch_id}/compare to compare outcomes.

    Requires the parent session to have at least *fork_turn_number* completed
    game turns and to have been played with snapshot-enabled pipeline (any
    session created after this feature was shipped).
    """
    db = request.app.state.db
    conn = db.connection()

    try:
        branch_session_id, created_at = fork_session(
            parent_session_id=session_id,
            fork_turn_number=body.fork_turn_number,
            conn=conn,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    return BranchSessionResponse(
        branch_session_id=branch_session_id,
        parent_session_id=session_id,
        fork_turn_number=body.fork_turn_number,
        state="PlayerTurnListening",
        created_at=created_at,
    )


def _debrief_headline(conn: Any, session_id: str) -> tuple[Optional[str], Optional[float], Optional[Dict[str, Any]]]:
    """Return (outcome, overall_score, headline_metrics) from the stored debrief, or Nones."""
    debrief_row = conn.execute(
        "SELECT content_json, metrics_json FROM session_debriefs "
        "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if debrief_row is None:
        return None, None, None
    doc = json.loads(debrief_row["content_json"])
    outcome: Optional[str] = doc.get("outcome")
    overall_score: Optional[float] = doc.get("overall_score")
    metrics_raw = debrief_row["metrics_json"] or doc.get("metrics")
    headline: Optional[Dict[str, Any]] = None
    if metrics_raw:
        m = json.loads(metrics_raw) if isinstance(metrics_raw, str) else metrics_raw
        headline = {
            "talk_ratio": m.get("talk_ratio"),
            "open_questions": m.get("open_questions"),
            "words_per_turn_player": m.get("words_per_turn_player"),
            "response_latency_p50_ms": m.get("response_latency_p50_ms"),
        }
    return outcome, overall_score, headline


@router.get("/{session_id}/compare", response_model=SessionCompareResponse)
async def compare_branch_session(session_id: str, request: Request) -> SessionCompareResponse:
    """Compare this branch session against its parent run.

    Returns headline outcome and metric summaries for both sessions so the
    player can see how their different choice at the fork point played out.
    Debrief data is included when available; sessions without a debrief return
    ``null`` for score and metrics fields.

    Returns 404 if the session is not a branch (has no parent in
    ``session_branches``).
    """
    db = request.app.state.db
    conn = db.connection()

    branch_row = conn.execute(
        "SELECT * FROM session_branches WHERE branch_session_id = ?", (session_id,)
    ).fetchone()
    if branch_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id!r} is not a branch session or has no recorded parent",
        )

    parent_id: str = branch_row["parent_session_id"]
    fork_turn: int = branch_row["fork_turn_number"]

    parent_session = conn.execute(
        "SELECT turn_count, ending_type FROM turn_sessions WHERE session_id = ?", (parent_id,)
    ).fetchone()
    branch_session = conn.execute(
        "SELECT turn_count, ending_type FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()

    if parent_session is None:
        raise HTTPException(status_code=404, detail=f"Parent session {parent_id!r} not found")
    if branch_session is None:
        raise HTTPException(status_code=404, detail=f"Branch session {session_id!r} not found")

    p_outcome, p_score, p_metrics = _debrief_headline(conn, parent_id)
    b_outcome, b_score, b_metrics = _debrief_headline(conn, session_id)

    return SessionCompareResponse(
        parent_session_id=parent_id,
        branch_session_id=session_id,
        fork_turn_number=fork_turn,
        parent=SessionCompareSummary(
            session_id=parent_id,
            outcome=p_outcome or parent_session["ending_type"],
            total_turns=int(parent_session["turn_count"]),
            overall_score=p_score,
            headline_metrics=p_metrics,
        ),
        branch=SessionCompareSummary(
            session_id=session_id,
            outcome=b_outcome or branch_session["ending_type"],
            total_turns=int(branch_session["turn_count"]),
            overall_score=b_score,
            headline_metrics=b_metrics,
        ),
    )


@router.get("/{session_id}/export", response_model=SessionExportResponse)
async def export_session(session_id: str, request: Request) -> SessionExportResponse:
    db = request.app.state.db
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    setup = json.loads(row["setup_json"])
    save_transcript = setup.get("save_transcript", True)
    scenario_id = row["scenario_id"]
    info = get_scenario_info(scenario_id)
    scenario_meta: Dict[str, Any] = {
        "id": scenario_id,
        "name": info.scenario_data.title if info else scenario_id,
    }

    state_vars: Dict[str, int] = json.loads(row["state_vars_json"] or "{}")
    var_defs = build_variable_defs()
    visible_state, _ = partition_state_by_visibility(state_vars, var_defs)

    turn_rows = (
        conn.execute(
            "SELECT turn_number, role, content, source_mode, emotion, flow_state_after, created_at "
            "FROM turn_session_turns WHERE session_id = ? ORDER BY turn_number ASC",
            (session_id,),
        ).fetchall()
        if save_transcript
        else []
    )

    event_rows = conn.execute(
        "SELECT id, turn_number, event_type, payload_json, occurred_at "
        "FROM turn_session_events WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()

    debrief_row = conn.execute(
        "SELECT content_json FROM session_debriefs "
        "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    debrief_doc = json.loads(debrief_row["content_json"]) if debrief_row else None

    return SessionExportResponse(
        session_id=session_id,
        exported_at=_now_iso(),
        scenario=scenario_meta,
        setup=setup,
        state=row["flow_state"],
        ending_type=row["ending_type"],
        turn_count=row["turn_count"],
        created_at=row["created_at"],
        transcript_saved=save_transcript,
        visible_state=visible_state,
        turns=_turns_from_rows(turn_rows),
        events=[
            EventEntry(
                id=e["id"],
                turn_number=e["turn_number"],
                event_type=e["event_type"],
                payload=json.loads(e["payload_json"]),
                occurred_at=e["occurred_at"],
            )
            for e in event_rows
        ],
        debrief=debrief_doc,
    )
