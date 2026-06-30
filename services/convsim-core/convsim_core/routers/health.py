# SPDX-License-Identifier: Apache-2.0
import os
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core import __version__

router = APIRouter()


class _DatabaseStatus(BaseModel):
    status: str
    path: Optional[str] = None
    migrations_applied: Optional[int] = None
    message: Optional[str] = None


class _RuntimeReadiness(BaseModel):
    llm_ready: bool = False
    stt_ready: bool = False
    tts_ready: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str
    pid: int
    config_path: str
    database: _DatabaseStatus
    runtime: _RuntimeReadiness


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    config = request.app.state.service_config
    db = request.app.state.db
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
        runtime=_RuntimeReadiness(),
    )
