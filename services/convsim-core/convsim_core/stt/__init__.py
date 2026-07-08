# SPDX-License-Identifier: Apache-2.0
"""STT (speech-to-text) worker abstraction and built-in implementations.

Import this package to ensure all built-in workers are registered before
calling build_stt_worker().
"""

from convsim_core.stt.base import SttWorker
from convsim_core.stt.registry import build_stt_worker, list_stt_worker_ids, register_stt
from convsim_core.stt.types import (
    SttError,
    SttHealth,
    SttRequest,
    SttResult,
    SttSegment,
    SttUnavailableError,
)

# Import built-in workers to trigger their @register_stt() decorators.
import convsim_core.stt.fake  # noqa: F401, E402
import convsim_core.stt.whisper_cpp  # noqa: F401, E402

__all__ = [
    "SttWorker",
    "SttError",
    "SttHealth",
    "SttRequest",
    "SttResult",
    "SttSegment",
    "SttUnavailableError",
    "build_stt_worker",
    "list_stt_worker_ids",
    "register_stt",
]
