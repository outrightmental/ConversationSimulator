# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from abc import ABC, abstractmethod

from convsim_core.stt.types import SttHealth, SttRequest, SttResult


class SttWorker(ABC):
    """Provider-agnostic interface for a local speech-to-text worker.

    Concrete implementations (whisper_cpp, fake, …) are registered via
    @register_stt() and never imported directly by router code.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable machine-readable identifier (e.g. "whisper_cpp", "fake")."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    async def transcribe(self, request: SttRequest) -> SttResult:
        """Transcribe audio bytes and return a structured result.

        Raises SttUnavailableError when the runtime or model is missing.
        Raises SttError for other recoverable failures.
        """

    @abstractmethod
    async def health(self) -> SttHealth:
        """Return a point-in-time health snapshot for this worker."""
