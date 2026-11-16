# SPDX-License-Identifier: Apache-2.0
"""A reply's words never wait for its audio (issue #533).

With the character's voice on, a turn used to hold its answer until every
sentence had been synthesised. These cases pin the replacement: the answer
goes out with each sentence listed as pending, synthesis runs behind it, and
each sentence's audio is collected from its own address, which waits for it.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

from convsim_core.services.speech_jobs import SpeechRegistry
from convsim_core.services.turn_timing import load_turn_timings
from convsim_core.tts.types import TtsRequest, TtsResult, TtsUnavailableError
from tests.helpers import recorded_speech, speech_audio

_WAV = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\0" * 24 + b"data" + b"\0" * 4

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Alice",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": True,
    "tts_voice_id": "af_heart",
    "save_transcript": True,
    "runtime_id": "fake",
}


class _GatedWorker:
    """A voice worker that synthesises only once the test lets it.

    The gate is a threading.Event because the test thread opens it while the
    app's loop, in another thread, is waiting on it.
    """

    id = "gated"
    display_name = "Gated test voice"

    def __init__(self, cache_dir: Path, *, fail_on: tuple[str, ...] = ()) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self.gate = threading.Event()
        self.fail_on = fail_on
        self.spoken: list[str] = []
        self.languages: list[str | None] = []

    async def synthesize(self, request: TtsRequest) -> TtsResult:
        while not self.gate.is_set():
            await asyncio.sleep(0.005)
        self.spoken.append(request.text)
        self.languages.append(request.language)
        if any(marker in request.text for marker in self.fail_on):
            raise TtsUnavailableError("this sentence cannot be spoken")
        path = self._cache_dir / f"{len(self.spoken):032x}.wav"
        path.write_bytes(_WAV)
        return TtsResult(audio_path=str(path), voice_id=request.voice_id)

    async def clear_cache(self) -> int:
        return 0

    async def cache_size(self) -> dict:
        return {"files": 0, "size_bytes": 0}


@pytest.fixture()
def voiced(client, tmp_path):
    """A client whose voice worker is gated, and that worker."""
    worker = _GatedWorker(tmp_path / "tts-cache")
    client.app.state.tts_worker = worker
    yield client, worker
    worker.gate.set()  # never leave the app's loop spinning on a closed gate


def _session(client, **overrides) -> str:
    response = client.post("/api/sessions", json={**_SETUP, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _chunks(response) -> list[dict]:
    return [e for e in response.json()["events"] if e["event_type"] == "tts_audio_chunk"]


# ── The answer does not wait ──────────────────────────────────────────────────


def test_opening_line_answers_before_any_audio_exists(voiced):
    client, worker = voiced
    sid = _session(client)

    # The gate is closed: nothing can be synthesised. The request returning at
    # all is the proof that it did not wait for audio.
    response = client.post(f"/api/sessions/{sid}/start")

    assert response.status_code == 200
    opening = next(e for e in response.json()["events"] if e["event_type"] == "npc_opening")
    assert opening["payload"]["content"]
    assert worker.spoken == []
    chunks = _chunks(response)
    assert chunks, "the opening line should be listed for speaking"
    assert [c["payload"]["chunk_index"] for c in chunks] == list(range(len(chunks)))
    for index, chunk in enumerate(chunks):
        payload = chunk["payload"]
        assert payload["pending"] is True
        assert payload["cache_path"] is None and payload["error"] is None
        assert payload["audio_path"] == f"/sessions/{sid}/speech/0/{index}"
        assert payload["total_chunks"] == len(chunks)
        assert payload["text"]


def test_turn_answers_before_any_audio_exists(voiced):
    client, worker = voiced
    sid = _session(client)
    client.post(f"/api/sessions/{sid}/start")
    worker.spoken.clear()

    response = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hello there."})

    assert response.status_code == 200
    npc = next(e for e in response.json()["events"] if e["event_type"] == "npc_turn")
    assert npc["payload"]["content"]
    assert worker.spoken == []
    chunks = _chunks(response)
    assert chunks and all(c["payload"]["pending"] for c in chunks)
    # The turn's record goes out with the voice stage present but unknown.
    assert npc["payload"]["timing"]["voice"] == {"synth_ms": None, "first_audio_ms": None}


# ── The audio follows ─────────────────────────────────────────────────────────


def test_each_sentence_is_served_once_synthesised_and_recorded(voiced):
    client, worker = voiced
    sid = _session(client)
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))

    worker.gate.set()
    for chunk in chunks:
        response = speech_audio(client, chunk)
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.content == _WAV
        recorded = recorded_speech(client, chunk)
        assert recorded["pending"] is False
        assert recorded["error"] is None
        assert Path(recorded["cache_path"]).is_file()
        # Everything else about the sentence is as it was announced.
        for key in ("chunk_index", "total_chunks", "text", "voice_id", "audio_path"):
            assert recorded[key] == chunk["payload"][key]
    assert worker.spoken == [c["payload"]["text"] for c in chunks] or sorted(worker.spoken) == sorted(
        c["payload"]["text"] for c in chunks
    )


def test_a_request_for_audio_waits_for_its_sentence(voiced):
    client, worker = voiced
    sid = _session(client)
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))

    # Open the gate from another thread a moment after the request is made.
    # A request that did not wait would have answered 404 at once.
    opener = threading.Timer(0.3, worker.gate.set)
    opener.start()
    started = time.monotonic()
    response = speech_audio(client, chunks[0])
    waited = time.monotonic() - started
    opener.join()

    assert response.status_code == 200
    assert waited >= 0.25


def test_a_sentence_that_fails_is_skipped_and_the_rest_are_spoken(voiced):
    client, worker = voiced
    sid = _session(client)
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))
    assert len(chunks) >= 2, "the opening line should have several sentences"
    # Nothing has been synthesised yet (the gate is closed), so the sentence
    # to fail can still be chosen: the second one.
    failing = chunks[1]
    worker.fail_on = (failing["payload"]["text"],)
    worker.gate.set()

    for chunk in chunks:
        response = speech_audio(client, chunk)
        recorded = recorded_speech(client, chunk)
        if chunk is failing:
            assert response.status_code == 404
            assert recorded["cache_path"] is None
            assert "cannot be spoken" in recorded["error"]
        else:
            assert response.status_code == 200
            assert recorded["error"] is None
        assert recorded["pending"] is False


def test_the_session_language_reaches_the_voice(tmp_path, client):
    worker = _GatedWorker(tmp_path / "tts-cache")
    worker.gate.set()
    client.app.state.tts_worker = worker
    sid = _session(client, scenario_id="spanish_coffee", language="es")
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))
    for chunk in chunks:
        assert speech_audio(client, chunk).status_code == 200
    assert worker.languages and set(worker.languages) == {"es"}


def test_voice_timing_is_filled_in_when_the_last_sentence_is_done(voiced):
    client, worker = voiced
    sid = _session(client)
    client.post(f"/api/sessions/{sid}/start")
    worker.gate.set()
    turn = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hello there."})
    chunks = _chunks(turn)
    for chunk in chunks:
        assert speech_audio(client, chunk).status_code == 200

    deadline = time.monotonic() + 5
    voice = None
    while time.monotonic() < deadline:
        timings = load_turn_timings(client.app.state.db.connection(), sid)
        voice = next(iter(timings.values()))["voice"]
        if voice and voice["synth_ms"] is not None:
            break
        time.sleep(0.02)
    assert voice is not None and voice["synth_ms"] is not None
    assert voice["first_audio_ms"] is not None
    assert 0 <= voice["first_audio_ms"] <= voice["synth_ms"]


def test_voice_off_lists_and_synthesises_nothing(voiced):
    client, worker = voiced
    worker.gate.set()
    sid = _session(client, tts_enabled=False)
    start = client.post(f"/api/sessions/{sid}/start")
    turn = client.post(f"/api/sessions/{sid}/turn", json={"content": "Hello there."})
    assert _chunks(start) == [] and _chunks(turn) == []
    npc = next(e for e in turn.json()["events"] if e["event_type"] == "npc_turn")
    assert npc["payload"]["timing"]["voice"] is None
    assert worker.spoken == []


# ── The audio address ─────────────────────────────────────────────────────────


def test_audio_is_still_served_after_the_app_forgot_the_job(voiced):
    """After a restart nothing is in flight; the session's record answers."""
    client, worker = voiced
    worker.gate.set()
    sid = _session(client)
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))
    assert speech_audio(client, chunks[0]).status_code == 200

    client.app.state.speech.forget_session(sid)
    again = speech_audio(client, chunks[0])
    assert again.status_code == 200
    assert again.content == _WAV


