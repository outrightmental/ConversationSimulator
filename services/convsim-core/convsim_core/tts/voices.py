# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pydantic import BaseModel


class VoiceInfo(BaseModel):
    voice_id: str
    display_name: str
    engine: str
    gender: str
    locale: str


# Fixed set of approved built-in voices. All entries are fictional synthetic
# voices shipped with the Kokoro TTS engine. No user-uploaded or cloned voices
# are permitted in any code path; validate_voice_id() enforces this boundary.
APPROVED_VOICES: dict[str, VoiceInfo] = {
    "af_heart": VoiceInfo(
        voice_id="af_heart", display_name="Heart (US female)", engine="kokoro", gender="female", locale="en-US"
    ),
    "af_bella": VoiceInfo(
        voice_id="af_bella", display_name="Bella (US female)", engine="kokoro", gender="female", locale="en-US"
    ),
    "af_nicole": VoiceInfo(
        voice_id="af_nicole", display_name="Nicole (US female)", engine="kokoro", gender="female", locale="en-US"
    ),
    "af_sky": VoiceInfo(
        voice_id="af_sky", display_name="Sky (US female)", engine="kokoro", gender="female", locale="en-US"
    ),
    "am_adam": VoiceInfo(
        voice_id="am_adam", display_name="Adam (US male)", engine="kokoro", gender="male", locale="en-US"
    ),
    "am_michael": VoiceInfo(
        voice_id="am_michael", display_name="Michael (US male)", engine="kokoro", gender="male", locale="en-US"
    ),
    "bf_emma": VoiceInfo(
        voice_id="bf_emma", display_name="Emma (UK female)", engine="kokoro", gender="female", locale="en-GB"
    ),
    "bf_isabella": VoiceInfo(
        voice_id="bf_isabella", display_name="Isabella (UK female)", engine="kokoro", gender="female", locale="en-GB"
    ),
    "bm_george": VoiceInfo(
        voice_id="bm_george", display_name="George (UK male)", engine="kokoro", gender="male", locale="en-GB"
    ),
    "bm_lewis": VoiceInfo(
        voice_id="bm_lewis", display_name="Lewis (UK male)", engine="kokoro", gender="male", locale="en-GB"
    ),
}


def validate_voice_id(voice_id: str) -> VoiceInfo:
    """Return VoiceInfo for an approved built-in voice id.

    Raises TtsVoiceValidationError for any id that is not in APPROVED_VOICES,
    including cloned voices, user-imported samples, and real-person names.
    """
    from convsim_core.tts.types import TtsVoiceValidationError  # avoid circular import at module level

    if voice_id not in APPROVED_VOICES:
        approved = sorted(APPROVED_VOICES)
        raise TtsVoiceValidationError(
            f"Voice {voice_id!r} is not in the approved built-in voice list. "
            f"Approved voices: {approved}. "
            "Voice cloning, voice import, and real-person voice flows are not supported."
        )
    return APPROVED_VOICES[voice_id]
