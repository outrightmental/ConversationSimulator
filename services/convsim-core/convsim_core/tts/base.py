# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from abc import ABC, abstractmethod

from convsim_core.tts.types import TtsHealth, TtsRequest, TtsResult


class TtsWorker(ABC):
    """Provider-agnostic interface for a local text-to-speech worker.

    Concrete implementations (kokoro, fake, …) are registered via
    @register_tts() and never imported directly by router code.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable machine-readable identifier (e.g. "kokoro", "fake")."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    async def synthesize(self, request: TtsRequest) -> TtsResult:
        """Synthesize text to audio and return a reference to the cached WAV.

        Raises TtsUnavailableError when the TTS backend is not installed.
        Raises TtsVoiceValidationError if voice_id is not in the approved list.
        Raises TtsError for other recoverable failures.
        """

    @abstractmethod
    async def health(self) -> TtsHealth:
        """Return a point-in-time health snapshot for this worker."""

    @abstractmethod
    async def clear_cache(self) -> int:
        """Delete all locally cached audio files for this worker.

        Called by the privacy 'clear cache' action.  Returns the number of
        files deleted.  Must not raise — callers do not expect failures here.
        """

    @abstractmethod
    async def cache_size(self) -> dict:
        """Return cache size information without deleting any files.

        Returns a dict with ``files`` (int) and ``size_bytes`` (int).
        Must not raise — callers do not expect failures here.
        """