def test_unknown_sentences_are_not_found(voiced):
    client, worker = voiced
    worker.gate.set()
    sid = _session(client)
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))
    assert speech_audio(client, chunks[0]).status_code == 200

    assert client.get(f"/api/sessions/{sid}/speech/0/{len(chunks)}").status_code == 404
    assert client.get(f"/api/sessions/{sid}/speech/7/0").status_code == 404
    assert client.get("/api/sessions/sess-nope/speech/0/0").status_code == 404


def test_only_files_in_the_voice_cache_are_served(voiced, tmp_path):
    """Whatever a record says, a file outside the TTS cache is never served."""
    client, worker = voiced
    worker.gate.set()
    sid = _session(client)
    chunk = _chunks(client.post(f"/api/sessions/{sid}/start"))[0]
    assert speech_audio(client, chunk).status_code == 200

    secret = tmp_path / "not-audio.txt"
    secret.write_text("private", encoding="utf-8")
    recorded = recorded_speech(client, chunk)
    recorded["cache_path"] = str(secret)
    conn = client.app.state.db.connection()
    conn.execute(
        "UPDATE turn_session_events SET payload_json = ? WHERE id = ?",
        (json.dumps(recorded), chunk["event_id"]),
    )
    conn.commit()
    client.app.state.speech.forget_session(sid)

    assert speech_audio(client, chunk).status_code == 404


