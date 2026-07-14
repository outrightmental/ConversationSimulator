# SPDX-License-Identifier: Apache-2.0
"""Tests for /api/runtime/settings (GET / PUT / reset)."""

_SETTING_KEYS = (
    "context_length",
    "gpu_layers",
    "threads",
    "temperature",
    "top_p",
    "repeat_penalty",
)


def test_get_runtime_settings_returns_200(client):
    resp = client.get("/api/runtime/settings")
    assert resp.status_code == 200


def test_get_runtime_settings_shape(client):
    body = client.get("/api/runtime/settings").json()
    assert "settings" in body
    assert "recommended" in body
    assert body["requires_restart"] is False
    for key in _SETTING_KEYS:
        assert key in body["settings"]
        assert key in body["recommended"]


def test_get_runtime_settings_defaults_are_null(client):
    settings = client.get("/api/runtime/settings").json()["settings"]
    assert all(settings[key] is None for key in _SETTING_KEYS)


def test_put_runtime_settings_persists(client):
    resp = client.put(
        "/api/runtime/settings",
        json={"context_length": 4096, "temperature": 0.7},
    )
    assert resp.status_code == 200
    assert resp.json()["settings"]["context_length"] == 4096

    settings = client.get("/api/runtime/settings").json()["settings"]
    assert settings["context_length"] == 4096
    assert settings["temperature"] == 0.7
    assert settings["threads"] is None


def test_put_runtime_settings_partial_update_preserves_others(client):
    client.put("/api/runtime/settings", json={"threads": 8})
    client.put("/api/runtime/settings", json={"top_p": 0.9})
    settings = client.get("/api/runtime/settings").json()["settings"]
    assert settings["threads"] == 8
    assert settings["top_p"] == 0.9


def test_put_runtime_settings_restart_flag_for_context_length(client):
    resp = client.put("/api/runtime/settings", json={"context_length": 8192})
    assert resp.json()["requires_restart"] is True


def test_put_runtime_settings_no_restart_for_sampling_params(client):
    resp = client.put("/api/runtime/settings", json={"temperature": 1.0})
    assert resp.json()["requires_restart"] is False


def test_put_runtime_settings_rejects_invalid_context_length(client):
    resp = client.put("/api/runtime/settings", json={"context_length": 100})
    assert resp.status_code == 422
    assert "Context length" in resp.json()["error"]["message"]


def test_put_runtime_settings_rejects_invalid_temperature(client):
    resp = client.put("/api/runtime/settings", json={"temperature": 5.0})
    assert resp.status_code == 422


def test_put_runtime_settings_rejects_invalid_gpu_layers(client):
    resp = client.put("/api/runtime/settings", json={"gpu_layers": -5})
    assert resp.status_code == 422


def test_put_runtime_settings_accepts_null_to_clear(client):
    client.put("/api/runtime/settings", json={"threads": 8})
    client.put("/api/runtime/settings", json={"threads": None})
    settings = client.get("/api/runtime/settings").json()["settings"]
    assert settings["threads"] is None


def test_reset_runtime_settings(client):
    client.put("/api/runtime/settings", json={"context_length": 4096, "threads": 8})
    resp = client.post("/api/runtime/settings/reset")
    assert resp.status_code == 200
    body = resp.json()
    assert all(body["settings"][key] is None for key in _SETTING_KEYS)
    assert body["requires_restart"] is True


def test_runtime_settings_do_not_break_app_settings(client):
    """runtime_setting.* keys share user_settings; AppSettings must ignore them."""
    client.put("/api/runtime/settings", json={"temperature": 0.5})
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["privacy"]["telemetry_enabled"] is False
