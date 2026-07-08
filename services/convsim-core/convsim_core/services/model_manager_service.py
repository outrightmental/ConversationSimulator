# SPDX-License-Identifier: Apache-2.0
"""Service layer for model install, selection, and benchmark persistence."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


def get_installed_models(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all rows from installed_models as a list of dicts."""
    rows = conn.execute(
        """
        SELECT id, registry_id, filename, file_path, size_bytes,
               install_status, progress_bytes, error_message, verified_sha256, installed_at
        FROM installed_models
        ORDER BY id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def create_install_record(
    conn: sqlite3.Connection,
    registry_id: str | None,
    filename: str,
    file_path: str,
) -> int:
    """Insert a new 'pending' install record and return its id."""
    cursor = conn.execute(
        """
        INSERT INTO installed_models (registry_id, filename, file_path, install_status)
        VALUES (?, ?, ?, 'pending')
        """,
        (registry_id, filename, file_path),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_active_config(conn: sqlite3.Connection) -> dict[str, str | None]:
    """Return the active runtime/model selection from user_settings."""
    rows = conn.execute(
        "SELECT key, value FROM user_settings WHERE key IN ('active_runtime_id', 'active_model_id')"
    ).fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    return {
        "runtime_id": stored.get("active_runtime_id"),
        "model_id": stored.get("active_model_id"),
    }


def set_active_config(
    conn: sqlite3.Connection,
    runtime_id: str,
    model_id: str | None = None,
) -> None:
    """Persist active runtime/model selection to user_settings."""
    conn.execute(
        """
        INSERT INTO user_settings (key, value, updated_at)
        VALUES ('active_runtime_id', ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (runtime_id,),
    )
    if model_id is not None:
        conn.execute(
            """
            INSERT INTO user_settings (key, value, updated_at)
            VALUES ('active_model_id', ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (model_id,),
        )
    else:
        conn.execute("DELETE FROM user_settings WHERE key = 'active_model_id'")
    conn.commit()


def save_benchmark_result(
    conn: sqlite3.Connection,
    *,
    model_id: str,
    runtime_id: str,
    tokens_per_sec: float,
    context_length: int | None = None,
    warnings: list[str] | None = None,
    prompt_used: str | None = None,
    output_tokens: int | None = None,
    benchmarked_at: str | None = None,
) -> None:
    """Persist a benchmark result to the benchmark_results table."""
    conn.execute(
        """
        INSERT INTO benchmark_results
            (model_id, runtime_id, tokens_per_sec, context_length,
             warnings_json, prompt_used, output_tokens, benchmarked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))
        """,
        (
            model_id,
            runtime_id,
            tokens_per_sec,
            context_length,
            json.dumps(warnings or []),
            prompt_used,
            output_tokens,
            benchmarked_at,
        ),
    )
    conn.commit()


def register_user_gguf(
    conn: sqlite3.Connection,
    *,
    path: str,
    display_name: str | None = None,
    family_guess: str | None = None,
    context_length_default: int | None = None,
) -> dict[str, Any]:
    """Store a user-supplied GGUF file profile and return the created record.

    The file is not copied or modified. The caller is responsible for validating
    that the path exists and has a .gguf extension before calling this function.
    """
    filename = os.path.basename(path)
    name = display_name or filename
    cursor = conn.execute(
        """
        INSERT INTO installed_models
            (registry_id, filename, file_path, install_status,
             display_name, family_guess, context_length_default, source)
        VALUES (NULL, ?, ?, 'complete', ?, ?, ?, 'user-supplied')
        """,
        (filename, path, name, family_guess, context_length_default),
    )
    conn.commit()
    return {
        "id": cursor.lastrowid,
        "filename": filename,
        "file_path": path,
        "display_name": name,
        "family_guess": family_guess,
        "context_length_default": context_length_default,
        "install_status": "complete",
        "source": "user-supplied",
    }


def get_latest_benchmark(
    conn: sqlite3.Connection, model_id: str, runtime_id: str
) -> dict[str, Any] | None:
    """Return the most recent benchmark result for a model/runtime pair, or None."""
    row = conn.execute(
        """
        SELECT id, model_id, runtime_id, tokens_per_sec, context_length,
               warnings_json, prompt_used, output_tokens, benchmarked_at
        FROM benchmark_results
        WHERE model_id = ? AND runtime_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (model_id, runtime_id),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["warnings"] = json.loads(result.pop("warnings_json", "[]"))
    return result
