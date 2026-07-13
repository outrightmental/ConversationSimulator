# SPDX-License-Identifier: Apache-2.0
"""One-click install pipeline: engine → model → verify → warmup → packs.

POST   /api/setup/install          start (or reattach to) the unified pipeline
GET    /api/setup/install/{id}     poll progress; each stage carries per-byte counts
DELETE /api/setup/install/{id}     cancel a running job

The pipeline composes existing services — ``download_binary()``,
``execute_download()``, the LlamaCppSidecar, and ``seed_official_packs()`` —
so there is no new download machinery.  Stages that are already satisfied are
skipped (idempotent), so re-running after a partial install repairs the state.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.errors import ConvsimError
from convsim_core.packs.seeder import seed_official_packs
from convsim_core.runtime.llama_cpp_download import DownloadProgress, download_binary
from convsim_core.runtime.sidecar import LlamaCppSidecar, SidecarState, find_executable
from convsim_core.services.model_download_service import execute_download
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_install_record,
    set_active_config,
)
from convsim_core.services.setup_install_service import (
    StageState,
    create_job,
    get_job,
    update_job_stages,
    update_job_status,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Strong references to in-flight pipeline tasks (asyncio keeps only weak refs).
_pipeline_tasks: set[asyncio.Task[None]] = set()

_WARMUP_PORT = 7356
_WARMUP_PROMPT = "Hello"
_WARMUP_TIMEOUT = 15.0


# ── Schemas ───────────────────────────────────────────────────────────────────


class StartInstallRequest(BaseModel):
    registry_id: str


class StageResponse(BaseModel):
    id: str
    label: str
    state: str
    bytes_downloaded: Optional[int] = None
    bytes_total: Optional[int] = None
    error: Optional[str] = None


class SetupInstallJobResponse(BaseModel):
    id: int
    status: str
    registry_id: Optional[str] = None
    stages: list[StageResponse]
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


def _job_to_response(job: dict[str, Any]) -> SetupInstallJobResponse:
    return SetupInstallJobResponse(
        id=job["id"],
        status=job["status"],
        registry_id=job.get("registry_id"),
        stages=[StageResponse(**s) for s in job["stages"]],
        error_message=job.get("error_message"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


def _get_registry_row(conn: sqlite3.Connection, registry_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, name, sha256, source_type, download_url, license_spdx, size_gb "
        "FROM model_registry WHERE id = ?",
        (registry_id,),
    ).fetchone()
    return dict(row) if row else None


# ── Pipeline ──────────────────────────────────────────────────────────────────


async def _run_pipeline(
    *,
    job_id: int,
    registry_id: str,
    model_label: str,
    conn: sqlite3.Connection,
    config: Any,
    sidecar: LlamaCppSidecar,
    model_cancel_events: dict[int, asyncio.Event],
    cancel_event: asyncio.Event,
) -> None:
    """Orchestrate all five setup stages, persisting progress after each change."""

    stages = [
        StageState(id="engine",  label="Getting the AI engine",     state="pending"),
        StageState(id="model",   label=model_label,                 state="pending"),
        StageState(id="verify",  label="Verifying (SHA-256)",       state="pending"),
        StageState(id="warmup",  label="First launch of the model", state="pending"),
        StageState(id="packs",   label="Preparing scenarios",       state="pending"),
    ]

    def _save() -> None:
        update_job_stages(conn, job_id, stages)

    def _fail(stage_id: str, error: str) -> None:
        for s in stages:
            if s.id == stage_id:
                s.state = "failed"
                s.error = error
        _save()
        update_job_status(conn, job_id, "failed", error)

    def _cancel(stage_id: str) -> None:
        # A user-requested cancel is a distinct terminal state from a failure:
        # the job status must read 'cancelled', not 'failed' (the DELETE-with-no-
        # running-task path already records it that way, so both paths agree and
        # SetupInstallJobStatus consumers can tell an abort from a real error).
        msg = "Cancelled by user."
        for s in stages:
            if s.id == stage_id:
                s.state = "failed"
                s.error = msg
        _save()
        update_job_status(conn, job_id, "cancelled", msg)

    def _is_cancelled() -> bool:
        return cancel_event.is_set()

    update_job_status(conn, job_id, "running")

    # ── Stage 1: Engine ───────────────────────────────────────────────────────
    stages[0].state = "running"
    _save()

    existing_exe = find_executable()
    if existing_exe:
        logger.info("setup-install(%d): engine found at %s, skipping", job_id, existing_exe)
        stages[0].state = "skipped"
        _save()
    else:
        dest_dir = Path.home() / ".convsim" / "bin"

        def _on_engine_progress(p: DownloadProgress) -> None:
            stages[0].bytes_downloaded = p.bytes_downloaded or None
            stages[0].bytes_total = p.total_bytes
            update_job_stages(conn, job_id, stages)

        try:
            await download_binary(
                dest_dir=dest_dir,
                cancel_event=cancel_event,
                progress_cb=_on_engine_progress,
            )
            stages[0].state = "complete"
            stages[0].bytes_downloaded = None
            stages[0].bytes_total = None
            _save()
        except asyncio.CancelledError:
            _cancel("engine")
            return
        except Exception as exc:
            _fail("engine", str(exc))
            return

    if _is_cancelled():
        _cancel("engine")
        return

    # ── Stage 2 + 3: Model download + verify ─────────────────────────────────
    model_row = _get_registry_row(conn, registry_id)
    if model_row is None:
        _fail("model", f"Model '{registry_id}' not found in the local registry.")
        return

    sha256 = (model_row.get("sha256") or "").strip()
    download_url = (model_row.get("download_url") or "").strip()

    if not sha256 or sha256.upper() == "PENDING":
        _fail("model", "No verified SHA-256 checksum for this model — cannot install safely.")
        return
    if not download_url:
        _fail("model", "No download URL configured for this model.")
        return

    # Check if already installed and ready.
    existing_ready = conn.execute(
        "SELECT id, file_path FROM installed_models "
        "WHERE registry_id = ? AND install_status IN ('ready', 'complete') "
        "ORDER BY id DESC LIMIT 1",
        (registry_id,),
    ).fetchone()

    model_file_path: str

    if existing_ready:
        model_file_path = existing_ready["file_path"]
        logger.info("setup-install(%d): model already ready at %s", job_id, model_file_path)
        stages[1].state = "skipped"
        stages[2].state = "skipped"
        _save()
    else:
        filename = f"{registry_id}.gguf"
        models_dir = Path(config.models_dir)

        # Pre-flight disk check (only when we will actually download): need
        # ~2.2× model size for the .part file plus the final copy. Skipped on
        # the already-installed path above so an idempotent repair re-run is
        # never blocked by a full disk when nothing needs to be fetched.
        size_gb: float | None = model_row.get("size_gb")
        if size_gb and size_gb > 0:
            models_dir.mkdir(parents=True, exist_ok=True)
            free_bytes = shutil.disk_usage(str(models_dir)).free
            required_bytes = int(size_gb * 2.2 * 1024 ** 3)
            if free_bytes < required_bytes:
                free_gb = free_bytes / 1024 ** 3
                shortfall_gb = (required_bytes / 1024 ** 3) - free_gb
                _fail(
                    "model",
                    f"Not enough disk space: {free_gb:.1f} GB available, "
                    f"{size_gb * 2.2:.1f} GB needed ({shortfall_gb:.1f} GB short). "
                    "Free up space and try again.",
                )
                return

        in_progress = conn.execute(
            "SELECT id FROM installed_models "
            "WHERE registry_id = ? AND install_status IN ('pending', 'downloading') "
            "ORDER BY id DESC LIMIT 1",
            (registry_id,),
        ).fetchone()
        if in_progress:
            install_id = in_progress["id"]
            conn.execute(
                "UPDATE installed_models "
                "SET install_status = 'pending', error_message = NULL WHERE id = ?",
                (install_id,),
            )
            conn.commit()
        else:
            install_id = create_install_record(
                conn, registry_id=registry_id, filename=filename, file_path=""
            )

        # Register per-install cancel event so DELETE /api/models/install also works.
        model_cancel = asyncio.Event()
        model_cancel_events[install_id] = model_cancel

        stages[1].state = "running"
        stages[1].bytes_downloaded = None
        stages[1].bytes_total = None
        _save()

        # Concurrently poll the install record for byte progress while downloading.
        async def _poll_model() -> None:
            while True:
                rec = get_install_record(conn, install_id)
                if rec is None:
                    break
                pb = rec.get("progress_bytes") or 0
                sb = rec.get("size_bytes")
                stages[1].bytes_downloaded = pb or None
                stages[1].bytes_total = sb
                # When bytes are done but record still 'downloading': SHA-256 phase.
                if sb and pb >= sb and rec["install_status"] == "downloading":
                    stages[2].state = "running"
                update_job_stages(conn, job_id, stages)
                if rec["install_status"] not in ("pending", "downloading"):
                    break
                await asyncio.sleep(0.5)

        # Forward the pipeline cancel signal to the model download cancel event.
        async def _watch_cancel() -> None:
            while not cancel_event.is_set():
                await asyncio.sleep(0.2)
            model_cancel.set()

        poll_task = asyncio.create_task(_poll_model())
        watch_task = asyncio.create_task(_watch_cancel())

        try:
            await execute_download(
                conn, install_id, download_url, sha256, models_dir, filename,
                cancel_event=model_cancel,
            )
        finally:
            watch_task.cancel()
            poll_task.cancel()
            for t in (watch_task, poll_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            model_cancel_events.pop(install_id, None)

        rec = get_install_record(conn, install_id)
        final_status = rec["install_status"] if rec else "failed"

        if final_status == "cancelled" or _is_cancelled():
            _cancel("model")
            return

        if final_status == "checksum_mismatch":
            # One silent retry before surfacing the error.
            logger.warning("setup-install(%d): checksum mismatch, retrying once", job_id)
            stages[2].state = "pending"
            _save()
            conn.execute(
                "UPDATE installed_models "
                "SET install_status = 'pending', error_message = NULL, progress_bytes = 0 "
                "WHERE id = ?",
                (install_id,),
            )
            conn.commit()

            model_cancel2 = asyncio.Event()
            model_cancel_events[install_id] = model_cancel2

            async def _watch_cancel2() -> None:
                while not cancel_event.is_set():
                    await asyncio.sleep(0.2)
                model_cancel2.set()

            watch_task2 = asyncio.create_task(_watch_cancel2())
            try:
                await execute_download(
                    conn, install_id, download_url, sha256, models_dir, filename,
                    cancel_event=model_cancel2,
                )
            finally:
                watch_task2.cancel()
                try:
                    await watch_task2
                except asyncio.CancelledError:
                    pass
                model_cancel_events.pop(install_id, None)

            rec = get_install_record(conn, install_id)
            final_status = rec["install_status"] if rec else "failed"
            if final_status != "ready":
                err = (rec.get("error_message") if rec else None) or (
                    "SHA-256 checksum mismatch after two attempts. "
                    "The file may be corrupted at the source. Try again later."
                )
                _fail("verify", err)
                return

        elif final_status not in ("ready", "complete"):
            err = (rec.get("error_message") if rec else None) or "Download failed."
            _fail("model", err)
            return

        model_file_path = (rec.get("file_path") if rec else "") or ""
        stages[1].state = "complete"
        stages[1].bytes_downloaded = rec.get("size_bytes") if rec else None
        stages[1].bytes_total = rec.get("size_bytes") if rec else None
        stages[2].state = "complete"
        _save()

    if _is_cancelled():
        _cancel("warmup")
        return

    # ── Stage 4: Warmup ───────────────────────────────────────────────────────
    stages[3].state = "running"
    _save()

    try:
        if sidecar.state == SidecarState.RUNNING:
            logger.info("setup-install(%d): sidecar already running, skipping start", job_id)
            stages[3].state = "skipped"
        else:
            if sidecar.state not in (SidecarState.STOPPED,):
                await sidecar.stop()

            exe = find_executable()
            if exe is None:
                _fail("warmup", "llama-server binary not found after the engine stage completed.")
                return

            await sidecar.start(
                model_path=model_file_path,
                executable=exe,
                startup_timeout=120.0,
            )

            # Quick 1-token probe to verify the model can generate output.
            try:
                async with httpx.AsyncClient(timeout=_WARMUP_TIMEOUT) as client:
                    resp = await client.post(
                        f"http://127.0.0.1:{_WARMUP_PORT}/v1/completions",
                        json={
                            "prompt": _WARMUP_PROMPT,
                            "max_tokens": 1,
                            "temperature": 0.0,
                        },
                    )
                    resp.raise_for_status()
            except Exception as exc:
                logger.warning(
                    "setup-install(%d): warmup inference probe failed (non-fatal): %s",
                    job_id, exc,
                )

            stages[3].state = "complete"

    except (RuntimeError, TimeoutError) as exc:
        _fail(
            "warmup",
            f"Model downloaded but failed to start: {exc}. "
            "This may indicate insufficient RAM or a corrupt model file. "
            "Check system requirements or try a smaller model.",
        )
        return
    except Exception as exc:
        _fail("warmup", f"Warmup failed unexpectedly: {exc}")
        return

    # Only now that the model has actually launched do we persist it as the
    # active runtime. Setting it earlier would leave a model that fails warmup
    # (e.g. too large for available RAM) as the active selection, so the next
    # app boot would try to load it and crash-loop — exactly the failure this
    # stage exists to catch before the user's first conversation.
    set_active_config(conn, runtime_id="llama_cpp", model_id=model_file_path)

    _save()

    if _is_cancelled():
        _cancel("packs")
        return

    # ── Stage 5: Packs ────────────────────────────────────────────────────────
    stages[4].state = "running"
    _save()

    try:
        seeded = await asyncio.to_thread(seed_official_packs, config, conn)
        logger.info("setup-install(%d): seeded %d packs", job_id, seeded)
        stages[4].state = "complete"
    except Exception as exc:
        # Pack seeding failures are non-fatal — the model is ready to use.
        logger.warning("setup-install(%d): pack seeding failed (non-fatal): %s", job_id, exc)
        stages[4].state = "failed"
        stages[4].error = str(exc)

    _save()
    update_job_status(conn, job_id, "complete")
    logger.info("setup-install(%d): pipeline complete", job_id)


# ── Task launch + restart recovery ────────────────────────────────────────────


def _launch_pipeline_task(
    *, app: Any, job_id: int, registry_id: str, model_label: str
) -> None:
    """Spawn the background pipeline task for *job_id* and track a strong ref.

    Shared by the POST endpoint and the startup restart-recovery path so both
    wire the cancel event, error handling, and task bookkeeping identically.
    """
    conn = app.state.db.connection()
    config = app.state.service_config
    sidecar: LlamaCppSidecar = app.state.sidecar
    model_cancel_events: dict[int, asyncio.Event] = app.state.cancel_events
    setup_cancel_events: dict[int, asyncio.Event] = app.state.setup_install_cancel_events

    cancel_event = asyncio.Event()
    setup_cancel_events[job_id] = cancel_event

    async def _run() -> None:
        try:
            await _run_pipeline(
                job_id=job_id,
                registry_id=registry_id,
                model_label=model_label,
                conn=conn,
                config=config,
                sidecar=sidecar,
                model_cancel_events=model_cancel_events,
                cancel_event=cancel_event,
            )
        except Exception as exc:
            logger.exception("setup-install(%d): unhandled error", job_id)
            update_job_status(conn, job_id, "failed", str(exc))
        finally:
            setup_cancel_events.pop(job_id, None)

    task = asyncio.create_task(_run())
    _pipeline_tasks.add(task)
    task.add_done_callback(_pipeline_tasks.discard)


def resume_orphaned_jobs(app: Any) -> None:
    """Re-drive any setup-install job left non-terminal by a crash or app kill.

    Called once at startup. When the app is killed mid-install the job row
    persists as 'running'/'pending' but the asyncio task that drove it dies with
    the process, so nothing advances it on relaunch — the client would poll a
    frozen job forever. Re-running the pipeline is safe: ``execute_download``
    resumes from the ``.part`` byte offset and every stage's idempotency check
    skips already-satisfied work, so an interrupted download continues rather
    than restarting. This is the server half of the #382 resume acceptance
    criterion (the client half routes the user back to the progress step).
    """
    conn = app.state.db.connection()
    try:
        rows = conn.execute(
            "SELECT id, registry_id FROM setup_install_jobs "
            "WHERE status IN ('pending', 'running') ORDER BY id DESC"
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - table missing shouldn't happen post-migration
        return
    if not rows:
        return

    # Only the newest non-terminal job is resumed; any older ones are stale
    # orphans from earlier runs and are retired so they don't linger as active.
    for stale in rows[1:]:
        update_job_status(conn, stale["id"], "failed", "Superseded by a newer install job.")

    newest = dict(rows[0])
    job_id = newest["id"]
    registry_id = newest.get("registry_id")
    if not registry_id:
        update_job_status(conn, job_id, "failed", "Missing model reference; cannot resume.")
        return
    model_row = _get_registry_row(conn, registry_id)
    if model_row is None:
        update_job_status(
            conn, job_id, "failed",
            f"Model '{registry_id}' is no longer in the registry; cannot resume.",
        )
        return

    logger.info("setup-install(%d): resuming after app restart", job_id)
    _launch_pipeline_task(
        app=app,
        job_id=job_id,
        registry_id=registry_id,
        model_label=f"Downloading {model_row['name']}",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/api/setup/install", response_model=SetupInstallJobResponse)
async def start_setup_install(
    request: Request, body: StartInstallRequest
) -> SetupInstallJobResponse:
    """Start the one-click install pipeline, or reattach to an in-progress job."""
    conn = request.app.state.db.connection()

    model_row = _get_registry_row(conn, body.registry_id)
    if model_row is None:
        raise ConvsimError(
            code="MODEL_NOT_FOUND",
            message=f"Model '{body.registry_id}' not found in the local registry.",
            status_code=404,
        )

    model_label = f"Downloading {model_row['name']}"

    # Reattach if a job for this registry_id is still running.
    existing = conn.execute(
        "SELECT id FROM setup_install_jobs "
        "WHERE registry_id = ? AND status IN ('pending', 'running') "
        "ORDER BY id DESC LIMIT 1",
        (body.registry_id,),
    ).fetchone()
    if existing:
        job = get_job(conn, existing["id"])
        if job:
            return _job_to_response(job)

    job_id = create_job(conn, registry_id=body.registry_id, model_label=model_label)
    _launch_pipeline_task(
        app=request.app,
        job_id=job_id,
        registry_id=body.registry_id,
        model_label=model_label,
    )

    job = get_job(conn, job_id)
    return _job_to_response(job)  # type: ignore[arg-type]


@router.get("/api/setup/install/{job_id}", response_model=SetupInstallJobResponse)
async def get_setup_install_status(
    request: Request, job_id: int
) -> SetupInstallJobResponse:
    """Return current pipeline job status and per-stage progress."""
    conn = request.app.state.db.connection()
    job = get_job(conn, job_id)
    if job is None:
        raise ConvsimError(
            code="JOB_NOT_FOUND",
            message=f"Setup install job {job_id} not found.",
            status_code=404,
        )
    return _job_to_response(job)


@router.delete("/api/setup/install/{job_id}", status_code=204)
async def cancel_setup_install(request: Request, job_id: int) -> None:
    """Cancel a running install pipeline."""
    conn = request.app.state.db.connection()
    job = get_job(conn, job_id)
    if job is None:
        raise ConvsimError(
            code="JOB_NOT_FOUND",
            message=f"Setup install job {job_id} not found.",
            status_code=404,
        )

    _TERMINAL = {"cancelled", "complete", "failed"}
    if job["status"] in _TERMINAL:
        raise ConvsimError(
            code="JOB_NOT_CANCELLABLE",
            message=(
                f"Setup install job {job_id} is already in "
                f"terminal state '{job['status']}'."
            ),
            status_code=409,
        )

    setup_cancel_events: dict[int, asyncio.Event] = (
        request.app.state.setup_install_cancel_events
    )
    event = setup_cancel_events.get(job_id)
    if event is not None:
        event.set()
    else:
        update_job_status(conn, job_id, "cancelled", "Cancelled by user.")
