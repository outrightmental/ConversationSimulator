# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

router = APIRouter()

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB hard cap

_ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/mpeg",
    "audio/mp4",
    "application/octet-stream",
}


class SttUploadResponse(BaseModel):
    transcript: str | None = None
    status: str


@router.post("/api/stt/upload", response_model=SttUploadResponse)
async def upload_audio(request: Request, audio: UploadFile = File(...)) -> SttUploadResponse:
    """Accept a local audio recording and return a transcript.

    Audio is read into memory and immediately discarded — it is never written to
    disk unless save_raw_audio is explicitly enabled in settings (future).  The
    actual transcript is produced by the local whisper.cpp runtime once that
    integration is wired up; for now the endpoint returns status='received' with
    a null transcript as a placeholder.
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
        # Future: pass `data` to local storage or the STT runtime here.
        pass

    return SttUploadResponse(transcript=None, status="received")
