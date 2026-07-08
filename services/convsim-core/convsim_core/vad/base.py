# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from abc import ABC, abstractmethod

from convsim_core.vad.types import VadCalibrationResult, VadHealth, VadRequest


class VadWorker(ABC):
    """Provider-agnostic interface for a local voice activity detection worker.

    Concrete implementations (silero_vad, fake, …) are registered via
    @register_vad() and never imported directly by router code.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable machine-readable identifier (e.g. "silero_vad", "fake")."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    async def calibrate(self, request: VadRequest) -> VadCalibrationResult:
        """Analyze ambient noise audio and return recommended threshold settings.

        The caller sends a short (≈3 s) recording of ambient room noise.
        The result contains a recommended_threshold suitable for real-time
        silence detection in the browser via AnalyserNode RMS energy comparison.

        Raises VadUnavailableError when the runtime or model is missing.
        Raises VadError for other recoverable failures.
        """

    @abstractmethod
    async def health(self) -> VadHealth:
        """Return a point-in-time health snapshot for this worker."""
