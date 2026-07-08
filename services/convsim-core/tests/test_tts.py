# SPDX-License-Identifier: Apache-2.0
import os
from unittest.mock import AsyncMock, patch

import pytest

from convsim_core.tts.types import TtsResult, TtsUnavailableError, TtsVoiceValidationError
from convsim_core.tts.voices import APPROVED_VOICES, validate_voice_id


# ---------------------------------------------------------------------------
# Voice validation — unit tests
# ---------------------------------------------------------------------------


def test_validate_voice_id_accepts_approved_voice():
    info = validate_voice_id("af_heart")
    assert info.voice_id == "af_heart"


def test_validate_voice_id_returns_voice_info_fields():
    info = validate_voice_id("am_adam")
    assert info.engine == "kokoro"
    assert info.gender == "male"
    assert info.locale == "en-US"


def test_validate_voice_id_rejects_unknown_voice():
    with pytest.raises(TtsVoiceValidationError):
        validate_voice_id("unknown_voice_xyz")


def test_validate_voice_id_rejects_clone_style_id():
    with pytest.raises(TtsVoiceValidationError):
        validate_voice_id("clone:user_upload_abc")


def test_validate_voice_id_rejects_empty_string():
    with pytest.raises(TtsVoiceValidationError):
        validate_voice_id("")


def test_validate_voice_id_rejects_real_person_name():
    with pytest.raises(TtsVoiceValidationError):
        validate_voice_id("elon_musk")


def test_validate_voice_id_error_message_lists_approved_voices():
    with pytest.raises(TtsVoiceValidationError, match="af_heart"):
        validate_voice_id("not_a_real_voice")


def test_validate_voice_id_error_is_non_recoverable():
    with pytest.raises(TtsVoiceValidationError) as exc_info:
        validate_voice_id("bad_voice")
    assert exc_info.value.recoverable is False


def test_approved_voices_not_empty():
    assert len(APPROVED_VOICES) > 0


def test_approved_voices_include_both_genders():
    genders = {v.gender for v in APPROVED_VOICES.values()}
    assert "male" in genders
    assert "female" in genders


def test_approved_voices_all_have_kokoro_engine():
    for voice in APPROVED_VOICES.values():
        assert voice.engine == "kokoro"


def test_approved_voices_include_us_and_gb_locales():
    locales = {v.locale for v in APPROVED_VOICES.values()}
    assert "en-US" in locales
    assert "en-GB" in locales


def test_all_approved_voice_ids_pass_validation():
    for voice_id in APPROVED_VOICES:
        info = validate_voice_id(voice_id)
        assert info.voice_id == voice_id


# ---------------------------------------------------------------------------
# TTS synthesis endpoint — integration tests (mocked backend)
# ---------------------------------------------------------------------------


def _make_fake_result(voice_id: str, audio_path: str) -> TtsResult:
    return TtsResult(
        audio_path=audio_path,
        audio_format="wav",
        duration_ms=500.0,
        voice_id=voice_id,
    )


def test_tts_synthesize_returns_200_when_worker_succeeds(client, tmp_path):
    audio_path = str(tmp_path / "out.wav")
    mock_result = _make_fake_result("af_heart", audio_path)
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(return_value=mock_result),
    ):
        resp = client.post("/api/tts/synthesize", json={"text": "Hello", "voice_id": "af_heart"})
    assert resp.status_code == 200


def test_tts_synthesize_status_ok_on_success(client, tmp_path):
    audio_path = str(tmp_path / "out.wav")
    mock_result = _make_fake_result("af_heart", audio_path)
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(return_value=mock_result),
    ):
        body = client.post(
            "/api/tts/synthesize", json={"text": "Hello", "voice_id": "af_heart"}
        ).json()
    assert body["status"] == "ok"
    assert body["audio_path"] == audio_path
    assert body["voice_id"] == "af_heart"
    assert body["audio_format"] == "wav"


def test_tts_synthesize_returns_unavailable_when_backend_down(client):
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(side_effect=TtsUnavailableError("Kokoro not running")),
    ):
        body = client.post(
            "/api/tts/synthesize", json={"text": "Hello", "voice_id": "af_heart"}
        ).json()
    assert body["status"] == "unavailable"
    assert body["audio_path"] is None


def test_tts_synthesize_unavailable_does_not_return_500(client):
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(side_effect=TtsUnavailableError("Kokoro not running")),
    ):
        resp = client.post(
            "/api/tts/synthesize", json={"text": "Hello", "voice_id": "af_heart"}
        )
    assert resp.status_code == 200


def test_tts_synthesize_rejects_unknown_voice_with_422(client):
    resp = client.post(
        "/api/tts/synthesize", json={"text": "Hello", "voice_id": "clone:evil_voice"}
    )
    assert resp.status_code == 422


def test_tts_synthesize_rejects_unknown_voice_before_calling_backend(client):
    with patch.object(
        client.app.state.tts_worker,
        "synthesize",
        new=AsyncMock(return_value=None),
    ) as mock_synth:
        client.post(
            "/api/tts/synthesize", json={"text": "Hello", "voice_id": "bad_voice"}
        )
    mock_synth.assert_not_called()


def test_tts_synthesize_requires_text_field(client):
    resp = client.post("/api/tts/synthesize", json={"voice_id": "af_heart"})
    assert resp.status_code == 422


