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
from pydantic import BaseModel, field_validator

from convsim_core.scenario_state import build_variable_defs, partition_state_by_visibility
from convsim_core.scenarios import get_scenario_info
from convsim_core.services.debrief_engine import generate_debrief
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
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    player_role_name: str
    language: str = "en"
    input_mode: Literal["text-only", "push-to-talk", "hands-free"] = "text-only"
    tts_enabled: bool = False
    tts_voice_id: str = _DEFAULT_TTS_VOICE_ID
    show_state_meters: bool = False
    save_transcript: bool = True
    seed: Optional[int] = None

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
    turning_points: List[DebriefTurningPoint]
    replay_suggestions: List[str]
    npc_final_state: Dict[str, int]
    generated_at: str
    used_fallback: bool


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
) -> List[SessionEventPayload]:
    """Synthesize *utterance* sentence-by-sentence and persist tts_audio_chunk events.

    Returns an ordered list of SessionEventPayload for the caller to include in
    the HTTP response.  Any TTS failure is captured per-chunk and does not raise.
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
    for chunk in chunks:
        payload: Dict[str, Any] = {
            "chunk_index": chunk.chunk_index,
            "total_chunks": chunk.total_chunks,
            "text": chunk.text,
            "voice_id": chunk.voice_id,
            "cache_path": chunk.audio_path,
            "error": chunk.error,
        }
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
    difficulty = setup.get("difficulty", "normal")
    info = get_scenario_info(scenario_id)
    if info is None:
        raise HTTPException(status_code=500, detail=f"Scenario {scenario_id!r} not found in registry")

    scenario_data = info.get_scenario_data(difficulty)
    max_turns = info.max_turns

    runtime = request.app.state.runtime
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
        )
    except TurnInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = _now_iso()
    player_event = SessionEventPayload(
        event_id=result.player_event_id,
        session_id=session_id,
        event_type="player_turn",
        payload={"content": result.player_content},
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
            "event_flags": result.event_flags,
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
        tts_events = await _run_tts_for_utterance(
            utterance=result.npc_utterance,
            session_id=session_id,
            turn_number=result.turn_number,
            voice_id=voice_id,
            tts_worker=request.app.state.tts_worker,
            conn=conn,
            now=now,
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
        "UPDATE turn_sessions SET flow_state = 'Ended', ending_type = ? WHERE session_id = ?",
        (ending_type, session_id),
    )
    conn.commit()

    return SessionEndResponse(
        session_id=session_id,
        state="Ended",
        ending_type=ending_type,
    )


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
                turning_points=[
                    DebriefTurningPoint(**tp) for tp in doc.get("turning_points", [])
                ],
                replay_suggestions=doc.get("replay_suggestions", []),
                npc_final_state=doc.get("npc_final_state", {}),
                generated_at=doc.get("generated_at", _now_iso()),
                used_fallback=doc.get("used_fallback", False),
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
    difficulty = setup.get("difficulty", "normal")
    info = get_scenario_info(scenario_id)
    if info is None:
        raise HTTPException(status_code=500, detail=f"Scenario {scenario_id!r} not found in registry")

    scenario_data = info.get_scenario_data(difficulty)
    runtime = request.app.state.runtime

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
        turning_points=[
            DebriefTurningPoint(**tp) for tp in result.turning_points
        ],
        replay_suggestions=result.replay_suggestions,
        npc_final_state=result.npc_final_state,
        generated_at=result.generated_at,
        used_fallback=result.used_fallback,
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
