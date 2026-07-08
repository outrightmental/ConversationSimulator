# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timezone

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.vad.base import VadWorker
from convsim_core.vad.registry import register_vad
from convsim_core.vad.types import VadCalibrationResult, VadHealth, VadRequest


@register_vad("fake")
class FakeVadWorker(VadWorker):
    """Deterministic fake VAD worker for tests and text-only demo development.

    Always returns a fixed calibration result so test assertions are stable.
    Reports READY status and never raises VadUnavailableError.
    """

    @property
    def id(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake VAD (deterministic)"

    async def calibrate(self, request: VadRequest) -> VadCalibrationResult:
        return VadCalibrationResult(
            recommended_threshold=0.05,
            noise_floor=0.01,
            worker_id=self.id,
            message=None,
        )

    async def health(self) -> VadHealth:
        return VadHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.READY,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
