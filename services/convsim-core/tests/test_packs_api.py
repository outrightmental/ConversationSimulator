# SPDX-License-Identifier: Apache-2.0
"""Integration tests for pack API endpoints."""
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import make_pack_dir, make_pack_zip


# client fixture is inherited from conftest.py


def test_list_packs_empty(client):
    resp = client.get("/api/packs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_import_zip_valid(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path)
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pack_slug"] == "test.sample_pack"
    assert body["scenarios_indexed"] >= 1
    assert body["assets_indexed"] >= 1


def test_list_packs_after_import(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path)
    client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    resp = client.get("/api/packs")
    assert resp.status_code == 200
    packs = resp.json()
    assert len(packs) == 1
    assert packs[0]["slug"] == "test.sample_pack"
    assert packs[0]["license"] == "CC BY 4.0"


def test_import_zip_with_executable_rejected(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path, extra_files={"malware.exe": b"MZ"})
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PACK_INVALID"


def test_import_zip_missing_manifest_rejected(client, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pack/README.txt", "no manifest here")
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 422


def test_import_not_a_zip_rejected(client):
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", b"THIS IS NOT A ZIP", "application/zip")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_ZIP"


def test_import_zip_slip_rejected(client, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil/pack.json", json.dumps({}))
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ZIP_SLIP"


def test_import_duplicate_pack_returns_conflict(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path)
    client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PACK_CONFLICT"


def test_validate_valid_zip_returns_valid(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path)
    resp = client.post(
        "/api/packs/validate",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["pack_id"] == "test.sample_pack"


def test_validate_invalid_zip_returns_errors(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path, extra_files={"hack.sh": b"#!/bin/sh"})
    resp = client.post(
        "/api/packs/validate",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


def test_validate_not_a_zip(client):
    resp = client.post(
        "/api/packs/validate",
        files={"file": ("pack.zip", b"garbage", "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_export_installed_pack(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path)
    client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    resp = client.get("/api/packs/test.sample_pack/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert zipfile.is_zipfile(io.BytesIO(resp.content))


def test_export_unknown_pack_returns_404(client):
    resp = client.get("/api/packs/no_such_pack/export")
    assert resp.status_code == 404


def test_import_folder_endpoint(client, tmp_path):
    pack_dir = make_pack_dir(tmp_path)
    resp = client.post(
        "/api/packs/import/folder",
        json={"path": str(pack_dir)},
    )
    assert resp.status_code == 201
    assert resp.json()["pack_slug"] == "test.sample_pack"


def test_import_folder_missing_path_returns_error(client, tmp_path):
    resp = client.post(
        "/api/packs/import/folder",
        json={"path": str(tmp_path / "does_not_exist")},
    )
    assert resp.status_code == 404


def test_import_folder_path_outside_allowed_dirs_rejected(client, tmp_path):
    """Source paths outside packs_dir and local_dev_packs_dir must be rejected."""
    resp = client.post(
        "/api/packs/import/folder",
        # tmp_path.parent is guaranteed to be outside tmp_path (the local_dev_packs_dir)
        json={"path": str(tmp_path.parent)},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_PATH"
