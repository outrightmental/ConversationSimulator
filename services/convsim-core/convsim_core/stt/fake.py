# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timezone

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.stt.base import SttWorker
from convsim_core.stt.registry import register_stt
from convsim_core.stt.types import SttHealth, SttRequest, SttResult, SttSegment

_FAKE_TRANSCRIPT = "This is a fake transcription for testing and demo purposes."


@register_stt("fake")
class FakeSttWorker(SttWorker):
    """Deterministic fake STT worker for tests and text-only demo development.

    Always returns the same transcript so test assertions are stable. Reports
    READY status and never raises SttUnavailableError.
    """

    @property
    def id(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake STT (deterministic)"

    async def transcribe(self, request: SttRequest) -> SttResult:
        duration_ms = float(len(request.audio)) / 32.0  # crude estimate: 16 kHz 16-bit mono = 32 bytes/ms
        return SttResult(
            transcript=_FAKE_TRANSCRIPT,
            language=request.language or "en",
            confidence=0.99,
            duration_ms=duration_ms,
            processing_ms=0.0,
            segments=[
                SttSegment(
                    start_ms=0.0,
                    end_ms=duration_ms,
                    text=_FAKE_TRANSCRIPT,
                    confidence=0.99,
                )
            ],
        )

    async def health(self) -> SttHealth:
        return SttHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.READY,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
