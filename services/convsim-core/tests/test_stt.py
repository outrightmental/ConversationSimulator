# SPDX-License-Identifier: Apache-2.0
import io


def test_stt_upload_returns_200(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    )
    assert resp.status_code == 200


def test_stt_upload_status_received(client):
    audio = io.BytesIO(b"\x00" * 100)
    body = client.post(
        "/api/stt/upload",
        files={"audio": ("recording.webm", audio, "audio/webm")},
    ).json()
    assert body["status"] == "received"


def test_stt_upload_transcript_is_null(client):
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


def test_stt_upload_requires_audio_field(client):
    resp = client.post("/api/stt/upload")
    assert resp.status_code == 422
