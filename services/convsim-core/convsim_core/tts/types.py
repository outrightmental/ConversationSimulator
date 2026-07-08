# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pydantic import BaseModel

from convsim_core.runtime.types import RuntimeStatus


class TtsRequest(BaseModel):
    text: str
    voice_id: str
    speed: float = 1.0


class TtsResult(BaseModel):
    audio_path: str  # Absolute path to cached WAV under local cache dir
    audio_format: str = "wav"
    duration_ms: float | None = None
    voice_id: str


class TtsHealth(BaseModel):
    worker_id: str
    worker_name: str
    status: RuntimeStatus
    voice_count: int = 0
    message: str | None = None
    checked_at: str  # ISO 8601


class TtsError(Exception):
    """Typed, recoverable error from a TTS worker."""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class TtsUnavailableError(TtsError):
    """Raised when the TTS runtime is not installed or not reachable.

    Callers should treat this as a signal to fall back to text-only mode.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, recoverable=True)


class TtsVoiceValidationError(TtsError):
    """Raised when voice_id is not in the approved built-in voice list.

    Voice cloning, voice import, and real-person voice flows are rejected with
    this error. It is non-recoverable: the caller must choose an approved voice.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, recoverable=False)
