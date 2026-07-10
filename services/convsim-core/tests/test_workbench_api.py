# SPDX-License-Identifier: Apache-2.0
"""Integration tests for Creator Workbench API endpoints."""
import io
import zipfile
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


# ---------------------------------------------------------------------------
# POST /api/workbench/packs/import
# ---------------------------------------------------------------------------


def _make_minimal_pack_zip(pack_id: str = "local.test_import") -> bytes:
    """Build an in-memory zip containing a minimal valid pack."""
    buf = io.BytesIO()
    top = "test-import-pack"
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{top}/manifest.yaml", (
            f'schema_version: "0.1"\n'
            f'pack_id: {pack_id}\n'
            f'name: Test Import Pack\n'
            f'version: 1.0.0\n'
            f'description: Minimal import test pack.\n'
            f'author: Test Suite\n'
            f'license: CC-BY-4.0\n'
            f'content_rating: G\n'
            f'tags:\n'
            f'  - test\n'
            f'supported_languages:\n'
            f'  - en\n'
            f'entry_scenarios:\n'
            f'  - scenarios/intro.yaml\n'
            f'assets:\n'
            f'  allow_external_urls: false\n'
            f'safety:\n'
            f'  policy: safety/policy.yaml\n'
        ))
        zf.writestr(f"{top}/safety/policy.yaml", (
            'schema_version: "0.1"\n'
            'policy_id: test_import_policy\n'
            'content_rating_cap: G\n'
            'content_categories:\n'
            '  nsfw_sexual: block\n'
            '  real_person_impersonation: block\n'
            '  instructional_criminal: block\n'
            '  crisis_content: redirect\n'
            'redirect_message: "Let\'s keep things on topic."\n'
        ))
        zf.writestr(f"{top}/npcs/npc.yaml", (
            'schema_version: "0.1"\n'
            'npc_id: test_npc\n'
            'display_name: Test NPC\n'
            'archetype: guide\n'
            'fictional: true\n'
            'age_band: adult\n'
            'public_persona:\n'
            '  occupation: Test Guide\n'
            '  speaking_style: Neutral\n'
            '  demeanor: Friendly\n'
            'private_persona: {}\n'
        ))
        zf.writestr(f"{top}/rubrics/rubric.yaml", (
            'schema_version: "0.1"\n'
            'rubric_id: test_rubric\n'
            'title: Test Rubric\n'
            'dimensions:\n'
            '  - id: clarity\n'
            '    name: Clarity\n'
            '    description: Clear communication.\n'
            '    scoring:\n'
            '      low: Unclear\n'
            '      medium: Adequate\n'
            '      high: Excellent\n'
        ))
        zf.writestr(f"{top}/scenarios/intro.yaml", (
            'schema_version: "0.1"\n'
            'scenario_id: test_intro\n'
            'title: Test Introduction\n'
            'summary: Minimal import test scenario.\n'
            'player_role:\n'
            '  label: Tester\n'
            '  brief: You are testing the import flow.\n'
            'npc:\n'
            '  ref: ../npcs/npc.yaml\n'
            'rubric:\n'
            '  ref: ../rubrics/rubric.yaml\n'
            'duration:\n'
            '  max_turns: 5\n'
            'opening:\n'
            '  npc_says: "Welcome. This is an import test."\n'
            'goals:\n'
            '  player_visible:\n'
            '    - Verify import works\n'
        ))
    return buf.getvalue()


