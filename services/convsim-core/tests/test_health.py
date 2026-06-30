# SPDX-License-Identifier: Apache-2.0
import os

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


def test_health_database_placeholder(client):
    body = client.get("/api/health").json()
    assert body["database"]["status"] == "unavailable"


def test_health_runtime_readiness_fields_exist(client):
    rt = client.get("/api/health").json()["runtime"]
    assert rt["llm_ready"] is False
    assert rt["stt_ready"] is False
    assert rt["tts_ready"] is False


def test_health_config_path_present(client):
    body = client.get("/api/health").json()
    assert "config_path" in body
    assert isinstance(body["config_path"], str)
