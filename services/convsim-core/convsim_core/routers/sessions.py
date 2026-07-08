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


class SessionCreateRequest(BaseModel):
    scenario_id: str
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    player_role_name: str
    language: str = "en"
    input_mode: Literal["text-only", "push-to-talk", "hands-free"] = "text-only"
    tts_enabled: bool = False
    show_state_meters: bool = False
    save_transcript: bool = True
    seed: Optional[int] = None

    @field_validator("player_role_name")
    @classmethod
    def player_role_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("player_role_name cannot be blank")
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    event = SessionEventPayload(
        event_id=cursor.lastrowid,
        session_id=session_id,
        event_type="npc_opening",
        payload={"content": opening_text},
        created_at=now,
    )
    return SessionStartResponse(
        session_id=session_id,
        state="PlayerTurnListening",
        events=[event],
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

    return TurnResponse(
        session_id=session_id,
        state=result.new_flow_state,
        events=[player_event, npc_event],
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
        debrief=None,
    )
