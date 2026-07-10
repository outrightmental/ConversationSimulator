# SPDX-License-Identifier: Apache-2.0
"""End-to-end voice smoke tests (issue #64).

Exercises the complete voice pipeline:
  session setup → STT upload → transcript edit → player turn → NPC response → TTS output

Paths covered
-------------
English:      job-interview-basic / behavioral_interview
Non-English:  language-cafe / spanish_coffee  (Spanish, es)

CI mode (default)
-----------------
Uses FakeSttWorker + FakeTtsWorker — no whisper.cpp binary or Kokoro server
required. Both workers always return READY status and produce deterministic
output, so the full pipeline can run in any CI environment without model
downloads.

Real-runtime mode
-----------------
See docs/voice-smoke-tests.md for instructions on running with whisper.cpp
(STT) and Kokoro (TTS) installed locally. Set:

    CONVSIM_STT_WORKER_ID=whisper_cpp
    CONVSIM_TTS_WORKER_ID=kokoro

before running pytest to exercise the actual model binaries.

Failure attribution
-------------------
Each assertion carries a ``[stage: X]`` label so CI logs immediately identify
which part of the voice pipeline broke:

  session_setup  — create/start session, NPC opening delivery
  stt            — audio upload, transcript return, language detection
  text_correction — transcript can be edited before submission
  turn_loop      — player turn submitted, NPC responds, safety gate passes
  tts            — TTS audio chunks emitted, cache_path populated, no error

Mic capture and VAD are hardware/frontend concerns; they cannot be tested at
the API level and are documented separately in docs/voice-smoke-tests.md.
"""
from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


# ---------------------------------------------------------------------------
# Minimal silent WAV fixture (44-byte RIFF header, 0 PCM samples, 22050 Hz)
#
# Used as the synthetic "microphone recording" uploaded to the STT endpoint.
# The FakeSttWorker ignores audio bytes and returns a fixed transcript, so
# any valid WAV header is sufficient for CI. Real-runtime tests replace this
# with an actual recorded utterance — see docs/voice-smoke-tests.md.
# ---------------------------------------------------------------------------

_SILENT_WAV: bytes = (
    b"RIFF"
    + (36).to_bytes(4, "little")     # chunk size = 36 + 0 data bytes
    + b"WAVE"
    + b"fmt "
    + (16).to_bytes(4, "little")     # PCM subchunk size
    + (1).to_bytes(2, "little")      # audio format = PCM
    + (1).to_bytes(2, "little")      # channels = 1 (mono)
    + (22050).to_bytes(4, "little")  # sample rate
    + (44100).to_bytes(4, "little")  # byte rate = rate * channels * bitsPerSample/8
    + (2).to_bytes(2, "little")      # block align
    + (16).to_bytes(2, "little")     # bits per sample
    + b"data"
    + (0).to_bytes(4, "little")      # 0 PCM samples
)

# Scripted player inputs for each path: a behavioral-interview answer for the
# English job-interview scenario and a café order matching smoke_spanish_coffee.yaml
# for the Spanish language-cafe scenario.
_ENGLISH_PLAYER_TURN = (
    "I handled a major production outage by rolling back a bad deploy within fifteen minutes "
    "and writing a post-mortem that prevented recurrence."
)
_SPANISH_PLAYER_TURN = (
    "Hola, buenos días. Quiero un café con leche, por favor. ¿Tiene también croissants?"
)

# Optional real-audio fixture overrides. When set, the language path uploads the
# referenced WAV instead of the built-in silent fixture (see docs/voice-smoke-tests.md).
_FIXTURE_ENV_BY_LANGUAGE = {
    "en": "CONVSIM_VOICE_SMOKE_FIXTURE_EN",
    "es": "CONVSIM_VOICE_SMOKE_FIXTURE_ES",
}


