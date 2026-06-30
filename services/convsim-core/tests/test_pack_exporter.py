# SPDX-License-Identifier: Apache-2.0
"""Tests for pack export to zip and round-trip re-validation."""
import io
import zipfile
from pathlib import Path

import pytest

from convsim_core.errors import ConvsimError
from convsim_core.packs.exporter import export_to_zip
from convsim_core.packs.importer import import_from_zip
from convsim_core.packs.validator import validate_pack_dir
from convsim_core.storage.database import Database
from tests.helpers import make_pack_zip


def _open_db(tmp_path: Path) -> Database:
    return Database.open(str(tmp_path / "db"))


def test_export_unknown_pack_raises(tmp_path):
    db = _open_db(tmp_path)
    exc = pytest.raises(ConvsimError, export_to_zip, "no_such_pack", db.connection())
    assert exc.value.code == "NOT_FOUND"
    db.close()


def test_export_produces_zip_bytes(tmp_path):
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())
    exported, filename = export_to_zip("test.sample_pack", db.connection())

    assert zipfile.is_zipfile(io.BytesIO(exported))
    assert "sample_pack" in filename
    assert filename.endswith(".zip")
    db.close()


def test_exported_zip_contains_manifest(tmp_path):
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())
    exported, _ = export_to_zip("test.sample_pack", db.connection())

    with zipfile.ZipFile(io.BytesIO(exported)) as zf:
        names = zf.namelist()
    assert any(n.endswith("pack.json") for n in names)
    db.close()


def test_export_filename_strips_header_injection_chars(tmp_path):
    """Exported filename must not contain CR, LF, or double-quote even if slug does."""
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())

    # Patch the stored slug to contain injection chars, simulating a slug
    # that somehow bypassed the validator (defence-in-depth for the exporter).
    db.connection().execute(
        "UPDATE packs SET slug = ? WHERE slug = 'test.sample_pack'",
        ('evil"; X-Injected: header',),
    )
    db.connection().commit()

    _, filename = export_to_zip('evil"; X-Injected: header', db.connection())
    assert '"' not in filename
    assert "\r" not in filename
    assert "\n" not in filename
    db.close()


def test_exported_zip_revalidates_successfully(tmp_path):
    """Round-trip: import → export → extract → validate must pass."""
    db = _open_db(tmp_path)
    zip_bytes = make_pack_zip(tmp_path / "src")
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()

    import_from_zip(zip_bytes, packs_dir, db.connection())
    exported, _ = export_to_zip("test.sample_pack", db.connection())

    # Import the exported zip into a fresh packs dir to confirm it re-validates.
    db2 = _open_db(tmp_path / "db2")
    packs_dir2 = tmp_path / "packs2"
    packs_dir2.mkdir()

    result = import_from_zip(exported, packs_dir2, db2.connection())
    assert result.pack_slug == "test.sample_pack"
    db.close()
    db2.close()
