# SPDX-License-Identifier: Apache-2.0
"""HTTP-endpoint tests for the VAD router (/api/vad/health, /api/vad/calibrate).

These mirror the STT router tests: they exercise media-type validation, the
size cap, and the graceful-degradation contract (calibration always returns a
usable threshold with status "ok" even when Silero/onnxruntime is unavailable).
"""
import io
import struct
import wave


def _make_wav_bytes(n_frames: int = 16000, sample_rate: int = 16000, amplitude: float = 0.01) -> bytes:
    """Build a minimal 16-bit mono WAV of near-silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        samples = [int(amplitude * 32767)] * n_frames
        w.writeframes(struct.pack(f"{n_frames}h", *samples))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# /api/vad/health
# ---------------------------------------------------------------------------


def test_vad_health_returns_200(client):
    resp = client.get("/api/vad/health")
    assert resp.status_code == 200


def test_vad_health_reports_worker_and_status(client):
    # Default config uses the silero_vad worker; onnxruntime is not installed in
    # the test environment, so it reports UNAVAILABLE rather than failing.
    body = client.get("/api/vad/health").json()
    assert body["worker_id"] == "silero_vad"
    assert body["status"] in {"unavailable", "starting", "ready", "degraded", "error"}
    assert body["checked_at"]


# ---------------------------------------------------------------------------
# /api/vad/calibrate — content-type validation
# ---------------------------------------------------------------------------


def test_vad_calibrate_rejects_unsupported_content_type(client):
    data = io.BytesIO(b"not audio")
    resp = client.post(
        "/api/vad/calibrate",
        files={"audio": ("file.txt", data, "text/plain")},
    )
    assert resp.status_code == 415


def test_vad_calibrate_rejects_oversized_audio(client):
    big_audio = io.BytesIO(b"\x00" * (10 * 1024 * 1024 + 1))
    resp = client.post(
        "/api/vad/calibrate",
        files={"audio": ("big.webm", big_audio, "audio/webm")},
    )
    assert resp.status_code == 413


def test_vad_calibrate_accepts_webm(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/vad/calibrate",
        files={"audio": ("calibration.webm", audio, "audio/webm")},
    )
    assert resp.status_code == 200


def test_vad_calibrate_accepts_ogg(client):
    audio = io.BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/vad/calibrate",
        files={"audio": ("calibration.ogg", audio, "audio/ogg")},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/vad/calibrate — graceful-degradation contract
# ---------------------------------------------------------------------------


def test_vad_calibrate_wav_returns_ok_with_usable_threshold(client):
    """A decodable WAV yields status "ok" and a threshold in (0, 1] even without
    onnxruntime (energy-only calibration)."""
    wav = _make_wav_bytes(amplitude=0.02)
    body = client.post(
        "/api/vad/calibrate",
        files={"audio": ("calibration.wav", io.BytesIO(wav), "audio/wav")},
    ).json()
    assert body["status"] == "ok"
    assert 0.0 < body["recommended_threshold"] <= 1.0
    assert body["noise_floor"] >= 0.0
    assert body["worker_id"] == "silero_vad"


def test_vad_calibrate_undecodable_audio_still_returns_ok_default(client):
    """Undecodable audio degrades to a static default threshold, never an error."""
    body = client.post(
        "/api/vad/calibrate",
        files={"audio": ("calibration.webm", io.BytesIO(b"not really audio"), "audio/webm")},
    ).json()
    assert body["status"] == "ok"
    assert 0.0 < body["recommended_threshold"] <= 1.0
