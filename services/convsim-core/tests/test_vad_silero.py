# SPDX-License-Identifier: Apache-2.0
"""Tests for SileroVadWorker — config, health checks, and calibration logic."""
import io
import struct
import wave
from unittest.mock import MagicMock, patch

import pytest

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.vad.silero import (
    SileroVadConfig,
    SileroVadWorker,
    _frame_energies,
    _rms,
    _try_wav_to_pcm,
)
from convsim_core.vad.types import VadRequest

_FAKE_MODEL = "/home/user/.convsim/models/vad/silero_vad.onnx"


def _make_worker(model: str = _FAKE_MODEL) -> SileroVadWorker:
    config = SileroVadConfig(model_path=model)
    return SileroVadWorker(config)


def _make_wav_bytes(
    n_frames: int = 16000,
    sample_rate: int = 16000,
    amplitude: float = 0.01,
) -> bytes:
    """Build a minimal 16-bit mono WAV of silence (near-zero amplitude)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        samples = [int(amplitude * 32767)] * n_frames
        w.writeframes(struct.pack(f"{n_frames}h", *samples))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_rms_zero_for_silence():
    samples = [0.0] * 512
    assert _rms(samples) == pytest.approx(0.0)


def test_rms_correct_for_unit_sine():
    import math
    samples = [math.sin(2 * math.pi * i / 512) for i in range(512)]
    # RMS of a full-period sine is 1/sqrt(2) ≈ 0.707
    assert _rms(samples) == pytest.approx(0.707, abs=0.01)


def test_rms_empty_returns_zero():
    assert _rms([]) == pytest.approx(0.0)


def test_frame_energies_count():
    # 2048 samples → 4 full 512-sample frames
    samples = [0.1] * 2048
    energies = _frame_energies(samples)
    assert len(energies) == 4


def test_frame_energies_partial_frame_ignored():
    # 600 samples → only 1 full frame (512); remainder discarded
    samples = [0.1] * 600
    energies = _frame_energies(samples)
    assert len(energies) == 1


def test_frame_energies_all_same_amplitude():
    amplitude = 0.1
    samples = [amplitude] * 1024
    energies = _frame_energies(samples)
    assert all(e == pytest.approx(amplitude) for e in energies)


# ---------------------------------------------------------------------------
# _try_wav_to_pcm
# ---------------------------------------------------------------------------


def test_try_wav_to_pcm_decodes_16bit_mono():
    wav = _make_wav_bytes(n_frames=512, amplitude=0.1)
    samples = _try_wav_to_pcm(wav)
    assert samples is not None
    assert len(samples) == 512
    # All samples should be close to the amplitude
    assert all(abs(s - 0.1) < 0.01 for s in samples)


def test_try_wav_to_pcm_returns_none_for_garbage():
    samples = _try_wav_to_pcm(b"not a wav file at all")
    assert samples is None


def test_try_wav_to_pcm_handles_stereo_by_mixing_to_mono():
    buf = io.BytesIO()
    n = 512
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        # Left = 0.2, Right = 0.4 → mono should be ≈ 0.3
        interleaved = []
        for _ in range(n):
            interleaved += [int(0.2 * 32767), int(0.4 * 32767)]
        w.writeframes(struct.pack(f"{n * 2}h", *interleaved))
    samples = _try_wav_to_pcm(buf.getvalue())
    assert samples is not None
    assert len(samples) == n
    assert all(abs(s - 0.3) < 0.02 for s in samples)


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_unavailable_when_onnxruntime_missing():
    worker = _make_worker()
    with patch.dict("sys.modules", {"onnxruntime": None}):
        h = await worker.health()
    assert h.status == RuntimeStatus.UNAVAILABLE
    assert "onnxruntime" in (h.message or "")


@pytest.mark.asyncio
async def test_health_unavailable_when_model_file_missing():
    worker = _make_worker(model="/nonexistent/silero_vad.onnx")
    fake_ort = MagicMock()
    with patch.dict("sys.modules", {"onnxruntime": fake_ort}):
        h = await worker.health()
    assert h.status == RuntimeStatus.UNAVAILABLE
    assert "/nonexistent/silero_vad.onnx" in (h.model_path or "")


@pytest.mark.asyncio
async def test_health_ready_when_onnxruntime_and_model_present(tmp_path):
    model_file = tmp_path / "silero_vad.onnx"
    model_file.write_bytes(b"\x00" * 64)
    worker = _make_worker(model=str(model_file))
    fake_ort = MagicMock()
    with patch.dict("sys.modules", {"onnxruntime": fake_ort}):
        h = await worker.health()
    assert h.status == RuntimeStatus.READY
    assert h.model_path == str(model_file)
    assert h.checked_at


# ---------------------------------------------------------------------------
# calibrate() — WAV input without Silero (energy-only fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calibrate_returns_threshold_from_wav_without_onnxruntime():
    """Without onnxruntime the worker falls back to energy-based calibration."""
    worker = _make_worker()
    wav = _make_wav_bytes(n_frames=16000, amplitude=0.01)
    with patch("convsim_core.vad.silero._try_ffmpeg_to_pcm", return_value=None), \
         patch.dict("sys.modules", {"onnxruntime": None}):
        result = await worker.calibrate(VadRequest(audio=wav, audio_format="wav"))
    assert 0.0 < result.recommended_threshold <= 1.0
    assert result.noise_floor >= 0.0
    assert result.worker_id == worker.id


@pytest.mark.asyncio
async def test_calibrate_threshold_above_noise_floor():
    worker = _make_worker()
    wav = _make_wav_bytes(n_frames=16000, amplitude=0.02)
    with patch("convsim_core.vad.silero._try_ffmpeg_to_pcm", return_value=None), \
         patch.dict("sys.modules", {"onnxruntime": None}):
        result = await worker.calibrate(VadRequest(audio=wav, audio_format="wav"))
    assert result.recommended_threshold >= result.noise_floor


@pytest.mark.asyncio
async def test_calibrate_fallback_message_when_silero_unavailable():
    worker = _make_worker()
    wav = _make_wav_bytes(n_frames=16000, amplitude=0.01)
    with patch("convsim_core.vad.silero._try_ffmpeg_to_pcm", return_value=None), \
         patch.dict("sys.modules", {"onnxruntime": None}):
        result = await worker.calibrate(VadRequest(audio=wav, audio_format="wav"))
    # Should have a message explaining the fallback
    assert result.message is not None
    assert len(result.message) > 0


@pytest.mark.asyncio
async def test_calibrate_returns_default_when_audio_cannot_be_decoded():
    """Undecodeable audio returns static default threshold rather than error."""
    worker = _make_worker()
    with patch("convsim_core.vad.silero._try_ffmpeg_to_pcm", return_value=None):
        result = await worker.calibrate(
            VadRequest(audio=b"not audio", audio_format="webm")
        )
    # Should still return a valid threshold with an explanation
    assert result.recommended_threshold == pytest.approx(0.05)
    assert result.message is not None


@pytest.mark.asyncio
async def test_calibrate_louder_noise_produces_higher_threshold():
    worker = _make_worker()
    wav_quiet = _make_wav_bytes(n_frames=16000, amplitude=0.01)
    wav_loud = _make_wav_bytes(n_frames=16000, amplitude=0.20)
    with patch("convsim_core.vad.silero._try_ffmpeg_to_pcm", return_value=None), \
         patch.dict("sys.modules", {"onnxruntime": None}):
        result_quiet = await worker.calibrate(VadRequest(audio=wav_quiet, audio_format="wav"))
        result_loud = await worker.calibrate(VadRequest(audio=wav_loud, audio_format="wav"))
    assert result_loud.recommended_threshold > result_quiet.recommended_threshold


# ---------------------------------------------------------------------------
# calibrate() — with mocked Silero session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calibrate_uses_silero_confidences_to_identify_silence():
    """Low-confidence frames (silence) determine the noise floor used for threshold."""
    worker = _make_worker()
    wav = _make_wav_bytes(n_frames=16000, amplitude=0.05)

    # Mock the ONNX session to return alternating high/low confidence
    n_frames = 16000 // 512
    mock_confidences = [0.9 if i % 2 == 0 else 0.1 for i in range(n_frames)]

    def _fake_run_silero(session, samples):
        return mock_confidences

    with patch("convsim_core.vad.silero._try_ffmpeg_to_pcm", return_value=None), \
         patch("convsim_core.vad.silero._run_silero_sync", side_effect=_fake_run_silero), \
         patch.object(worker, "_load_session", return_value=MagicMock()):
        result = await worker.calibrate(VadRequest(audio=wav, audio_format="wav"))

    assert 0.0 < result.recommended_threshold <= 1.0
    assert result.message is None  # no fallback message when Silero succeeds


# ---------------------------------------------------------------------------
# SileroVadConfig
# ---------------------------------------------------------------------------


def test_silero_vad_config_default_model_path():
    config = SileroVadConfig()
    assert "silero_vad.onnx" in config.model_path
    assert ".convsim" in config.model_path


def test_silero_vad_config_env_override(monkeypatch):
    monkeypatch.setenv("CONVSIM_SILERO_VAD_MODEL_PATH", "/custom/path/model.onnx")
    config = SileroVadConfig()
    assert config.model_path == "/custom/path/model.onnx"
