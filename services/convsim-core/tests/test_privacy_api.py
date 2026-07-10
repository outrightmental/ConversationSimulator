# SPDX-License-Identifier: Apache-2.0
"""Tests for the /api/privacy endpoints."""
from pathlib import Path


def test_get_data_folder_returns_200(client):
    response = client.get("/api/privacy/data-folder")
    assert response.status_code == 200


def test_get_data_folder_has_path(client):
    data = client.get("/api/privacy/data-folder").json()
    assert "path" in data
    assert isinstance(data["path"], str)


def test_get_data_folder_is_absolute(client):
    data = client.get("/api/privacy/data-folder").json()
    assert Path(data["path"]).is_absolute()


def test_get_folders_returns_200(client):
    response = client.get("/api/privacy/folders")
    assert response.status_code == 200


_ALL_FOLDER_KEYS = ("data", "logs", "models", "packs", "exports", "cache", "crash_bundles")


def test_get_folders_has_all_keys(client):
    data = client.get("/api/privacy/folders").json()
    for key in _ALL_FOLDER_KEYS:
        assert key in data, f"missing key: {key}"


def test_get_folders_all_paths_are_strings(client):
    data = client.get("/api/privacy/folders").json()
    for key in _ALL_FOLDER_KEYS:
        assert isinstance(data[key], str), f"{key} is not a string"


def test_get_folders_all_paths_are_absolute(client):
    data = client.get("/api/privacy/folders").json()
    for key in _ALL_FOLDER_KEYS:
        assert Path(data[key]).is_absolute(), f"{key} path is not absolute: {data[key]}"


def test_get_folders_exports_path_uses_exports_dir(client):
    data = client.get("/api/privacy/folders").json()
    assert "exports" in data["exports"].lower() or len(data["exports"]) > 0


def test_exports_folder_created_at_startup(client):
    """The exports folder must exist on startup so the desktop 'Open exports
    folder' button works on a fresh install, before anything is exported."""
    data = client.get("/api/privacy/folders").json()
    assert Path(data["exports"]).is_dir()


def test_cache_folder_created_at_startup(client):
    """The cache folder must exist on startup."""
    data = client.get("/api/privacy/folders").json()
    assert Path(data["cache"]).is_dir()


def test_crash_bundles_folder_created_at_startup(client):
    """The crash bundles folder must exist on startup."""
    data = client.get("/api/privacy/folders").json()
    assert Path(data["crash_bundles"]).is_dir()


def test_nosteamcloudpath_written_to_user_data_dirs(client):
    """Each mutable user-data dir must have a .nosteamcloudpath marker.

    models (model files) is explicitly named in issue #221 as data that must
    not reach Steam Cloud, so it must be marked alongside the other dirs.
    """
    data = client.get("/api/privacy/folders").json()
    for key in ("data", "logs", "packs", "exports", "cache", "crash_bundles", "models"):
        marker = Path(data[key]) / ".nosteamcloudpath"
        assert marker.exists(), f".nosteamcloudpath missing in {key} folder: {data[key]}"


def test_nosteamcloudpath_written_to_db_dir(client):
    """The db directory holds conversation transcripts and prompts, which issue
    #221 requires be kept out of Steam Cloud; it must carry the marker even
    though it is not exposed by the /privacy/folders endpoint."""
    db_dir = Path(client.app.state.service_config.db_dir)
    assert (db_dir / ".nosteamcloudpath").exists(), (
        f".nosteamcloudpath missing in db folder: {db_dir}"
    )


def test_post_clear_returns_200(client):
    response = client.post("/api/privacy/clear")
    assert response.status_code == 200


def test_post_clear_returns_deleted_sessions_field(client):
    data = client.post("/api/privacy/clear").json()
    assert "deleted_sessions" in data
    assert isinstance(data["deleted_sessions"], int)


def test_post_clear_with_no_sessions_returns_zero(client):
    data = client.post("/api/privacy/clear").json()
    assert data["deleted_sessions"] == 0