def _audio_for(language: str | None) -> bytes:
    """Return the audio bytes to upload for a given language.

    Uses the real WAV referenced by ``CONVSIM_VOICE_SMOKE_FIXTURE_EN`` /
    ``CONVSIM_VOICE_SMOKE_FIXTURE_ES`` when set (real-runtime mode); otherwise
    falls back to the built-in silent WAV so CI needs no external assets.
    """
    env_var = _FIXTURE_ENV_BY_LANGUAGE.get(language or "")
    if env_var:
        fixture_path = os.environ.get(env_var)
        if fixture_path:
            with open(fixture_path, "rb") as fh:
                return fh.read()
    return _SILENT_WAV


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def voice_client(tmp_path):
    """FastAPI test client wired with FakeSttWorker and FakeTtsWorker.

    No whisper.cpp binary or Kokoro server is required — suitable for CI.
    Both workers always return READY status and produce deterministic output.
    Override with real workers for manual real-runtime tests:

        CONVSIM_STT_WORKER_ID=whisper_cpp CONVSIM_TTS_WORKER_ID=kokoro pytest
    """
    # Default to the fake workers so CI needs no binaries, but honor the
    # documented env-var overrides so real-runtime mode actually switches
    # workers. Explicit kwargs win over env in pydantic-settings, so only
    # pass "fake" when the corresponding env var is absent.
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        stt_worker_id=os.environ.get("CONVSIM_STT_WORKER_ID", "fake"),
        tts_worker_id=os.environ.get("CONVSIM_TTS_WORKER_ID", "fake"),
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_and_start(
    client: TestClient,
    scenario_id: str,
    language: str,
    tts_enabled: bool = True,
) -> tuple[str, list]:
    """Create and immediately start a session; return (session_id, start_events).

    Uses push-to-talk input mode to reflect the voice path.
    On failure, assertion messages carry the [stage: session_setup] label.
    """
    setup = {
        "scenario_id": scenario_id,
        "difficulty": "standard",
        "player_role_name": "Smoke Tester",
        "language": language,
        "input_mode": "push-to-talk",
        "tts_enabled": tts_enabled,
        "tts_voice_id": "af_heart",
        "show_state_meters": False,
        "save_transcript": True,
        "seed": None,
    }
    create_resp = client.post("/api/sessions", json=setup)
    assert create_resp.status_code == 201, (
        f"[stage: session_setup] POST /api/sessions returned {create_resp.status_code}: "
        f"{create_resp.text}"
    )
    session_id: str = create_resp.json()["session_id"]

    start_resp = client.post(f"/api/sessions/{session_id}/start")
    assert start_resp.status_code == 200, (
        f"[stage: session_setup] POST /api/sessions/{session_id}/start returned "
        f"{start_resp.status_code}: {start_resp.text}"
    )
    return session_id, start_resp.json()["events"]


def _upload_audio(
    client: TestClient,
    audio: bytes,
    mime: str = "audio/wav",
    language: str | None = None,
) -> dict:
    """POST audio to /api/stt/upload; return the parsed response body.

    Failure messages carry the [stage: stt] label.
    """
    form_data: dict = {}
    if language:
        form_data["language"] = language
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.wav", io.BytesIO(audio), mime)},
        data=form_data,
    )
    assert resp.status_code == 200, (
        f"[stage: stt] POST /api/stt/upload returned {resp.status_code}: {resp.text}"
    )
    return resp.json()


def _submit_turn(client: TestClient, session_id: str, text: str) -> dict:
    """POST a player turn and return the parsed response body.

    Failure messages carry the [stage: turn_loop] label.
    """
    resp = client.post(f"/api/sessions/{session_id}/turn", json={"content": text})
    assert resp.status_code == 200, (
        f"[stage: turn_loop] POST /api/sessions/{session_id}/turn returned "
        f"{resp.status_code}: {resp.text}"
    )
    return resp.json()


# ===========================================================================
# Worker health: both voice workers must be READY with fake backends
# ===========================================================================


def test_voice_workers_ready_with_fake_backends(voice_client):
    """Both STT and TTS workers must report READY when using fake backends.

    If this test fails, the fake worker registration is broken — subsequent
    voice smoke tests would fail at the wrong stage.
    """
    health = voice_client.get("/api/health").json()
    assert health["stt"]["status"] == "ready", (
        f"[stage: stt] FakeSttWorker not READY — check worker registration: {health['stt']}"
    )
    assert health["tts"]["status"] == "ready", (
        f"[stage: tts] FakeTtsWorker not READY — check worker registration: {health['tts']}"
    )


# ===========================================================================
# STT unit smoke: audio upload returns a usable transcript
# ===========================================================================