def test_tts_synthesize_requires_voice_id_field(client):
    resp = client.post("/api/tts/synthesize", json={"text": "Hello"})
    assert resp.status_code == 422


def test_tts_synthesize_speed_defaults_to_1(client, tmp_path):
    audio_path = str(tmp_path / "out.wav")
    mock_result = _make_fake_result("af_heart", audio_path)
    captured = []

    async def _capturing_synthesize(req):
        captured.append(req)
        return mock_result

    with patch.object(client.app.state.tts_worker, "synthesize", side_effect=_capturing_synthesize):
        client.post("/api/tts/synthesize", json={"text": "Hello", "voice_id": "af_heart"})
    assert captured[0].speed == pytest.approx(1.0)


def test_tts_synthesize_passes_custom_speed(client, tmp_path):
    audio_path = str(tmp_path / "out.wav")
    mock_result = _make_fake_result("af_heart", audio_path)
    captured = []

    async def _capturing_synthesize(req):
        captured.append(req)
        return mock_result

    with patch.object(client.app.state.tts_worker, "synthesize", side_effect=_capturing_synthesize):
        client.post(
            "/api/tts/synthesize",
            json={"text": "Hello", "voice_id": "af_heart", "speed": 1.25},
        )
    assert captured[0].speed == pytest.approx(1.25)


# ---------------------------------------------------------------------------
# GET /api/tts/voices — voice list endpoint
# ---------------------------------------------------------------------------


def test_tts_voices_returns_200(client):
    resp = client.get("/api/tts/voices")
    assert resp.status_code == 200


def test_tts_voices_returns_list(client):
    body = client.get("/api/tts/voices").json()
    assert "voices" in body
    assert len(body["voices"]) > 0


def test_tts_voices_all_have_required_fields(client):
    voices = client.get("/api/tts/voices").json()["voices"]
    for v in voices:
        assert "voice_id" in v
        assert "display_name" in v
        assert "engine" in v
        assert "gender" in v
        assert "locale" in v


def test_tts_voices_no_clone_or_import_endpoint_exists(client):
    # Verify there is no voice upload or cloning endpoint in the API.
    # 404 = route doesn't exist; 405 = path exists but method not allowed — both
    # confirm that no cloning/import capability is exposed.
    for method, path in [
        ("post", "/api/tts/clone"),
        ("post", "/api/tts/voices/upload"),
        ("post", "/api/tts/voices/import"),
        ("put", "/api/tts/voices"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code in (404, 405), (
            f"Unexpected success for {method.upper()} {path}: got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Fake TTS worker — smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_tts_worker_synthesize_returns_wav_file():
    from convsim_core.tts.fake import FakeTtsWorker

    worker = FakeTtsWorker()
    result = await worker.synthesize(
        __import__("convsim_core.tts.types", fromlist=["TtsRequest"]).TtsRequest(
            text="Hello world", voice_id="af_heart"
        )
    )
    assert os.path.isfile(result.audio_path)
    assert result.audio_path.endswith(".wav")
    os.unlink(result.audio_path)


@pytest.mark.asyncio
async def test_fake_tts_worker_wav_has_riff_header():
    from convsim_core.tts.fake import FakeTtsWorker
    from convsim_core.tts.types import TtsRequest

    worker = FakeTtsWorker()
    result = await worker.synthesize(TtsRequest(text="Test", voice_id="am_adam"))
    with open(result.audio_path, "rb") as f:
        header = f.read(4)
    os.unlink(result.audio_path)
    assert header == b"RIFF"


@pytest.mark.asyncio
async def test_fake_tts_worker_rejects_unknown_voice():
    from convsim_core.tts.fake import FakeTtsWorker
    from convsim_core.tts.types import TtsRequest

    worker = FakeTtsWorker()
    with pytest.raises(TtsVoiceValidationError):
        await worker.synthesize(TtsRequest(text="Hello", voice_id="unknown_voice"))


@pytest.mark.asyncio
async def test_fake_tts_worker_health_is_ready():
    from convsim_core.tts.fake import FakeTtsWorker
    from convsim_core.runtime.types import RuntimeStatus

    worker = FakeTtsWorker()
    health = await worker.health()
    assert health.status == RuntimeStatus.READY
    assert health.worker_id == "fake"
    assert health.voice_count > 0


# ---------------------------------------------------------------------------
# /api/health — TTS field
# ---------------------------------------------------------------------------


def test_health_tts_field_present(client):
    body = client.get("/api/health").json()
    assert "tts" in body


def test_health_tts_worker_id_present(client):
    tts = client.get("/api/health").json()["tts"]
    assert "worker_id" in tts


def test_health_tts_status_present(client):
    tts = client.get("/api/health").json()["tts"]
    assert "status" in tts


def test_health_tts_checked_at_present(client):
    tts = client.get("/api/health").json()["tts"]
    assert tts["checked_at"]


def test_health_tts_unavailable_when_kokoro_not_running(client):
    # Default config uses kokoro worker; in the test environment no Kokoro server
    # is running, so the worker returns status='unavailable'.
    tts = client.get("/api/health").json()["tts"]
    assert tts["worker_id"] == "kokoro"
    assert tts["status"] == "unavailable"
