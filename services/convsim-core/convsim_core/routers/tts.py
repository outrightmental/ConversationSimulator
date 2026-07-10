# SPDX-License-Identifier: Apache-2.0
import logging
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from convsim_core.tts.types import TtsError, TtsRequest, TtsUnavailableError, TtsVoiceValidationError
from convsim_core.tts.voices import validate_voice_id

_SAFE_FILENAME_RE = re.compile(r'^[a-f0-9]{1,64}\.wav$')

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


@router.get("/api/tts/cache/size")
async def get_tts_cache_size(request: Request) -> dict:
    """Return the number of cached TTS audio files and their total size in bytes.

    Called by the privacy settings panel to display the current cache footprint
    before or after a clear action.
    """
    tts_worker = request.app.state.tts_worker
    return await tts_worker.cache_size()


def _resolve_tts_cache_dir(tts_worker: object) -> Path:
    """Return the cache directory used by *tts_worker*.

    KokoroTtsWorker stores the resolved path as ``_cache_dir``.  For other
    worker types the default location is used so the endpoint stays functional.
    """
    cache_dir = getattr(tts_worker, "_cache_dir", None)
    if cache_dir is not None:
        return Path(cache_dir)
    return Path.home() / ".convsim" / "tts_cache"


@router.get("/api/tts/audio/{filename}")
async def get_tts_audio(filename: str, request: Request) -> FileResponse:
    """Serve a cached TTS WAV file so the browser can play it via URL.

    Only hex-named .wav files inside the configured TTS cache directory are
    served.  Any other filename (path traversal, non-hex, non-wav) returns 404.
    """
    if not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="Not found")

    tts_worker = request.app.state.tts_worker
    cache_dir = _resolve_tts_cache_dir(tts_worker)
    audio_path = cache_dir / filename

    # Resolve symlinks and confirm the file stays inside the cache directory.
    try:
        resolved = audio_path.resolve()
        resolved_cache = cache_dir.resolve()
        if not str(resolved).startswith(str(resolved_cache)):
            raise HTTPException(status_code=404, detail="Not found")
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(str(resolved), media_type="audio/wav")


_BACKCHANNEL_PHRASES: list[str] = ["mm-hm", "right", "I see", "go on", "uh-huh"]

_DEFAULT_BACKCHANNEL_VOICE = "af_heart"


@router.get("/api/tts/backchannels")
async def get_backchannels(request: Request) -> dict:
    """Return pre-synthesized backchannel acknowledgment audio paths.

    Synthesizes a small set of short acknowledgment phrases ("mm-hm", "right",
    etc.) using the default voice and caches them via the TTS cache.  The
    client can play one of these at random while the player is speaking to
    make the NPC feel present during long player utterances.

    Returns a list of objects with ``text`` and ``cache_path`` fields.
    Only phrases that synthesized without error are included.  Returns an
    empty list when TTS is unavailable.
    """
    from convsim_core.tts.types import TtsRequest, TtsUnavailableError, TtsError

    tts_worker = request.app.state.tts_worker
    results = []
    for phrase in _BACKCHANNEL_PHRASES:
        tts_request = TtsRequest(
            text=phrase,
            voice_id=_DEFAULT_BACKCHANNEL_VOICE,
            speed=1.0,
        )
        try:
            result = await tts_worker.synthesize(tts_request)
            if result.audio_path:
                results.append({"text": phrase, "cache_path": result.audio_path})
        except (TtsUnavailableError, TtsError):
            break  # TTS unavailable — return what we have (may be empty)
    return {"backchannels": results}


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
