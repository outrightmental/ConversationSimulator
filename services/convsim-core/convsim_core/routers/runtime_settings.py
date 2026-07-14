# SPDX-License-Identifier: Apache-2.0
"""Runtime settings endpoints (/api/runtime/settings).

Implements the shared ``RuntimeSettingsResponse`` contract consumed by the
web UI (see packages/shared/src/types/models.ts). Settings are persisted in
the ``user_settings`` table under ``runtime_setting.<name>`` keys so they
survive restarts and live alongside the active model selection.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.errors import ConvsimError

router = APIRouter()

_KEY_PREFIX = "runtime_setting."

_SETTING_KEYS = (
    "context_length",
    "gpu_layers",
    "threads",
    "temperature",
    "top_p",
    "repeat_penalty",
)

# Changing these requires restarting the llama-server sidecar to take effect.
_RESTART_REQUIRED = {"context_length", "gpu_layers"}

_INT_KEYS = {"context_length", "gpu_layers", "threads"}


class RuntimeSettings(BaseModel):
    context_length: Optional[int] = None
    gpu_layers: Optional[int] = None
    threads: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    repeat_penalty: Optional[float] = None


class RuntimeSettingsResponse(BaseModel):
    settings: RuntimeSettings
    recommended: RuntimeSettings
    requires_restart: bool


def load_runtime_settings(conn: sqlite3.Connection) -> RuntimeSettings:
    """Read persisted runtime settings; missing/invalid values become None."""
    rows = conn.execute(
        "SELECT key, value FROM user_settings WHERE key LIKE ?",
        (_KEY_PREFIX + "%",),
    ).fetchall()
    stored = {row["key"][len(_KEY_PREFIX):]: row["value"] for row in rows}

    values: dict[str, int | float | None] = {}
    for key in _SETTING_KEYS:
        raw = stored.get(key)
        if raw is None or raw == "" or raw == "null":
            values[key] = None
            continue
        try:
            values[key] = int(raw) if key in _INT_KEYS else float(raw)
        except ValueError:
            values[key] = None
    return RuntimeSettings(**values)


def _save_runtime_settings(conn: sqlite3.Connection, patch: dict[str, object]) -> None:
    for key in _SETTING_KEYS:
        if key not in patch:
            continue
        value = patch[key]
        conn.execute(
            """
            INSERT INTO user_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (_KEY_PREFIX + key, "null" if value is None else str(value)),
        )
    conn.commit()


def _validate(patch: dict[str, object]) -> list[str]:
    """Return human-readable validation errors; empty list when valid."""
    errors: list[str] = []

    def _check_int(key: str, lo: int, hi: int, label: str) -> None:
        v = patch.get(key)
        if v is None or key not in patch:
            return
        if not isinstance(v, int) or isinstance(v, bool) or v < lo or v > hi:
            errors.append(f"{label} must be an integer between {lo} and {hi}.")

    def _check_float(key: str, lo: float, hi: float, label: str) -> None:
        v = patch.get(key)
        if v is None or key not in patch:
            return
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < lo or v > hi:
            errors.append(f"{label} must be between {lo} and {hi}.")

    _check_int("context_length", 512, 131072, "Context length")
    _check_int("gpu_layers", -1, 256, "GPU layers")
    _check_int("threads", 1, 64, "Thread count")
    _check_float("temperature", 0.0, 2.0, "Temperature")
    _check_float("top_p", 0.0, 1.0, "Top-P")
    _check_float("repeat_penalty", 1.0, 2.0, "Repeat penalty")
    return errors


def _recommended() -> RuntimeSettings:
    """Conservative recommendations; None means 'use the runtime default'."""
    cpu = os.cpu_count()
    return RuntimeSettings(threads=max(1, (cpu or 2) // 2) if cpu else None)


@router.get("/api/runtime/settings", response_model=RuntimeSettingsResponse)
async def get_runtime_settings(request: Request) -> RuntimeSettingsResponse:
    conn = request.app.state.db.connection()
    return RuntimeSettingsResponse(
        settings=load_runtime_settings(conn),
        recommended=_recommended(),
        requires_restart=False,
    )


@router.put("/api/runtime/settings", response_model=RuntimeSettingsResponse)
async def update_runtime_settings(request: Request, body: RuntimeSettings) -> RuntimeSettingsResponse:
    conn = request.app.state.db.connection()
    patch = body.model_dump(exclude_unset=True)

    errors = _validate(patch)
    if errors:
        raise ConvsimError(
            code="INVALID_RUNTIME_SETTINGS",
            message=" ".join(errors),
            status_code=422,
        )

    current = load_runtime_settings(conn).model_dump()
    requires_restart = any(
        key in patch and patch[key] != current[key] for key in _RESTART_REQUIRED
    )
    _save_runtime_settings(conn, patch)

    return RuntimeSettingsResponse(
        settings=load_runtime_settings(conn),
        recommended=_recommended(),
        requires_restart=requires_restart,
    )


@router.post("/api/runtime/settings/reset", response_model=RuntimeSettingsResponse)
async def reset_runtime_settings(request: Request) -> RuntimeSettingsResponse:
    conn = request.app.state.db.connection()
    _save_runtime_settings(conn, {key: None for key in _SETTING_KEYS})
    return RuntimeSettingsResponse(
        settings=load_runtime_settings(conn),
        recommended=_recommended(),
        requires_restart=True,
    )
