# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from convsim_core.config import ServiceConfig
from convsim_core.storage.database import Database
from convsim_core.storage.repositories.settings_repo import load_settings


def test_get_settings_returns_200(client):
    assert client.get("/api/settings").status_code == 200


def test_get_settings_privacy_defaults(client):
    body = client.get("/api/settings").json()
    assert body["save_transcripts"] is False
    assert body["save_raw_audio"] is False
    assert body["telemetry_enabled"] is False
    assert body["crash_logging_enabled"] is False
    assert body["tts_cache_enabled"] is True


def test_put_settings_round_trip(client, tmp_path):
    payload = {
        "data_dir": str(tmp_path / "data"),
        "log_dir": str(tmp_path / "logs"),
        "save_transcripts": True,
        "save_raw_audio": False,
        "tts_cache_enabled": False,
        "telemetry_enabled": False,
        "crash_logging_enabled": True,
    }
    put_resp = client.put("/api/settings", json=payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["save_transcripts"] is True

    get_resp = client.get("/api/settings")
    assert get_resp.status_code == 200
    assert get_resp.json()["save_transcripts"] is True
    assert get_resp.json()["tts_cache_enabled"] is False
    assert get_resp.json()["crash_logging_enabled"] is True


def test_put_settings_invalid_body_returns_structured_error(client, tmp_config):
    resp = client.put("/api/settings", json={
        "data_dir": tmp_config.data_dir,
        "log_dir": tmp_config.log_dir,
        "save_transcripts": "not-a-bool",
    })
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_put_settings_missing_required_field_returns_structured_error(client):
    resp = client.put("/api/settings", json={"save_transcripts": True})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_put_settings_persists_to_database(client, tmp_config):
    """Settings must be persisted to the SQLite database, not a JSON file."""
    payload = {
        "data_dir": tmp_config.data_dir,
        "log_dir": tmp_config.log_dir,
        "save_transcripts": True,
        "save_raw_audio": False,
        "tts_cache_enabled": False,
        "telemetry_enabled": False,
        "crash_logging_enabled": True,
    }
    resp = client.put("/api/settings", json=payload)
    assert resp.status_code == 200

    # Verify by reading directly from the database
    fresh_db = Database.open(tmp_config.db_dir)
    try:
        settings = load_settings(fresh_db.connection(), tmp_config.data_dir, tmp_config.log_dir)
        assert settings.save_transcripts is True
        assert settings.tts_cache_enabled is False
        assert settings.crash_logging_enabled is True
        assert settings.telemetry_enabled is False
        assert settings.save_raw_audio is False
    finally:
        fresh_db.close()


def test_host_config_rejects_0_0_0_0():
    with pytest.raises((ValueError, ValidationError)):
        ServiceConfig(host="0.0.0.0", lan_access_enabled=False)


def test_host_config_rejects_ipv6_wildcard():
    with pytest.raises((ValueError, ValidationError)):
        ServiceConfig(host="::", lan_access_enabled=False)


def test_host_config_allows_localhost():
    config = ServiceConfig(host="127.0.0.1", lan_access_enabled=False)
    assert config.host == "127.0.0.1"