def test_deleting_a_session_forgets_its_speech(voiced):
    client, worker = voiced
    sid = _session(client)
    chunks = _chunks(client.post(f"/api/sessions/{sid}/start"))
    assert client.app.state.speech.sentence(sid, 0, 0) is not None

    worker.gate.set()
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.app.state.speech.sentence(sid, 0, 0) is None
    assert speech_audio(client, chunks[0]).status_code == 404


# ── The registry on its own ───────────────────────────────────────────────────


class _InstantWorker:
    max_concurrency = 2

    def __init__(self, fail: tuple[str, ...] = ()) -> None:
        self.fail = fail

    async def synthesize(self, request: TtsRequest) -> TtsResult:
        # The first sentence takes longest, so it finishes last.
        await asyncio.sleep(0.05 if request.text.startswith("One") else 0.01)
        if request.text in self.fail:
            raise TtsUnavailableError("no")
        return TtsResult(audio_path=f"/cache/{request.text}", voice_id=request.voice_id)


@pytest.mark.asyncio
async def test_registry_resolves_each_sentence_and_reports_when_done():
    registry = SpeechRegistry()
    finished: list[int] = []
    done: list[object] = []
    job = registry.start(
        session_id="s", turn_number=1, sentences=["One.", "Two.", "Three."],
        voice_id="af_heart", language=None, tts_worker=_InstantWorker(fail=("Two.",)),
        on_sentence=lambda chunk: finished.append(chunk.chunk_index),
        on_done=done.append,
    )

    paths = await asyncio.gather(*(registry.sentence("s", 1, i) for i in range(3)))
    await asyncio.sleep(0.02)

    assert paths == ["/cache/One.", None, "/cache/Three."]
    # They finish out of order; each is still found by its own index.
    assert sorted(finished) == [0, 1, 2] and finished[-1] == 0
    assert done == [job]
    assert job.first_audio_ms is not None and job.synth_ms is not None
    assert job.first_audio_ms <= job.synth_ms
    assert registry.sentence("s", 1, 3) is None
    assert registry.sentence("s", 2, 0) is None
    await registry.shutdown()


@pytest.mark.asyncio
async def test_registry_keeps_only_a_sessions_latest_turns():
    registry = SpeechRegistry()
    for turn in range(4):
        registry.start(
            session_id="s", turn_number=turn, sentences=["One."], voice_id="af_heart",
            language=None, tts_worker=_InstantWorker(),
        )
    registry.start(
        session_id="other", turn_number=0, sentences=["One."], voice_id="af_heart",
        language=None, tts_worker=_InstantWorker(),
    )

    assert registry.sentence("s", 0, 0) is None and registry.sentence("s", 1, 0) is None
    assert registry.sentence("s", 2, 0) is not None and registry.sentence("s", 3, 0) is not None
    assert registry.sentence("other", 0, 0) is not None
    await registry.shutdown()


@pytest.mark.asyncio
async def test_registry_never_leaves_a_listener_waiting():
    """A worker that blows up still resolves every sentence, as no audio."""

    class _Broken:
        async def synthesize(self, request: TtsRequest) -> TtsResult:
            raise RuntimeError("engine fell over")

    registry = SpeechRegistry()
    registry.start(
        session_id="s", turn_number=0, sentences=["One.", "Two."], voice_id="af_heart",
        language=None, tts_worker=_Broken(),
    )
    paths = await asyncio.wait_for(
        asyncio.gather(registry.sentence("s", 0, 0), registry.sentence("s", 0, 1)), timeout=2
    )
    assert paths == [None, None]
    await registry.shutdown()
