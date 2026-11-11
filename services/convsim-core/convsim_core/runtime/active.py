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

from convsim_core.edition import demo_model_paths, is_demo, resolve_demo_model_id
from convsim_core.runtime.registry import build_runtime, list_runtime_ids

logger = logging.getLogger(__name__)

#: Runtimes that answer from authored/canned content with no model behind them.
#: A session must never land on one of these implicitly — only an explicit
#: request pin may select them (issues #473, #476).
MODEL_FREE_RUNTIME_IDS = ("scripted", "fake")


def unpinned_session_runtime_is_model_free(app: Any, conn: sqlite3.Connection) -> bool:
    """True when a session created without an explicit runtime pin would answer
    from a model-free runtime — the no-model-installed state.

    Resolution order matches what the session routers enforce at create time:
    the persisted active selection wins (tests may activate a selection without
    swapping the live runtime), else the live ``app.state.runtime`` — whose
    config default is ``fake`` on a profile that never installed a model.

    A persisted id the current build does not register cannot vouch for a
    session: startup ignores it the same way (``resolve_startup_runtime_id``)
    and boots the config default, so it falls through to the live runtime here
    too instead of silently approving a conversation the fake runtime would
    serve.
    """
    from convsim_core.services.model_manager_service import get_active_config

    effective = get_active_config(conn).get("runtime_id")
    if effective not in list_runtime_ids():
        effective = getattr(getattr(app.state, "runtime", None), "id", None)
    return effective in MODEL_FREE_RUNTIME_IDS


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


def resolve_startup_runtime_id(
    conn: sqlite3.Connection, config_runtime_id: str, config: Any = None
) -> str:
    """Return the runtime id the app should boot with.

    The persisted active selection (written by /api/models/use and the setup
    pipeline) wins over the static config default, so restarting the app keeps
    the user's model choice. Unknown/corrupt persisted ids fall back to the
    config default rather than failing startup.

    The demo edition (*config* says so) plays only its own model, on the
    managed llama.cpp engine; ``/api/models/use`` refuses any other runtime
    there. A saved selection is the full app's on the shared data root
    (D-06), so whatever runtime it names, Ollama included, the demo boots
    ``llama_cpp``, whose autostart loads the demo model's own install. With
    nothing saved, a model-free config default (``fake``) still applies, so a
    fresh profile keeps the no-model backstop (issue #473); any other default
    boots ``llama_cpp`` too.
    """
    try:
        from convsim_core.services.model_manager_service import get_active_config

        persisted = (get_active_config(conn) or {}).get("runtime_id")
    except Exception:  # pragma: no cover - a fresh DB has no config yet
        persisted = None
    if is_demo(config):
        if persisted or config_runtime_id not in MODEL_FREE_RUNTIME_IDS:
            return "llama_cpp"
        return config_runtime_id
    if persisted and persisted in list_runtime_ids():
        return str(persisted)
    return config_runtime_id


def find_ready_model_path(conn: sqlite3.Connection, config: Any = None) -> Optional[str]:
    """Return the newest installed-and-ready GGUF path, or the active model id
    when it points at an existing file. None when no usable model exists.

    In the demo edition (*config* says so) only the demo model's own files
    count. The demo shares the full app's data root (D-06), so the saved
    selection and the newest install can be another model, such as the
    earlier starter a pre-v0.4 profile still has selected. Those are skipped,
    so with no demo model installed this returns None, as on a fresh profile.
    Without *config* the full edition's rule applies.
    """
    demo_id: Optional[str] = None
    demo_paths: set[str] = set()
    if is_demo(config):
        demo_id = resolve_demo_model_id(conn, config)
        if demo_id is None:
            return None
        demo_paths = demo_model_paths(conn, config)
    try:
        from convsim_core.services.model_manager_service import get_active_config

        active = (get_active_config(conn) or {}).get("model_id")
    except Exception:
        active = None
    candidates: list[str] = []
    if active and (demo_id is None or str(active) in demo_paths):
        candidates.append(str(active))
    query = (
        "SELECT file_path FROM installed_models "
        "WHERE install_status IN ('ready', 'complete') AND file_path != ''"
    )
    params: tuple[str, ...] = ()
    if demo_id is not None:
        query += " AND registry_id = ?"
        params = (demo_id,)
    try:
        row = conn.execute(query + " ORDER BY id DESC LIMIT 1", params).fetchone()
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

    In the demo edition a *model_path* that is not one of the demo model's own
    install paths is ignored, as ``find_ready_model_path`` ignores the full
    app's other models: the benchmark passes the saved selection, which on a
    shared data root can name a model the demo does not play.
    """
    from convsim_core.runtime.launch import resolve_launch_config
    from convsim_core.runtime.sidecar import SidecarState, find_executable

    sidecar = getattr(app.state, "sidecar", None)
    if sidecar is None:
        return None
    if sidecar.state in (SidecarState.RUNNING, SidecarState.STARTING):
        return None

    conn = app.state.db.connection()
    config = getattr(app.state, "service_config", None)
    path = None
    if model_path and (not is_demo(config) or model_path in demo_model_paths(conn, config)):
        p = Path(model_path).expanduser()
        if p.is_file() and p.suffix.lower() == ".gguf":
            path = str(p)
    if path is None:
        path = find_ready_model_path(conn, config)
    if path is None:
        logger.info("llama-server autostart skipped: no ready model file found")
        return None

    exe = find_executable()
    if exe is None:
        logger.info("llama-server autostart skipped: no engine executable found")
        return None

    # Same launch configuration as the other start sites (issue #523): the
    # registry's context size for this model, one slot, small batches.
    launch = resolve_launch_config(path, conn)

    try:
        await sidecar.start(
            model_path=path,
            executable=exe,
            launch=launch,
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
