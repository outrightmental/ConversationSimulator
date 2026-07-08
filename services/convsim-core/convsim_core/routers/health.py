# SPDX-License-Identifier: Apache-2.0
import os
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core import __version__
from convsim_core.runtime.types import RuntimeHealth
from convsim_core.services.model_manager_service import get_active_config, get_most_recent_benchmark
from convsim_core.stt.types import SttHealth
from convsim_core.tts.types import TtsHealth

router = APIRouter()


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
    )
