# SPDX-License-Identifier: Apache-2.0
"""Tests for the Steam Cloud settings file (steam_cloud.py and its router)."""
import json
import time

import pytest

from convsim_core.steam_cloud import (
    CLOUD_SETTINGS_FILENAME,
    CloudSettings,
    cloud_settings_path,
    read_cloud_settings,
    schedule_cloud_settings_write,
    write_cloud_settings,
)


# ── cloud_settings_path ───────────────────────────────────────────────────────


def test_cloud_settings_path_is_at_data_root(tmp_path):
    result = cloud_settings_path(tmp_path)
    assert result == tmp_path / CLOUD_SETTINGS_FILENAME


def test_cloud_settings_filename_is_json():
    assert CLOUD_SETTINGS_FILENAME.endswith(".json")


# ── read_cloud_settings ───────────────────────────────────────────────────────


def test_read_returns_defaults_when_file_absent(tmp_path):
    settings = read_cloud_settings(tmp_path)
    assert settings == CloudSettings()
    assert settings.last_model_id is None


def test_read_returns_defaults_for_corrupt_json(tmp_path):
    (tmp_path / CLOUD_SETTINGS_FILENAME).write_text("not valid json", "utf-8")
    settings = read_cloud_settings(tmp_path)
    assert settings == CloudSettings()


def test_read_returns_defaults_for_empty_file(tmp_path):
    (tmp_path / CLOUD_SETTINGS_FILENAME).write_text("", "utf-8")
    settings = read_cloud_settings(tmp_path)
    assert settings == CloudSettings()


def test_read_returns_persisted_last_model_id(tmp_path):
    (tmp_path / CLOUD_SETTINGS_FILENAME).write_text(
        json.dumps({"last_model_id": "qwen3-4b-q4_k_m"}), "utf-8"
    )
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id == "qwen3-4b-q4_k_m"


def test_read_ignores_unknown_fields_in_file(tmp_path):
    (tmp_path / CLOUD_SETTINGS_FILENAME).write_text(
        json.dumps({"last_model_id": "some-model", "future_field": "ignored"}),
        "utf-8",
    )
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id == "some-model"


# ── write_cloud_settings ──────────────────────────────────────────────────────


def test_write_creates_file_at_data_root(tmp_path):
    write_cloud_settings(tmp_path, CloudSettings(last_model_id="llama3-8b"))
    assert (tmp_path / CLOUD_SETTINGS_FILENAME).exists()


def test_write_round_trips_last_model_id(tmp_path):
    write_cloud_settings(tmp_path, CloudSettings(last_model_id="mistral-7b"))
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id == "mistral-7b"


def test_write_round_trips_null_last_model_id(tmp_path):
    write_cloud_settings(tmp_path, CloudSettings(last_model_id=None))
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id is None


def test_write_creates_parent_directories(tmp_path):
    nested_root = tmp_path / "a" / "b" / "c"
    write_cloud_settings(nested_root, CloudSettings())
    assert (nested_root / CLOUD_SETTINGS_FILENAME).exists()


def test_write_produces_valid_json(tmp_path):
    write_cloud_settings(tmp_path, CloudSettings(last_model_id="phi-3-mini"))
    raw = (tmp_path / CLOUD_SETTINGS_FILENAME).read_text("utf-8")
    parsed = json.loads(raw)
    assert parsed["last_model_id"] == "phi-3-mini"


def test_write_overwrites_existing_file(tmp_path):
    write_cloud_settings(tmp_path, CloudSettings(last_model_id="model-a"))
    write_cloud_settings(tmp_path, CloudSettings(last_model_id="model-b"))
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id == "model-b"


# ── schedule_cloud_settings_write (debounce) ──────────────────────────────────


def test_debounced_write_eventually_persists(tmp_path, monkeypatch):
    # Shrink the debounce window so the test finishes quickly.
    monkeypatch.setattr("convsim_core.steam_cloud._DEBOUNCE_SECONDS", 0.05)
    schedule_cloud_settings_write(tmp_path, CloudSettings(last_model_id="fast-model"))
    time.sleep(0.2)
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id == "fast-model"