def test_stt_upload_returns_transcript_for_any_valid_audio(voice_client):
    """Stage stt: any valid WAV returns a non-empty transcript."""
    body = _upload_audio(voice_client, _SILENT_WAV)
    assert body["status"] == "ok", f"[stage: stt] Status not ok: {body}"
    assert body["transcript"], f"[stage: stt] Transcript is empty: {body}"


def test_stt_upload_passes_english_language_hint(voice_client):
    """Stage stt: language='en' is preserved through the STT pipeline."""
    body = _upload_audio(voice_client, _SILENT_WAV, language="en")
    assert body["language"] == "en", f"[stage: stt] Language mismatch: {body}"


def test_stt_upload_passes_spanish_language_hint(voice_client):
    """Stage stt: language='es' is preserved through the STT pipeline."""
    body = _upload_audio(voice_client, _SILENT_WAV, language="es")
    assert body["language"] == "es", f"[stage: stt] Language mismatch: {body}"


def test_stt_transcript_has_sufficient_length(voice_client):
    """Stage stt: transcript is long enough to be a real sentence."""
    body = _upload_audio(voice_client, _SILENT_WAV)
    transcript = body.get("transcript", "")
    assert len(transcript.split()) >= 3, (
        f"[stage: stt] Transcript too short to be useful: {transcript!r}"
    )


# ===========================================================================
# English voice smoke path — job-interview-basic / behavioral_interview
# ===========================================================================


