# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Request

from convsim_core.models import AppSettings
from convsim_core.storage.repositories.settings_repo import save_settings

router = APIRouter()


@router.get("/api/settings", response_model=AppSettings)
async def get_settings(request: Request) -> AppSettings:
    return request.app.state.app_settings


@router.put("/api/settings", response_model=AppSettings)
async def put_settings(body: AppSettings, request: Request) -> AppSettings:
    db = request.app.state.db
    save_settings(db.connection(), body)
    request.app.state.app_settings = body
    return body
