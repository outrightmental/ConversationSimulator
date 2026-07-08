# SPDX-License-Identifier: Apache-2.0
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from convsim_core.tts.types import TtsError, TtsRequest, TtsUnavailableError, TtsVoiceValidationError
from convsim_core.tts.voices import validate_voice_id

logger = logging.getLogger(__name__)

router = APIRouter()


class TtsSynthesizeRequest(BaseModel):
    text: str
    voice_id: str
    speed: float = 1.0


class TtsSynthesizeResponse(BaseModel):
    status: Literal["ok", "unavailable", "error"]
    audio_path: str | None = None
    audio_format: str | None = None
    duration_ms: float | None = None
    voice_id: str | None = None
    message: str | None = None


@router.post("/api/tts/synthesize", response_model=TtsSynthesizeResponse)
async def synthesize(request: Request, body: TtsSynthesizeRequest) -> TtsSynthesizeResponse:
    """Synthesize text using a built-in voice and return the cached audio path.

    Audio is synthesized locally using the configured TTS backend and cached
    under the local TTS cache directory. The response includes the absolute path
    to the cached WAV file for localhost playback.

    Returns status='unavailable' when the TTS backend is not installed rather
    than an HTTP error, enabling graceful text-only fallback. Returns 422 when
    the requested voice_id is not in the approved built-in voice list — voice
    cloning and voice import are not supported.
    """
    # Validate voice before reaching the backend — ensures no cloned or unknown
    # voice id ever reaches a synthesis code path.
    try:
        validate_voice_id(body.voice_id)
    except TtsVoiceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    tts_worker = request.app.state.tts_worker
    tts_request = TtsRequest(text=body.text, voice_id=body.voice_id, speed=body.speed)

    try:
        result = await tts_worker.synthesize(tts_request)
        return TtsSynthesizeResponse(
            status="ok",
            audio_path=result.audio_path,
            audio_format=result.audio_format,
            duration_ms=result.duration_ms,
            voice_id=result.voice_id,
        )
    except TtsVoiceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TtsUnavailableError as exc:
        logger.info("TTS worker unavailable: %s", exc)
        return TtsSynthesizeResponse(status="unavailable", message=str(exc))
    except TtsError as exc:
        logger.warning("TTS worker error during synthesis: %s", exc, exc_info=True)
        return TtsSynthesizeResponse(status="error", message=str(exc))


@router.post("/api/tts/cache/clear")
async def clear_tts_cache(request: Request) -> dict:
    """Delete all locally cached TTS audio files.

    Called by the privacy settings 'clear cache' action.  Removes every cached
    WAV file from the local TTS cache directory so future synthesis requests
    re-synthesize from scratch.  Returns the number of files deleted.
    """
    tts_worker = request.app.state.tts_worker
    deleted = await tts_worker.clear_cache()
    return {"deleted_files": deleted}


@router.get("/api/tts/voices")
async def list_voices() -> dict:
    """Return the approved built-in voice list.

    Only voices in this list may be used for synthesis. Voice cloning, voice
    import, and real-person voice flows have no endpoint in this API.
    """
    from convsim_core.tts.voices import APPROVED_VOICES

    return {
        "voices": [v.model_dump() for v in APPROVED_VOICES.values()],
    }
