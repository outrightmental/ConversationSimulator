# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class AppSettings(BaseModel):
    """User-facing application settings: local paths and privacy defaults."""

    data_dir: str
    log_dir: str
    save_transcripts: bool = False
    tts_cache_enabled: bool = True
