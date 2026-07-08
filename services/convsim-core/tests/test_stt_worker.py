# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the STT worker abstraction and fake implementation."""
import pytest

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.stt.fake import FakeSttWorker
from convsim_core.stt.types import SttRequest


@pytest.fixture()
def fake_worker() -> FakeSttWorker:
    return FakeSttWorker()


# ---------------------------------------------------------------------------
# FakeSttWorker identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_worker_id(fake_worker):
    assert fake_worker.id == "fake"


@pytest.mark.asyncio
async def test_fake_worker_display_name(fake_worker):
    assert "Fake" in fake_worker.display_name


# ---------------------------------------------------------------------------
# FakeSttWorker health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_worker_health_ready(fake_worker):
    h = await fake_worker.health()
    assert h.status == RuntimeStatus.READY
    assert h.worker_id == "fake"
    assert h.checked_at


@pytest.mark.asyncio
async def test_fake_worker_health_model_path_is_none(fake_worker):
    h = await fake_worker.health()
    assert h.model_path is None


# ---------------------------------------------------------------------------
# FakeSttWorker transcription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_worker_returns_transcript(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    result = await fake_worker.transcribe(req)
    assert result.transcript
    assert len(result.transcript) > 0


@pytest.mark.asyncio
async def test_fake_worker_transcript_is_stable(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    r1 = await fake_worker.transcribe(req)
    r2 = await fake_worker.transcribe(req)
    assert r1.transcript == r2.transcript


@pytest.mark.asyncio
async def test_fake_worker_uses_requested_language(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav", language="fr")
    result = await fake_worker.transcribe(req)
    assert result.language == "fr"


@pytest.mark.asyncio
async def test_fake_worker_defaults_language_to_en(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    result = await fake_worker.transcribe(req)
    assert result.language == "en"


@pytest.mark.asyncio
async def test_fake_worker_confidence_is_high(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    result = await fake_worker.transcribe(req)
    assert result.confidence is not None
    assert result.confidence > 0.9


@pytest.mark.asyncio
async def test_fake_worker_has_segments(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    result = await fake_worker.transcribe(req)
    assert result.segments is not None
    assert len(result.segments) > 0


@pytest.mark.asyncio
async def test_fake_worker_segment_text_matches_transcript(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    result = await fake_worker.transcribe(req)
    assert result.segments is not None
    assert result.segments[0].text == result.transcript


@pytest.mark.asyncio
async def test_fake_worker_processing_ms_is_zero(fake_worker):
    req = SttRequest(audio=b"\x00" * 1600, audio_format="wav")
    result = await fake_worker.transcribe(req)
    assert result.processing_ms == 0.0
