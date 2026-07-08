# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import io
import logging
import os
import struct
import subprocess
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.vad.base import VadWorker
from convsim_core.vad.registry import register_vad
from convsim_core.vad.types import (
    VadCalibrationResult,
    VadError,
    VadHealth,
    VadRequest,
    VadUnavailableError,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = str(Path.home() / ".convsim" / "models" / "vad" / "silero_vad.onnx")
_SILERO_SAMPLE_RATE = 16000
_FRAME_SAMPLES = 512  # 32 ms at 16 kHz — the frame size Silero expects


class SileroVadConfig(BaseSettings):
    """Configuration for the Silero VAD worker.

    All values can be set via CONVSIM_SILERO_VAD_* environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONVSIM_SILERO_VAD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model_path: str = _DEFAULT_MODEL_PATH


def _try_ffmpeg_to_pcm(audio: bytes, audio_format: str) -> list[float] | None:
    """Convert audio bytes to 16 kHz mono float32 PCM using ffmpeg.

    Returns None if ffmpeg is unavailable or conversion fails.
    """
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(audio)

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", tmp_path,
                "-ar", str(_SILERO_SAMPLE_RATE),
                "-ac", "1",
                "-f", "f32le",
                "-",
            ],
            capture_output=True,
            timeout=30.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if result.returncode != 0:
        return None

    raw = result.stdout
    n_samples = len(raw) // 4
    if n_samples == 0:
        return None
    return list(struct.unpack(f"{n_samples}f", raw))


def _try_wav_to_pcm(audio: bytes) -> list[float] | None:
    """Decode 16-bit or 32-bit WAV bytes to float32 PCM without ffmpeg.

    Returns None if the bytes are not valid WAV or use an unsupported encoding.
    """
    try:
        with wave.open(io.BytesIO(audio)) as w:
            n_ch = w.getnchannels()
            n_frames = w.getnframes()
            sampwidth = w.getsampwidth()
            raw = w.readframes(n_frames)
    except Exception:
        return None

    if sampwidth == 2:
        fmt = f"{n_frames * n_ch}h"
        scale = 32768.0
    elif sampwidth == 4:
        fmt = f"{n_frames * n_ch}i"
        scale = 2147483648.0
    else:
        return None

    try:
        raw_samples: tuple[int, ...] = struct.unpack(fmt, raw)
    except struct.error:
        return None

    if n_ch == 1:
        return [s / scale for s in raw_samples]
    # Mix to mono
    return [
        sum(raw_samples[i : i + n_ch]) / (n_ch * scale)
        for i in range(0, len(raw_samples), n_ch)
    ]


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def _frame_energies(samples: list[float]) -> list[float]:
    """Return RMS energy for each non-overlapping 512-sample frame."""
    return [
        _rms(samples[i : i + _FRAME_SAMPLES])
        for i in range(0, len(samples) - _FRAME_SAMPLES + 1, _FRAME_SAMPLES)
    ]


def _run_silero_sync(session, samples: list[float]) -> list[float]:
    """Run the Silero ONNX model on samples, returning per-frame confidence scores."""
    import numpy as np  # only imported here; onnxruntime users have numpy transitively

    h = np.zeros((2, 1, 64), dtype=np.float32)
    c = np.zeros((2, 1, 64), dtype=np.float32)
    audio = np.array(samples, dtype=np.float32)
    sr = np.array([_SILERO_SAMPLE_RATE], dtype=np.int64)
    confidences: list[float] = []

    for start in range(0, len(audio) - _FRAME_SAMPLES + 1, _FRAME_SAMPLES):
        frame = audio[start : start + _FRAME_SAMPLES][np.newaxis, :]  # (1, 512)
        outs = session.run(None, {"input": frame, "h": h, "c": c, "sr": sr})
        confidences.append(float(outs[0].squeeze()))
        h = outs[1]
        c = outs[2]

    return confidences


@register_vad("silero_vad")
class SileroVadWorker(VadWorker):
    """VAD worker backed by the Silero VAD ONNX model (local inference only).

    Requires onnxruntime (``pip install onnxruntime``) and the ONNX model at
    ``~/.convsim/models/vad/silero_vad.onnx`` (see runtimes/silero_vad/README.md).

    If either onnxruntime or the model is absent, calibration falls back to
    energy-only statistics so the endpoint still returns a usable threshold
    rather than an error.  Health reports UNAVAILABLE in that case so the
    frontend can display the appropriate notice.

    Audio conversion relies on ffmpeg being on PATH (or the input being
    16-bit/32-bit WAV).  Without ffmpeg, only WAV input is processed precisely;
    other formats receive a static default threshold with an explanatory message.
    """

    def __init__(self, config: SileroVadConfig | None = None) -> None:
        cfg = config or SileroVadConfig()
        self._model_path = cfg.model_path
        self._session = None  # lazy-loaded onnxruntime.InferenceSession

    @property
    def id(self) -> str:
        return "silero_vad"

    @property
    def display_name(self) -> str:
        return "Silero VAD (local ONNX)"

    def _load_session(self):
        if self._session is not None:
            return self._session
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise VadUnavailableError(
                "onnxruntime is not installed. Install it with: pip install onnxruntime. "
                "See runtimes/silero_vad/README.md."
            ) from exc

        if not os.path.isfile(self._model_path):
            raise VadUnavailableError(
                f"Silero VAD model not found at {self._model_path!r}. "
                "Run runtimes/silero_vad/download-model.sh to download it."
            )

        try:
            opts = ort.SessionOptions()
            opts.log_severity_level = 3  # suppress verbose ONNX runtime logs
            self._session = ort.InferenceSession(self._model_path, sess_options=opts)
        except Exception as exc:
            raise VadError(f"Failed to load Silero VAD model: {exc}") from exc

        return self._session

    async def calibrate(self, request: VadRequest) -> VadCalibrationResult:
        loop = asyncio.get_running_loop()

        # Attempt audio decoding: prefer ffmpeg, fall back to WAV parser.
        samples: list[float] | None = await loop.run_in_executor(
            None, _try_ffmpeg_to_pcm, request.audio, request.audio_format
        )
        if samples is None and request.audio_format in ("wav", "wave"):
            samples = await loop.run_in_executor(None, _try_wav_to_pcm, request.audio)

        if not samples or len(samples) < _FRAME_SAMPLES:
            logger.warning(
                "VAD calibration: could not decode audio (format=%r, len=%d). "
                "Returning default threshold.",
                request.audio_format,
                len(request.audio),
            )
            return VadCalibrationResult(
                recommended_threshold=0.05,
                noise_floor=0.0,
                worker_id=self.id,
                message=(
                    "Could not decode audio for calibration. "
                    "Install ffmpeg or send WAV audio for better accuracy."
                ),
            )

        energies = _frame_energies(samples)

        # Try Silero model; degrade gracefully if unavailable.
        silero_confidences: list[float] | None = None
        silero_message: str | None = None
        try:
            session = await loop.run_in_executor(None, self._load_session)
            silero_confidences = await loop.run_in_executor(
                None, _run_silero_sync, session, samples
            )
        except (VadUnavailableError, VadError) as exc:
            silero_message = str(exc)
            logger.info("Silero VAD not available; using energy-only calibration: %s", exc)
        except Exception as exc:
            silero_message = str(exc)
            logger.warning(
                "Unexpected error during Silero inference; falling back to energy-only calibration: %s",
                exc,
                exc_info=True,
            )

        if silero_confidences is not None:
            # Identify frames the model classifies as silence (confidence < 0.3).
            silence_energies = [
                e
                for e, c in zip(energies, silero_confidences)
                if c < 0.3
            ]
            if not silence_energies:
                silence_energies = energies
        else:
            silence_energies = energies

        sorted_silence = sorted(silence_energies)
        noise_floor = sorted_silence[len(sorted_silence) // 2]  # median
        # Threshold: 3× the median noise floor, capped at 0.30 so it stays
        # well below typical speech levels.
        recommended_threshold = min(max(noise_floor * 3.0, 0.01), 0.30)

        return VadCalibrationResult(
            recommended_threshold=recommended_threshold,
            noise_floor=noise_floor,
            worker_id=self.id,
            message=(
                f"Silero model not available; used energy-based calibration. ({silero_message})"
                if silero_message
                else None
            ),
        )

    async def health(self) -> VadHealth:
        checked_at = datetime.now(timezone.utc).isoformat()

        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return VadHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                message=(
                    "onnxruntime is not installed. "
                    "Install it with: pip install onnxruntime"
                ),
                checked_at=checked_at,
            )

        if not os.path.isfile(self._model_path):
            return VadHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                model_path=self._model_path,
                message=(
                    f"Silero VAD model not found at {self._model_path!r}. "
                    "Run runtimes/silero_vad/download-model.sh to download it."
                ),
                checked_at=checked_at,
            )

        return VadHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.READY,
            model_path=self._model_path,
            checked_at=checked_at,
        )
