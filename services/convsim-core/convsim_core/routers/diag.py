# SPDX-License-Identifier: Apache-2.0
"""Diagnostics endpoints for local log-folder access and crash-bundle creation."""
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.beta_report import (
    beta_report_manifest,
    create_beta_report_bundle,
)
from convsim_core.crash_report import create_crash_bundle
from convsim_core.redaction import redact_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diag", tags=["diagnostics"])

_BUNDLE_NOTICE = (
    "Crash bundle created locally. "
    "It is never transmitted automatically. "
    "Review the contents and attach it to a GitHub issue manually."
)

_BETA_REPORT_NOTICE = (
    "Beta report bundle created locally. "
    "It is never transmitted automatically. "
    "Review the contents, then attach it to a GitHub issue manually."
)


class _LogsFolderResponse(BaseModel):
    logs_folder: str


class _CrashBundleResponse(BaseModel):
    bundle_path: str
    notice: str


class _BetaReportRequest(BaseModel):
    include_session_metadata: bool = False


class _BetaReportResponse(BaseModel):
    bundle_path: str
    manifest: list[str]
    notice: str


@router.get("/logs-folder", response_model=_LogsFolderResponse)
async def get_logs_folder(request: Request) -> _LogsFolderResponse:
    """Return the absolute path of the local logs folder.

    Intended for UI/desktop integration (e.g. an 'Open Logs Folder' button).
    """
    config = request.app.state.service_config
    return _LogsFolderResponse(logs_folder=str(Path(config.log_dir).resolve()))


@router.post("/crash-bundle", response_model=_CrashBundleResponse)
async def post_crash_bundle(request: Request) -> _CrashBundleResponse:
    """Create a local crash bundle that the user can manually attach to an issue.

    The bundle contains version info, sanitised settings, recent error logs, and
    system info.  No conversation transcripts, prompts, or audio are included.
    The bundle is never transmitted — the user must share it manually.
    """
    config = request.app.state.service_config
    settings = request.app.state.app_settings
    bundle_path = create_crash_bundle(
        config.log_dir, settings, bundle_dir=config.crash_bundles_dir
    )
    logger.info("Crash bundle created at %s", redact_path(str(bundle_path)))
    return _CrashBundleResponse(bundle_path=str(bundle_path), notice=_BUNDLE_NOTICE)


@router.post("/beta-report", response_model=_BetaReportResponse)
async def post_beta_report(
    body: _BetaReportRequest, request: Request
) -> _BetaReportResponse:
    """Create a local beta-report bundle for attaching to a GitHub issue.

    Extends the crash bundle with a preflight health snapshot and an optional
    last-session metadata entry (never includes transcript content or player
    input).  The bundle is written locally and never transmitted automatically.
    """
    config = request.app.state.service_config
    settings = request.app.state.app_settings

    # Build a safe preflight snapshot from the health state already in memory.
    # We read from app.state directly (no HTTP call) to keep this path offline.
    runtime_health = await request.app.state.runtime.health()
    stt_health = await request.app.state.stt_worker.health()
    tts_health = await request.app.state.tts_worker.health()
    preflight: dict[str, Any] = {
        "runtime": runtime_health.model_dump() if hasattr(runtime_health, "model_dump") else str(runtime_health),
        "stt": stt_health.model_dump() if hasattr(stt_health, "model_dump") else str(stt_health),
        "tts": tts_health.model_dump() if hasattr(tts_health, "model_dump") else str(tts_health),
    }

    db_conn = request.app.state.db.connection() if body.include_session_metadata else None

    bundle_path = create_beta_report_bundle(
        log_dir=config.log_dir,
        settings=settings,
        preflight=preflight,
        bundle_dir=config.crash_bundles_dir,
        db_conn=db_conn,
        include_session_metadata=body.include_session_metadata,
    )

    manifest = beta_report_manifest(body.include_session_metadata)
    logger.info("Beta report bundle created at %s", redact_path(str(bundle_path)))
    return _BetaReportResponse(
        bundle_path=str(bundle_path),
        manifest=manifest,
        notice=_BETA_REPORT_NOTICE,
    )
