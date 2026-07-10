# SPDX-License-Identifier: Apache-2.0
"""Privacy and data-management endpoints for the desktop UI."""
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


class _DataFolderResponse(BaseModel):
    path: str


class _FoldersResponse(BaseModel):
    data: str
    logs: str
    models: str
    packs: str
    exports: str


class _ClearResponse(BaseModel):
    deleted_sessions: int


@router.get("/data-folder", response_model=_DataFolderResponse)
async def get_data_folder(request: Request) -> _DataFolderResponse:
    """Return the absolute path to the local data folder."""
    config = request.app.state.service_config
    return _DataFolderResponse(path=str(Path(config.data_dir).resolve()))


@router.get("/folders", response_model=_FoldersResponse)
async def get_folders(request: Request) -> _FoldersResponse:
    """Return absolute paths for all local storage folders.

    Used by the Settings screen to show folder paths and open them in the OS
    file manager via the Tauri shell.
    """
    config = request.app.state.service_config
    return _FoldersResponse(
        data=str(Path(config.data_dir).resolve()),
        logs=str(Path(config.log_dir).resolve()),
        models=str(Path(config.models_dir).resolve()),
        packs=str(Path(config.packs_dir).resolve()),
        exports=str(Path(config.exports_dir).resolve()),
    )


@router.post("/clear", response_model=_ClearResponse)
async def clear_local_data(request: Request) -> _ClearResponse:
    """Delete all sessions and their events from the local database.

    This is the 'Clear all local data' action from the Settings screen.
    Installed models and packs are not removed.
    """
    db = request.app.state.db
    conn = db.connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM turn_sessions"
    ).fetchone()[0]
    conn.execute("DELETE FROM turn_session_events")
    conn.execute("DELETE FROM turn_sessions")
    conn.commit()
    return _ClearResponse(deleted_sessions=count)
