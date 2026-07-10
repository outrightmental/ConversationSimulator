# SPDX-License-Identifier: Apache-2.0
"""CRUD helpers for the relationship_state table.

Each row stores a bounded JSON recap for one (npc_id, pack_id) pair.  All
writes go through the relationship_memory service, which validates the recap
against a schema before calling upsert_relationship_recap.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


def get_relationship_recap(
    conn: sqlite3.Connection, npc_id: str, pack_id: str
) -> Optional[Dict[str, Any]]:
    """Return the stored recap dict, or None if no entry exists."""
    row = conn.execute(
        "SELECT recap_json FROM relationship_state WHERE npc_id = ? AND pack_id = ?",
        (npc_id, pack_id),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["recap_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def upsert_relationship_recap(
    conn: sqlite3.Connection,
    npc_id: str,
    pack_id: str,
    recap: Dict[str, Any],
    session_count: int,
) -> None:
    """Insert or replace the recap for (npc_id, pack_id)."""
    conn.execute(
        """
        INSERT INTO relationship_state (npc_id, pack_id, recap_json, session_count, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(npc_id, pack_id) DO UPDATE SET
            recap_json    = excluded.recap_json,
            session_count = excluded.session_count,
            updated_at    = excluded.updated_at
        """,
        (npc_id, pack_id, json.dumps(recap), session_count),
    )
    conn.commit()


def list_relationship_recaps(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return all relationship recaps as flat dicts for the API layer."""
    rows = conn.execute(
        "SELECT npc_id, pack_id, recap_json, session_count, updated_at "
        "FROM relationship_state ORDER BY updated_at DESC"
    ).fetchall()
    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            recap = json.loads(row["recap_json"])
        except (json.JSONDecodeError, TypeError):
            recap = {}
        results.append({
            "npc_id": row["npc_id"],
            "pack_id": row["pack_id"],
            "session_count": row["session_count"],
            "updated_at": row["updated_at"],
            "key_observations": recap.get("key_observations", []),
            "player_style_tags": recap.get("player_style_tags", []),
            "last_outcome": recap.get("last_outcome"),
            "last_session_at": recap.get("last_session_at"),
        })
    return results


def delete_relationship_recap(
    conn: sqlite3.Connection, npc_id: str, pack_id: str
) -> bool:
    """Delete a specific recap.  Returns True iff a row was deleted."""
    cursor = conn.execute(
        "DELETE FROM relationship_state WHERE npc_id = ? AND pack_id = ?",
        (npc_id, pack_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_all_relationship_recaps(conn: sqlite3.Connection) -> int:
    """Delete every recap row.  Returns the count of deleted rows."""
    cursor = conn.execute("DELETE FROM relationship_state")
    conn.commit()
    return cursor.rowcount
