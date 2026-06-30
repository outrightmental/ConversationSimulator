# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from convsim_core.config import ServiceConfig


def test_get_settings_returns_200(client):
    assert client.get("/api/settings").status_code == 200


def test_get_settings_privacy_defaults(client):
    body = client.get("/api/settings").json()
    assert body["save_transcripts"] is False
    assert body["tts_cache_enabled"] is True


def test_put_settings_round_trip(client, tmp_path):
    payload = {
        "data_dir": str(tmp_path / "data"),
        "log_dir": str(tmp_path / "logs"),
        "save_transcripts": True,
        "tts_cache_enabled": False,
    }
    put_resp = client.put("/api/settings", json=payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["save_transcripts"] is True

    get_resp = client.get("/api/settings")
    assert get_resp.status_code == 200
    assert get_resp.json()["save_transcripts"] is True
    assert get_resp.json()["tts_cache_enabled"] is False


def test_put_settings_invalid_body_returns_structured_error(client):
    resp = client.put("/api/settings", json={"save_transcripts": "not-a-bool"})
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_put_settings_missing_required_field_returns_structured_error(client):
    resp = client.put("/api/settings", json={"save_transcripts": True})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_put_settings_persists_to_config_data_dir(client, tmp_config, tmp_path):
    """Settings file must land in config.data_dir regardless of the data_dir field in the body."""
    other_data_dir = str(tmp_path / "other_data")
    payload = {
        "data_dir": other_data_dir,
        "log_dir": str(tmp_path / "logs"),
        "save_transcripts": True,
        "tts_cache_enabled": False,
    }
    resp = client.put("/api/settings", json=payload)
    assert resp.status_code == 200

    settings_at_config = Path(tmp_config.data_dir) / "settings.json"
    settings_at_payload = Path(other_data_dir) / "settings.json"
    assert settings_at_config.exists(), "settings.json must be written to config.data_dir"
    assert not settings_at_payload.exists(), "settings.json must NOT be written to body.data_dir"
    assert json.loads(settings_at_config.read_text())["save_transcripts"] is True


def test_host_config_rejects_0_0_0_0():
    with pytest.raises((ValueError, ValidationError)):
        ServiceConfig(host="0.0.0.0", lan_access_enabled=False)


def test_host_config_allows_localhost():
    config = ServiceConfig(host="127.0.0.1", lan_access_enabled=False)
    assert config.host == "127.0.0.1"
