# SPDX-License-Identifier: Apache-2.0
"""Tests for the VAD worker abstraction, registry, fake worker, and threshold config."""
import pytest

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.vad import build_vad_worker, list_vad_worker_ids
from convsim_core.vad.types import VadRequest


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_list_vad_worker_ids_includes_fake_and_silero():
    ids = list_vad_worker_ids()
    assert "fake" in ids
    assert "silero_vad" in ids


def test_build_vad_worker_fake():
    worker = build_vad_worker("fake")
    assert worker.id == "fake"


def test_build_vad_worker_unknown_raises():
    with pytest.raises(KeyError, match="Unknown VAD worker"):
        build_vad_worker("nonexistent_worker")


# ---------------------------------------------------------------------------
# FakeVadWorker — health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_vad_health_is_ready():
    worker = build_vad_worker("fake")
    h = await worker.health()
    assert h.status == RuntimeStatus.READY
    assert h.worker_id == "fake"
    assert h.checked_at


@pytest.mark.asyncio
async def test_fake_vad_health_display_name():
    worker = build_vad_worker("fake")
    h = await worker.health()
    assert "fake" in h.worker_name.lower()


# ---------------------------------------------------------------------------
# FakeVadWorker — calibrate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_vad_calibrate_returns_valid_threshold():
    worker = build_vad_worker("fake")
    result = await worker.calibrate(VadRequest(audio=b"\x00" * 1024, audio_format="wav"))
    assert 0.0 < result.recommended_threshold <= 1.0


@pytest.mark.asyncio
async def test_fake_vad_calibrate_noise_floor_is_non_negative():
    worker = build_vad_worker("fake")
    result = await worker.calibrate(VadRequest(audio=b"\x00" * 1024, audio_format="wav"))
    assert result.noise_floor >= 0.0


@pytest.mark.asyncio
async def test_fake_vad_calibrate_threshold_above_noise_floor():
    worker = build_vad_worker("fake")
    result = await worker.calibrate(VadRequest(audio=b"\x00" * 1024, audio_format="wav"))
    assert result.recommended_threshold >= result.noise_floor


@pytest.mark.asyncio
async def test_fake_vad_calibrate_worker_id_matches():
    worker = build_vad_worker("fake")
    result = await worker.calibrate(VadRequest(audio=b"\x00" * 1024, audio_format="wav"))
    assert result.worker_id == worker.id


@pytest.mark.asyncio
async def test_fake_vad_calibrate_is_deterministic():
    worker = build_vad_worker("fake")
    r1 = await worker.calibrate(VadRequest(audio=b"\x00" * 1024, audio_format="wav"))
    r2 = await worker.calibrate(VadRequest(audio=b"\xff" * 2048, audio_format="webm"))
    assert r1.recommended_threshold == r2.recommended_threshold


# ---------------------------------------------------------------------------
# VadRequest model
# ---------------------------------------------------------------------------


def test_vad_request_default_format():
    req = VadRequest(audio=b"\x00")
    assert req.audio_format == "wav"
    assert req.sample_rate == 16000


def test_vad_request_custom_format():
    req = VadRequest(audio=b"\x00", audio_format="webm")
    assert req.audio_format == "webm"
