# SPDX-License-Identifier: Apache-2.0
"""Persistence for the flyting volley log and the local high-score table.

The volley log is the session's record of what each line was worth: one row per
volley, player and opponent alike, carrying the whole scorecard as JSON. Session
results are pure aggregates over these rows, so a debrief computed now and a
debrief recomputed next year agree.

High scores are per scenario and format, stored locally, and never leave the
machine — the whole arcade loop works with no account and no server.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

# Boards are a local practice aid, not a league table; keeping ten entries means
# a player can see whether tonight beat last Tuesday without the table growing
# without bound.
HIGH_SCORE_BOARD_SIZE = 10


def insert_volley(
    conn: sqlite3.Connection,
    session_id: str,
    scorecard: Dict[str, Any],
    *,
    text: str,
) -> int:
    """Append one scored volley to a session's log and return its row id."""
    cursor = conn.execute(
        """
        INSERT INTO flyting_volleys
            (session_id, volley_number, speaker, text, score, band, heat,
             banked_score, momentum, scorecard_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            int(scorecard["volley_number"]),
            str(scorecard["speaker"]),
            text,
            int(scorecard["score"]),
            str(scorecard["band"]),
            float(scorecard.get("heat", 1.0)),
            int(scorecard.get("banked_score", 0)),
            scorecard.get("momentum"),
            json.dumps(scorecard),
        ),
    )
    return int(cursor.lastrowid)


def list_volleys(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    speaker: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return a session's volleys in play order, newest last."""
    sql = (
        "SELECT speaker, text, score, band, heat, banked_score, momentum, "
        "scorecard_json, created_at FROM flyting_volleys WHERE session_id = ?"
    )
    params: tuple[Any, ...] = (session_id,)
    if speaker is not None:
        sql += " AND speaker = ?"
        params += (speaker,)
    sql += " ORDER BY id"

    out: List[Dict[str, Any]] = []
    for row in conn.execute(sql, params).fetchall():
        try:
            scorecard = json.loads(row["scorecard_json"])
        except (json.JSONDecodeError, TypeError):
            # A row whose JSON cannot be read is still a volley that happened;
            # report the columns rather than dropping it from the log.
            scorecard = {}
        out.append({
            "speaker": row["speaker"],
            "text": row["text"],
            "score": row["score"],
            "band": row["band"],
            "heat": row["heat"],
            "banked_score": row["banked_score"],
            "momentum": row["momentum"],
            "scorecard": scorecard,
            "created_at": row["created_at"],
        })
    return out


def volley_texts(conn: sqlite3.Connection, session_id: str) -> List[str]:
    """Every volley's text this session, for the novelty comparison.

    Both speakers, deliberately: parroting the opponent is redundancy, so the
    opponent's lines have to be in the corpus the player is compared against.
    """
    rows = conn.execute(
        "SELECT text FROM flyting_volleys WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [row["text"] for row in rows]


def record_high_score(
    conn: sqlite3.Connection,
    *,
    scenario_id: str,
    play_format: str,
    total_score: int,
    pack_id: Optional[str] = None,
    batting_format: Optional[str] = None,
    session_id: Optional[str] = None,
    outcome: Optional[str] = None,
    volley_count: int = 0,
    best_volley_score: int = 0,
    peak_heat: float = 1.0,
    daily_seed: Optional[int] = None,
) -> int:
    """Record a finished run on its board and return its 1-based rank.

    Every finished run is recorded, not only record-breaking ones: the board is
    a practice log first and a leaderboard second, and a run you cannot see is a
    run you cannot learn from.

    One run occupies one row. Ending a run is idempotent from the client's side —
    a retried request, a double-clicked button, a debrief reopened — and a second
    row for the same session would both double the run on the board and inflate
    every later run's rank.
    """
    columns = (
        "scenario_id = ?, pack_id = ?, play_format = ?, batting_format = ?, "
        "outcome = ?, total_score = ?, volley_count = ?, best_volley_score = ?, "
        "peak_heat = ?, daily_seed = ?"
    )
    values = (
        scenario_id, pack_id, play_format, batting_format, outcome,
        int(total_score), int(volley_count), int(best_volley_score),
        float(peak_heat), daily_seed,
    )
    updated = 0
    if session_id is not None:
        updated = conn.execute(
            f"UPDATE flyting_high_scores SET {columns} WHERE session_id = ?",
            (*values, session_id),
        ).rowcount
    if not updated:
        conn.execute(
            """
            INSERT INTO flyting_high_scores
                (scenario_id, pack_id, play_format, batting_format, outcome,
                 total_score, volley_count, best_volley_score, peak_heat, daily_seed,
                 session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*values, session_id),
        )
    conn.commit()
    row = conn.execute(
        """
        SELECT COUNT(*) + 1 AS rank FROM flyting_high_scores
        WHERE scenario_id = ? AND play_format = ?
          AND (batting_format IS ? OR batting_format = ?)
          AND total_score > ?
        """,
        (scenario_id, play_format, batting_format, batting_format, int(total_score)),
    ).fetchone()
    return int(row["rank"]) if row is not None else 1


def list_high_scores(
    conn: sqlite3.Connection,
    *,
    scenario_id: str,
    play_format: Optional[str] = None,
    batting_format: Optional[str] = None,
    limit: int = HIGH_SCORE_BOARD_SIZE,
) -> List[Dict[str, Any]]:
    """Return the top scores for a scenario, optionally narrowed to one format."""
    sql = (
        "SELECT scenario_id, pack_id, play_format, batting_format, session_id, outcome, "
        "total_score, volley_count, best_volley_score, peak_heat, daily_seed, achieved_at "
        "FROM flyting_high_scores WHERE scenario_id = ?"
    )
    params: tuple[Any, ...] = (scenario_id,)
    if play_format is not None:
        sql += " AND play_format = ?"
        params += (play_format,)
    if batting_format is not None:
        sql += " AND batting_format = ?"
        params += (batting_format,)
    sql += " ORDER BY total_score DESC, achieved_at ASC LIMIT ?"
    params += (max(1, int(limit)),)

    return [
        {
            "scenario_id": row["scenario_id"],
            "pack_id": row["pack_id"],
            "play_format": row["play_format"],
            "batting_format": row["batting_format"],
            "session_id": row["session_id"],
            "outcome": row["outcome"],
            "total_score": row["total_score"],
            "volley_count": row["volley_count"],
            "best_volley_score": row["best_volley_score"],
            "peak_heat": row["peak_heat"],
            "daily_seed": row["daily_seed"],
            "achieved_at": row["achieved_at"],
        }
        for row in conn.execute(sql, params).fetchall()
    ]


def personal_best(
    conn: sqlite3.Connection,
    *,
    scenario_id: str,
    play_format: str,
    batting_format: Optional[str] = None,
) -> Optional[int]:
    """The best total on one board, or None when it has never been played."""
    row = conn.execute(
        """
        SELECT MAX(total_score) AS best FROM flyting_high_scores
        WHERE scenario_id = ? AND play_format = ?
          AND (batting_format IS ? OR batting_format = ?)
        """,
        (scenario_id, play_format, batting_format, batting_format),
    ).fetchone()
    if row is None or row["best"] is None:
        return None
    return int(row["best"])
