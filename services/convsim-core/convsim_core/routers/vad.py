# SPDX-License-Identifier: Apache-2.0
import logging
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from convsim_core.vad.types import VadCalibrationResult, VadError, VadHealth, VadRequest, VadUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB cap for calibration clips

_MIME_TO_EXT: dict[str, str] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp4": "mp4",
    "application/octet-stream": "bin",
}

_ALLOWED_CONTENT_TYPES = set(_MIME_TO_EXT)


class VadCalibrateResponse(BaseModel):
    recommended_threshold: float
    noise_floor: float
    worker_id: str
    status: Literal["ok", "unavailable", "error"]
    message: str | None = None


class VadHealthResponse(BaseModel):
    worker_id: str
    worker_name: str
    status: Literal["unavailable", "starting", "ready", "degraded", "error"]
    model_path: str | None = None
    message: str | None = None
    checked_at: str


def _health_to_response(h: VadHealth) -> VadHealthResponse:
    return VadHealthResponse(
        worker_id=h.worker_id,
        worker_name=h.worker_name,
        status=h.status.value,
        model_path=h.model_path,
        message=h.message,
        checked_at=h.checked_at,
    )


@router.get("/api/vad/health", response_model=VadHealthResponse)
async def vad_health(request: Request) -> VadHealthResponse:
    """Return availability status of the configured VAD worker.

    The frontend calls this on load to decide whether to offer hands-free mode
    calibration. A UNAVAILABLE status means the Silero model or onnxruntime is
    not installed; calibration will use energy-based fallback in that case.
    """
    h = await request.app.state.vad_worker.health()
    return _health_to_response(h)


@router.post("/api/vad/calibrate", response_model=VadCalibrateResponse)
async def vad_calibrate(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = Form(None),  # unused; accepted for forward-compat
) -> VadCalibrateResponse:
    """Accept a short ambient noise recording and return a recommended silence threshold.

    The caller (frontend) records approximately 3 seconds of ambient noise and
    POSTs it here. The response contains a ``recommended_threshold`` value (0–1
    RMS energy) that the client stores locally and uses for real-time silence
    detection via AnalyserNode during hands-free recording.

    Raw audio is not persisted; only the derived threshold is returned.
    If the Silero model is unavailable, an energy-based calibration is still
    performed and the response status is still "ok" with a message explaining
    the fallback.
    """
    content_type = (audio.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {content_type}")

    data = await audio.read()
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Calibration audio exceeds 10 MB limit")

    vad_worker = request.app.state.vad_worker
    audio_format = _MIME_TO_EXT.get(content_type, "bin")

    try:
        result: VadCalibrationResult = await vad_worker.calibrate(
            VadRequest(audio=data, audio_format=audio_format)
        )
        return VadCalibrateResponse(
            recommended_threshold=result.recommended_threshold,
            noise_floor=result.noise_floor,
            worker_id=result.worker_id,
            status="ok",
            message=result.message,
        )
    except VadUnavailableError as exc:
        logger.info("VAD worker unavailable during calibration: %s", exc)
        return VadCalibrateResponse(
            recommended_threshold=0.05,
            noise_floor=0.0,
            worker_id="unavailable",
            status="unavailable",
            message=str(exc),
        )
    except VadError as exc:
        logger.warning("VAD worker error during calibration: %s", exc, exc_info=True)
        return VadCalibrateResponse(
            recommended_threshold=0.05,
            noise_floor=0.0,
            worker_id="error",
            status="error",
            message=str(exc),
        )
