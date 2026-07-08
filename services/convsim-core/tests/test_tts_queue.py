# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the TTS queue service (issue #62).

Covers:
  - Single and multi-sentence utterances produce ordered TtsChunkResult lists.
  - TTS unavailable: all chunks capture the error; no exception raised.
  - Partial TTS failure: later chunks still synthesize.
  - Empty utterance returns [].
  - Session endpoint: tts_enabled=False skips TTS entirely.
  - Session endpoint: tts_audio_chunk events appear in the turn response.
  - Cache clear endpoint deletes cached files.
"""
from __future__ import annotations

import os
import json
from unittest.mock import AsyncMock, patch

import pytest

from convsim_core.services.tts_queue import TtsChunkResult, synthesize_utterance
from convsim_core.tts.types import TtsRequest, TtsResult, TtsUnavailableError, TtsError


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _make_ok_result(text: str, voice_id: str, tmp_path) -> TtsResult:
    p = tmp_path / f"{hash(text)}.wav"
    p.write_bytes(b"RIFF")
    return TtsResult(audio_path=str(p), audio_format="wav", duration_ms=100.0, voice_id=voice_id)


class _AlwaysOkWorker:
    async def synthesize(self, req: TtsRequest) -> TtsResult:
        raise NotImplementedError  # replaced by mock in each test

    async def clear_cache(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# synthesize_utterance — unit tests with mocked TTS worker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_utterance_returns_empty_list():
    worker = _AlwaysOkWorker()
    result = await synthesize_utterance("", "af_heart", worker)
    assert result == []


@pytest.mark.asyncio
async def test_whitespace_utterance_returns_empty_list():
    worker = _AlwaysOkWorker()
    result = await synthesize_utterance("   ", "af_heart", worker)
    assert result == []


@pytest.mark.asyncio
async def test_single_sentence_produces_one_chunk(tmp_path):
    worker = _AlwaysOkWorker()
    worker.synthesize = AsyncMock(
        return_value=_make_ok_result("Hello.", "af_heart", tmp_path)
    )
    chunks = await synthesize_utterance("Hello.", "af_heart", worker)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].total_chunks == 1
    assert chunks[0].text == "Hello."
    assert chunks[0].succeeded
    assert chunks[0].error is None


@pytest.mark.asyncio
async def test_multi_sentence_produces_ordered_chunks(tmp_path):
    sentences = ["Hello there.", "How are you?", "I am fine."]
    utterance = " ".join(sentences)

    call_count = 0

    async def mock_synthesize(req: TtsRequest) -> TtsResult:
        nonlocal call_count
        result = _make_ok_result(req.text, req.voice_id, tmp_path)
        call_count += 1
        return result

    worker = _AlwaysOkWorker()
    worker.synthesize = mock_synthesize

    chunks = await synthesize_utterance(utterance, "af_heart", worker)

    assert len(chunks) == 3
    assert call_count == 3
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.total_chunks == 3
        assert chunk.succeeded


@pytest.mark.asyncio
async def test_chunks_carry_correct_text(tmp_path):
    utterance = "First sentence. Second sentence."
    worker = _AlwaysOkWorker()
    worker.synthesize = AsyncMock(
        side_effect=lambda req: _make_result_coro(req, tmp_path)
    )

    async def _make_result_coro(req, tp):
        return _make_ok_result(req.text, req.voice_id, tp)

    worker.synthesize = AsyncMock(side_effect=_make_result_coro)
    chunks = await synthesize_utterance(utterance, "am_adam", worker)

    assert chunks[0].text == "First sentence."
    assert chunks[1].text == "Second sentence."


@pytest.mark.asyncio
async def test_tts_unavailable_records_error_does_not_raise():
    worker = _AlwaysOkWorker()
    worker.synthesize = AsyncMock(
        side_effect=TtsUnavailableError("Kokoro not running")
    )
    chunks = await synthesize_utterance(
        "Hello. World.", "af_heart", worker
    )
    assert len(chunks) == 2
    for chunk in chunks:
        assert not chunk.succeeded
        assert chunk.error is not None
        assert chunk.audio_path is None


@pytest.mark.asyncio
async def test_tts_error_records_error_does_not_raise():
    worker = _AlwaysOkWorker()
    worker.synthesize = AsyncMock(side_effect=TtsError("synthesis failed"))
    chunks = await synthesize_utterance("Hello there.", "af_heart", worker)
    assert len(chunks) == 1
    assert not chunks[0].succeeded
    assert "synthesis failed" in chunks[0].error


@pytest.mark.asyncio
async def test_partial_failure_later_chunks_still_run(tmp_path):
    call_count = 0

    async def _partial(req: TtsRequest) -> TtsResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TtsError("first fails")
        return _make_ok_result(req.text, req.voice_id, tmp_path)

    worker = _AlwaysOkWorker()
    worker.synthesize = _partial

    chunks = await synthesize_utterance("One. Two. Three.", "af_heart", worker)
    assert len(chunks) == 3
    assert not chunks[0].succeeded
    assert chunks[1].succeeded
    assert chunks[2].succeeded


@pytest.mark.asyncio
async def test_chunks_include_voice_id():
    worker = _AlwaysOkWorker()
    worker.synthesize = AsyncMock(side_effect=TtsUnavailableError("down"))
    chunks = await synthesize_utterance("Hello.", "bm_george", worker)
    assert chunks[0].voice_id == "bm_george"


@pytest.mark.asyncio
async def test_unexpected_exception_is_captured():
    worker = _AlwaysOkWorker()
    worker.synthesize = AsyncMock(side_effect=RuntimeError("boom"))
    chunks = await synthesize_utterance("Hello.", "af_heart", worker)
    assert len(chunks) == 1
    assert not chunks[0].succeeded
    assert "boom" in chunks[0].error


# ---------------------------------------------------------------------------
# TtsChunkResult helpers
# ---------------------------------------------------------------------------


def test_chunk_result_succeeded_when_audio_path_set(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"")
    chunk = TtsChunkResult(
        chunk_index=0, total_chunks=1, text="Hi", voice_id="af_heart",
        audio_path=str(f),
    )
    assert chunk.succeeded is True


def test_chunk_result_not_succeeded_when_audio_path_none():
    chunk = TtsChunkResult(
        chunk_index=0, total_chunks=1, text="Hi", voice_id="af_heart",
        error="backend down",
    )
    assert chunk.succeeded is False


# ---------------------------------------------------------------------------
# HTTP session endpoint integration (mocked TTS, real DB)
# ---------------------------------------------------------------------------


_BASE_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "normal",
    "player_role_name": "Alice",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "tts_voice_id": "af_heart",
    "save_transcript": True,
}


def _create_session(client, tts_enabled: bool = False, voice_id: str = "af_heart") -> str:
    setup = {**_BASE_SETUP, "tts_enabled": tts_enabled, "tts_voice_id": voice_id}
    resp = client.post("/api/sessions", json=setup)
    assert resp.status_code == 201
    return resp.json()["session_id"]


def test_tts_disabled_no_audio_chunk_events_in_start(client):
    sid = _create_session(client, tts_enabled=False)
    resp = client.post(f"/api/sessions/{sid}/start")
    assert resp.status_code == 200
    events = resp.json()["events"]
    types = [e["event_type"] for e in events]
    assert "tts_audio_chunk" not in types


def test_tts_disabled_no_audio_chunk_events_in_turn(client):
    sid = _create_session(client, tts_enabled=False)
    client.post(f"/api/sessions/{sid}/start")
    resp = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hello"})
    assert resp.status_code == 200
    events = resp.json()["events"]
    types = [e["event_type"] for e in events]
    assert "tts_audio_chunk" not in types


def test_tts_enabled_emits_audio_chunk_events_on_start(client, tmp_path):
    sid = _create_session(client, tts_enabled=True)
    fake_path = str(tmp_path / "out.wav")
    mock_result = TtsResult(
        audio_path=fake_path, audio_format="wav", duration_ms=200.0, voice_id="af_heart"
    )
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(return_value=mock_result),
    ):
        resp = client.post(f"/api/sessions/{sid}/start")
    assert resp.status_code == 200
    events = resp.json()["events"]
    tts_events = [e for e in events if e["event_type"] == "tts_audio_chunk"]
    assert len(tts_events) >= 1


def test_tts_audio_chunk_event_has_required_fields(client, tmp_path):
    sid = _create_session(client, tts_enabled=True)
    fake_path = str(tmp_path / "out.wav")
    mock_result = TtsResult(
        audio_path=fake_path, audio_format="wav", duration_ms=100.0, voice_id="af_heart"
    )
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(return_value=mock_result),
    ):
        resp = client.post(f"/api/sessions/{sid}/start")
    events = resp.json()["events"]
    tts_event = next(e for e in events if e["event_type"] == "tts_audio_chunk")
    payload = tts_event["payload"]
    assert "chunk_index" in payload
    assert "total_chunks" in payload
    assert "text" in payload
    assert "voice_id" in payload
    assert "cache_path" in payload
    assert "error" in payload


def test_tts_audio_chunk_cache_path_matches_synthesize_result(client, tmp_path):
    sid = _create_session(client, tts_enabled=True)
    fake_path = str(tmp_path / "audio.wav")
    mock_result = TtsResult(
        audio_path=fake_path, audio_format="wav", duration_ms=100.0, voice_id="af_heart"
    )
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(return_value=mock_result),
    ):
        resp = client.post(f"/api/sessions/{sid}/start")
    tts_event = next(
        e for e in resp.json()["events"] if e["event_type"] == "tts_audio_chunk"
    )
    assert tts_event["payload"]["cache_path"] == fake_path


def test_tts_unavailable_does_not_fail_turn(client):
    sid = _create_session(client, tts_enabled=True)
    client.post(f"/api/sessions/{sid}/start")
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(side_effect=TtsUnavailableError("Kokoro down")),
    ):
        resp = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hello"})
    assert resp.status_code == 200
    data = resp.json()
    # Session state must not be corrupted; turn still processed
    assert data["state"] in ("PlayerTurnListening", "Ended")
    # tts_audio_chunk events may be present but with error field set
    tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
    for ev in tts_events:
        assert ev["payload"]["cache_path"] is None
        assert ev["payload"]["error"] is not None


def test_tts_enabled_turn_emits_ordered_chunks(client, tmp_path):
    sid = _create_session(client, tts_enabled=True)
    client.post(f"/api/sessions/{sid}/start")
    call_index = [0]

    async def _sequential_synth(req: TtsRequest) -> TtsResult:
        idx = call_index[0]
        call_index[0] += 1
        path = str(tmp_path / f"chunk_{idx}.wav")
        return TtsResult(audio_path=path, audio_format="wav", duration_ms=100.0, voice_id=req.voice_id)

    with patch.object(client.app.state.tts_worker, "synthesize", side_effect=_sequential_synth):
        resp = client.post(f"/api/sessions/{sid}/turn", json={"content": "Tell me about yourself"})
    assert resp.status_code == 200
    tts_events = [e for e in resp.json()["events"] if e["event_type"] == "tts_audio_chunk"]
    if tts_events:
        indices = [e["payload"]["chunk_index"] for e in tts_events]
        assert indices == sorted(indices)  # ordered
        assert indices[0] == 0  # zero-based


def test_invalid_tts_voice_id_rejected_at_session_creation(client):
    setup = {**_BASE_SETUP, "tts_enabled": True, "tts_voice_id": "clone:evil_voice"}
    resp = client.post("/api/sessions", json=setup)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cache clear endpoint
# ---------------------------------------------------------------------------


def test_cache_clear_returns_200(client):
    resp = client.post("/api/tts/cache/clear")
    assert resp.status_code == 200


def test_cache_clear_returns_deleted_files_count(client):
    body = client.post("/api/tts/cache/clear").json()
    assert "deleted_files" in body
    assert isinstance(body["deleted_files"], int)


@pytest.mark.asyncio
async def test_cache_clear_deletes_wav_files(tmp_path):
    from convsim_core.tts.kokoro import KokoroConfig, KokoroTtsWorker

    cache_dir = tmp_path / "tts_cache"
    cache_dir.mkdir()
    (cache_dir / "abc123.wav").write_bytes(b"RIFF")
    (cache_dir / "def456.wav").write_bytes(b"RIFF")
    (cache_dir / "notes.txt").write_bytes(b"keep")

    worker = KokoroTtsWorker(KokoroConfig(cache_dir=str(cache_dir)))
    deleted = await worker.clear_cache()

    assert deleted == 2
    assert not (cache_dir / "abc123.wav").exists()
    assert not (cache_dir / "def456.wav").exists()
    assert (cache_dir / "notes.txt").exists()  # non-WAV untouched


@pytest.mark.asyncio
async def test_cache_clear_nonexistent_dir_returns_zero(tmp_path):
    from convsim_core.tts.kokoro import KokoroConfig, KokoroTtsWorker

    worker = KokoroTtsWorker(KokoroConfig(cache_dir=str(tmp_path / "no_such_dir")))
    deleted = await worker.clear_cache()
    assert deleted == 0


@pytest.mark.asyncio
async def test_fake_worker_clear_cache_returns_zero():
    from convsim_core.tts.fake import FakeTtsWorker

    worker = FakeTtsWorker()
    deleted = await worker.clear_cache()
    assert deleted == 0