class TestEnglishVoiceSmoke:
    """Full voice smoke path for the English job-interview-basic scenario.

    Stage order mirrors the in-app voice flow:
      1. session_setup  — create and start session
      2. npc_opening    — NPC delivers opening line
      3. stt            — audio fixture → raw transcript
      4. text_correction — player edits transcript in review panel
      5. turn_loop      — corrected text submitted; NPC responds
      6. tts            — NPC utterance synthesised; audio chunk(s) returned
    """

    _SCENARIO = "behavioral_interview"
    _LANGUAGE = "en"

    def test_session_setup(self, voice_client):
        """Stage session_setup: session creates and starts without error."""
        session_id, events = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        assert session_id, "[stage: session_setup] No session_id returned"
        assert events, "[stage: session_setup] No events returned on start"

    def test_npc_opening_delivered(self, voice_client):
        """Stage session_setup: NPC opening line is present and non-empty."""
        _, events = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        opening = next((e for e in events if e["event_type"] == "npc_opening"), None)
        assert opening is not None, (
            "[stage: session_setup] No npc_opening event in start response"
        )
        assert opening["payload"].get("content"), (
            "[stage: session_setup] NPC opening content is empty"
        )

    def test_stt_produces_transcript(self, voice_client):
        """Stage stt: audio fixture transcribes to a non-empty string."""
        body = _upload_audio(voice_client, _audio_for(self._LANGUAGE), language=self._LANGUAGE)
        assert body["status"] == "ok", f"[stage: stt] Status not ok: {body}"
        assert body["transcript"], f"[stage: stt] Empty transcript: {body}"

    def test_transcript_can_be_corrected_before_submit(self, voice_client):
        """Stage text_correction: raw transcript differs from corrected text.

        Simulates the TranscriptReviewPanel edit flow: the player receives the
        raw STT output and replaces it with their intended utterance before
        submitting.  The corrected text is non-empty and ready for the turn.
        """
        body = _upload_audio(voice_client, _audio_for(self._LANGUAGE), language=self._LANGUAGE)
        raw_transcript = body["transcript"]
        corrected = _ENGLISH_PLAYER_TURN
        # Verify the edit path is actually exercised (raw != corrected).
        assert corrected != raw_transcript, (
            "[stage: text_correction] Raw transcript matches scripted input — "
            "edit path is not being exercised"
        )
        assert corrected.strip(), "[stage: text_correction] Corrected transcript is empty"

    def test_npc_responds_to_player_turn(self, voice_client):
        """Stage turn_loop: NPC replies after player submits their corrected text."""
        session_id, _ = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        npc_event = next((e for e in data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: turn_loop] No npc_turn event in response"
        assert npc_event["payload"].get("content"), (
            "[stage: turn_loop] NPC response content is empty"
        )

    def test_tts_emits_at_least_one_audio_chunk(self, voice_client):
        """Stage tts: at least one tts_audio_chunk event is returned for the NPC utterance."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, (
            "[stage: tts] No tts_audio_chunk events. "
            "Verify TTS worker is READY and tts_enabled=True."
        )

    def test_tts_audio_chunk_has_cache_path(self, voice_client):
        """Stage tts: the first TTS chunk carries a non-null cache_path."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "[stage: tts] No tts_audio_chunk events"
        first = tts_events[0]["payload"]
        assert first.get("cache_path") is not None, (
            f"[stage: tts] First audio chunk has no cache_path: {first}"
        )

    def test_tts_audio_chunk_has_no_error(self, voice_client):
        """Stage tts: the first TTS chunk has error=null (synthesis succeeded)."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "[stage: tts] No tts_audio_chunk events"
        first = tts_events[0]["payload"]
        assert first.get("error") is None, (
            f"[stage: tts] TTS synthesis error on first chunk: {first.get('error')}"
        )

    def test_full_voice_path(self, voice_client):
        """Combined gate: full English voice path runs end-to-end in a single test.

        Runs all six stages in sequence. Labelled assertions pinpoint failures:
          session_setup → npc_opening → stt → text_correction → turn_loop → tts
        """
        # Stage: session_setup
        session_id, start_events = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        assert session_id, "[stage: session_setup] No session_id"

        # Stage: npc_opening
        opening = next((e for e in start_events if e["event_type"] == "npc_opening"), None)
        assert opening is not None, "[stage: npc_opening] No opening event"
        assert opening["payload"].get("content"), "[stage: npc_opening] Empty NPC opening"

        # Stage: stt — microphone audio → raw transcript
        stt = _upload_audio(voice_client, _audio_for(self._LANGUAGE), language=self._LANGUAGE)
        assert stt["status"] == "ok", f"[stage: stt] {stt}"
        raw_transcript = stt["transcript"]
        assert raw_transcript, "[stage: stt] Empty transcript"

        # Stage: text_correction — player edits STT output in review panel
        corrected = _ENGLISH_PLAYER_TURN
        assert corrected != raw_transcript, "[stage: text_correction] Edit not exercised"
        assert corrected.strip(), "[stage: text_correction] Corrected text is empty"

        # Stage: turn_loop — submit corrected text; NPC responds
        turn_data = _submit_turn(voice_client, session_id, corrected)
        npc_event = next((e for e in turn_data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: turn_loop] No NPC response"
        assert npc_event["payload"].get("content"), "[stage: turn_loop] Empty NPC content"

        # Stage: tts — NPC utterance produces at least one audio chunk
        tts_events = [e for e in turn_data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "[stage: tts] No TTS audio chunks"
        first = tts_events[0]["payload"]
        assert first.get("cache_path"), "[stage: tts] Missing cache_path on first chunk"
        assert first.get("error") is None, f"[stage: tts] Synthesis error: {first.get('error')}"


# ===========================================================================
# Non-English voice smoke path — language-cafe / spanish_coffee (Spanish, es)
# ===========================================================================


class TestSpanishVoiceSmoke:
    """Full voice smoke path for the Spanish Language Café scenario.

    Mirrors TestEnglishVoiceSmoke but with:
      scenario:  language-cafe / spanish_coffee
      language:  es (Spanish)
      input:     Spanish non-native utterance from smoke_spanish_coffee.yaml

    This path verifies the runtime handles multilingual audio hints, non-ASCII
    text in player turns, and that benign Spanish input does not trigger a
    safety stop.
    """

    _SCENARIO = "spanish_coffee"
    _LANGUAGE = "es"

    def test_session_setup(self, voice_client):
        """Stage session_setup: Spanish session creates and starts without error."""
        session_id, events = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        assert session_id, "[stage: session_setup] No session_id"
        assert events, "[stage: session_setup] No events on start"

    def test_npc_opening_delivered(self, voice_client):
        """Stage session_setup: NPC opening line is present for Spanish scenario."""
        _, events = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        opening = next((e for e in events if e["event_type"] == "npc_opening"), None)
        assert opening is not None, "[stage: session_setup] No npc_opening event"
        assert opening["payload"].get("content"), "[stage: session_setup] Empty NPC opening"

    def test_stt_passes_spanish_language_hint(self, voice_client):
        """Stage stt: language='es' is preserved through the full STT round-trip."""
        body = _upload_audio(voice_client, _audio_for(self._LANGUAGE), language=self._LANGUAGE)
        assert body["status"] == "ok", f"[stage: stt] Status not ok: {body}"
        assert body["transcript"], f"[stage: stt] Empty transcript: {body}"
        assert body["language"] == "es", (
            f"[stage: stt] Language mismatch — expected 'es', got: {body.get('language')!r}"
        )

    def test_transcript_can_be_corrected_to_spanish(self, voice_client):
        """Stage text_correction: player replaces raw transcript with Spanish utterance."""
        body = _upload_audio(voice_client, _audio_for(self._LANGUAGE), language=self._LANGUAGE)
        raw_transcript = body["transcript"]
        corrected = _SPANISH_PLAYER_TURN
        assert corrected != raw_transcript, (
            "[stage: text_correction] Edit path not exercised — raw matches scripted input"
        )
        assert corrected.strip(), "[stage: text_correction] Corrected text is empty"

    def test_npc_responds_to_spanish_player_input(self, voice_client):
        """Stage turn_loop: NPC replies to non-native Spanish without safety stop."""
        session_id, _ = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        data = _submit_turn(voice_client, session_id, _SPANISH_PLAYER_TURN)

        npc_event = next((e for e in data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: turn_loop] No npc_turn event"
        assert npc_event["payload"].get("content"), "[stage: turn_loop] Empty NPC content"

    def test_no_safety_stop_for_benign_spanish_input(self, voice_client):
        """Stage turn_loop: benign non-native Spanish input must not trigger safety_stop."""
        session_id, _ = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        data = _submit_turn(voice_client, session_id, _SPANISH_PLAYER_TURN)
        safety_stop = next(
            (e for e in data["events"] if e["event_type"] == "safety_stop"), None
        )
        assert safety_stop is None, (
            f"[stage: turn_loop] Safety stop triggered for benign Spanish input: {safety_stop}"
        )

    def test_tts_emits_audio_chunk_for_spanish_npc_turn(self, voice_client):
        """Stage tts: TTS emits at least one chunk for a Spanish-scenario NPC utterance."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        data = _submit_turn(voice_client, session_id, _SPANISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, (
            "[stage: tts] No tts_audio_chunk events for Spanish scenario. "
            "TTS synthesises NPC responses regardless of player input language."
        )
        assert tts_events[0]["payload"].get("cache_path"), (
            "[stage: tts] Missing cache_path on first TTS chunk"
        )

    def test_full_voice_path(self, voice_client):
        """Combined gate: full Spanish voice path runs end-to-end in a single test.

        Runs all six stages in sequence:
          session_setup → npc_opening → stt → text_correction → turn_loop → tts
        Failure messages include a [stage: X] label for CI log attribution.
        """
        # Stage: session_setup
        session_id, start_events = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        assert session_id, "[stage: session_setup] No session_id"

        # Stage: npc_opening
        opening = next((e for e in start_events if e["event_type"] == "npc_opening"), None)
        assert opening is not None, "[stage: npc_opening] Missing"
        assert opening["payload"].get("content"), "[stage: npc_opening] Empty"

        # Stage: stt — audio with Spanish language hint
        stt = _upload_audio(voice_client, _audio_for(self._LANGUAGE), language=self._LANGUAGE)
        assert stt["status"] == "ok", f"[stage: stt] {stt}"
        raw_transcript = stt["transcript"]
        assert raw_transcript, "[stage: stt] Empty transcript"
        assert stt["language"] == "es", f"[stage: stt] Language mismatch: {stt}"

        # Stage: text_correction — player replaces raw output with intended Spanish
        corrected = _SPANISH_PLAYER_TURN
        assert corrected != raw_transcript, "[stage: text_correction] Edit not exercised"
        assert corrected.strip(), "[stage: text_correction] Empty after edit"

        # Stage: turn_loop — submit Spanish text; NPC responds; no safety stop
        turn_data = _submit_turn(voice_client, session_id, corrected)
        npc_event = next((e for e in turn_data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: turn_loop] No NPC response"
        assert npc_event["payload"].get("content"), "[stage: turn_loop] Empty NPC content"
        safety_stop = next(
            (e for e in turn_data["events"] if e["event_type"] == "safety_stop"), None
        )
        assert safety_stop is None, (
            f"[stage: turn_loop] Unexpected safety stop for benign Spanish input: {safety_stop}"
        )

        # Stage: tts — NPC utterance produces at least one audio chunk
        tts_events = [e for e in turn_data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "[stage: tts] No TTS audio chunks for Spanish scenario"
        first = tts_events[0]["payload"]
        assert first.get("cache_path"), "[stage: tts] Missing cache_path"
        assert first.get("error") is None, f"[stage: tts] Synthesis error: {first.get('error')}"


# ===========================================================================
# Text fallback — verified separately per acceptance criteria
# ===========================================================================


class TestTextFallback:
    """Verify the text-only path is unaffected by voice pipeline state.

    Acceptance criterion: 'Text fallback remains verified separately.'
    These tests confirm that disabling TTS does not break session or NPC turns,
    and that no stale audio state leaks when voice output is off.
    """

    def test_no_tts_events_when_disabled_english(self, voice_client):
        """No tts_audio_chunk events when tts_enabled=False (English path)."""
        session_id, _ = _create_and_start(
            voice_client, "behavioral_interview", "en", tts_enabled=False
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert not tts_events, (
            f"[stage: tts] Unexpected TTS events when tts_enabled=False: {tts_events}"
        )

    def test_no_tts_events_when_disabled_spanish(self, voice_client):
        """No tts_audio_chunk events when tts_enabled=False (Spanish path)."""
        session_id, _ = _create_and_start(
            voice_client, "spanish_coffee", "es", tts_enabled=False
        )
        data = _submit_turn(voice_client, session_id, _SPANISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert not tts_events, (
            f"[stage: tts] Unexpected TTS events when tts_enabled=False (Spanish): {tts_events}"
        )

    def test_npc_content_present_without_tts_english(self, voice_client):
        """NPC content field is always populated regardless of TTS status (English)."""
        session_id, _ = _create_and_start(
            voice_client, "behavioral_interview", "en", tts_enabled=False
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        npc_event = next((e for e in data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: turn_loop] No NPC response (text fallback)"
        assert npc_event["payload"].get("content"), (
            "[stage: turn_loop] Empty NPC content in text-fallback mode"
        )

    def test_npc_content_present_without_tts_spanish(self, voice_client):
        """NPC content field is always populated regardless of TTS status (Spanish)."""
        session_id, _ = _create_and_start(
            voice_client, "spanish_coffee", "es", tts_enabled=False
        )
        data = _submit_turn(voice_client, session_id, _SPANISH_PLAYER_TURN)
        npc_event = next((e for e in data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: turn_loop] No NPC response (text fallback, Spanish)"
        assert npc_event["payload"].get("content"), (
            "[stage: turn_loop] Empty NPC content in text-fallback mode (Spanish)"
        )

    def test_session_state_valid_after_text_fallback_turn(self, voice_client):
        """Session remains in PlayerTurnListening after a text-fallback turn."""
        session_id, _ = _create_and_start(
            voice_client, "behavioral_interview", "en", tts_enabled=False
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        assert data["state"] in ("PlayerTurnListening", "Ended"), (
            f"[stage: turn_loop] Unexpected session state after text-fallback turn: {data['state']}"
        )


# ===========================================================================
# Conversational timing features — issue #308
# ===========================================================================


class TestNpcThinkingPause:
    """Verify the NPC thinking-pause feature (issue #308).

    The backend embeds ``thinking_pause_ms`` on the first ``tts_audio_chunk``
    event payload when TTS is enabled and the feature is on (default).
    """

    _SCENARIO = "behavioral_interview"
    _LANGUAGE = "en"

    def test_thinking_pause_present_in_first_tts_chunk(self, voice_client):
        """Stage tts: first chunk payload contains thinking_pause_ms (integer ≥ 0)."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "[stage: tts] No tts_audio_chunk events"
        first = tts_events[0]["payload"]
        pause = first.get("thinking_pause_ms")
        assert isinstance(pause, int) and pause >= 0, (
            f"[stage: tts] thinking_pause_ms missing or invalid on first chunk: {first}"
        )

    def test_thinking_pause_absent_on_subsequent_chunks(self, voice_client):
        """Stage tts: subsequent chunks (chunk_index > 0) do not carry thinking_pause_ms."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        if len(tts_events) < 2:
            pytest.skip("Not enough TTS chunks to test subsequent-chunk absence")
        for chunk_event in tts_events[1:]:
            assert "thinking_pause_ms" not in chunk_event["payload"], (
                f"thinking_pause_ms unexpectedly present on chunk > 0: {chunk_event['payload']}"
            )

    def test_thinking_pause_absent_when_tts_disabled(self, voice_client):
        """No thinking_pause_ms when TTS is off (no TTS events)."""
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=False
        )
        data = _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        tts_events = [e for e in data["events"] if e["event_type"] == "tts_audio_chunk"]
        assert not tts_events, "[stage: tts] Unexpected TTS events when tts_enabled=False"


class TestBargeIn:
    """Verify the barge-in feature end-to-end (issue #308).

    When the player submits a turn with ``barged_in=True`` the backend:
      1. Persists the flag on the player turn row.
      2. Still delivers a full NPC response (barge-in does not abort the LLM).
      3. Reflects the count in the debrief metrics ``interruption_count``.

    Barge-in script:
      1. Start a TTS-enabled session.
      2. Submit a first turn without barge-in to advance the session.
      3. Submit a second turn with barged_in=True (simulating the player
         starting to speak while NPC TTS was playing).
      4. End the session and generate a debrief.
      5. Assert interruption_count == 1 in debrief metrics.
    """

    _SCENARIO = "behavioral_interview"
    _LANGUAGE = "en"

    def _submit_barged_in_turn(
        self, client, session_id: str, text: str
    ) -> dict:
        """POST a player turn with barged_in=True."""
        resp = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": text, "barged_in": True},
        )
        assert resp.status_code == 200, (
            f"[stage: barge_in] Turn with barged_in=True returned "
            f"{resp.status_code}: {resp.text}"
        )
        return resp.json()

    def test_barge_in_turn_still_delivers_npc_response(self, voice_client):
        """Stage barge_in: barged-in turn receives a full NPC response."""
        session_id, _ = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        data = self._submit_barged_in_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        npc_event = next((e for e in data["events"] if e["event_type"] == "npc_turn"), None)
        assert npc_event is not None, "[stage: barge_in] No npc_turn event after barged-in turn"
        assert npc_event["payload"].get("content"), (
            "[stage: barge_in] Empty NPC content after barged-in turn"
        )

    def test_barge_in_flag_appears_on_player_event(self, voice_client):
        """Stage barge_in: player_turn event payload carries barged_in=True."""
        session_id, _ = _create_and_start(voice_client, self._SCENARIO, self._LANGUAGE)
        data = self._submit_barged_in_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        player_event = next((e for e in data["events"] if e["event_type"] == "player_turn"), None)
        assert player_event is not None, "[stage: barge_in] No player_turn event"
        assert player_event["payload"].get("barged_in") is True, (
            f"[stage: barge_in] Expected barged_in=True in player_turn payload: "
            f"{player_event['payload']}"
        )

    def test_barge_in_increments_interruption_count_in_debrief(self, voice_client):
        """Stage barge_in: debrief metrics reflect one interruption after one barge-in turn."""
        # Step 1: create and start session.
        session_id, _ = _create_and_start(
            voice_client, self._SCENARIO, self._LANGUAGE, tts_enabled=True
        )
        # Step 2: first normal turn (no barge-in).
        _submit_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        # Step 3: second turn with barge-in.
        self._submit_barged_in_turn(voice_client, session_id, _ENGLISH_PLAYER_TURN)
        # Step 4: end the session.
        end_resp = voice_client.post(f"/api/sessions/{session_id}/end")
        assert end_resp.status_code == 200, (
            f"[stage: barge_in] End session returned {end_resp.status_code}"
        )
        # Step 5: generate debrief.
        debrief_resp = voice_client.post(f"/api/sessions/{session_id}/debrief")
        assert debrief_resp.status_code == 200, (
            f"[stage: barge_in] Debrief generation returned {debrief_resp.status_code}: "
            f"{debrief_resp.text}"
        )
        debrief = debrief_resp.json()
        metrics = debrief.get("metrics") or {}
        assert metrics.get("interruption_count") == 1, (
            f"[stage: barge_in] Expected interruption_count=1, got: {metrics}"
        )
