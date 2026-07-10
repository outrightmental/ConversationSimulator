# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATA_DIR = str(Path.home() / ".convsim" / "data")
_DEFAULT_LOG_DIR = str(Path.home() / ".convsim" / "logs")
_DEFAULT_DB_DIR = str(Path.home() / ".convsim" / "db")
_DEFAULT_PACKS_DIR = str(Path.home() / ".convsim" / "packs")
# Read-only bundled official packs.
#
# In a PyInstaller packaged build (sys._MEIPASS is set), the packs are
# embedded in the executable and extracted to sys._MEIPASS/packs/official/
# at runtime.  In a developer checkout the packs live at the repo root.
_is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
if _is_frozen:
    _DEFAULT_OFFICIAL_PACKS_DIR = str(Path(sys._MEIPASS) / "packs" / "official")  # type: ignore[attr-defined]
else:
    # Resolve relative to this file: config.py → convsim_core → convsim-core →
    # services → repo root.  The default points at the repo's packs/official so
    # `convsim-core` works from any process CWD in a developer checkout.
    _DEFAULT_OFFICIAL_PACKS_DIR = str(Path(__file__).resolve().parents[3] / "packs" / "official")


class ServiceConfig(BaseSettings):
    """Runtime configuration for the convsim-core process.

    All values can be overridden via CONVSIM_* environment variables or a .env file.
    Binding to wildcard addresses (0.0.0.0 or ::) is rejected unless lan_access_enabled
    is explicitly set.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONVSIM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 7355
    data_dir: str = _DEFAULT_DATA_DIR
    log_dir: str = _DEFAULT_LOG_DIR
    db_dir: str = _DEFAULT_DB_DIR
    packs_dir: str = _DEFAULT_PACKS_DIR
    # Read-only official packs served (browse-only) by the Creator Workbench.
    # Defaults to the repo's bundled packs/official directory.
    official_packs_dir: str = _DEFAULT_OFFICIAL_PACKS_DIR
    # Set CONVSIM_LOCAL_DEV_PACKS_DIR to a directory that contains in-progress
    # pack folders.  The /api/packs/import/folder endpoint only accepts source
    # paths that fall within packs_dir or this directory; leaving it unset
    # restricts folder import to paths already inside packs_dir.  The Creator
    # Workbench also uses it as the editable local-dev pack root, falling back
    # to <packs_dir>/local-dev when unset.
    local_dev_packs_dir: Optional[str] = None
    models_dir: str = str(Path.home() / ".convsim" / "models" / "llm")
    lan_access_enabled: bool = False
    runtime_id: str = "fake"
    stt_worker_id: str = "whisper_cpp"
    vad_worker_id: str = "silero_vad"
    tts_worker_id: str = "kokoro"
    ollama_base_url: str = "http://127.0.0.1:11434"
    # Set CONVSIM_DEV_DEBUG=true to enable DEBUG-level logging.
    # Even in debug mode callers must use convsim_core.redaction helpers
    # before logging any value derived from conversation content.
    dev_debug: bool = False

    @model_validator(mode="after")
    def _reject_wildcard_bind(self) -> "ServiceConfig":
        if self.host in ("0.0.0.0", "::") and not self.lan_access_enabled:
            raise ValueError(
                f"Binding to {self.host} is not allowed in default mode. "
                "Set CONVSIM_LAN_ACCESS_ENABLED=true to enable LAN access "
                "and specify an explicit LAN IP address."
            )
        return self

    @property
    def config_path(self) -> str:
        dotenv = Path(".env").resolve()
        return str(dotenv) if dotenv.exists() else "<environment variables>"
