# SPDX-License-Identifier: Apache-2.0
"""Integration tests for Creator Workbench API endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


def _make_pack(root: Path, slug: str, name: str, pack_id: str) -> Path:
    pack_dir = root / slug
    (pack_dir / "scenarios").mkdir(parents=True, exist_ok=True)
    (pack_dir / "npcs").mkdir(parents=True, exist_ok=True)
    (pack_dir / "manifest.yaml").write_text(
        f'schema_version: "0.1"\npack_id: {pack_id}\nname: {name}\nversion: 0.1.0\n',
        encoding="utf-8",
    )
    (pack_dir / "README.md").write_text(f"# {name}\n\nA test pack.\n", encoding="utf-8")
    (pack_dir / "scenarios" / "basic.yaml").write_text(
        'schema_version: "0.1"\nscenario_id: basic\ntitle: Basic Scenario\n',
        encoding="utf-8",
    )
    return pack_dir


@pytest.fixture()
def roots(tmp_path):
    official = tmp_path / "official"
    local_dev = tmp_path / "local-dev"
    official.mkdir()
    local_dev.mkdir()
    _make_pack(official, "sample-pack", "Sample Pack", "official.sample_pack")
    _make_pack(local_dev, "my-pack", "My Pack", "local.my_pack")
    return official, local_dev


@pytest.fixture()
def client(tmp_path, roots, monkeypatch):
    official, local_dev = roots
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(official),
        local_dev_packs_dir=str(local_dev),
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/workbench/packs
# ---------------------------------------------------------------------------

def test_list_packs(client):
    resp = client.get("/api/workbench/packs")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)

    official = next(p for p in body if p["kind"] == "official")
    assert official["slug"] == "sample-pack"
    assert official["editable"] is False

    local = next(p for p in body if p["kind"] == "local-dev")
    assert local["slug"] == "my-pack"
    assert local["editable"] is True


def test_list_packs_returns_manifest_basics(client):
    body = client.get("/api/workbench/packs").json()
    official = next(p for p in body if p["kind"] == "official")
    assert official["pack_id"] == "official.sample_pack"
    assert official["name"] == "Sample Pack"


# ---------------------------------------------------------------------------
# GET /api/workbench/packs/{kind}/{slug}/files
# ---------------------------------------------------------------------------

def test_file_tree(client):
    resp = client.get("/api/workbench/packs/official/sample-pack/files")
    assert resp.status_code == 200
    tree = resp.json()["tree"]

    manifest = next(n for n in tree if n["name"] == "manifest.yaml")
    assert manifest["kind"] == "yaml"

    readme = next(n for n in tree if n["name"] == "README.md")
    assert readme["kind"] == "markdown"

    scenarios = next(n for n in tree if n["name"] == "scenarios")
    assert scenarios["kind"] == "dir"
    # Directories sort first and contain nested files.
    assert tree[0]["kind"] == "dir"
    assert any(child["name"] == "basic.yaml" for child in scenarios["children"])


def test_file_tree_unknown_pack_returns_404(client):
    resp = client.get("/api/workbench/packs/official/does-not-exist/files")
    assert resp.status_code == 404


def test_file_tree_invalid_kind_returns_400(client):
    resp = client.get("/api/workbench/packs/community/sample-pack/files")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/workbench/packs/{kind}/{slug}/file
# ---------------------------------------------------------------------------

def test_read_official_file(client):
    resp = client.get(
        "/api/workbench/packs/official/sample-pack/file", params={"path": "README.md"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Sample Pack" in body["content"]
    assert body["editable"] is False


def test_read_local_dev_file_is_editable(client):
    resp = client.get(
        "/api/workbench/packs/local-dev/my-pack/file", params={"path": "manifest.yaml"}
    )
    assert resp.status_code == 200
    assert resp.json()["editable"] is True


def test_read_file_missing_path_returns_400(client):
    resp = client.get("/api/workbench/packs/official/sample-pack/file")
    assert resp.status_code == 400


def test_read_file_directory_returns_400(client):
    resp = client.get(
        "/api/workbench/packs/official/sample-pack/file", params={"path": "scenarios"}
    )
    assert resp.status_code == 400


def test_read_file_path_traversal_returns_400(client):
    resp = client.get(
        "/api/workbench/packs/official/sample-pack/file",
        params={"path": "../../etc/passwd"},
    )
    assert resp.status_code == 400


def test_read_file_dot_returns_400(client):
    resp = client.get(
        "/api/workbench/packs/official/sample-pack/file", params={"path": "."}
    )
    assert resp.status_code == 400


def test_read_file_missing_returns_404(client):
    resp = client.get(
        "/api/workbench/packs/official/sample-pack/file", params={"path": "ghost.yaml"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/workbench/packs/{kind}/{slug}/file
# ---------------------------------------------------------------------------

def test_write_local_dev_file(client):
    new_content = 'schema_version: "0.1"\nname: Updated\n'
    resp = client.put(
        "/api/workbench/packs/local-dev/my-pack/file",
        params={"path": "manifest.yaml"},
        json={"content": new_content},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    read_back = client.get(
        "/api/workbench/packs/local-dev/my-pack/file", params={"path": "manifest.yaml"}
    )
    assert read_back.json()["content"] == new_content


def test_write_official_file_returns_403(client):
    resp = client.put(
        "/api/workbench/packs/official/sample-pack/file",
        params={"path": "manifest.yaml"},
        json={"content": "evil"},
    )
    assert resp.status_code == 403


def test_write_non_editable_type_returns_400(client):
    resp = client.put(
        "/api/workbench/packs/local-dev/my-pack/file",
        params={"path": "image.png"},
        json={"content": "binary"},
    )
    assert resp.status_code == 400


def test_write_path_traversal_returns_400(client):
    resp = client.put(
        "/api/workbench/packs/local-dev/my-pack/file",
        params={"path": "../../etc/cron.d/evil"},
        json={"content": "evil"},
    )
    assert resp.status_code == 400


def test_write_missing_path_returns_400(client):
    resp = client.put(
        "/api/workbench/packs/local-dev/my-pack/file",
        json={"content": "hello"},
    )
    assert resp.status_code == 400


def test_write_dot_returns_400(client):
    resp = client.put(
        "/api/workbench/packs/local-dev/my-pack/file",
        params={"path": "."},
        json={"content": "hello"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/workbench/packs/{kind}/{slug}/copy-to-local
# ---------------------------------------------------------------------------

def test_copy_to_local(client):
    resp = client.post("/api/workbench/packs/official/sample-pack/copy-to-local")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "local-dev"
    assert "sample-pack" in body["slug"]
    assert body["editable"] is True

    packs = client.get("/api/workbench/packs").json()
    assert any(p["slug"] == body["slug"] for p in packs)

    # The copied file is now writable.
    write = client.put(
        f"/api/workbench/packs/local-dev/{body['slug']}/file",
        params={"path": "README.md"},
        json={"content": "# edited\n"},
    )
    assert write.status_code == 200


def test_copy_local_dev_returns_400(client):
    resp = client.post("/api/workbench/packs/local-dev/my-pack/copy-to-local")
    assert resp.status_code == 400


def test_copy_unknown_pack_returns_404(client):
    resp = client.post("/api/workbench/packs/official/does-not-exist/copy-to-local")
    assert resp.status_code == 404


def test_copy_avoids_slug_collision(client):
    slug1 = client.post(
        "/api/workbench/packs/official/sample-pack/copy-to-local"
    ).json()["slug"]
    slug2 = client.post(
        "/api/workbench/packs/official/sample-pack/copy-to-local"
    ).json()["slug"]
    assert slug1 != slug2


# ---------------------------------------------------------------------------
# GET /api/workbench/packs/{kind}/{slug}/validate + save-triggered refresh
# ---------------------------------------------------------------------------

def test_validate_pack_returns_result(client):
    resp = client.get("/api/workbench/packs/local-dev/my-pack/validate")
    assert resp.status_code == 200
    body = resp.json()
    # A well-formed ValidationResult is returned regardless of validity.
    assert isinstance(body["valid"], bool)
    assert isinstance(body["errors"], list)
    assert isinstance(body["warnings"], list)
    # The minimal fixture pack is missing required manifest fields, proving the
    # validator actually ran rather than short-circuiting.
    assert body["valid"] is False
    assert len(body["errors"]) > 0


def test_validate_invalid_kind_returns_400(client):
    resp = client.get("/api/workbench/packs/community/my-pack/validate")
    assert resp.status_code == 400


def test_validate_unknown_pack_returns_404(client):
    resp = client.get("/api/workbench/packs/local-dev/does-not-exist/validate")
    assert resp.status_code == 404


def test_write_refreshes_validation(client):
    # Writing a syntactically-broken manifest surfaces errors in the save
    # response's validation payload — the save "triggers validation refresh".
    resp = client.put(
        "/api/workbench/packs/local-dev/my-pack/file",
        params={"path": "manifest.yaml"},
        json={"content": "schema_version: [unterminated\n"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["validation"] is not None
    assert body["validation"]["valid"] is False
    assert len(body["validation"]["errors"]) > 0
