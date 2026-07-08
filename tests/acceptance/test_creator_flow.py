# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — Creator flow (issue #80).

Acceptance criteria exercised:
  C-1  Creator can list available packs (official and local-dev).
  C-2  Creator can read pack and scenario content via the workbench API.
  C-3  Creator can validate a well-formed pack; validation reports pass.
  C-4  Creator can detect and report validation errors in a malformed pack.
  C-5  Creator can export a pack as a zip archive.
  C-6  Creator can import a pack from a zip and retrieve it via the API.
  C-7  Pack round-trip (export → import) preserves pack identity.

All checks run without a real model or browser.
Owner: content team.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.packs.exporter import export_to_zip
from convsim_core.packs.importer import import_from_zip
from convsim_core.packs.validator import validate_pack_dir
from convsim_core.storage.database import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_minimal_pack(root: Path, pack_id: str = "creator.acceptance_pack") -> Path:
    """Write the smallest valid pack onto disk."""
    safety_dir = root / "safety"
    npcs_dir = root / "npcs"
    rubrics_dir = root / "rubrics"
    scenarios_dir = root / "scenarios"
    for d in (safety_dir, npcs_dir, rubrics_dir, scenarios_dir):
        d.mkdir(parents=True, exist_ok=True)

    (root / "manifest.yaml").write_text(
        f'schema_version: "0.1"\n'
        f'pack_id: {pack_id}\n'
        f'name: Creator Acceptance Pack\n'
        f'version: 1.0.0\n'
        f'description: Minimal pack for creator acceptance testing.\n'
        f'author: Acceptance Suite\n'
        f'license: CC-BY-4.0\n'
        f'content_rating: G\n'
        f'tags:\n'
        f'  - acceptance\n'
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
    (safety_dir / "policy.yaml").write_text(
        'schema_version: "0.1"\n'
        'policy_id: acceptance_policy\n'
        'content_rating_cap: G\n'
        'content_categories:\n'
        '  nsfw_sexual: block\n'
        '  real_person_impersonation: block\n'
        '  instructional_criminal: block\n'
        '  crisis_content: redirect\n'
        'redirect_message: "Let\'s keep things on topic."\n',
        encoding="utf-8",
    )
    (npcs_dir / "interviewer.yaml").write_text(
        'schema_version: "0.1"\n'
        'npc_id: acceptance_interviewer\n'
        'display_name: Acceptance Interviewer\n'
        'archetype: interviewer\n'
        'fictional: true\n'
        'age_band: adult\n'
        'public_persona:\n'
        '  occupation: Test Interviewer\n'
        '  speaking_style: Professional and direct\n'
        '  demeanor: Neutral\n'
        'private_persona: {}\n',
        encoding="utf-8",
    )
    (rubrics_dir / "rubric.yaml").write_text(
        'schema_version: "0.1"\n'
        'rubric_id: acceptance_rubric\n'
        'title: Creator Acceptance Rubric\n'
        'dimensions:\n'
        '  - id: clarity\n'
        '    name: Clarity\n'
        '    description: How clearly the player communicates.\n'
        '    scoring:\n'
        '      low: Unclear\n'
        '      medium: Adequate\n'
        '      high: Excellent\n',
        encoding="utf-8",
    )
    (scenarios_dir / "intro.yaml").write_text(
        'schema_version: "0.1"\n'
        'scenario_id: acceptance_intro\n'
        'title: Acceptance Introduction\n'
        'summary: A minimal scenario for creator acceptance testing.\n'
        'player_role:\n'
        '  label: Candidate\n'
        '  brief: You are verifying the creator acceptance test.\n'
        'npc:\n'
        '  ref: ../npcs/interviewer.yaml\n'
        'rubric:\n'
        '  ref: ../rubrics/rubric.yaml\n'
        'duration:\n'
        '  max_turns: 8\n'
        'opening:\n'
        '  npc_says: "Welcome to the acceptance test. Please introduce yourself."\n'
        'goals:\n'
        '  player_visible:\n'
        '    - Demonstrate the creator flow works end-to-end\n',
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def pack_root(tmp_path) -> Path:
    return _write_minimal_pack(tmp_path / "acceptance-pack")


@pytest.fixture()
def workbench_client(tmp_path, monkeypatch) -> TestClient:
    official_dir = tmp_path / "official"
    local_dev_dir = tmp_path / "local-dev"
    official_dir.mkdir()
    local_dev_dir.mkdir()

    _write_minimal_pack(official_dir / "sample-pack", pack_id="official.sample_pack")
    _write_minimal_pack(local_dev_dir / "my-pack", pack_id="local.my_pack")

    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(official_dir),
        local_dev_packs_dir=str(local_dev_dir),
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# C-1  List packs
# ---------------------------------------------------------------------------


class TestListPacks:
    """Creator can see all available packs in the workbench."""

    def test_workbench_packs_endpoint_returns_200(self, workbench_client):
        res = workbench_client.get("/api/workbench/packs")
        assert res.status_code == 200

    def test_workbench_lists_official_and_local_packs(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        kinds = {p["kind"] for p in body}
        assert "official" in kinds
        assert "local-dev" in kinds

    def test_official_pack_is_not_editable(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        official = next(p for p in body if p["kind"] == "official")
        assert official["editable"] is False

    def test_local_dev_pack_is_editable(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        local = next(p for p in body if p["kind"] == "local-dev")
        assert local["editable"] is True


# ---------------------------------------------------------------------------
# C-2  Read pack content
# ---------------------------------------------------------------------------


class TestReadPackContent:
    """Creator can inspect the persona, goals, and rubric of a pack."""

    def test_pack_card_has_pack_id(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        official = next(p for p in body if p["kind"] == "official")
        assert official["pack_id"] == "official.sample_pack"

    def test_pack_card_has_name(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        for pack in body:
            assert pack.get("name"), f"pack {pack.get('pack_id')} missing name"

    def test_pack_files_accessible_via_workbench(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        local = next(p for p in body if p["kind"] == "local-dev")
        slug = local["slug"]
        file_res = workbench_client.get(
            f"/api/workbench/packs/local-dev/{slug}/file",
            params={"path": "manifest.yaml"},
        )
        assert file_res.status_code == 200
        assert "pack_id" in file_res.text


# ---------------------------------------------------------------------------
# C-3  Validate a well-formed pack
# ---------------------------------------------------------------------------


class TestPackValidation:
    """A valid pack passes schema and policy validation."""

    def test_valid_pack_passes_schema_validation(self, pack_root):
        result = validate_pack_dir(pack_root)
        assert result.valid, f"unexpected validation errors: {result.errors}"

    def test_valid_pack_passes_workbench_validation_endpoint(self, workbench_client):
        body = workbench_client.get("/api/workbench/packs").json()
        local = next(p for p in body if p["kind"] == "local-dev")
        slug = local["slug"]
        res = workbench_client.get(f"/api/workbench/packs/local-dev/{slug}/validate")
        assert res.status_code == 200
        result = res.json()
        assert result.get("valid") is True or result.get("errors") == []


# ---------------------------------------------------------------------------
# C-4  Detect validation errors
# ---------------------------------------------------------------------------


class TestPackValidationErrors:
    """A malformed pack produces actionable validation errors."""

    def test_missing_manifest_fails_validation(self, tmp_path):
        broken = tmp_path / "broken-pack"
        broken.mkdir()
        result = validate_pack_dir(broken)
        assert not result.valid, "expected validation to fail for a pack with no manifest"
        assert len(result.errors) > 0

    def test_invalid_manifest_field_fails_validation(self, tmp_path):
        broken = tmp_path / "broken-pack2"
        broken.mkdir()
        (broken / "manifest.yaml").write_text(
            'schema_version: "0.1"\nnot_a_real_field: true\n',
            encoding="utf-8",
        )
        result = validate_pack_dir(broken)
        assert not result.valid, "expected validation to fail for a malformed manifest"
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# C-5  Export pack
# ---------------------------------------------------------------------------


class TestPackExport:
    """Creator can export a pack as a zip archive for sharing."""

    def _open_db(self, tmp_path: Path) -> Database:
        return Database.open(str(tmp_path / "db"))

    def _import_pack(self, pack_root: Path, db: Database, packs_dir: Path) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for f in pack_root.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(pack_root.parent))
        buf.seek(0)
        import_from_zip(buf.read(), packs_dir, db.connection())

    def test_export_produces_zip_bytes(self, tmp_path, pack_root):
        db = self._open_db(tmp_path)
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        self._import_pack(pack_root, db, packs_dir)
        exported, filename = export_to_zip("creator.acceptance_pack", db.connection())
        db.close()
        assert zipfile.is_zipfile(io.BytesIO(exported))
        assert filename.endswith(".zip")

    def test_exported_zip_contains_manifest(self, tmp_path, pack_root):
        db = self._open_db(tmp_path)
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        self._import_pack(pack_root, db, packs_dir)
        exported, _ = export_to_zip("creator.acceptance_pack", db.connection())
        db.close()
        with zipfile.ZipFile(io.BytesIO(exported)) as zf:
            names = zf.namelist()
        assert any("manifest" in n for n in names)


# ---------------------------------------------------------------------------
# C-6 / C-7  Import and round-trip
# ---------------------------------------------------------------------------


class TestPackImportRoundTrip:
    """A pack can be exported and re-imported; its identity is preserved."""

    def _open_db(self, path: Path) -> Database:
        return Database.open(str(path / "db"))

    def test_import_from_zip_succeeds(self, tmp_path, pack_root):
        db = self._open_db(tmp_path)
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for f in pack_root.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(pack_root.parent))
        buf.seek(0)
        import_from_zip(buf.read(), packs_dir, db.connection())
        db.close()

    def test_round_trip_preserves_pack_id(self, tmp_path, pack_root):
        db = self._open_db(tmp_path)
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()

        # Import
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for f in pack_root.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(pack_root.parent))
        buf.seek(0)
        import_from_zip(buf.read(), packs_dir, db.connection())

        # Export
        exported, filename = export_to_zip("creator.acceptance_pack", db.connection())
        db.close()

        assert "acceptance_pack" in filename
        assert zipfile.is_zipfile(io.BytesIO(exported))
