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


def test_health_runtime_readiness_fields_exist(client):
    rt = client.get("/api/health").json()["runtime"]
    assert rt["llm_ready"] is False
    assert rt["stt_ready"] is False
    assert rt["tts_ready"] is False


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