def test_debounced_write_coalesces_rapid_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("convsim_core.steam_cloud._DEBOUNCE_SECONDS", 0.1)
    # Fire three writes in quick succession; only the last value should persist.
    schedule_cloud_settings_write(tmp_path, CloudSettings(last_model_id="first"))
    schedule_cloud_settings_write(tmp_path, CloudSettings(last_model_id="second"))
    schedule_cloud_settings_write(tmp_path, CloudSettings(last_model_id="third"))
    time.sleep(0.4)
    settings = read_cloud_settings(tmp_path)
    assert settings.last_model_id == "third"


# ── REST API ──────────────────────────────────────────────────────────────────


def test_get_cloud_settings_returns_200(client):
    resp = client.get("/api/cloud-settings")
    assert resp.status_code == 200


def test_get_cloud_settings_returns_defaults_on_fresh_install(client):
    body = client.get("/api/cloud-settings").json()
    assert body["last_model_id"] is None


def test_put_cloud_settings_returns_200(client):
    resp = client.put("/api/cloud-settings", json={"last_model_id": "qwen3-4b"})
    assert resp.status_code == 200


def test_put_cloud_settings_echoes_body(client):
    resp = client.put("/api/cloud-settings", json={"last_model_id": "qwen3-4b"})
    assert resp.json()["last_model_id"] == "qwen3-4b"


def test_put_then_get_round_trip(client, tmp_config):
    import convsim_core.steam_cloud as sc_mod

    # The debounce timer fires asynchronously; bypass it by patching the debounce
    # constant to near-zero so the file is written before the GET is issued.
    original = sc_mod._DEBOUNCE_SECONDS
    sc_mod._DEBOUNCE_SECONDS = 0.0
    try:
        client.put("/api/cloud-settings", json={"last_model_id": "test-model-xyz"})
        time.sleep(0.05)
        resp = client.get("/api/cloud-settings")
        assert resp.json()["last_model_id"] == "test-model-xyz"
    finally:
        sc_mod._DEBOUNCE_SECONDS = original


def test_put_cloud_settings_null_last_model_id(client):
    resp = client.put("/api/cloud-settings", json={"last_model_id": None})
    assert resp.status_code == 200
    assert resp.json()["last_model_id"] is None


def test_cloud_settings_file_does_not_land_inside_nosteamcloudpath_dirs(
    tmp_config, client
):
    """The cloud settings file must be at the data root, not inside any subdir.

    All subdirectories (db/, logs/, models/, etc.) carry .nosteamcloudpath
    markers that exclude them from Steam Cloud.  The cloud settings file must
    sit one level above these markers so Steam Cloud can reach it.
    """
    data_root = __import__("pathlib").Path(tmp_config.data_dir).parent
    import convsim_core.steam_cloud as sc_mod

    original = sc_mod._DEBOUNCE_SECONDS
    sc_mod._DEBOUNCE_SECONDS = 0.0
    try:
        client.put("/api/cloud-settings", json={"last_model_id": "placed-correctly"})
        time.sleep(0.05)
    finally:
        sc_mod._DEBOUNCE_SECONDS = original

    expected_path = data_root / CLOUD_SETTINGS_FILENAME
    assert expected_path.exists(), (
        f"steam_cloud_settings.json not found at data root {data_root}"
    )
    # Verify it is NOT inside any subdirectory with a .nosteamcloudpath marker.
    for subdir in (
        tmp_config.data_dir,
        tmp_config.db_dir,
        tmp_config.log_dir,
        tmp_config.packs_dir,
        tmp_config.exports_dir,
        tmp_config.cache_dir,
        tmp_config.crash_bundles_dir,
    ):
        subdir_path = __import__("pathlib").Path(subdir)
        assert not (subdir_path / CLOUD_SETTINGS_FILENAME).exists(), (
            f"steam_cloud_settings.json must not be inside {subdir_path}"
        )
