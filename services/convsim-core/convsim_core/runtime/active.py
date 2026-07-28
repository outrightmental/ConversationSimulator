# SPDX-License-Identifier: Apache-2.0
"""Live runtime activation: keep ``app.state.runtime`` in sync with selection.

Historically ``app.state.runtime`` was built once at startup from
``config.runtime_id`` (default ``"fake"``) and never touched again, while
``POST /api/models/use`` and the one-click install pipeline only persisted the
selection to the DB via ``set_active_config`` — which nothing read back. The
result: sessions ran on the startup runtime (the fake one, in packaged builds)
forever, no matter what the user installed or selected.

This module is the single place that swaps the live runtime object, and the
startup path resolves the persisted selection so a restart keeps the user's
choice.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

import httpx

from convsim_core.runtime.registry import build_runtime, list_runtime_ids

logger = logging.getLogger(__name__)


async def _close_runtime(runtime: Any) -> None:
    """Release a replaced runtime's resources (persistent HTTP clients)."""
    client = getattr(runtime, "_client", None)
    if isinstance(client, httpx.AsyncClient):
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


async def activate_runtime(app: Any, runtime_id: str) -> None:
    """Swap ``app.state.runtime`` to *runtime_id*, releasing the old runtime.

    No-op when the requested runtime is already active. Raises ``KeyError``
    for unknown runtime ids (same contract as ``build_runtime``).
    """
    old = getattr(app.state, "runtime", None)
    if old is not None and getattr(old, "id", None) == runtime_id:
        return
    new = build_runtime(runtime_id)
    app.state.runtime = new
    logger.info(
        "Active runtime switched: %s -> %s",
        getattr(old, "id", None),
        runtime_id,
    )
    if old is not None:
        await _close_runtime(old)


def resolve_startup_runtime_id(conn: sqlite3.Connection, config_runtime_id: str) -> str:
    """Return the runtime id the app should boot with.

    The persisted active selection (written by /api/models/use and the setup
    pipeline) wins over the static config default, so restarting the app keeps
    the user's model choice. Unknown/corrupt persisted ids fall back to the
    config default rather than failing startup.
    """
    try:
        from convsim_core.services.model_manager_service import get_active_config

        persisted = (get_active_config(conn) or {}).get("runtime_id")
    except Exception:  # pragma: no cover - a fresh DB has no config yet
        persisted = None
    if persisted and persisted in list_runtime_ids():
        return str(persisted)
    return config_runtime_id


def find_ready_model_path(conn: sqlite3.Connection) -> Optional[str]:
    """Return the newest installed-and-ready GGUF path, or the active model id
    when it points at an existing file. None when no usable model exists."""
    try:
        from convsim_core.services.model_manager_service import get_active_config

        active = (get_active_config(conn) or {}).get("model_id")
    except Exception:
        active = None
    candidates: list[str] = []
    if active:
        candidates.append(str(active))
    try:
        row = conn.execute(
            "SELECT file_path FROM installed_models "
            "WHERE install_status IN ('ready', 'complete') AND file_path != '' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row["file_path"]:
            candidates.append(str(row["file_path"]))
    except sqlite3.Error:  # pragma: no cover - table missing pre-migration
        pass
    for cand in candidates:
        p = Path(cand).expanduser()
        if p.is_file() and p.suffix.lower() == ".gguf":
            return str(p)
    return None


async def ensure_llama_sidecar_running(
    app: Any,
    *,
    model_path: Optional[str] = None,
    startup_timeout: float = 120.0,
) -> Optional[str]:
    """Start the managed llama-server if it is not already reachable.

    Best-effort: returns the model path used on success, None when starting was
    not possible (no sidecar, no executable, no model, or start failure). Never
    raises — callers decide how to surface unavailability.
    """
    from convsim_core.runtime.sidecar import SidecarState, find_executable

    sidecar = getattr(app.state, "sidecar", None)
    if sidecar is None:
        return None
    if sidecar.state in (SidecarState.RUNNING, SidecarState.STARTING):
        return None

    conn = app.state.db.connection()
    path = None
    if model_path:
        p = Path(model_path).expanduser()
        if p.is_file() and p.suffix.lower() == ".gguf":
            path = str(p)
    if path is None:
        path = find_ready_model_path(conn)
    if path is None:
        logger.info("llama-server autostart skipped: no ready model file found")
        return None

    exe = find_executable()
    if exe is None:
        logger.info("llama-server autostart skipped: no engine executable found")
        return None

    try:
        await sidecar.start(
            model_path=path,
            executable=exe,
            startup_timeout=startup_timeout,
        )
        logger.info("llama-server autostarted with model %s", path)
        return path
    except Exception as exc:
        logger.warning("llama-server autostart failed: %s", exc)
        return None


def schedule_startup_autostart(app: Any) -> None:
    """If the persisted runtime is llama_cpp, start its engine in the background.

    Called from app startup so a restarted app comes back with a working local
    engine instead of surfacing "runtime unavailable" on the first turn. Runs
    as a fire-and-forget task; failures are logged and the health endpoints
    report the true state.
    """
    runtime = getattr(app.state, "runtime", None)
    if getattr(runtime, "id", None) != "llama_cpp":
        return

    async def _run() -> None:
        await ensure_llama_sidecar_running(app)

    task = asyncio.create_task(_run())
    # Keep a strong reference on app.state so the task is not GC'd mid-start.
    tasks = getattr(app.state, "_autostart_tasks", None)
    if tasks is None:
        tasks = set()
        app.state._autostart_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)
