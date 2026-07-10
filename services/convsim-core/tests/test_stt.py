# SPDX-License-Identifier: Apache-2.0
import io
from unittest.mock import AsyncMock, patch

import pytest

from convsim_core.stt.types import SttError, SttResult


def test_stt_upload_returns_200(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )
    assert resp.status_code == 200


def test_stt_upload_status_unavailable_when_no_runtime(client):
    # Default config uses whisper_cpp worker; in the test environment no binary
    # is installed, so the worker returns status='unavailable' rather than failing.
    audio = io.BytesIO(b"\x00" * 100)
    body = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    ).json()
    assert body["status"] == "unavailable"


def test_stt_upload_transcript_is_null_when_unavailable(client):
    audio = io.BytesIO(b"\x00" * 100)
    body = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    ).json()
    assert body["transcript"] is None


def test_stt_upload_accepts_ogg(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.ogg", audio, "audio/ogg")},
    )
    assert resp.status_code == 200


def test_stt_upload_accepts_wav(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.wav", audio, "audio/wav")},
    )
    assert resp.status_code == 200


def test_stt_upload_accepts_octet_stream(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.bin", audio, "application/octet-stream")},
    )
    assert resp.status_code == 200


def test_stt_upload_rejects_unsupported_content_type(client):
    data = io.BytesIO(b"not audio")
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("file.txt", data, "text/plain")},
    )
    assert resp.status_code == 415


def test_stt_upload_rejects_oversized_audio(client):
    big_audio = io.BytesIO(b"\x00" * (25 * 1024 * 1024 + 1))
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("big.webm", big_audio, "audio/webm")},
    )
    assert resp.status_code == 413


def test_stt_upload_accepts_empty_content_type(client):
    # An empty/missing content-type should default to application/octet-stream (accepted),
    # not silently bypass the allowlist check entirely.
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "")},
    )
    assert resp.status_code == 200


def test_stt_upload_requires_audio_field(client):
    resp = client.post("/api/stt/upload")
    assert resp.status_code == 422


def test_stt_upload_response_has_status_field(client):
    audio = io.BytesIO(b"\x00" * 100)
    body = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    ).json()
    assert "status" in body


def test_stt_upload_accepts_language_form_field(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
        data={"language": "fr"},
    )
    assert resp.status_code == 200


def test_stt_upload_language_field_is_optional(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )
    assert resp.status_code == 200


def test_stt_upload_status_error_on_worker_failure(client):
    # Simulate whisper-cli crashing (e.g. bad audio, non-zero exit) — the router
    # must return status='error' with null transcript rather than a 500.
    audio = io.BytesIO(b"\x00" * 100)
    with patch.object(
        client.app.state.stt_worker,
        "transcribe",
        new=AsyncMock(side_effect=SttError("whisper-cli exited with code 1: error: bad input")),
    ):
        body = client.post(
            "/api/stt/upload",
            files={"audio": ("recording.webm", audio, "audio/webm")},
        ).json()
    assert body["status"] == "error"
    assert body["transcript"] is None


def test_stt_upload_status_ok_on_successful_transcription(client):
    # Simulate a working STT worker returning a real transcript.
    audio = io.BytesIO(b"\x00" * 100)
    mock_result = SttResult(
        transcript="Hello world",
        language="en",
        confidence=0.95,
        duration_ms=1200.0,
        processing_ms=350.0,
    )
    with patch.object(
        client.app.state.stt_worker,
        "transcribe",
        new=AsyncMock(return_value=mock_result),
    ):
        body = client.post(
            "/api/stt/upload",
            files={"audio": ("recording.webm", audio, "audio/webm")},
        ).json()
    assert body["status"] == "ok"
    assert body["transcript"] == "Hello world"
    assert body["language"] == "en"
    assert body["confidence"] == pytest.approx(0.95)


def test_stt_upload_ok_response_passes_language_to_worker(client):
    # Language form field should be forwarded to the STT worker.
    audio = io.BytesIO(b"\x00" * 100)
    mock_result = SttResult(transcript="Bonjour", language="fr")
    captured: list = []

    async def _capturing_transcribe(req):
        captured.append(req)
        return mock_result

    with patch.object(client.app.state.stt_worker, "transcribe", side_effect=_capturing_transcribe):
        client.post(
            "/api/stt/upload",
            files={"audio": ("recording.webm", audio, "audio/webm")},
            data={"language": "fr"},
        )
    assert captured[0].language == "fr"


# ---------------------------------------------------------------------------
# GET /api/stt/health
# ---------------------------------------------------------------------------


