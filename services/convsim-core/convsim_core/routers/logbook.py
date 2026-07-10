# SPDX-License-Identifier: Apache-2.0
"""Logbook endpoints: a local, aggregated skill profile across all sessions.

The Logbook is the player-facing record of practice — sessions played, hours
practiced, per-skill trajectory, consecutive-day streak, and personal records.
All data is derived from the local SQLite store (turn_sessions +
session_debriefs); nothing leaves the device and clearing local data clears the
logbook too (the /api/privacy/clear cascade removes the underlying rows).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/logbook", tags=["logbook"])

# Temporary workbench test sessions are created under this scenario id and must
# never contribute to the player's training record (mirrors the /api/sessions
# exclusion so a lingering row cannot inflate the logbook).
_WORKBENCH_SCENARIO_ID = "workbench_test"

# Flow states that represent a completed practice session. A session is "Ended"
# once it terminates and "DebriefReady" once a debrief has been generated for
# it; both count as sessions played.
_COMPLETED_STATES = ("Ended", "DebriefReady")

# Exponential recency decay applied per-session when computing rolling skill
# scores: the most recent debriefed session carries weight 1.0, the previous
# 0.85, and so on. Recent form matters more than distant history.
_DECAY = 0.85


class DimensionScore(BaseModel):
    dimension_id: str
    rolling_score: float
    session_count: int
    # Per-session scores for this dimension in chronological order (oldest →
    # newest); raw material for the Logbook's per-skill trajectory chart.
    trajectory: list[float]


class PersonalRecord(BaseModel):
    scenario_id: str
    difficulty: str
    best_score: float
    achieved_at: str


class LogbookProfile(BaseModel):
    total_sessions: int
    total_practice_seconds: int
    streak_days: int
    last_session_date: Optional[str]
    dimension_scores: list[DimensionScore]
    personal_records: list[PersonalRecord]
    strongest_dimension: Optional[str]
    weakest_dimension: Optional[str]
    last_session_delta: Optional[float]


class SessionScoreRecord(BaseModel):
    session_id: str
    scenario_id: str
    difficulty: str
    ended_at: Optional[str]
    overall_score: Optional[float]
    scores: dict[str, float]


class LogbookExport(BaseModel):
    exported_at: str
    profile: LogbookProfile
    session_scores: list[SessionScoreRecord]


def _parse_dt(value: str) -> Optional[datetime]:
    """Parse a stored timestamp (SQLite 'YYYY-MM-DD HH:MM:SS' or ISO-8601).

    Stored timestamps are all UTC but inconsistently formatted: session
    created_at is written as tz-aware ISO ('...+00:00') while ended_at is
    written by SQLite's datetime('now') as a naive 'YYYY-MM-DD HH:MM:SS'.
    Normalise naive values to UTC so an aware created_at and a naive ended_at
    can be subtracted without raising "can't subtract offset-naive and
    offset-aware datetimes".
    """
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _to_date_str(value: str) -> str:
    """Return YYYY-MM-DD from a stored timestamp, using it as-is (UTC)."""
    return value[:10]


def _rolling_score(scores: list[float]) -> float:
    """Recency-weighted average. scores[0] is the most recent session score."""
    if not scores:
        return 0.0
    weighted_sum = 0.0
    weight_sum = 0.0
    for i, score in enumerate(scores):
        w = _DECAY ** i
        weighted_sum += score * w
        weight_sum += w
    return round(weighted_sum / weight_sum, 1)


def _compute_streak(dates: list[str]) -> int:
    """Count consecutive calendar days (UTC) ending on today or yesterday."""
    if not dates:
        return 0

    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    unique = sorted({d for d in dates}, reverse=True)
    first = datetime.fromisoformat(unique[0]).date()
    if first != today and first != yesterday:
        return 0

    streak = 1
    prev = first
    for d in unique[1:]:
        curr = datetime.fromisoformat(d).date()
        if (prev - curr).days == 1:
            streak += 1
            prev = curr
        else:
            break
    return streak


def _session_difficulty(setup_json: Optional[str]) -> str:
    try:
        return json.loads(setup_json or "{}").get("difficulty", "standard")
    except (ValueError, TypeError):
        return "standard"


def _build_profile(conn) -> LogbookProfile:
    placeholders = ",".join("?" for _ in _COMPLETED_STATES)
    sessions = conn.execute(
        f"""
        SELECT session_id, scenario_id, created_at, ended_at, setup_json
        FROM turn_sessions
        WHERE flow_state IN ({placeholders}) AND scenario_id != ?
        ORDER BY COALESCE(ended_at, created_at) DESC
        """,
        (*_COMPLETED_STATES, _WORKBENCH_SCENARIO_ID),
    ).fetchall()

    total_sessions = len(sessions)

    total_practice_seconds = 0
    for s in sessions:
        if s["ended_at"]:
            start = _parse_dt(s["created_at"])
            end = _parse_dt(s["ended_at"])
            if start and end:
                diff = (end - start).total_seconds()
                if diff > 0:
                    total_practice_seconds += round(diff)

    session_dates = [_to_date_str(s["ended_at"] or s["created_at"]) for s in sessions]
    streak_days = _compute_streak(session_dates)
    last_session_date = (
        _to_date_str(sessions[0]["ended_at"] or sessions[0]["created_at"])
        if sessions
        else None
    )

    # One debrief per session (session_debriefs has a unique index on
    # session_id), so no re-debrief de-duplication is needed here.
    debriefs = conn.execute(
        """
        SELECT sd.session_id, sd.content_json
        FROM session_debriefs sd
        INNER JOIN turn_sessions ts ON ts.session_id = sd.session_id
        WHERE ts.scenario_id != ?
        ORDER BY sd.id DESC
        """,
        (_WORKBENCH_SCENARIO_ID,),
    ).fetchall()

    session_meta = {
        s["session_id"]: {
            "scenario_id": s["scenario_id"],
            "difficulty": _session_difficulty(s["setup_json"]),
            "achieved_at": s["ended_at"] or s["created_at"],
        }
        for s in sessions
    }

    # dimension_id -> scores ordered most-recent-first
    dim_scores: dict[str, list[float]] = {}
    # (scenario_id|difficulty) -> best personal record
    pr_map: dict[str, PersonalRecord] = {}
    # session_id -> overall_score
    overall_by_session: dict[str, float] = {}

    for row in debriefs:
        meta = session_meta.get(row["session_id"])
        if meta is None:
            continue
        payload = json.loads(row["content_json"])

        for dim_id, score in (payload.get("scores") or {}).items():
            dim_scores.setdefault(dim_id, []).append(float(score))

        overall = payload.get("overall_score")
        if overall is not None:
            overall_by_session[row["session_id"]] = float(overall)
            pr_key = f"{meta['scenario_id']}|{meta['difficulty']}"
            existing = pr_map.get(pr_key)
            if existing is None or float(overall) > existing.best_score:
                pr_map[pr_key] = PersonalRecord(
                    scenario_id=meta["scenario_id"],
                    difficulty=meta["difficulty"],
                    best_score=float(overall),
                    achieved_at=meta["achieved_at"],
                )

    dimension_scores = [
        DimensionScore(
            dimension_id=dim_id,
            rolling_score=_rolling_score(scores),
            session_count=len(scores),
            # scores is most-recent-first; reverse to chronological for the chart.
            trajectory=list(reversed(scores)),
        )
        for dim_id, scores in dim_scores.items()
    ]

    strongest_dimension: Optional[str] = None
    weakest_dimension: Optional[str] = None
    if dimension_scores:
        ranked = sorted(dimension_scores, key=lambda d: d.rolling_score, reverse=True)
        strongest_dimension = ranked[0].dimension_id
        weakest_dimension = ranked[-1].dimension_id

    # last_session_delta: most recent session's overall score minus the previous
    # scored session's. sessions is ordered most-recent-first.
    last_session_delta: Optional[float] = None
    scores_in_order = [
        overall_by_session[s["session_id"]]
        for s in sessions
        if s["session_id"] in overall_by_session
    ]
    if len(scores_in_order) >= 2:
        last_session_delta = scores_in_order[0] - scores_in_order[1]

    return LogbookProfile(
        total_sessions=total_sessions,
        total_practice_seconds=total_practice_seconds,
        streak_days=streak_days,
        last_session_date=last_session_date,
        dimension_scores=dimension_scores,
        personal_records=list(pr_map.values()),
        strongest_dimension=strongest_dimension,
        weakest_dimension=weakest_dimension,
        last_session_delta=last_session_delta,
    )


@router.get("/profile", response_model=LogbookProfile)
async def get_logbook_profile(request: Request) -> LogbookProfile:
    """Aggregated training profile across all completed local sessions."""
    conn = request.app.state.db.connection()
    return _build_profile(conn)


@router.get("/export", response_model=LogbookExport)
async def export_logbook(request: Request) -> LogbookExport:
    """Full JSON export: the profile plus raw per-session score records."""
    conn = request.app.state.db.connection()
    profile = _build_profile(conn)

    placeholders = ",".join("?" for _ in _COMPLETED_STATES)
    sessions = conn.execute(
        f"""
        SELECT session_id, scenario_id, created_at, ended_at, setup_json
        FROM turn_sessions
        WHERE flow_state IN ({placeholders}) AND scenario_id != ?
        ORDER BY COALESCE(ended_at, created_at) DESC
        """,
        (*_COMPLETED_STATES, _WORKBENCH_SCENARIO_ID),
    ).fetchall()

    debriefs = conn.execute(
        """
        SELECT sd.session_id, sd.content_json
        FROM session_debriefs sd
        INNER JOIN turn_sessions ts ON ts.session_id = sd.session_id
        WHERE ts.scenario_id != ?
        ORDER BY sd.id DESC
        """,
        (_WORKBENCH_SCENARIO_ID,),
    ).fetchall()

    scores_by_session: dict[str, dict] = {}
    for row in debriefs:
        if row["session_id"] not in scores_by_session:
            payload = json.loads(row["content_json"])
            scores_by_session[row["session_id"]] = {
                "overall_score": payload.get("overall_score"),
                "scores": payload.get("scores") or {},
            }

    session_scores = []
    for s in sessions:
        debrief = scores_by_session.get(s["session_id"])
        session_scores.append(
            SessionScoreRecord(
                session_id=s["session_id"],
                scenario_id=s["scenario_id"],
                difficulty=_session_difficulty(s["setup_json"]),
                ended_at=s["ended_at"],
                overall_score=debrief["overall_score"] if debrief else None,
                scores=debrief["scores"] if debrief else {},
            )
        )

    return LogbookExport(
        exported_at=datetime.now(timezone.utc).isoformat(),
        profile=profile,
        session_scores=session_scores,
    )
