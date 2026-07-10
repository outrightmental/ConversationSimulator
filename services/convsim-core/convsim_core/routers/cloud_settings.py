# SPDX-License-Identifier: Apache-2.0
"""REST endpoints for Steam Cloud non-sensitive settings sync."""
from pathlib import Path

from fastapi import APIRouter, Request

from convsim_core.steam_cloud import (
    CloudSettings,
    read_cloud_settings,
    schedule_cloud_settings_write,
)

router = APIRouter()


def _data_root(request: Request) -> Path:
    """Derive the data root from the service config's data_dir.

    ``data_dir`` defaults to ``{data_root}/data``, so the parent is the data
    root where ``steam_cloud_settings.json`` lives.
    """
    config = request.app.state.service_config
    return Path(config.data_dir).parent


@router.get("/api/cloud-settings", response_model=CloudSettings)
async def get_cloud_settings(request: Request) -> CloudSettings:
    """Return the current Steam Cloud settings (non-sensitive preferences only)."""
    return read_cloud_settings(_data_root(request))


@router.put("/api/cloud-settings", response_model=CloudSettings)
async def put_cloud_settings(body: CloudSettings, request: Request) -> CloudSettings:
    """Persist non-sensitive preferences to the Steam Cloud settings file.

    Writes are debounced so rapid updates (e.g. repeated model switching)
    collapse into a single file write.
    """
    schedule_cloud_settings_write(_data_root(request), body)
    return body
