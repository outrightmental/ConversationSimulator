# SPDX-License-Identifier: Apache-2.0
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from convsim_core.stt.types import SttError, SttRequest, SttUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB hard cap

_MIME_TO_EXT: dict[str, str] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp4": "mp4",
    "application/octet-stream": "bin",
}

# Derived from _MIME_TO_EXT so the allowlist and extension map never drift apart.
_ALLOWED_CONTENT_TYPES = set(_MIME_TO_EXT)


class SttUploadResponse(BaseModel):
    transcript: str | None = None
    status: str  # "ok" | "unavailable" | "error"
    language: str | None = None
    confidence: float | None = None
    duration_ms: float | None = None
    processing_ms: float | None = None


@router.post("/api/stt/upload", response_model=SttUploadResponse)
async def upload_audio(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = Form(None),
) -> SttUploadResponse:
    """Accept a local audio recording and return a transcript via whisper.cpp.

    Audio is processed locally and never sent to remote services. If the STT
    runtime or model is unavailable, the endpoint returns status='unavailable'
    with a null transcript (text-only fallback) rather than an HTTP error.
    The optional `language` form field passes a BCP-47 / whisper language code
    from scenario setup to the STT worker when provided.
    """
    app_settings = request.app.state.app_settings

    content_type = (audio.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {content_type}")

    data = await audio.read()
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio exceeds 25 MB limit")

    # Raw audio is intentionally not persisted unless the user opts in.
    if app_settings.save_raw_audio:
        pass  # Future: pass data to local storage here.

    stt_worker = request.app.state.stt_worker
    audio_format = _MIME_TO_EXT.get(content_type, "bin")

    try:
        result = await stt_worker.transcribe(
            SttRequest(audio=data, audio_format=audio_format, language=language)
        )
        return SttUploadResponse(
            transcript=result.transcript,
            status="ok",
            language=result.language,
            confidence=result.confidence,
            duration_ms=result.duration_ms,
            processing_ms=result.processing_ms,
        )
    except SttUnavailableError as exc:
        logger.info("STT worker unavailable (binary or model not installed): %s", exc)
        return SttUploadResponse(transcript=None, status="unavailable")
    except SttError as exc:
        logger.warning("STT worker error during transcription: %s", exc, exc_info=True)
        return SttUploadResponse(transcript=None, status="error")
