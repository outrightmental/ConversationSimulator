# SPDX-License-Identifier: Apache-2.0
"""Steam Cloud sync: non-sensitive settings file management.

Steam Cloud is configured in the Steamworks partner portal to watch exactly one
file at the data root: ``steam_cloud_settings.json``.  All other data
directories (db/, logs/, models/, packs/, exports/, crashes/, cache/) carry a
``.nosteamcloudpath`` marker (written by the app lifespan hook) that signals to
Steam — and any compatible sync tool — that they must not be uploaded.

Sync scope — what the cloud settings file may contain:
  - last_model_id   Last model ID selected by the user in the Model Manager.
                    Carries their preference to a new machine without re-setup.

Explicit exclusions — never synced, ever:
  - db/             Conversation transcripts, session history, prompts
  - logs/           Application and service logs
  - models/         LLM / STT / TTS model weight files (GBs of data)
  - packs/          User-imported scenario packs (may be private)
  - exports/        Exported session JSON files
  - crashes/        Crash report bundles
  - cache/          TTS audio cache, download cache
  - Raw audio       Microphone recordings saved when save_raw_audio is enabled

The file lives at ``{data_root}/steam_cloud_settings.json``, one level above
the subdirectory tree, so it is not covered by any ``.nosteamcloudpath``
marker.  All other data stays under ``.nosteamcloudpath``-marked subdirs and
is never touched by Steam Cloud.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

# Filename placed at the data root (one level above db/, logs/, models/, etc.).
# This is the only file Steam Cloud is configured to sync.
CLOUD_SETTINGS_FILENAME = "steam_cloud_settings.json"

# Debounce delay for scheduled writes.  Rapid changes (e.g. a user switching
# models several times in quick succession) collapse into a single disk write.
_DEBOUNCE_SECONDS = 2.0

_debounce_lock = threading.Lock()
_debounce_timer: Optional[threading.Timer] = None


class CloudSettings(BaseModel):
    """Non-sensitive, cross-device syncable user preferences.

    Every field must be safe to upload to Valve's Steam Cloud infrastructure.
    No personal content, transcript text, audio data, model weights, session
    history, private pack metadata, or any locally-identifiable information
    may appear here.
    """

    # ID of the last model selected by the user (e.g. "qwen3-4b-q4_k_m").
    # Pre-selects the same model on a second machine so the user does not need
    # to repeat model selection after installing on a new device.
    last_model_id: Optional[str] = None

    @field_validator("last_model_id")
    @classmethod
    def last_model_id_must_not_be_a_path(cls, v: Optional[str]) -> Optional[str]:
        """Reject filesystem paths — they may leak a username or home directory.

        Only opaque model identifiers (registry IDs, Ollama tags) may be synced.
        A user-supplied GGUF is stored locally as an absolute path such as
        ``/Users/alice/models/foo.gguf``; syncing that would upload
        locally-identifiable data to Steam Cloud, violating the local-first
        privacy promise.  Any value containing a path separator is refused so a
        buggy or malicious client cannot smuggle a path into the cloud file.
        Values written by such a client are also rejected on read, resetting the
        settings to defaults rather than propagating the leak.
        """
        if v is not None and ("/" in v or "\\" in v):
            raise ValueError("last_model_id must be an opaque model id, not a filesystem path")
        return v


def cloud_settings_path(data_root: Path) -> Path:
    """Return the absolute path for the Steam Cloud settings file."""
    return data_root / CLOUD_SETTINGS_FILENAME


def read_cloud_settings(data_root: Path) -> CloudSettings:
    """Read cloud settings from disk; return defaults if absent or corrupt."""
    path = cloud_settings_path(data_root)
    if not path.exists():
        return CloudSettings()
    try:
        return CloudSettings.model_validate_json(path.read_text("utf-8"))
    except Exception:
        return CloudSettings()


def write_cloud_settings(data_root: Path, settings: CloudSettings) -> None:
    """Write cloud settings to disk immediately, without debounce."""
    path = cloud_settings_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), "utf-8")


def schedule_cloud_settings_write(data_root: Path, settings: CloudSettings) -> None:
    """Schedule a debounced write of cloud settings.

    Subsequent calls within ``_DEBOUNCE_SECONDS`` cancel the pending write and
    restart the timer so only one disk write occurs per burst.  This keeps
    Steam Cloud's change-detection quiet during rapid user interaction.
    """
    global _debounce_timer
    with _debounce_lock:
        if _debounce_timer is not None:
            _debounce_timer.cancel()
        t = threading.Timer(
            _DEBOUNCE_SECONDS,
            write_cloud_settings,
            args=[data_root, settings],
        )
        t.daemon = True
        t.start()
        _debounce_timer = t
