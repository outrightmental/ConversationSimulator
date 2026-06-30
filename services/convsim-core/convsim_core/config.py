# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATA_DIR = str(Path.home() / ".convsim" / "data")
_DEFAULT_LOG_DIR = str(Path.home() / ".convsim" / "logs")


class ServiceConfig(BaseSettings):
    """Runtime configuration for the convsim-core process.

    All values can be overridden via CONVSIM_* environment variables or a .env file.
    Binding to 0.0.0.0 is rejected unless lan_access_enabled is explicitly set.
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
    lan_access_enabled: bool = False

    @model_validator(mode="after")
    def _reject_wildcard_bind(self) -> "ServiceConfig":
        if self.host == "0.0.0.0" and not self.lan_access_enabled:
            raise ValueError(
                "Binding to 0.0.0.0 is not allowed in default mode. "
                "Set CONVSIM_LAN_ACCESS_ENABLED=true to enable LAN access "
                "and specify an explicit LAN IP address."
            )
        return self

    @property
    def config_path(self) -> str:
        dotenv = Path(".env").resolve()
        return str(dotenv) if dotenv.exists() else "<environment variables>"
