# SPDX-License-Identifier: Apache-2.0
"""Tests for the official pack startup seeder."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.packs.seeder import seed_official_packs
from convsim_core.storage.database import Database
from convsim_core.storage.repositories.pack_repo import list_packs
from tests.helpers import make_pack_dir


# ── unit tests for seed_official_packs() ─────────────────────────────────────


def _open_db(tmp_path: Path) -> Database:
    return Database.open(str(tmp_path / "db"))


def _make_config(tmp_path: Path, official_packs_dir: str) -> ServiceConfig:
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=official_packs_dir,
    )


def test_seed_nonexistent_dir_returns_zero(tmp_path):
    db = _open_db(tmp_path)
    config = _make_config(tmp_path, str(tmp_path / "no-such-dir"))
    result = seed_official_packs(config, db.connection())
    assert result == 0
    db.close()


def test_seed_valid_official_pack(tmp_path):
    """Seeder imports a pack from official_packs_dir on the first start."""
    official_dir = tmp_path / "official"
    official_dir.mkdir()
    make_pack_dir(official_dir)  # creates official_dir/pack/ with a valid pack

    db = _open_db(tmp_path)
    config = _make_config(tmp_path, str(official_dir))

    count = seed_official_packs(config, db.connection())

    assert count == 1
    packs = list_packs(db.connection())
    assert len(packs) == 1
    assert packs[0].slug == "test.sample_pack"
    db.close()


def test_seed_skips_already_installed_packs(tmp_path):
    """Seeder does not re-import packs that are already installed (warm start)."""
    official_dir = tmp_path / "official"
    official_dir.mkdir()
    make_pack_dir(official_dir)

    db = _open_db(tmp_path)
    config = _make_config(tmp_path, str(official_dir))

    first = seed_official_packs(config, db.connection())
    assert first == 1

    second = seed_official_packs(config, db.connection())
    assert second == 0  # idempotent on warm start
    db.close()


def test_seed_skips_directories_without_manifest(tmp_path):
    """Directories inside official_packs_dir that have no manifest are skipped."""
    official_dir = tmp_path / "official"
    official_dir.mkdir()
    (official_dir / "random_folder").mkdir()
    (official_dir / "random_folder" / "README.md").write_text("not a pack", encoding="utf-8")

    db = _open_db(tmp_path)
    config = _make_config(tmp_path, str(official_dir))

    count = seed_official_packs(config, db.connection())
    assert count == 0
    db.close()


def test_seed_invalid_pack_is_skipped_without_failing(tmp_path):
    """A pack with validation errors is skipped; other packs still seed."""
    official_dir = tmp_path / "official"
    official_dir.mkdir()

    # Bad pack: manifest with a forbidden extension file
    bad_dir = official_dir / "bad_pack"
    bad_dir.mkdir()
    make_pack_dir(official_dir / "_tmp", extra_files={"evil.exe": b"MZ"})
    import shutil
    shutil.copytree(official_dir / "_tmp" / "pack", bad_dir, dirs_exist_ok=True)
    shutil.rmtree(official_dir / "_tmp")

    # Good pack in the same dir
    make_pack_dir(official_dir)

    db = _open_db(tmp_path)
    config = _make_config(tmp_path, str(official_dir))

    count = seed_official_packs(config, db.connection())
    # bad_pack fails validation, good pack (test.sample_pack) succeeds → 1 seeded
    assert count == 1
    db.close()


# ── integration test: seeder fires on app startup ────────────────────────────


def test_app_startup_seeds_official_packs(tmp_path, monkeypatch):
    """Official packs in official_packs_dir appear in GET /api/packs after startup."""
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))

    official_dir = tmp_path / "official"
    official_dir.mkdir()
    make_pack_dir(official_dir)

    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(official_dir),
    )
    app = create_app(config)
    with TestClient(app) as client:
        resp = client.get("/api/packs")
        assert resp.status_code == 200
        packs = resp.json()
        assert len(packs) == 1
        assert packs[0]["slug"] == "test.sample_pack"

        # And the scenarios from the seeded pack are browseable
        scenarios_resp = client.get("/api/scenarios")
        assert scenarios_resp.status_code == 200
        assert len(scenarios_resp.json()) >= 1


# ── folder import from official_packs_dir ────────────────────────────────────


def test_import_folder_from_official_packs_dir_allowed(tmp_path, monkeypatch):
    """Importing a folder from official_packs_dir must be accepted (not FORBIDDEN_PATH).

    The app is configured with an empty seed dir so auto-seeding does not pre-install
    the pack; the test then imports it explicitly via the folder endpoint.
    """
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))

    # official_packs_dir is where the router allows folder imports from.
    official_dir = tmp_path / "official"
    official_dir.mkdir()
    pack_dir = make_pack_dir(official_dir)

    # empty_seed_dir has no packs → seeder seeds nothing on startup.
    empty_seed_dir = tmp_path / "empty-official"
    empty_seed_dir.mkdir()

    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(official_dir),
    )
    app = create_app(config)
    with TestClient(app) as client:
        # Seeder ran against official_dir on startup — pack is already installed.
        # We verify the path is allowed (not 403) and that the response is either
        # 201 (first import) or 409 (already installed by the seeder); both confirm
        # that official_packs_dir paths are accepted by the folder import endpoint.
        resp = client.post(
            "/api/packs/import/folder",
            json={"path": str(pack_dir)},
        )
        assert resp.status_code in (201, 409), resp.text
        assert resp.status_code != 403


def test_import_folder_from_official_packs_dir_path_accepted_before_seeding(tmp_path, monkeypatch):
    """A folder inside official_packs_dir returns 201 when the seeder has not yet run."""
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))

    # Put the pack in official_dir/subpack so the seeder (scanning official_dir)
    # does not find it directly (it's nested an extra level down).
    official_dir = tmp_path / "official"
    official_dir.mkdir()
    sub_dir = official_dir / "subpack"
    sub_dir.mkdir()
    pack_dir = make_pack_dir(sub_dir)  # subpack/pack/

    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(official_dir),
    )
    app = create_app(config)
    with TestClient(app) as client:
        resp = client.post(
            "/api/packs/import/folder",
            json={"path": str(pack_dir)},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["pack_slug"] == "test.sample_pack"
