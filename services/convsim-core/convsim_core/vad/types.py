# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pydantic import BaseModel

from convsim_core.runtime.types import RuntimeStatus


class VadRequest(BaseModel):
    audio: bytes
    audio_format: str = "wav"  # webm, ogg, wav, etc.
    sample_rate: int = 16000


class VadCalibrationResult(BaseModel):
    recommended_threshold: float  # RMS energy threshold; compare against live energy
    noise_floor: float            # median RMS energy measured during calibration
    worker_id: str
    message: str | None = None   # set when falling back to energy-only calibration


class VadHealth(BaseModel):
    worker_id: str
    worker_name: str
    status: RuntimeStatus
    model_path: str | None = None
    message: str | None = None
    checked_at: str  # ISO 8601


class VadError(Exception):
    """Typed, recoverable error from a VAD worker."""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class VadUnavailableError(VadError):
    """Raised when the VAD runtime or model is not installed.

    Callers should treat this as a signal to fall back to push-to-talk only.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, recoverable=True)
