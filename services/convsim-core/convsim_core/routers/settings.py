# SPDX-License-Identifier: Apache-2.0
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class AppSettings(BaseModel):
    """User-facing application settings: local paths and privacy defaults."""

    data_dir: str
    log_dir: str
    save_transcripts: bool = False
    tts_cache_enabled: bool = True


def _settings_file(data_dir: str) -> Path:
    return Path(data_dir) / "settings.json"


def load_settings_from_disk(data_dir: str, log_dir: str) -> AppSettings:
    path = _settings_file(data_dir)
    if path.exists():
        try:
            return AppSettings.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Could not parse settings file at %s; using defaults", path)
    return AppSettings(data_dir=data_dir, log_dir=log_dir)


def _persist(settings: AppSettings, data_dir: str) -> None:
    path = _settings_file(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")


@router.get("/api/settings", response_model=AppSettings)
async def get_settings(request: Request) -> AppSettings:
    return request.app.state.app_settings


@router.put("/api/settings", response_model=AppSettings)
async def put_settings(body: AppSettings, request: Request) -> AppSettings:
    config = request.app.state.service_config
    _persist(body, config.data_dir)
    request.app.state.app_settings = body
    return body
