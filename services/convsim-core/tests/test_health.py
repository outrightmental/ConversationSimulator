# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path

from convsim_core import __version__


def test_health_returns_200(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_status_ok(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_health_version(client):
    assert client.get("/api/health").json()["version"] == __version__


def test_health_pid(client):
    assert client.get("/api/health").json()["pid"] == os.getpid()


def test_health_database_status_ok(client):
    body = client.get("/api/health").json()
    assert body["database"]["status"] == "ok"


def test_health_database_path_present(client, tmp_config):
    body = client.get("/api/health").json()
    db_path = body["database"]["path"]
    assert db_path is not None
    assert Path(db_path).exists()
    assert db_path.endswith("convsim.sqlite")


def test_health_database_migrations_applied(client):
    body = client.get("/api/health").json()
    assert body["database"]["migrations_applied"] >= 1


def test_health_runtime_fields_exist(client):
    rt = client.get("/api/health").json()["runtime"]
    assert rt["runtime_id"] == "fake"
    assert rt["runtime_name"] == "Fake (deterministic)"
    assert rt["status"] == "ready"
    assert "checked_at" in rt


def test_health_config_path_present(client):
    body = client.get("/api/health").json()
    assert "config_path" in body
    assert isinstance(body["config_path"], str)


def test_health_privacy_posture_present(client):
    body = client.get("/api/health").json()
    assert "privacy" in body


def test_health_privacy_telemetry_disabled(client):
    privacy = client.get("/api/health").json()["privacy"]
    assert privacy["telemetry_enabled"] is False


def test_health_privacy_raw_audio_disabled(client):
    privacy = client.get("/api/health").json()["privacy"]
    assert privacy["save_raw_audio"] is False


def test_health_privacy_posture_has_all_fields(client):
    privacy = client.get("/api/health").json()["privacy"]
    assert "telemetry_enabled" in privacy
    assert "save_transcripts" in privacy
    assert "save_raw_audio" in privacy
    assert "crash_logging_enabled" in privacy


def test_health_stt_field_present(client):
    body = client.get("/api/health").json()
    assert "stt" in body


def test_health_stt_worker_id(client):
    stt = client.get("/api/health").json()["stt"]
    # Default config uses whisper_cpp; no binary in test env → unavailable.
    assert stt["worker_id"] == "whisper_cpp"


def test_health_stt_worker_name(client):
    stt = client.get("/api/health").json()["stt"]
    assert "whisper" in stt["worker_name"].lower()


def test_health_stt_status_unavailable_when_no_runtime(client):
    stt = client.get("/api/health").json()["stt"]
    # No binary installed in the test environment.
    assert stt["status"] == "unavailable"


def test_health_stt_checked_at_present(client):
    stt = client.get("/api/health").json()["stt"]
    assert stt["checked_at"]
