# SPDX-License-Identifier: Apache-2.0
"""Guided voice setup: tell the player what is missing, then install it (issue #487).

Settings used to report "STT: not installed / TTS: not installed" and stop
there. These endpoints are the other half of that sentence.

GET    /api/voice/setup/plan                 what voice needs here, and what is satisfied
POST   /api/voice/setup/install              download the chosen weight files
GET    /api/voice/setup/install/{id}         poll per-asset byte progress
DELETE /api/voice/setup/install/{id}         cancel a running download
POST   /api/voice/setup/engine/{id}/start    start an engine that is installed but stopped

The split matters: weight files are fetched and SHA-256 verified by the app,
while the two native engines (``whisper-cli``, the Kokoro server) publish no
checksummed cross-platform release, so the plan hands back the exact command
for this OS and the player re-checks. Nothing is downloaded without an explicit
POST naming the assets.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.errors import ConvsimError
from convsim_core.runtime.sidecar import SidecarState
from convsim_core.services.setup_install_service import StageState
from convsim_core.services.voice_download import (
    ChecksumMismatch,
    DownloadCancelled,
    download_voice_asset,
)
from convsim_core.services.voice_registry import get_asset, get_engine
from convsim_core.services.voice_setup_service import (
    apply_stt_model_path,
    build_plan,
    create_job,
    default_asset_ids,
    get_job,
    resolved_install_path,
    set_stt_model_path,
    stage_label,
    total_download_bytes,
    update_job_stages,
    update_job_status,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Strong references to in-flight install tasks (asyncio keeps only weak refs).
_install_tasks: set[asyncio.Task[None]] = set()

_TERMINAL_STATUSES = {"complete", "failed", "cancelled"}


# ── Schemas ───────────────────────────────────────────────────────────────────


class VoiceAssetView(BaseModel):
    id: str
    capability: str
    name: str
    description: str
    language_note: str
    recommended: bool
    selected: bool = False
    size_bytes: int
    license: str
    license_url: str
    source_url: str
    sha256: str
    install_path: str
    installed: bool


class VoiceEngineView(BaseModel):
    id: str
    capability: str
    name: str
    why_manual: str
    docs_url: str
    command: Optional[str] = None
    command_note: Optional[str] = None
    startable: bool
    installed: bool
    found_at: Optional[str] = None


class VoiceCapabilityView(BaseModel):
    id: str
    label: str
    description: str
    ready: bool
    required_engine_ids: list[str]
    asset_ids: list[str]


class VoiceSetupPlanResponse(BaseModel):
    capabilities: list[VoiceCapabilityView]
    assets: list[VoiceAssetView]
    engines: list[VoiceEngineView]
    platform: str
    kokoro_state: Optional[str] = None
    onnxruntime_installed: bool
    ffmpeg_installed: bool
    active_job_id: Optional[int] = None
    default_asset_ids: list[str]
    # Byte total the one-click path would transfer right now (already-installed
    # assets excluded), so the UI can promise an honest download size.
    default_download_bytes: int


class StartVoiceInstallRequest(BaseModel):
    # Omitted means "the one-click default": recommended STT model plus VAD.
    asset_ids: Optional[list[str]] = None


class VoiceStageResponse(BaseModel):
    id: str
    label: str
    state: str
    bytes_downloaded: Optional[int] = None
    bytes_total: Optional[int] = None
    error: Optional[str] = None


class VoiceInstallJobResponse(BaseModel):
    id: int
    status: str
    asset_ids: list[str]
    stages: list[VoiceStageResponse]
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class StartEngineResponse(BaseModel):
    engine_id: str
    state: str
    started: bool
    message: str


def _job_to_response(job: dict[str, Any]) -> VoiceInstallJobResponse:
    return VoiceInstallJobResponse(
        id=job["id"],
        status=job["status"],
        asset_ids=job["asset_ids"],
        stages=[VoiceStageResponse(**s) for s in job["stages"]],
        error_message=job.get("error_message"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


# ── Pipeline ──────────────────────────────────────────────────────────────────


async def _run_install(
    *,
    job_id: int,
    asset_ids: list[str],
    conn: Any,
    stt_worker: Any,
    cancel_event: asyncio.Event,
) -> None:
    """Download each requested asset in turn, then point the engines at them."""
    assets = [a for a in (get_asset(i) for i in asset_ids) if a is not None]
    stages = [
        StageState(id=a.id, label=stage_label(a), state="pending") for a in assets
    ]

    def _save() -> None:
        update_job_stages(conn, job_id, stages)

    update_job_status(conn, job_id, "running")
    _save()

    newest_stt_path: str | None = None

    for index, asset in enumerate(assets):
        # Cancel between assets, not only mid-transfer. download_voice_asset
        # sees the event on its first chunk, so an asset that actually downloads
        # aborts there — but the skip branch below never consults it, so a cancel
        # landing in the gap between two assets used to run the loop out and
        # report the job 'complete' after the client had been told 204. With
        # every asset already on disk there is no download call at all, so this
        # is the only place such a job can observe a cancel.
        #
        # This stage keeps its 'pending' state: nothing was attempted for it.
        # The mid-download path below marks its stage failed because that one
        # did run.
        if cancel_event.is_set():
            logger.info("voice-install(%d): cancelled before %s", job_id, asset.id)
            update_job_status(conn, job_id, "cancelled", "Cancelled by user.")
            return

        stage = stages[index]
        dest = resolved_install_path(asset)

        if dest.is_file():
            logger.info("voice-install(%d): %s already present, skipping", job_id, asset.id)
            stage.state = "skipped"
            if asset.capability == "stt":
                newest_stt_path = str(dest)
            _save()
            continue

        stage.state = "running"
        stage.bytes_total = asset.size_bytes
        _save()

        def _on_progress(done: int, total: int | None, _stage: StageState = stage) -> None:
            _stage.bytes_downloaded = done
            # The registry size is authoritative; a redirect chain can report a
            # content-length for an intermediate body, which would make the bar
            # jump. Only trust the header when the registry has no size.
            if total is not None and _stage.bytes_total is None:
                _stage.bytes_total = total
            update_job_stages(conn, job_id, stages)

        try:
            await download_voice_asset(
                url=asset.url,
                dest_path=dest,
                expected_sha256=asset.sha256,
                progress_cb=_on_progress,
                cancel_event=cancel_event,
            )
        except (DownloadCancelled, asyncio.CancelledError):
            stage.state = "failed"
            stage.error = "Cancelled by user."
            _save()
            update_job_status(conn, job_id, "cancelled", "Cancelled by user.")
            return
        except ChecksumMismatch as exc:
            stage.state = "failed"
            stage.error = str(exc)
            _save()
            update_job_status(conn, job_id, "failed", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the player
            message = f"{asset.name} could not be downloaded: {exc}"
            stage.state = "failed"
            stage.error = message
            _save()
            update_job_status(conn, job_id, "failed", message)
            return

        stage.state = "complete"
        stage.bytes_downloaded = asset.size_bytes
        if asset.capability == "stt":
            newest_stt_path = str(dest)
        _save()

    # An STT model is only useful once the worker is reading that exact file.
    # Persist before applying so a crash between the two still restores the
    # choice on the next boot.
    if newest_stt_path is not None:
        set_stt_model_path(conn, newest_stt_path)
        apply_stt_model_path(stt_worker, newest_stt_path)

    update_job_status(conn, job_id, "complete")
    logger.info("voice-install(%d): complete", job_id)


def _launch_install_task(*, app: Any, job_id: int, asset_ids: list[str]) -> None:
    conn = app.state.db.connection()
    cancel_events: dict[int, asyncio.Event] = app.state.voice_install_cancel_events
    cancel_event = asyncio.Event()
    cancel_events[job_id] = cancel_event

    async def _run() -> None:
        try:
            await _run_install(
                job_id=job_id,
                asset_ids=asset_ids,
                conn=conn,
                stt_worker=app.state.stt_worker,
                cancel_event=cancel_event,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("voice-install(%d): unhandled error", job_id)
            update_job_status(conn, job_id, "failed", str(exc))
        finally:
            cancel_events.pop(job_id, None)

    task = asyncio.create_task(_run())
    _install_tasks.add(task)
    task.add_done_callback(_install_tasks.discard)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/voice/setup/plan", response_model=VoiceSetupPlanResponse)
async def get_voice_setup_plan(request: Request) -> VoiceSetupPlanResponse:
    """Report what voice needs on this machine and what is already satisfied."""
    conn = request.app.state.db.connection()
    stt_health = await request.app.state.stt_worker.health()
    tts_health = await request.app.state.tts_worker.health()

    kokoro = getattr(request.app.state, "kokoro_sidecar", None)
    kokoro_state = kokoro.state.value if kokoro is not None else None

    from convsim_core.runtime.types import RuntimeStatus

    ready = (RuntimeStatus.READY, RuntimeStatus.DEGRADED)
    plan = build_plan(
        conn,
        stt_ready=stt_health.status in ready,
        tts_ready=tts_health.status in ready,
        kokoro_state=kokoro_state,
    )
    defaults = default_asset_ids()
    plan["default_asset_ids"] = defaults
    plan["default_download_bytes"] = total_download_bytes(defaults)
    return VoiceSetupPlanResponse(**plan)


@router.post("/api/voice/setup/install", response_model=VoiceInstallJobResponse)
async def start_voice_install(
    request: Request, body: StartVoiceInstallRequest | None = None
) -> VoiceInstallJobResponse:
    """Start downloading the requested voice assets, or reattach to a running job."""
    conn = request.app.state.db.connection()
    asset_ids = (body.asset_ids if body is not None else None) or default_asset_ids()

    unknown = [i for i in asset_ids if get_asset(i) is None]
    if unknown:
        raise ConvsimError(
            code="VOICE_ASSET_NOT_FOUND",
            message=f"Unknown voice asset(s): {', '.join(unknown)}.",
            status_code=404,
        )

    # Reattach rather than racing a second downloader onto the same files.
    existing = conn.execute(
        "SELECT id FROM voice_install_jobs WHERE status IN ('pending', 'running') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if existing:
        job = get_job(conn, existing["id"])
        if job:
            return _job_to_response(job)

    stages = [
        StageState(id=a.id, label=stage_label(a), state="pending")
        for a in (get_asset(i) for i in asset_ids)
        if a is not None
    ]
    job_id = create_job(conn, asset_ids=asset_ids, stages=stages)
    _launch_install_task(app=request.app, job_id=job_id, asset_ids=asset_ids)

    job = get_job(conn, job_id)
    return _job_to_response(job)  # type: ignore[arg-type]


@router.get("/api/voice/setup/install/{job_id}", response_model=VoiceInstallJobResponse)
async def get_voice_install_status(request: Request, job_id: int) -> VoiceInstallJobResponse:
    """Return current voice install status and per-asset byte progress."""
    conn = request.app.state.db.connection()
    job = get_job(conn, job_id)
    if job is None:
        raise ConvsimError(
            code="JOB_NOT_FOUND",
            message=f"Voice install job {job_id} not found.",
            status_code=404,
        )
    return _job_to_response(job)


@router.delete("/api/voice/setup/install/{job_id}", status_code=204)
async def cancel_voice_install(request: Request, job_id: int) -> None:
    """Cancel a running voice install; partial files are removed."""
    conn = request.app.state.db.connection()
    job = get_job(conn, job_id)
    if job is None:
        raise ConvsimError(
            code="JOB_NOT_FOUND",
            message=f"Voice install job {job_id} not found.",
            status_code=404,
        )
    if job["status"] in _TERMINAL_STATUSES:
        raise ConvsimError(
            code="JOB_NOT_CANCELLABLE",
            message=(
                f"Voice install job {job_id} is already in terminal "
                f"state '{job['status']}'."
            ),
            status_code=409,
        )

    cancel_events: dict[int, asyncio.Event] = request.app.state.voice_install_cancel_events
    event = cancel_events.get(job_id)
    if event is not None:
        event.set()
    else:
        update_job_status(conn, job_id, "cancelled", "Cancelled by user.")


@router.post("/api/voice/setup/engine/{engine_id}/start", response_model=StartEngineResponse)
async def start_voice_engine(request: Request, engine_id: str) -> StartEngineResponse:
    """Start a voice engine that is installed but not running.

    Only Kokoro is startable: the app owns its server process when the binary
    is present (Steam depots bundle it). whisper.cpp is a CLI invoked per
    utterance, so there is nothing to start.
    """
    engine = get_engine(engine_id)
    if engine is None or not engine.startable:
        raise ConvsimError(
            code="ENGINE_NOT_STARTABLE",
            message=f"No startable voice engine with id '{engine_id}'.",
            status_code=404,
        )

    sidecar = getattr(request.app.state, "kokoro_sidecar", None)
    if sidecar is None:  # pragma: no cover - always wired in app startup
        raise ConvsimError(
            code="ENGINE_UNAVAILABLE",
            message="The Kokoro sidecar is not available in this process.",
            status_code=503,
        )

    if sidecar.state == SidecarState.RUNNING:
        return StartEngineResponse(
            engine_id=engine_id,
            state=sidecar.state.value,
            started=False,
            message="The voice server is already running.",
        )

    try:
        await sidecar.start()
    except (RuntimeError, TimeoutError) as exc:
        # A missing binary, a port conflict or a slow start are all things the
        # player can act on, so the reason is returned rather than a 500.
        return StartEngineResponse(
            engine_id=engine_id,
            state=sidecar.state.value,
            started=False,
            message=str(exc),
        )

    return StartEngineResponse(
        engine_id=engine_id,
        state=sidecar.state.value,
        started=True,
        message="The voice server is running. NPC replies can now be spoken.",
    )
