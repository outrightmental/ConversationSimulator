# SPDX-License-Identifier: Apache-2.0
"""Diagnostics endpoints for local log-folder access and crash-bundle creation."""
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.crash_report import create_crash_bundle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diag", tags=["diagnostics"])

_BUNDLE_NOTICE = (
    "Crash bundle created locally. "
    "It is never transmitted automatically. "
    "Review the contents and attach it to a GitHub issue manually."
)


class _LogsFolderResponse(BaseModel):
    logs_folder: str


class _CrashBundleResponse(BaseModel):
    bundle_path: str
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
    bundle_path = create_crash_bundle(config.log_dir, settings)
    logger.info("Crash bundle created at %s", bundle_path)
    return _CrashBundleResponse(bundle_path=str(bundle_path), notice=_BUNDLE_NOTICE)
