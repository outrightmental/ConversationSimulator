# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.tts.base import TtsWorker
from convsim_core.tts.registry import register_tts
from convsim_core.tts.types import TtsHealth, TtsRequest, TtsResult
from convsim_core.tts.voices import APPROVED_VOICES, validate_voice_id

# Minimal silent WAV: RIFF header with 0 PCM samples (22050 Hz, 16-bit, mono).
_SILENT_WAV: bytes = (
    b"RIFF"
    + (36).to_bytes(4, "little")     # chunk size = 36 + 0 data bytes
    + b"WAVE"
    + b"fmt "
    + (16).to_bytes(4, "little")     # PCM subchunk size
    + (1).to_bytes(2, "little")      # audio format = PCM
    + (1).to_bytes(2, "little")      # channels = 1 (mono)
    + (22050).to_bytes(4, "little")  # sample rate
    + (44100).to_bytes(4, "little")  # byte rate = rate * channels * bitsPerSample/8
    + (2).to_bytes(2, "little")      # block align
    + (16).to_bytes(2, "little")     # bits per sample
    + b"data"
    + (0).to_bytes(4, "little")      # 0 PCM samples
)


@register_tts("fake")
class FakeTtsWorker(TtsWorker):
    """Deterministic fake TTS worker for tests and text-only demo development.

    Always returns a silent WAV file so test assertions are stable. Reports
    READY status and never raises TtsUnavailableError.
    """

    @property
    def id(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake TTS (deterministic)"

    async def synthesize(self, request: TtsRequest) -> TtsResult:
        validate_voice_id(request.voice_id)
        fd, audio_path = tempfile.mkstemp(suffix=".wav", prefix="convsim_tts_fake_")
        try:
            os.write(fd, _SILENT_WAV)
        finally:
            os.close(fd)
        return TtsResult(
            audio_path=audio_path,
            audio_format="wav",
            duration_ms=0.0,
            voice_id=request.voice_id,
        )

    async def clear_cache(self) -> int:
        return 0  # Fake worker writes to temp files; nothing to clear.

    async def health(self) -> TtsHealth:
        return TtsHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.READY,
            voice_count=len(APPROVED_VOICES),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
