# SPDX-License-Identifier: Apache-2.0
"""REST API for managed llama-server sidecar lifecycle.

Endpoints allow the UI (or advanced users) to start/stop a local
llama-server process managed by the app. Users who run their own
llama-server externally can ignore these endpoints entirely.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.errors import ConvsimError
from convsim_core.runtime.sidecar import LlamaCppSidecar, SidecarState

router = APIRouter()


class SidecarStartRequest(BaseModel):
    model_path: str
    executable: Optional[str] = None
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


@router.post("/api/sidecar/start", response_model=SidecarStartResponse)
async def start_sidecar(request: Request, body: SidecarStartRequest) -> SidecarStartResponse:
    """Start the managed llama-server with the specified GGUF model.

    Returns 409 if a sidecar is already running. Returns 503 on port conflict,
    missing executable, or startup failure (with a descriptive message).
    """
    sidecar: LlamaCppSidecar = request.app.state.sidecar

    if sidecar.state == SidecarState.RUNNING:
        raise ConvsimError(
            code="SIDECAR_ALREADY_RUNNING",
            message="A managed llama-server is already running. Stop it first via POST /api/sidecar/stop.",
            status_code=409,
        )

    try:
        await sidecar.start(
            body.model_path,
            executable=body.executable,
            context_length=body.context_length,
            threads=body.threads,
            gpu_layers=body.gpu_layers,
            startup_timeout=body.startup_timeout,
        )
    except RuntimeError as exc:
        current = sidecar.get_status()
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

    if sidecar.state not in (SidecarState.RUNNING, SidecarState.STARTING):
        return SidecarStopResponse(
            state=sidecar.state.value,
            message="No managed llama-server is running.",
        )

    await sidecar.stop()
    return SidecarStopResponse(
        state=SidecarState.STOPPED.value,
        message="Managed llama-server stopped.",
    )


@router.get("/api/sidecar/status", response_model=SidecarStatusResponse)
async def sidecar_status(request: Request) -> SidecarStatusResponse:
    """Return the current state of the managed sidecar process."""
    sidecar: LlamaCppSidecar = request.app.state.sidecar
    status = sidecar.get_status()
    return SidecarStatusResponse(**status)
