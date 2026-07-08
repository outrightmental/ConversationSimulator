# SPDX-License-Identifier: Apache-2.0
"""VAD (voice activity detection) worker abstraction and built-in implementations.

Import this package to ensure all built-in workers are registered before
calling build_vad_worker().
"""

from convsim_core.vad.base import VadWorker
from convsim_core.vad.registry import build_vad_worker, list_vad_worker_ids, register_vad
from convsim_core.vad.types import (
    VadCalibrationResult,
    VadError,
    VadHealth,
    VadRequest,
    VadUnavailableError,
)

# Import built-in workers to trigger their @register_vad() decorators.
import convsim_core.vad.fake  # noqa: F401, E402
import convsim_core.vad.silero  # noqa: F401, E402

__all__ = [
    "VadWorker",
    "VadError",
    "VadHealth",
    "VadRequest",
    "VadCalibrationResult",
    "VadUnavailableError",
    "build_vad_worker",
    "list_vad_worker_ids",
    "register_vad",
]
