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


# ---------------------------------------------------------------------------
# Kokoro TTS worker — mocked backend (httpx) integration tests
#
# These exercise the real KokoroTtsWorker HTTP path (payload, caching, and
# error mapping) with a fake httpx client, since the endpoint tests above mock
# worker.synthesize wholesale and never reach the Kokoro adapter itself.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = ""):
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeAsyncClient:
    """Minimal async-context-manager stand-in for httpx.AsyncClient."""

    def __init__(self, *, response=None, post_exc=None, get_exc=None):
        self._response = response
        self._post_exc = post_exc
        self._get_exc = get_exc
        self.post_calls = []
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        self.post_calls.append((url, json))
        if self._post_exc is not None:
            raise self._post_exc
        return self._response

    async def get(self, url):
        self.get_calls.append(url)
        if self._get_exc is not None:
            raise self._get_exc
        return self._response


def _make_kokoro(tmp_path):
    from convsim_core.tts.kokoro import KokoroConfig, KokoroTtsWorker

    return KokoroTtsWorker(KokoroConfig(cache_dir=str(tmp_path / "tts_cache")))


@pytest.mark.asyncio
async def test_kokoro_synthesize_connect_error_maps_to_unavailable(tmp_path):
    import httpx

    from convsim_core.tts.types import TtsRequest

    worker = _make_kokoro(tmp_path)
    fake = _FakeAsyncClient(post_exc=httpx.ConnectError("connection refused"))
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        with pytest.raises(TtsUnavailableError):
            await worker.synthesize(TtsRequest(text="Hi", voice_id="af_heart"))


@pytest.mark.asyncio
async def test_kokoro_synthesize_writes_cache_file_under_cache_dir(tmp_path):
    from convsim_core.tts.kokoro import KokoroConfig, KokoroTtsWorker
    from convsim_core.tts.types import TtsRequest

    cache_dir = tmp_path / "tts_cache"
    worker = KokoroTtsWorker(KokoroConfig(cache_dir=str(cache_dir)))
    fake = _FakeAsyncClient(response=_FakeResponse(200, content=b"RIFFfake-wav-bytes"))
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        result = await worker.synthesize(TtsRequest(text="Hi", voice_id="af_heart"))

    # Generated audio must stay under the local cache directory.
    assert os.path.commonpath([str(cache_dir), result.audio_path]) == str(cache_dir)
    assert os.path.isfile(result.audio_path)
    with open(result.audio_path, "rb") as f:
        assert f.read() == b"RIFFfake-wav-bytes"
    assert result.voice_id == "af_heart"


@pytest.mark.asyncio
async def test_kokoro_synthesize_sends_expected_payload(tmp_path):
    from convsim_core.tts.types import TtsRequest

    worker = _make_kokoro(tmp_path)
    fake = _FakeAsyncClient(response=_FakeResponse(200, content=b"wav"))
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        await worker.synthesize(TtsRequest(text="Hello", voice_id="am_adam", speed=1.25))

    assert len(fake.post_calls) == 1
    url, payload = fake.post_calls[0]
    assert url.endswith("/v1/audio/speech")
    assert payload["voice"] == "am_adam"
    assert payload["input"] == "Hello"
    assert payload["response_format"] == "wav"
    assert payload["speed"] == pytest.approx(1.25)


@pytest.mark.asyncio
async def test_kokoro_synthesize_reuses_cache_without_second_request(tmp_path):
    from convsim_core.tts.types import TtsRequest

    worker = _make_kokoro(tmp_path)
    fake = _FakeAsyncClient(response=_FakeResponse(200, content=b"wav"))
    req = TtsRequest(text="Same text", voice_id="af_heart")
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        first = await worker.synthesize(req)
        second = await worker.synthesize(req)

    assert first.audio_path == second.audio_path
    # Second call is served from cache, so the backend is hit only once.
    assert len(fake.post_calls) == 1


@pytest.mark.asyncio
async def test_kokoro_synthesize_non_200_raises_error(tmp_path):
    from convsim_core.tts.types import TtsError, TtsRequest

    worker = _make_kokoro(tmp_path)
    fake = _FakeAsyncClient(response=_FakeResponse(500, content=b"", text="boom"))
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        with pytest.raises(TtsError) as exc_info:
            await worker.synthesize(TtsRequest(text="Hi", voice_id="af_heart"))
    # Non-200 is a recoverable backend error, not an unavailability signal.
    assert not isinstance(exc_info.value, TtsUnavailableError)


@pytest.mark.asyncio
async def test_kokoro_synthesize_rejects_unknown_voice_before_http(tmp_path):
    from convsim_core.tts.types import TtsRequest

    worker = _make_kokoro(tmp_path)
    fake = _FakeAsyncClient(response=_FakeResponse(200, content=b"wav"))
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        with pytest.raises(TtsVoiceValidationError):
            await worker.synthesize(TtsRequest(text="Hi", voice_id="clone:stolen_voice"))
    assert fake.post_calls == []


def test_kokoro_construction_does_not_create_cache_dir(tmp_path):
    from convsim_core.tts.kokoro import KokoroConfig, KokoroTtsWorker

    cache_dir = tmp_path / "tts_cache"
    # Constructing the worker must not touch the filesystem — the cache dir is
    # created lazily on the first successful synthesis, not at startup.
    KokoroTtsWorker(KokoroConfig(cache_dir=str(cache_dir)))
    assert not cache_dir.exists()


@pytest.mark.asyncio
async def test_kokoro_health_unavailable_when_server_unreachable(tmp_path):
    import httpx

    from convsim_core.runtime.types import RuntimeStatus

    worker = _make_kokoro(tmp_path)
    fake = _FakeAsyncClient(get_exc=httpx.ConnectError("refused"))
    with patch("convsim_core.tts.kokoro.httpx.AsyncClient", lambda **kw: fake):
        health = await worker.health()
    assert health.status == RuntimeStatus.UNAVAILABLE
    assert health.worker_id == "kokoro"
