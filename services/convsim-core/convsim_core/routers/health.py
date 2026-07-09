# SPDX-License-Identifier: Apache-2.0
import os
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core import __version__
from convsim_core.runtime.types import RuntimeHealth
from convsim_core.services.model_manager_service import get_active_config, get_most_recent_benchmark
from convsim_core.stt.types import SttHealth
from convsim_core.tts.types import TtsHealth

router = APIRouter()


# ---------------------------------------------------------------------------
# Sidecar diagnostics helpers
# ---------------------------------------------------------------------------


def _user_message_for_sidecar(state: str, error: Optional[str]) -> str:
    """Return an actionable one-sentence message for non-technical users."""
    if state == "running":
        return "Running."
    if state == "starting":
        return "Starting — this may take a minute while the model loads."
    if state == "stopped":
        return "Not started. Select a model in Settings to enable AI responses."
    if state == "crashed":
        hint = f": {error}" if error else "."
        return f"Crashed unexpectedly{hint} Try restarting from Settings."
    if state == "port_conflict":
        return (
            "Cannot start: another application is using the required port. "
            "Close competing applications and try again from Settings."
        )
    return f"Unknown state ({state})."


def _build_sidecar_diagnostics(
    supervisor: Any,
) -> "_SidecarDiagnostics":
    """Build a SidecarDiagnostics object from the ProcessSupervisor."""
    if supervisor is None:
        return _SidecarDiagnostics(all_ready=False, user_message="Supervisor not available.", sidecars=[])

    entries: list[_SidecarEntry] = []
    for item in supervisor.health_summary():
        state = item.get("state", "stopped")
        error = item.get("error")
        entries.append(
            _SidecarEntry(
                sidecar_id=item["sidecar_id"],
                display_name=item["display_name"],
                state=state,
                pid=item.get("pid"),
                error=error,
                user_message=_user_message_for_sidecar(state, error),
            )
        )

    all_ready = all(e.state == "running" for e in entries) if entries else True
    if all_ready:
        user_message = "All sidecars are running." if entries else "No sidecars registered."
    else:
        not_ready = [e for e in entries if e.state != "running"]
        if len(not_ready) == 1:
            user_message = not_ready[0].user_message
        else:
            user_message = f"{len(not_ready)} sidecars are not ready. Check Settings for details."

    return _SidecarDiagnostics(all_ready=all_ready, user_message=user_message, sidecars=entries)


class _SidecarEntry(BaseModel):
    sidecar_id: str
    display_name: str
    state: str
    pid: Optional[int] = None
    error: Optional[str] = None
    user_message: str


class _SidecarDiagnostics(BaseModel):
    """Aggregate health view of all registered sidecar processes.

    ``all_ready`` is True when every sidecar is in the ``running`` state (or
    when no sidecars are registered). ``user_message`` is a single sentence
    suitable for display in the non-technical health panel.
    """

    all_ready: bool
    user_message: str
    sidecars: list[_SidecarEntry]


class _DatabaseStatus(BaseModel):
    status: str
    path: Optional[str] = None
    migrations_applied: Optional[int] = None
    message: Optional[str] = None


class _PrivacyPosture(BaseModel):
    """Current privacy-relevant settings, safe to expose publicly."""

    telemetry_enabled: bool
    save_transcripts: bool
    save_raw_audio: bool
    crash_logging_enabled: bool


class _ActiveModelConfig(BaseModel):
    runtime_id: Optional[str] = None
    model_id: Optional[str] = None


class _BenchmarkSummary(BaseModel):
    model_id: str
    runtime_id: str
    tokens_per_sec: float
    context_length: Optional[int] = None
    warnings: list[str]
    output_tokens: int
    benchmarked_at: str


class HealthResponse(BaseModel):
    status: str
    version: str
    pid: int
    config_path: str
    database: _DatabaseStatus
    runtime: RuntimeHealth
    active_model: _ActiveModelConfig
    privacy: _PrivacyPosture
    stt: SttHealth
    tts: TtsHealth
    sidecar_diagnostics: _SidecarDiagnostics
    last_benchmark: Optional[_BenchmarkSummary] = None


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    config = request.app.state.service_config
    db = request.app.state.db
    app_settings = request.app.state.app_settings
    conn = db.connection()
    active_cfg = get_active_config(conn)

    bm_row = get_most_recent_benchmark(conn)
    last_benchmark: _BenchmarkSummary | None = None
    if bm_row is not None:
        last_benchmark = _BenchmarkSummary(
            model_id=bm_row["model_id"],
            runtime_id=bm_row["runtime_id"],
            tokens_per_sec=bm_row["tokens_per_sec"],
            context_length=bm_row.get("context_length"),
            warnings=bm_row.get("warnings", []),
            output_tokens=bm_row.get("output_tokens") or 0,
            benchmarked_at=bm_row["benchmarked_at"],
        )

    supervisor = getattr(request.app.state, "supervisor", None)

    return HealthResponse(
        status="ok",
        version=__version__,
        pid=os.getpid(),
        config_path=config.config_path,
        database=_DatabaseStatus(
            status="ok",
            path=db.path,
            migrations_applied=db.migrations_applied,
        ),
        runtime=await request.app.state.runtime.health(),
        active_model=_ActiveModelConfig(**active_cfg),
        privacy=_PrivacyPosture(
            telemetry_enabled=app_settings.telemetry_enabled,
            save_transcripts=app_settings.save_transcripts,
            save_raw_audio=app_settings.save_raw_audio,
            crash_logging_enabled=app_settings.crash_logging_enabled,
        ),
        stt=await request.app.state.stt_worker.health(),
        tts=await request.app.state.tts_worker.health(),
        sidecar_diagnostics=_build_sidecar_diagnostics(supervisor),
        last_benchmark=last_benchmark,
    )