def test_stt_health_returns_200(client):
    resp = client.get("/api/stt/health")
    assert resp.status_code == 200


def test_stt_health_response_has_worker_id(client):
    body = client.get("/api/stt/health").json()
    assert "worker_id" in body


def test_stt_health_response_has_status(client):
    body = client.get("/api/stt/health").json()
    assert body["status"] in ("unavailable", "starting", "ready", "degraded", "error")


def test_stt_health_unavailable_when_binary_missing(client):
    # Default test config pins whisper-cli to a nonexistent path → UNAVAILABLE.
    body = client.get("/api/stt/health").json()
    assert body["status"] == "unavailable"


def test_stt_health_response_has_checked_at(client):
    body = client.get("/api/stt/health").json()
    assert body["checked_at"]


# ---------------------------------------------------------------------------
# Local-only behavior — raw audio is not saved by default
# ---------------------------------------------------------------------------


def test_raw_audio_not_saved_to_disk_by_default(client, tmp_path):
    # Verify that with save_raw_audio=False (the default), no file is written
    # under the data directory when an audio clip is uploaded.
    data_dir = str(tmp_path / "data")
    client.app.state.app_settings.save_raw_audio = False
    client.app.state.app_settings.data_dir = data_dir

    audio = io.BytesIO(b"\x00" * 100)
    client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )

    audio_dir = tmp_path / "data" / "audio"
    assert not audio_dir.exists(), "Audio directory must not be created when save_raw_audio=False"


def test_raw_audio_saved_to_disk_when_setting_enabled(client, tmp_path):
    # When the user explicitly opts in, the raw audio must be persisted locally.
    data_dir = str(tmp_path / "data")
    client.app.state.app_settings.save_raw_audio = True
    client.app.state.app_settings.data_dir = data_dir

    audio = io.BytesIO(b"\xde\xad\xbe\xef" * 25)
    client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )

    audio_dir = tmp_path / "data" / "audio"
    saved_files = list(audio_dir.glob("*.webm"))
    assert len(saved_files) == 1, "Exactly one audio file must be written when save_raw_audio=True"


def test_raw_audio_saved_file_contains_original_bytes(client, tmp_path):
    data_dir = str(tmp_path / "data")
    client.app.state.app_settings.save_raw_audio = True
    client.app.state.app_settings.data_dir = data_dir

    payload = b"\xca\xfe\xba\xbe" * 50
    audio = io.BytesIO(payload)
    client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )

    saved = list((tmp_path / "data" / "audio").glob("*.webm"))[0]
    assert saved.read_bytes() == payload


# ---------------------------------------------------------------------------
# Text fallback — STT unavailable must not prevent text submission
# ---------------------------------------------------------------------------


def test_text_fallback_status_is_unavailable_not_error(client):
    # When the STT runtime is missing the response status must be 'unavailable',
    # not 'error'. The UI shows a text-only prompt only for 'unavailable'.
    audio = io.BytesIO(b"\x00" * 100)
    body = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    ).json()
    # Default test env has no whisper-cli binary → unavailable
    assert body["status"] == "unavailable"
    assert body["transcript"] is None


def test_text_fallback_returns_200_not_5xx(client):
    # Even when STT is unavailable the HTTP status must be 200 so the frontend
    # can read the body and show the text-entry fallback.
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Non-English language support
# ---------------------------------------------------------------------------


def test_stt_upload_non_english_language_accepted(client):
    # Non-English language codes (BCP-47) must be accepted without HTTP error.
    for lang in ("fr", "ja", "es", "de", "zh"):
        audio = io.BytesIO(b"\x00" * 100)
        resp = client.post(
            "/api/stt/upload",
            files={"audio": ("recording.webm", audio, "audio/webm")},
            data={"language": lang},
        )
        assert resp.status_code == 200, f"Expected 200 for language={lang!r}, got {resp.status_code}"


def test_stt_upload_non_english_transcript_returned(client):
    # Verify that a non-English transcript is returned verbatim.
    audio = io.BytesIO(b"\x00" * 100)
    mock_result = SttResult(transcript="Bonjour le monde", language="fr", confidence=0.9)
    with patch.object(
        client.app.state.stt_worker,
        "transcribe",
        new=AsyncMock(return_value=mock_result),
    ):
        body = client.post(
            "/api/stt/upload",
            files={"audio": ("recording.webm", audio, "audio/webm")},
            data={"language": "fr"},
        ).json()
    assert body["status"] == "ok"
    assert body["transcript"] == "Bonjour le monde"
    assert body["language"] == "fr"
