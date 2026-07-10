# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from convsim_core.stt.types import SttError, SttHealth, SttRequest, SttUnavailableError

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
    status: Literal["ok", "unavailable", "error"]
    language: str | None = None
    confidence: float | None = None
    duration_ms: float | None = None
    processing_ms: float | None = None


class SttHealthResponse(BaseModel):
    worker_id: str
    worker_name: str
    status: Literal["unavailable", "starting", "ready", "degraded", "error"]
    model_path: str | None = None
    message: str | None = None
    checked_at: str


def _health_to_response(h: SttHealth) -> SttHealthResponse:
    return SttHealthResponse(
        worker_id=h.worker_id,
        worker_name=h.worker_name,
        status=h.status.value,
        model_path=h.model_path,
        message=h.message,
        checked_at=h.checked_at,
    )


def _save_audio_locally(data: bytes, audio_format: str, data_dir: str) -> None:
    """Persist raw audio to <data_dir>/audio/ with a timestamped filename.

    Only called when the user has explicitly enabled save_raw_audio in Settings.
    Errors are logged and silently swallowed so a write failure never blocks
    the transcription response.
    """
    try:
        audio_dir = Path(data_dir) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uid = uuid.uuid4().hex[:8]
        filename = f"{ts}_{uid}.{audio_format}"
        (audio_dir / filename).write_bytes(data)
        logger.debug("Raw audio saved to %s", audio_dir / filename)
    except OSError:
        logger.warning("Failed to save raw audio to disk", exc_info=True)


@router.get("/api/stt/health", response_model=SttHealthResponse)
async def stt_health(request: Request) -> SttHealthResponse:
    """Return availability status of the configured STT worker.

    The frontend calls this on load to decide whether to offer push-to-talk. A
    status of 'unavailable' means the whisper.cpp binary or GGML model is not
    installed; the app continues in text-only mode.
    """
    h = await request.app.state.stt_worker.health()
    return _health_to_response(h)


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

    audio_format = _MIME_TO_EXT.get(content_type, "bin")

    # Raw audio is saved only when the user explicitly opts in via Settings.
    if app_settings.save_raw_audio:
        _save_audio_locally(data, audio_format, app_settings.data_dir)

    stt_worker = request.app.state.stt_worker

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