def test_import_pack_success(client):
    zip_bytes = _make_minimal_pack_zip("local.test_import")
    resp = client.post(
        "/api/workbench/packs/import",
        content=zip_bytes,
        headers={"Content-Type": "application/zip"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "local-dev"
    assert body["editable"] is True
    assert body["pack_id"] == "local.test_import"
    assert body.get("renamed_from") is None

    # The imported pack should appear in the pack list.
    packs = client.get("/api/workbench/packs").json()
    assert any(p["slug"] == body["slug"] for p in packs)


def test_import_pack_slug_collision_renames(client):
    # Import the same pack twice; the second import should be renamed.
    zip_bytes = _make_minimal_pack_zip("local.test_collision")
    first = client.post(
        "/api/workbench/packs/import",
        content=zip_bytes,
        headers={"Content-Type": "application/zip"},
    )
    assert first.status_code == 201
    assert first.json().get("renamed_from") is None

    second = client.post(
        "/api/workbench/packs/import",
        content=zip_bytes,
        headers={"Content-Type": "application/zip"},
    )
    assert second.status_code == 201
    body = second.json()
    assert body["renamed_from"] is not None
    assert body["slug"] != first.json()["slug"]


def test_import_pack_invalid_zip_returns_422(client):
    resp = client.post(
        "/api/workbench/packs/import",
        content=b"not a zip",
        headers={"Content-Type": "application/zip"},
    )
    assert resp.status_code == 422


def test_import_pack_validation_failure_returns_422(client):
    # A zip with a broken manifest (missing required fields) must return 422
    # with a structured errors list so the UI can show actionable findings.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bad-pack/manifest.yaml", "schema_version: '0.1'\nnot_a_valid_field: true\n")
    resp = client.post(
        "/api/workbench/packs/import",
        content=buf.getvalue(),
        headers={"Content-Type": "application/zip"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body.get("errors"), list)
    assert len(body["errors"]) > 0


# ---------------------------------------------------------------------------
# GET /api/workbench/packs/{kind}/{slug}/export
# ---------------------------------------------------------------------------


def test_export_pack_returns_zip(client, tmp_path, roots):
    """A valid local-dev pack can be exported as a zip."""
    # The fixture pack is missing required manifest fields, so write a valid one first.
    official, local_dev = roots
    _make_full_pack(local_dev / "export-pack")

    resp = client.get("/api/workbench/packs/local-dev/export-pack/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".zip" in cd
    assert zipfile.is_zipfile(io.BytesIO(resp.content))


def test_export_pack_validation_preflight_returns_422(client):
    """A pack with schema errors must return 422 with an error list before zipping."""
    resp = client.get("/api/workbench/packs/local-dev/my-pack/export")
    # The minimal fixture pack is missing required manifest fields.
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body.get("errors"), list)
    assert len(body["errors"]) > 0


def test_export_pack_unknown_returns_404(client):
    resp = client.get("/api/workbench/packs/local-dev/does-not-exist/export")
    assert resp.status_code == 404


def _make_full_pack(pack_dir: Path, pack_id: str = "local.full_export_pack") -> None:
    """Write a complete, schema-valid pack to pack_dir."""
    (pack_dir / "scenarios").mkdir(parents=True, exist_ok=True)
    (pack_dir / "npcs").mkdir(parents=True, exist_ok=True)
    (pack_dir / "rubrics").mkdir(parents=True, exist_ok=True)
    (pack_dir / "safety").mkdir(parents=True, exist_ok=True)

    (pack_dir / "manifest.yaml").write_text(
        f'schema_version: "0.1"\n'
        f'pack_id: {pack_id}\n'
        f'name: Full Export Pack\n'
        f'version: 1.0.0\n'
        f'description: A schema-valid pack for export testing.\n'
        f'author: Test Suite\n'
        f'license: CC-BY-4.0\n'
        f'content_rating: G\n'
        f'tags:\n'
        f'  - test\n'
        f'supported_languages:\n'
        f'  - en\n'
        f'entry_scenarios:\n'
        f'  - scenarios/intro.yaml\n'
        f'assets:\n'
        f'  allow_external_urls: false\n'
        f'safety:\n'
        f'  policy: safety/policy.yaml\n',
        encoding="utf-8",
    )
    (pack_dir / "safety" / "policy.yaml").write_text(
        'schema_version: "0.1"\n'
        'policy_id: export_test_policy\n'
        'content_rating_cap: G\n'
        'content_categories:\n'
        '  nsfw_sexual: block\n'
        '  real_person_impersonation: block\n'
        '  instructional_criminal: block\n'
        '  crisis_content: redirect\n'
        'redirect_message: "Let\'s stay on topic."\n',
        encoding="utf-8",
    )
    (pack_dir / "npcs" / "npc.yaml").write_text(
        'schema_version: "0.1"\n'
        'npc_id: export_npc\n'
        'display_name: Export NPC\n'
        'archetype: guide\n'
        'fictional: true\n'
        'age_band: adult\n'
        'public_persona:\n'
        '  occupation: Tester\n'
        '  speaking_style: Neutral\n'
        '  demeanor: Friendly\n'
        'private_persona: {}\n',
        encoding="utf-8",
    )
    (pack_dir / "rubrics" / "rubric.yaml").write_text(
        'schema_version: "0.1"\n'
        'rubric_id: export_rubric\n'
        'title: Export Rubric\n'
        'dimensions:\n'
        '  - id: clarity\n'
        '    name: Clarity\n'
        '    description: Clear communication.\n'
        '    scoring:\n'
        '      low: Unclear\n'
        '      medium: OK\n'
        '      high: Great\n',
        encoding="utf-8",
    )
    (pack_dir / "scenarios" / "intro.yaml").write_text(
        'schema_version: "0.1"\n'
        'scenario_id: export_intro\n'
        'title: Export Introduction\n'
        'summary: A valid scenario for export testing.\n'
        'player_role:\n'
        '  label: Tester\n'
        '  brief: You are testing export.\n'
        'npc:\n'
        '  ref: ../npcs/npc.yaml\n'
        'rubric:\n'
        '  ref: ../rubrics/rubric.yaml\n'
        'duration:\n'
        '  max_turns: 5\n'
        'opening:\n'
        '  npc_says: "Export test ready."\n'
        'goals:\n'
        '  player_visible:\n'
        '    - Verify export works\n',
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# POST /api/workbench/packs/{kind}/{slug}/test-session
# ---------------------------------------------------------------------------


def _make_test_session_pack(root: Path, slug: str) -> Path:
    """Write a pack with a proper scenario for test-session testing."""
    pack_dir = root / slug
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "scenarios").mkdir(exist_ok=True)
    (pack_dir / "npcs").mkdir(exist_ok=True)

    (pack_dir / "manifest.yaml").write_text(
        'schema_version: "0.1"\n'
        f'pack_id: local.{slug.replace("-", "_")}\n'
        f'name: {slug}\n'
        'version: 0.1.0\n'
        'entry_scenarios:\n'
        '  - scenarios/intro.yaml\n',
        encoding="utf-8",
    )
    (pack_dir / "npcs" / "guide.yaml").write_text(
        'schema_version: "0.1"\n'
        'npc_id: guide\n'
        'display_name: Guide\n'
        'archetype: guide\n'
        'fictional: true\n'
        'age_band: adult\n'
        'public_persona:\n'
        '  occupation: Guide\n'
        '  speaking_style: Helpful\n'
        '  demeanor: Warm\n'
        'private_persona:\n'
        '  hidden_agenda:\n'
        '    - Help the player\n',
        encoding="utf-8",
    )
    (pack_dir / "scenarios" / "intro.yaml").write_text(
        'schema_version: "0.1"\n'
        'scenario_id: ts_intro\n'
        'title: Test Session Intro\n'
        'summary: Minimal scenario for test session.\n'
        'player_role:\n'
        '  label: Player\n'
        '  brief: You are testing the workbench.\n'
        'npc:\n'
        '  ref: ../npcs/guide.yaml\n'
        'rubric:\n'
        '  ref: ../rubrics/rubric.yaml\n'
        'duration:\n'
        '  max_turns: 5\n'
        'opening:\n'
        '  npc_says: "Hello from the workbench test session."\n'
        'goals:\n'
        '  player_visible:\n'
        '    - Test the session\n',
        encoding="utf-8",
    )
    return pack_dir


@pytest.fixture()
def ts_client(tmp_path, monkeypatch):
    """Client fixture with a pack that has a loadable scenario for test-session tests."""
    official = tmp_path / "official"
    local_dev = tmp_path / "local-dev"
    official.mkdir()
    local_dev.mkdir()
    _make_test_session_pack(local_dev, "ts-pack")

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


def test_start_test_session_returns_session(ts_client):
    resp = ts_client.post("/api/workbench/packs/local-dev/ts-pack/test-session")
    assert resp.status_code == 200
    body = resp.json()
    assert "session_id" in body
    assert body["state"] == "PlayerTurnListening"
    assert isinstance(body["npc_opening"], str)
    assert len(body["npc_opening"]) > 0
    assert isinstance(body["state_vars"], dict)
    assert len(body["state_vars"]) > 0


def test_start_test_session_npc_opening_matches_scenario(ts_client):
    resp = ts_client.post("/api/workbench/packs/local-dev/ts-pack/test-session")
    assert resp.status_code == 200
    assert "Hello from the workbench test session." in resp.json()["npc_opening"]


def test_start_test_session_session_deletable(ts_client):
    resp = ts_client.post("/api/workbench/packs/local-dev/ts-pack/test-session")
    session_id = resp.json()["session_id"]
    del_resp = ts_client.delete(f"/api/sessions/{session_id}")
    assert del_resp.status_code == 204


def test_start_test_session_no_scenario_returns_422(client):
    # The minimal fixture pack (my-pack) has a scenario file but it's just a stub
    # without player_role/npc/opening. However there IS a scenarios/basic.yaml file,
    # so it will be found. The real 422 case is when the pack has NO scenario at all.
    official, local_dev = _get_roots_from_client(client)
    empty_pack = local_dev / "empty-pack"
    empty_pack.mkdir(exist_ok=True)
    (empty_pack / "manifest.yaml").write_text(
        'schema_version: "0.1"\npack_id: local.empty\nname: Empty\nversion: 0.1.0\n',
        encoding="utf-8",
    )

    resp = client.post("/api/workbench/packs/local-dev/empty-pack/test-session")
    assert resp.status_code == 422


def test_start_test_session_unknown_pack_returns_404(client):
    resp = client.post("/api/workbench/packs/local-dev/does-not-exist/test-session")
    assert resp.status_code == 404


def _get_roots_from_client(client) -> tuple:
    """Extract root directories from the test client's app state."""
    config = client.app.state.service_config
    from pathlib import Path
    return Path(config.official_packs_dir), Path(config.local_dev_packs_dir)
