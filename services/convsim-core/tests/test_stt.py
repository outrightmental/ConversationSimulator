# SPDX-License-Identifier: Apache-2.0
import io
from unittest.mock import AsyncMock, patch

from convsim_core.stt.types import SttError


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
