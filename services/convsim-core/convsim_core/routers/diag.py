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
    latest_crash_bundle,
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
    preflight_data = getattr(request.app.state, "last_preflight", None)
    bundle_path = create_crash_bundle(
        config.log_dir, settings, bundle_dir=config.crash_bundles_dir,
        preflight_data=preflight_data,
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

    # Build a safe preflight snapshot from the in-process health checkers.
    # These probe the local sidecars over loopback only (e.g. llama-server on
    # 127.0.0.1); no request ever leaves the machine, keeping this path offline.
    runtime_health = await request.app.state.runtime.health()
    stt_health = await request.app.state.stt_worker.health()
    tts_health = await request.app.state.tts_worker.health()
    preflight: dict[str, Any] = {
        "runtime": runtime_health.model_dump() if hasattr(runtime_health, "model_dump") else str(runtime_health),
        "stt": stt_health.model_dump() if hasattr(stt_health, "model_dump") else str(stt_health),
        "tts": tts_health.model_dump() if hasattr(tts_health, "model_dump") else str(tts_health),
    }

    # Include the full self-test snapshot (7-check preflight pipeline with fix
    # actions) when one has been run, so the beta report carries the same
    # diagnostic verdict a maintainer sees in Support.  The snapshot is redacted
    # for home paths inside create_beta_report_bundle like the rest of preflight.
    self_test = getattr(request.app.state, "last_preflight", None)
    if self_test is not None:
        preflight["self_test"] = self_test

    db_conn = request.app.state.db.connection() if body.include_session_metadata else None

    # Embed the most recent crash bundle (#288) when one exists — it is written
    # to the same directory and already redacted, so it adds no new sensitive data.
    crash_bundle_path = latest_crash_bundle(config.crash_bundles_dir)

    bundle_path = create_beta_report_bundle(
        log_dir=config.log_dir,
        settings=settings,
        preflight=preflight,
        bundle_dir=config.crash_bundles_dir,
        db_conn=db_conn,
        include_session_metadata=body.include_session_metadata,
        crash_bundle_path=crash_bundle_path,
    )

    manifest = beta_report_manifest(
        body.include_session_metadata,
        include_crash_bundle=crash_bundle_path is not None,
    )
    logger.info("Beta report bundle created at %s", redact_path(str(bundle_path)))
    return _BetaReportResponse(
        bundle_path=str(bundle_path),
        manifest=manifest,
        notice=_BETA_REPORT_NOTICE,
    )
