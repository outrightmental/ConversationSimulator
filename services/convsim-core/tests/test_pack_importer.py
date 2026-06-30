# SPDX-License-Identifier: Apache-2.0
"""Unit tests for pack import with rollback-on-failure guarantees."""
import io
import json
import zipfile
from pathlib import Path

import pytest

import convsim_core.packs.importer as _importer_mod
from convsim_core.errors import ConvsimError
from convsim_core.packs.importer import (
    PackConflictError,
    safe_extract_zip,
    import_from_folder,
    import_from_zip,
)
from convsim_core.storage.database import Database
from convsim_core.storage.repositories.pack_repo import get_pack_by_slug, list_packs
from tests.helpers import make_pack_dir, make_pack_zip


# ── helpers ──────────────────────────────────────────────────────────────────

def _open_db(tmp_path: Path) -> Database:
    return Database.open(str(tmp_path / "db"))


def _make_zip_slip_zip(dest_component: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(dest_component + "/pack.json", json.dumps({}))
    return buf.getvalue()


# ── zip extraction safety ─────────────────────────────────────────────────────

def test_zip_slip_dotdot_rejected(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    slip_zip = _make_zip_slip_zip("../evil")
    exc = pytest.raises(ConvsimError, safe_extract_zip, slip_zip, dest)
    assert exc.value.code == "ZIP_SLIP"


def test_zip_absolute_path_rejected(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/etc/passwd", "root:x:0:0")
    dest = tmp_path / "out"
    dest.mkdir()
    exc = pytest.raises(ConvsimError, safe_extract_zip, buf.getvalue(), dest)
    assert exc.value.code == "ZIP_SLIP"


def test_zip_symlink_external_attr_rejected(tmp_path):
    """Zip entries with Unix symlink external_attr must be rejected."""
    import stat as _stat
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("pack/evil_link")
        info.external_attr = (_stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/tmp/outside")
    dest = tmp_path / "out"
    dest.mkdir()
    exc = pytest.raises(ConvsimError, safe_extract_zip, buf.getvalue(), dest)
    assert exc.value.code == "ZIP_SLIP"


def test_zip_bomb_rejected(tmp_path, monkeypatch):
    """Archives whose total uncompressed size exceeds the limit must be rejected."""
    monkeypatch.setattr(_importer_mod, "_MAX_UNCOMPRESSED_BYTES", 1024)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pack/bigfile.bin", b"A" * 2048)
    dest = tmp_path / "out"
    dest.mkdir()
    exc = pytest.raises(ConvsimError, safe_extract_zip, buf.getvalue(), dest)
    assert exc.value.code == "ZIP_TOO_LARGE"


def test_valid_zip_extracts_normally(tmp_path):
    pack_dir = make_pack_dir(tmp_path / "src")
    zip_bytes = make_pack_zip(tmp_path / "src")
    dest = tmp_path / "out"
    dest.mkdir()
    safe_extract_zip(zip_bytes, dest)
    assert (dest / "pack" / "pack.json").exists()


# ── folder import ─────────────────────────────────────────────────────────────

def test_import_from_folder_succeeds(tmp_path):
    db = _open_db(tmp_path)
    pack_dir = make_pack_dir(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    result = import_from_folder(pack_dir, packs_dir, db.connection())

    assert result.pack_slug == "test.sample_pack"
    assert result.scenarios_indexed >= 1
    assert result.assets_indexed >= 1

    pack = get_pack_by_slug(db.connection(), "test.sample_pack")
    assert pack is not None
    assert pack.version == "1.0.0"
    db.close()


def test_import_missing_folder_raises(tmp_path):
    db = _open_db(tmp_path)
    exc = pytest.raises(ConvsimError, import_from_folder, tmp_path / "no_such_dir", tmp_path / "packs", db.connection())
    assert exc.value.code == "NOT_FOUND"
    db.close()


def test_import_invalid_pack_leaves_no_files(tmp_path):
    db = _open_db(tmp_path)
    # Pack with a forbidden .sh file
    pack_dir = make_pack_dir(tmp_path / "src", extra_files={"bad.sh": b"#!/bin/sh"})
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    exc = pytest.raises(ConvsimError, import_from_folder, pack_dir, packs_dir, db.connection())
    assert exc.value.code == "PACK_INVALID"

    # No partial installation must remain
    assert list(packs_dir.iterdir()) == []
    assert list_packs(db.connection()) == []
    db.close()


def test_duplicate_pack_raises_conflict(tmp_path):
    db = _open_db(tmp_path)
    pack_dir = make_pack_dir(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_folder(pack_dir, packs_dir, db.connection())

    with pytest.raises(PackConflictError):
        import_from_folder(pack_dir, packs_dir, db.connection())
    db.close()


# ── zip import ────────────────────────────────────────────────────────────────

def test_import_from_zip_succeeds(tmp_path):
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    result = import_from_zip(zip_bytes, packs_dir, db.connection())

    assert result.pack_slug == "test.sample_pack"
    assert result.assets_indexed >= 1
    db.close()


def test_import_bad_zip_raises(tmp_path):
    db = _open_db(tmp_path)
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()
    exc = pytest.raises(ConvsimError, import_from_zip, b"not a zip file at all", packs_dir, db.connection())
    assert exc.value.code == "INVALID_ZIP"
    db.close()


def test_import_invalid_zip_pack_no_partial_files(tmp_path):
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src", extra_files={"virus.exe": b"MZ"})
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    exc = pytest.raises(ConvsimError, import_from_zip, zip_bytes, packs_dir, db.connection())
    assert exc.value.code == "PACK_INVALID"

    assert list_packs(db.connection()) == []
    db.close()


def test_import_records_assets_in_index(tmp_path):
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())

    rows = db.connection().execute("SELECT * FROM asset_index").fetchall()
    assert len(rows) > 0
    # At least one image asset for npc.png
    types = {r["asset_type"] for r in rows}
    assert "image" in types
    db.close()


def test_import_asset_index_has_relative_path(tmp_path):
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())

    rows = db.connection().execute("SELECT relative_path, media_type FROM asset_index").fetchall()
    rel_paths = [r["relative_path"] for r in rows]
    assert any("scenarios/intro.yaml" in (p or "") for p in rel_paths)
    db.close()


def test_import_asset_index_file_paths_point_to_installed_location(tmp_path):
    """file_path in asset_index must reflect the final install path, not the staging dir."""
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())

    rows = db.connection().execute("SELECT file_path FROM asset_index").fetchall()
    assert len(rows) > 0
    for row in rows:
        assert Path(row["file_path"]).exists(), f"Stale file_path in asset_index: {row['file_path']!r}"
    db.close()


def test_import_different_version_same_id_raises_conflict(tmp_path):
    """A new version of an already-installed pack id must be rejected (same dir, would overwrite)."""
    db = _open_db(tmp_path)
    pack_dir = make_pack_dir(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_folder(pack_dir, packs_dir, db.connection())

    pack_dir_v2 = make_pack_dir(tmp_path / "src2", manifest={"version": "2.0.0"})
    with pytest.raises(PackConflictError):
        import_from_folder(pack_dir_v2, packs_dir, db.connection())
    db.close()


def test_import_links_scenario_scoped_assets(tmp_path):
    """Assets stored under scenarios/<slug>/ must have scenario_id set in asset_index."""
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(
        tmp_path / "src",
        extra_files={
            "scenarios/intro/portraits/npc2.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 10,
        },
    )
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())

    rows = db.connection().execute(
        "SELECT relative_path, scenario_id FROM asset_index WHERE scenario_id IS NOT NULL"
    ).fetchall()
    assert len(rows) > 0, "Expected at least one asset linked to a scenario via scenario_id"
    rel_paths = [r["relative_path"] for r in rows]
    assert any("intro" in p for p in rel_paths), (
        f"Expected an asset under scenarios/intro/ to be linked; got: {rel_paths}"
    )
    db.close()
