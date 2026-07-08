# SPDX-License-Identifier: Apache-2.0
"""TTS (text-to-speech) worker abstraction and built-in implementations.

Import this package to ensure all built-in workers are registered before
calling build_tts_worker().
"""

from convsim_core.tts.base import TtsWorker
from convsim_core.tts.registry import build_tts_worker, list_tts_worker_ids, register_tts
from convsim_core.tts.types import (
    TtsError,
    TtsHealth,
    TtsRequest,
    TtsResult,
    TtsUnavailableError,
    TtsVoiceValidationError,
)
from convsim_core.tts.voices import APPROVED_VOICES, VoiceInfo, validate_voice_id

# Import built-in workers to trigger their @register_tts() decorators.
import convsim_core.tts.fake  # noqa: F401, E402
import convsim_core.tts.kokoro  # noqa: F401, E402

__all__ = [
    "TtsWorker",
    "TtsError",
    "TtsHealth",
    "TtsRequest",
    "TtsResult",
    "TtsUnavailableError",
    "TtsVoiceValidationError",
    "APPROVED_VOICES",
    "VoiceInfo",
    "validate_voice_id",
    "build_tts_worker",
    "list_tts_worker_ids",
    "register_tts",
]
