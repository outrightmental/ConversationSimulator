# SPDX-License-Identifier: Apache-2.0
"""REST API for managed llama-server sidecar lifecycle.

Endpoints allow the UI (or advanced users) to start/stop a local
llama-server process managed by the app. Users who run their own
llama-server externally can ignore these endpoints entirely.

Also exposes:
  GET  /api/runtime/capabilities  — capability flags of the active runtime
  POST /api/sidecar/download-runtime — download/install llama-server binary
  GET  /api/sidecar/download-runtime — poll download progress
  DELETE /api/sidecar/download-runtime — cancel an in-progress download
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.errors import ConvsimError
from convsim_core.runtime.llama_cpp_download import (
    DownloadProgress,
    DownloadState,
    detect_platform_string,
    download_binary,
)
from convsim_core.runtime.sidecar import LlamaCppSidecar, SidecarState

router = APIRouter()

# ── Binary download state (one download at a time, module-level) ──────────────

_download_progress: DownloadProgress = DownloadProgress()
_download_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
_download_cancel: asyncio.Event = asyncio.Event()

# Strong reference so the task is not garbage-collected mid-download.
_active_download_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]


def _reset_download_state() -> None:
    """Reset module-level download state (called by tests to avoid bleed)."""
    global _download_progress, _download_task, _download_cancel
    _download_progress = DownloadProgress()
    _download_task = None
    _download_cancel = asyncio.Event()
    _active_download_tasks.clear()


# ── Sidecar schemas ───────────────────────────────────────────────────────────


class SidecarStartRequest(BaseModel):
    model_path: str
    executable: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 7356
    context_length: Optional[int] = None
    threads: Optional[int] = None
    gpu_layers: Optional[int] = None
    startup_timeout: float = 120.0


class SidecarStartResponse(BaseModel):
    state: str
    pid: Optional[int] = None
    model_path: Optional[str] = None
    log_path: str
    host: str
    port: int
    started_at: Optional[str] = None


class SidecarStopResponse(BaseModel):
    state: str
    message: str


class SidecarStatusResponse(BaseModel):
    state: str
    pid: Optional[int] = None
    model_path: Optional[str] = None
    error: Optional[str] = None
    log_path: str
    host: str
    port: int
    started_at: Optional[str] = None


# ── Download schemas ──────────────────────────────────────────────────────────


class DownloadRuntimeRequest(BaseModel):
    """Request body for POST /api/sidecar/download-runtime.

    ``version`` is the exact llama.cpp release tag (e.g. ``"b5140"``).
    Omit to auto-fetch the latest release.

    ``dest_dir`` overrides the default install directory
    (``~/.convsim/bin``). The binary is placed inside this directory as
    ``llama-server`` (or ``llama-server.exe`` on Windows).
    """

    version: Optional[str] = None
    dest_dir: Optional[str] = None


class DownloadRuntimeStatusResponse(BaseModel):
    """Current status of the binary download (or ``"idle"`` if never started)."""

    state: str
    bytes_downloaded: int = 0
    total_bytes: Optional[int] = None
    error: Optional[str] = None
    binary_path: Optional[str] = None
    release_tag: Optional[str] = None
    platform: Optional[str] = None


# ── Capabilities schema ───────────────────────────────────────────────────────


class RuntimeCapabilitiesResponse(BaseModel):
    """Feature flags advertised by the active runtime.

    Clients can use this to decide which UI features to enable (e.g. hide the
    structured-output toggle when ``json_schema`` is False).
    """

    runtime_id: str
    streaming: bool
    json_schema: bool
    grammar: bool
    tool_calling: bool
    embeddings: bool


# ── Sidecar lifecycle endpoints ───────────────────────────────────────────────


@router.post("/api/sidecar/start", response_model=SidecarStartResponse)
async def start_sidecar(request: Request, body: SidecarStartRequest) -> SidecarStartResponse:
    """Start the managed llama-server with the specified GGUF model.

    Returns 409 if a sidecar is already running. Returns 503 on port conflict,
    missing executable, or startup failure (with a descriptive message).
    """
    sidecar: LlamaCppSidecar = request.app.state.sidecar

    if sidecar.state in (SidecarState.RUNNING, SidecarState.STARTING):
        raise ConvsimError(
            code="SIDECAR_ALREADY_RUNNING",
            message="A managed llama-server is already running or starting. Stop it first via POST /api/sidecar/stop.",
            status_code=409,
        )

    try:
        await sidecar.start(
            body.model_path,
            executable=body.executable,
            host=body.host,
            port=body.port,
            context_length=body.context_length,
            threads=body.threads,
            gpu_layers=body.gpu_layers,
            startup_timeout=body.startup_timeout,
        )
    except (RuntimeError, TimeoutError) as exc:
        raise ConvsimError(
            code="SIDECAR_START_FAILED",
            message=str(exc),
            status_code=503,
        ) from exc

    status = sidecar.get_status()
    return SidecarStartResponse(
        state=status["state"],
        pid=status["pid"],
        model_path=status["model_path"],
        log_path=status["log_path"],
        host=status["host"],
        port=status["port"],
        started_at=status["started_at"],
    )


@router.post("/api/sidecar/stop", response_model=SidecarStopResponse)
async def stop_sidecar(request: Request) -> SidecarStopResponse:
    """Stop the managed llama-server process.

    No-op (200) if no sidecar is running.
    """
    sidecar: LlamaCppSidecar = request.app.state.sidecar

    was_running = sidecar.state in (SidecarState.RUNNING, SidecarState.STARTING)
    await sidecar.stop()

    if was_running:
        return SidecarStopResponse(state=SidecarState.STOPPED.value, message="Managed llama-server stopped.")
    return SidecarStopResponse(state=SidecarState.STOPPED.value, message="No managed llama-server is running.")


@router.get("/api/sidecar/status", response_model=SidecarStatusResponse)
async def sidecar_status(request: Request) -> SidecarStatusResponse:
    """Return the current state of the managed sidecar process."""
    sidecar: LlamaCppSidecar = request.app.state.sidecar
    status = sidecar.get_status()
    return SidecarStatusResponse(**status)


# ── Binary download endpoints ─────────────────────────────────────────────────


@router.post("/api/sidecar/download-runtime", response_model=DownloadRuntimeStatusResponse)
async def start_download_runtime(body: DownloadRuntimeRequest) -> DownloadRuntimeStatusResponse:
    """Start a background download/install of the llama-server binary.

    Only one download can run at a time. Returns 409 if a download is already
    in progress. Poll ``GET /api/sidecar/download-runtime`` for progress.

    On completion the binary is placed in ``dest_dir`` (default:
    ``~/.convsim/bin``) and ``find_executable()`` will discover it via PATH
    or the ``CONVSIM_BUNDLED_RUNTIME_DIR`` convention (see
    docs/sidecar-bundling.md).
    """
    global _download_progress, _download_task, _download_cancel

    if _download_task is not None and not _download_task.done():
        raise ConvsimError(
            code="DOWNLOAD_ALREADY_IN_PROGRESS",
            message=(
                "A binary download is already in progress. "
                "Poll GET /api/sidecar/download-runtime for status, "
                "or DELETE /api/sidecar/download-runtime to cancel."
            ),
            status_code=409,
        )

    try:
        platform_str = detect_platform_string()
    except RuntimeError as exc:
        raise ConvsimError(
            code="PLATFORM_NOT_SUPPORTED",
            message=str(exc),
            status_code=400,
        ) from exc

    dest = Path(body.dest_dir) if body.dest_dir else Path.home() / ".convsim" / "bin"

    _download_cancel = asyncio.Event()
    _download_progress = DownloadProgress(state=DownloadState.FETCHING_RELEASE)

    def _on_progress(p: DownloadProgress) -> None:
        global _download_progress
        _download_progress = p

    async def _run() -> None:
        try:
            await download_binary(
                dest_dir=dest,
                version=body.version,
                platform_string=platform_str,
                cancel_event=_download_cancel,
                progress_cb=_on_progress,
            )
        except asyncio.CancelledError:
            pass
        except Exception:
            pass  # error is captured in progress via progress_cb

    task = asyncio.create_task(_run())
    _active_download_tasks.add(task)
    task.add_done_callback(_active_download_tasks.discard)
    _download_task = task

    return DownloadRuntimeStatusResponse(
        state=_download_progress.state.value,
        bytes_downloaded=_download_progress.bytes_downloaded,
        total_bytes=_download_progress.total_bytes,
        error=_download_progress.error,
        binary_path=_download_progress.binary_path,
        release_tag=_download_progress.release_tag,
        platform=platform_str,
    )


@router.get("/api/sidecar/download-runtime", response_model=DownloadRuntimeStatusResponse)
async def get_download_runtime_status() -> DownloadRuntimeStatusResponse:
    """Return the current status of the binary download.

    Returns ``state: "idle"`` when no download has been started this session.
    """
    try:
        platform_str = detect_platform_string()
    except RuntimeError:
        platform_str = None

    p = _download_progress
    return DownloadRuntimeStatusResponse(
        state=p.state.value,
        bytes_downloaded=p.bytes_downloaded,
        total_bytes=p.total_bytes,
        error=p.error,
        binary_path=p.binary_path,
        release_tag=p.release_tag,
        platform=platform_str,
    )


@router.delete("/api/sidecar/download-runtime", status_code=204)
async def cancel_download_runtime() -> None:
    """Cancel an in-progress binary download.

    Returns 409 when no download is running.
    """
    global _download_task

    if _download_task is None or _download_task.done():
        raise ConvsimError(
            code="NO_DOWNLOAD_IN_PROGRESS",
            message="No binary download is currently in progress.",
            status_code=409,
        )
    _download_cancel.set()


# ── Runtime capabilities endpoint ─────────────────────────────────────────────


@router.get("/api/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
async def get_runtime_capabilities(request: Request) -> RuntimeCapabilitiesResponse:
    """Return the feature flags of the currently active runtime.

    Streaming and structured-output (json_schema) flags let the UI show or
    hide features that depend on runtime support.  The flags are determined
    by the runtime adapter selected at startup (llama_cpp, ollama, fake, …).
    """
    runtime = request.app.state.runtime
    caps = runtime.capabilities
    return RuntimeCapabilitiesResponse(
        runtime_id=runtime.id,
        streaming=caps.streaming,
        json_schema=caps.json_schema,
        grammar=caps.grammar,
        tool_calling=caps.tool_calling,
        embeddings=caps.embeddings,
    )
