# SPDX-License-Identifier: Apache-2.0
"""Tests for the /api/diag endpoints."""
import json
import zipfile
from pathlib import Path


def test_get_logs_folder_returns_200(client):
    response = client.get("/api/diag/logs-folder")
    assert response.status_code == 200


def test_get_logs_folder_returns_string_path(client):
    data = client.get("/api/diag/logs-folder").json()
    assert "logs_folder" in data
    assert isinstance(data["logs_folder"], str)


def test_get_logs_folder_is_absolute(client):
    data = client.get("/api/diag/logs-folder").json()
    assert Path(data["logs_folder"]).is_absolute()


def test_post_crash_bundle_returns_200(client):
    response = client.post("/api/diag/crash-bundle")
    assert response.status_code == 200


def test_post_crash_bundle_returns_bundle_path(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert "bundle_path" in data
    assert isinstance(data["bundle_path"], str)


def test_post_crash_bundle_file_exists(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert Path(data["bundle_path"]).exists()


def test_post_crash_bundle_is_valid_zip(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert zipfile.is_zipfile(data["bundle_path"])


def test_post_crash_bundle_contains_required_files(client):
    data = client.post("/api/diag/crash-bundle").json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
    assert "versions.json" in names
    assert "config.json" in names
    assert "recent_errors.txt" in names
    assert "system.txt" in names
    assert "README.txt" in names


def test_post_crash_bundle_notice_present(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert "notice" in data
    assert len(data["notice"]) > 0


def test_post_crash_bundle_notice_mentions_local(client):
    data = client.post("/api/diag/crash-bundle").json()
    notice = data["notice"].lower()
    assert "local" in notice or "manually" in notice


def test_post_crash_bundle_notice_not_transmitted(client):
    data = client.post("/api/diag/crash-bundle").json()
    notice = data["notice"].lower()
    assert "never" in notice or "not" in notice


def test_post_crash_bundle_versions_has_app(client):
    data = client.post("/api/diag/crash-bundle").json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        versions = json.loads(zf.read("versions.json"))
    assert "app" in versions


def test_post_crash_bundle_written_to_crash_bundles_dir(client):
    """The bundle must land in the exposed crash_bundles_dir, not the log dir.

    issue #221 exposes an 'Open Crash Bundles Folder' action; the bundles the
    user is directed to must actually be written into that folder.
    """
    crash_bundles_dir = Path(client.app.state.service_config.crash_bundles_dir).resolve()
    data = client.post("/api/diag/crash-bundle").json()
    bundle_path = Path(data["bundle_path"]).resolve()
    assert bundle_path.parent == crash_bundles_dir, (
        f"crash bundle written to {bundle_path.parent}, not crash_bundles_dir {crash_bundles_dir}"
    )
