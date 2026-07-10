# SPDX-License-Identifier: Apache-2.0
"""Branch session service: fork a completed session at any NPC-turn boundary.

A branch session is a new session that:
  - Starts from the exact simulation state at the end of game turn N-1.
  - Has a verbatim copy of all transcript turns up to game turn N-1.
  - Resumes in PlayerTurnListening so the player can try a different choice
    at game turn N.

Determinism policy:
  - State variables and fired event IDs are restored exactly from the
    ``state_snapshot_json`` stored on the parent NPC turn.
  - Player turns 1..N-1 are copied verbatim into the branch transcript.
  - NPC turns within the copied prefix are also copied verbatim; they serve
    as context for the NPC but are not re-simulated.
  - From turn N onwards, the NPC is re-simulated. Where the runtime accepts a
    seed (see ``setup_json.seed``), the parent seed is inherited to support
    reproducible comparison runs.
  - Storage of snapshots is bounded: ``state_snapshot_json`` lives on the turn
    row and is pruned automatically when the session is deleted (CASCADE).
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_session_id() -> str:
    return f"sess-{secrets.token_hex(8)}"


def fork_session(
    parent_session_id: str,
    fork_turn_number: int,
    conn: sqlite3.Connection,
) -> Tuple[str, str]:
    """Create a branch session forked at the start of game turn *fork_turn_number*.

    *fork_turn_number* is 1-indexed: ``1`` means retry the very first player
    turn (only the NPC opening is copied); ``N`` means retry game turn N (all
    turns through game turn N-1 are copied).

    Returns ``(branch_session_id, created_at_iso)`` so callers can build an
    HTTP response without a second DB round-trip.

    Raises:
        ValueError: parent session not found, fork_turn_number out of range
            [1, parent.turn_count], or the required state snapshot is absent.
    """
    parent_row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (parent_session_id,)
    ).fetchone()
    if parent_row is None:
        raise ValueError(f"Session {parent_session_id!r} not found")

    total_turns: int = int(parent_row["turn_count"])
    if fork_turn_number < 1 or fork_turn_number > total_turns:
        raise ValueError(
            f"fork_turn_number {fork_turn_number} is out of range "
            f"[1, {total_turns}] for session {parent_session_id!r}"
        )

    # Resolve the simulation state at the fork boundary.
    # fork_turn_number=1 → retry turn 1 → no prior NPC turn → initial state ({}).
    # fork_turn_number=N → retry turn N → state after NPC turn N-1.
    if fork_turn_number == 1:
        state_vars: Dict[str, Any] = {}
        fired_events: List[str] = []
    else:
        # DB turn_number for the NPC response at game turn fork_turn_number-1 is
        # 2*(fork_turn_number-1).
        prior_npc_db_turn = 2 * (fork_turn_number - 1)
        snapshot_row = conn.execute(
            "SELECT state_snapshot_json FROM turn_session_turns "
            "WHERE session_id = ? AND turn_number = ?",
            (parent_session_id, prior_npc_db_turn),
        ).fetchone()
        if snapshot_row is None or not snapshot_row["state_snapshot_json"]:
            raise ValueError(
                f"State snapshot missing for turn {prior_npc_db_turn} "
                f"in session {parent_session_id!r}. "
                "This session was played before per-turn snapshots were introduced; "
                "replay it to generate a fork-capable transcript."
            )
        snapshot = json.loads(snapshot_row["state_snapshot_json"])
        state_vars = snapshot.get("state_vars", {})
        fired_events = snapshot.get("fired_events", [])

    # Turns to copy: NPC opening (turn_number=0) through the last NPC turn
    # before the fork (turn_number=2*(fork_turn_number-1)).
    max_db_turn_to_copy = 2 * (fork_turn_number - 1)
    turns_to_copy = conn.execute(
        "SELECT turn_number, role, content, emotion, state_delta_json, "
        "event_flags_json, safety_json, raw_output_json, source_mode, "
        "barged_in, flow_state_after, state_snapshot_json, created_at "
        "FROM turn_session_turns "
        "WHERE session_id = ? AND turn_number <= ? ORDER BY turn_number ASC",
        (parent_session_id, max_db_turn_to_copy),
    ).fetchall()

    new_session_id = _generate_session_id()
    now = _now_iso()
    setup_json: str = parent_row["setup_json"]
    setup: Dict[str, Any] = json.loads(setup_json)
    save_transcript: bool = setup.get("save_transcript", True)

    with conn:
        conn.execute(
            "INSERT INTO turn_sessions "
            "(session_id, scenario_id, flow_state, state_vars_json, "
            "fired_events_json, turn_count, setup_json, created_at) "
            "VALUES (?, ?, 'PlayerTurnListening', ?, ?, ?, ?, ?)",
            (
                new_session_id,
                parent_row["scenario_id"],
                json.dumps(state_vars),
                json.dumps(fired_events),
                fork_turn_number - 1,
                setup_json,
                now,
            ),
        )

        if turns_to_copy:
            conn.executemany(
                "INSERT INTO turn_session_turns "
                "(session_id, turn_number, role, content, emotion, "
                "state_delta_json, event_flags_json, safety_json, "
                "raw_output_json, source_mode, barged_in, flow_state_after, "
                "state_snapshot_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        new_session_id,
                        t["turn_number"],
                        t["role"],
                        t["content"],
                        t["emotion"],
                        t["state_delta_json"],
                        t["event_flags_json"],
                        t["safety_json"],
                        t["raw_output_json"],
                        t["source_mode"],
                        t["barged_in"],
                        t["flow_state_after"],
                        t["state_snapshot_json"],
                        t["created_at"],
                    )
                    for t in turns_to_copy
                ],
            )

        conn.execute(
            "INSERT INTO session_branches "
            "(branch_session_id, parent_session_id, fork_turn_number, created_at) "
            "VALUES (?, ?, ?, ?)",
            (new_session_id, parent_session_id, fork_turn_number, now),
        )

        if save_transcript and turns_to_copy:
            conn.executemany(
                "INSERT INTO session_transcript_fts(session_id, turn_number, role, content) "
                "VALUES (?, ?, ?, ?)",
                [
                    (new_session_id, t["turn_number"], t["role"], t["content"])
                    for t in turns_to_copy
                ],
            )

    return new_session_id, now
