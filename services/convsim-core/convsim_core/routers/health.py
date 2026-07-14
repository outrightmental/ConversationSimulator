# SPDX-License-Identifier: Apache-2.0
import os
import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core import __version__
from convsim_core.runtime.types import RuntimeHealth, RuntimeStatus
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


class _RuntimeReadiness(BaseModel):
    """Matches ``RuntimeReadiness`` in packages/shared/src/types/runtime.ts.

    This is the contract the web UI's Home screen, scenario setup, and voice
    settings read from ``HealthResponse.runtime``. It must stay a superset-
    compatible shape with the shared TypeScript type.
    """

    llm_ready: bool
    llm_model_name: Optional[str] = None
    stt_ready: bool
    tts_ready: bool
    tts_voice_name: Optional[str] = None
    network_required: bool
    last_error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    pid: int
    config_path: str
    database: _DatabaseStatus
    # User-facing readiness summary consumed by the web UI (shared contract).
    runtime: _RuntimeReadiness
    # Detailed diagnostic health of the configured chat runtime.
    llm_runtime: RuntimeHealth
    active_model: _ActiveModelConfig
    privacy: _PrivacyPosture
    stt: SttHealth
    tts: TtsHealth
    sidecar_diagnostics: _SidecarDiagnostics
    last_benchmark: Optional[_BenchmarkSummary] = None


def _find_installed_model(
    conn: sqlite3.Connection, model_id: str
) -> Optional[dict[str, Any]]:
    """Look up an installed model by file path or registry id.

    Only rows in a usable terminal state count as installed.
    """
    row = conn.execute(
        """
        SELECT id, registry_id, filename, file_path, install_status, display_name
        FROM installed_models
        WHERE (file_path = ? OR registry_id = ?)
          AND install_status IN ('complete', 'ready')
        ORDER BY id DESC
        LIMIT 1
        """,
        (model_id, model_id),
    ).fetchone()
    return dict(row) if row is not None else None


def _build_readiness(
    conn: sqlite3.Connection,
    active_cfg: dict[str, Optional[str]],
    runtime_health: RuntimeHealth,
    stt_health: SttHealth,
    tts_health: TtsHealth,
) -> _RuntimeReadiness:
    """Derive the user-facing readiness summary.

    The LLM counts as installed/ready when the user has an active model
    selection backed by a usable install record (an existing GGUF file, or an
    Ollama tag validated at selection time). For a selected model the live
    sidecar process state is deliberately NOT required: it is started on
    demand, and "installed but not currently loaded" must still read as
    installed on the Home screen.

    When no local model file is involved — the fake/scripted runtimes or an
    external server — we fall back to the live runtime health, so a llama.cpp
    runtime selected without a model loaded does not falsely read as ready.

    ``last_error`` reports only a *blocking* problem: why the LLM (which gates
    play) is unavailable. Optional voice (STT/TTS) being uninstalled is
    surfaced through ``stt_ready``/``tts_ready`` and must not populate
    ``last_error``, or the Home screen shows an error card for a text-ready app.
    """
    runtime_id = active_cfg.get("runtime_id")
    model_id = active_cfg.get("model_id")

    llm_ready = False
    llm_model_name: Optional[str] = None
    errors: list[str] = []

    if model_id:
        installed = _find_installed_model(conn, model_id)
        if installed is not None and os.path.isfile(installed["file_path"]):
            llm_ready = True
            llm_model_name = installed.get("display_name") or installed.get("filename")
        elif os.path.isfile(model_id):
            # A user-supplied GGUF path that exists but has no DB row.
            llm_ready = True
            llm_model_name = os.path.basename(model_id)
        elif runtime_id == "ollama":
            # Ollama model tags are not files; availability was validated at
            # selection time by /api/models/use.
            llm_ready = True
            llm_model_name = model_id
        else:
            errors.append(
                f"Selected model file not found: {model_id}. "
                "Re-select a model in the model manager."
            )
            llm_model_name = os.path.basename(model_id) or model_id
    elif runtime_health.status in (RuntimeStatus.READY, RuntimeStatus.DEGRADED):
        # No local model file is involved (fake/scripted runtime, or an
        # external server), or nothing was explicitly selected and the default
        # runtime is usable. With nothing to stat, the live runtime health is
        # the only real signal — a llama.cpp runtime selected without a model
        # loaded is not ready here and correctly reports so.
        llm_ready = True
        llm_model_name = (
            runtime_health.model_id or runtime_health.runtime_name or runtime_id
        )
    elif runtime_health.message:
        errors.append(runtime_health.message)

    # Optional voice: readiness is conveyed via the booleans below. Their
    # "not installed" messages must NOT feed last_error — that field reports
    # only blocking (LLM) problems, so a text-ready app doesn't surface a
    # voice-unavailable message as a blocking error card on Home.
    stt_ready = stt_health.status in (RuntimeStatus.READY, RuntimeStatus.DEGRADED)
    tts_ready = tts_health.status in (RuntimeStatus.READY, RuntimeStatus.DEGRADED)

    return _RuntimeReadiness(
        llm_ready=llm_ready,
        llm_model_name=llm_model_name,
        stt_ready=stt_ready,
        tts_ready=tts_ready,
        tts_voice_name=None,
        # All supported runtimes (llama.cpp sidecar, Ollama, fake, scripted)
        # run locally; nothing requires network to play.
        network_required=False,
        last_error=errors[0] if errors else None,
    )


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

    runtime_health = await request.app.state.runtime.health()
    stt_health = await request.app.state.stt_worker.health()
    tts_health = await request.app.state.tts_worker.health()

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
        runtime=_build_readiness(conn, active_cfg, runtime_health, stt_health, tts_health),
        llm_runtime=runtime_health,
        active_model=_ActiveModelConfig(**active_cfg),
        privacy=_PrivacyPosture(
            telemetry_enabled=app_settings.telemetry_enabled,
            save_transcripts=app_settings.save_transcripts,
            save_raw_audio=app_settings.save_raw_audio,
            crash_logging_enabled=app_settings.crash_logging_enabled,
        ),
        stt=stt_health,
        tts=tts_health,
        sidecar_diagnostics=_build_sidecar_diagnostics(supervisor),
        last_benchmark=last_benchmark,
    )
