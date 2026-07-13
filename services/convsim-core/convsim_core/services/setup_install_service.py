# SPDX-License-Identifier: Apache-2.0
"""Service layer for the one-click install pipeline.

Manages ``setup_install_jobs`` rows that track orchestrated progress
across engine → model → verify → warmup → packs stages.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StageState:
    id: str
    label: str
    state: str  # "pending" | "running" | "complete" | "failed" | "skipped"
    bytes_downloaded: int | None = None
    bytes_total: int | None = None
    error: str | None = None


def _default_stages(model_label: str) -> list[StageState]:
    return [
        StageState(id="engine",  label="Getting the AI engine",    state="pending"),
        StageState(id="model",   label=model_label,                state="pending"),
        StageState(id="verify",  label="Verifying (SHA-256)",      state="pending"),
        StageState(id="warmup",  label="First launch of the model", state="pending"),
        StageState(id="packs",   label="Preparing scenarios",      state="pending"),
    ]


def create_job(
    conn: sqlite3.Connection,
    *,
    registry_id: str | None,
    model_label: str,
) -> int:
    """Insert a new pending job record and return its id."""
    stages = _default_stages(model_label)
    cursor = conn.execute(
        "INSERT INTO setup_install_jobs (registry_id, stages_json) VALUES (?, ?)",
        (registry_id, json.dumps([asdict(s) for s in stages])),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    """Return a single job by id, or None."""
    row = conn.execute(
        "SELECT id, status, registry_id, stages_json, error_message, created_at, updated_at "
        "FROM setup_install_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["stages"] = json.loads(result.pop("stages_json"))
    return result


def get_active_job(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the most recent non-terminal job, or None."""
    row = conn.execute(
        "SELECT id, status, registry_id, stages_json, error_message, created_at, updated_at "
        "FROM setup_install_jobs "
        "WHERE status IN ('pending', 'running') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["stages"] = json.loads(result.pop("stages_json"))
    return result


def update_job_status(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update the top-level status (and optional error) of a job."""
    conn.execute(
        "UPDATE setup_install_jobs "
        "SET status = ?, error_message = ?, updated_at = datetime('now') WHERE id = ?",
        (status, error_message, job_id),
    )
    conn.commit()


def update_job_stages(conn: sqlite3.Connection, job_id: int, stages: list[StageState]) -> None:
    """Persist the current stage snapshot for a job."""
    conn.execute(
        "UPDATE setup_install_jobs "
        "SET stages_json = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps([asdict(s) for s in stages]), job_id),
    )
    conn.commit()
