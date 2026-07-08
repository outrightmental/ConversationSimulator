# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pydantic import BaseModel

from convsim_core.runtime.types import RuntimeStatus


class SttRequest(BaseModel):
    audio: bytes
    audio_format: str = "wav"  # webm, ogg, wav, mp3, etc.
    language: str | None = None  # BCP-47 / whisper lang code; None = auto-detect


class SttSegment(BaseModel):
    start_ms: float
    end_ms: float
    text: str
    confidence: float | None = None


class SttResult(BaseModel):
    transcript: str
    language: str | None = None
    confidence: float | None = None  # average over segments when available
    duration_ms: float | None = None  # audio duration
    processing_ms: float | None = None  # wall-clock transcription time
    segments: list[SttSegment] | None = None


class SttHealth(BaseModel):
    worker_id: str
    worker_name: str
    status: RuntimeStatus
    model_path: str | None = None
    message: str | None = None
    checked_at: str  # ISO 8601


class SttError(Exception):
    """Typed, recoverable error from an STT worker."""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class SttUnavailableError(SttError):
    """Raised when the STT runtime or model is not installed.

    Callers should treat this as a signal to fall back to text-only mode.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, recoverable=True)
