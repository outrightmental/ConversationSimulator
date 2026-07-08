# SPDX-License-Identifier: Apache-2.0
import json
import sys
from pathlib import Path

import pytest

from convsim_core.packs.validator import validate_pack_dir
from tests.helpers import make_pack_dir


def test_valid_pack_has_no_errors(tmp_path):
    pack_dir = make_pack_dir(tmp_path)
    manifest, errors = validate_pack_dir(pack_dir)
    assert errors == []
    assert manifest is not None
    assert manifest.pack_id == "test.sample_pack"


def test_missing_manifest_returns_error(tmp_path):
    empty = tmp_path / "empty_pack"
    empty.mkdir()
    _, errors = validate_pack_dir(empty)
    assert any("Missing pack.json" in e for e in errors)


def test_invalid_json_manifest_returns_error(tmp_path):
    pack_dir = tmp_path / "bad_pack"
    pack_dir.mkdir()
    (pack_dir / "pack.json").write_text("NOT JSON {{{{", encoding="utf-8")
    _, errors = validate_pack_dir(pack_dir)
    assert any("not valid JSON" in e for e in errors)


def test_missing_required_field_returns_error(tmp_path):
    pack_dir = tmp_path / "incomplete"
    pack_dir.mkdir()
    # pack_id is required
    (pack_dir / "pack.json").write_text(
        json.dumps({"schema_version": "0.1", "name": "No ID Pack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    _, errors = validate_pack_dir(pack_dir)
    assert errors  # Pydantic validation error for missing pack_id


def test_forbidden_extension_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, extra_files={"run_me.sh": b"#!/bin/bash\necho hi"})
    _, errors = validate_pack_dir(pack_dir)
    assert any("run_me.sh" in e for e in errors)


def test_executable_extensions_rejected(tmp_path):
    for ext in (".exe", ".bat", ".ps1", ".py", ".js", ".dll"):
        sub = tmp_path / f"test_{ext.lstrip('.')}"
        pack_dir = make_pack_dir(sub, extra_files={f"bad{ext}": b""})
        _, errors = validate_pack_dir(pack_dir)
        assert any(ext in e for e in errors), f"Expected {ext!r} to be rejected"


def test_bad_content_rating_returns_error(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"content_rating": "NC-17"})
    _, errors = validate_pack_dir(pack_dir)
    assert any("content_rating" in e for e in errors)


def test_valid_content_ratings_accepted(tmp_path):
    for rating in ("G", "PG", "PG-13"):
        sub = tmp_path / rating.replace("-", "")
        pack_dir = make_pack_dir(sub, manifest={"content_rating": rating})
        _, errors = validate_pack_dir(pack_dir)
        assert errors == [], f"Rating {rating!r} should be accepted"


def test_missing_entry_scenario_file_returns_error(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"entry_scenarios": ["scenarios/nonexistent.yaml"]},
    )
    _, errors = validate_pack_dir(pack_dir)
    assert any("nonexistent.yaml" in e for e in errors)


def test_traversal_in_entry_scenario_rejected(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"entry_scenarios": ["../escape.yaml"]},
    )
    _, errors = validate_pack_dir(pack_dir)
    assert any("unsafe" in e.lower() or "escape" in e.lower() for e in errors)


def test_unsafe_pack_id_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": "../../evil"})
    _, errors = validate_pack_dir(pack_dir)
    assert any("unsafe" in e.lower() for e in errors)


@pytest.mark.parametrize("bad_id", [
    'evil"; X-Injected: header',
    "evil\r\nX-Injected: header",
    "evil\rX-Injected: header",
    "evil\nX-Injected: header",
])
def test_pack_id_header_injection_chars_rejected(tmp_path, bad_id):
    """pack_id containing CR, LF, or double-quote must be rejected (header injection)."""
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": bad_id})
    _, errors = validate_pack_dir(pack_dir)
    assert any("unsafe" in e.lower() for e in errors), (
        f"pack_id {bad_id!r} should have been rejected"
    )


def test_null_byte_in_pack_id_rejected(tmp_path):
    """pack_id containing a null byte must be rejected by the validator.

    On POSIX, os.path silently truncates paths at the first null byte, which could
    redirect an install to an unintended directory. On Windows, pathlib raises an
    unhandled ValueError that would produce a 500 instead of a 422.
    """
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": "evil\x00pack"})
    _, errors = validate_pack_dir(pack_dir)
    assert any("unsafe" in e.lower() for e in errors), (
        f"Expected pack_id with null byte to be rejected; got: {errors}"
    )


def test_null_byte_in_entry_scenario_rejected(tmp_path):
    """An entry_scenarios path containing a null byte must be rejected.

    pathlib raises an unhandled ValueError for null-byte paths, so the validator
    must catch this before delegating to pathlib.
    """
    pack_dir = make_pack_dir(tmp_path, manifest={"entry_scenarios": ["scenarios/intro\x00.yaml"]})
    _, errors = validate_pack_dir(pack_dir)
    assert any("null" in e.lower() for e in errors), (
        f"Expected entry_scenario with null byte to be rejected; got: {errors}"
    )


@pytest.mark.parametrize("bad_id", [
    "foo/bar",
    "foo\\bar",
    "/absolute",
    "a/b/c",
])
def test_pack_id_path_separator_rejected(tmp_path, bad_id):
    """pack_id containing path separators must be rejected.

    _install_from_dir maps pack_id to a directory name after stripping separators;
    two ids like 'foo/bar' and 'foo_bar' would collide to the same directory, causing
    the second import to silently overwrite the first pack's installed files.
    """
    pack_dir = make_pack_dir(tmp_path / bad_id.replace("/", "_").replace("\\", "_"), manifest={"pack_id": bad_id})
    _, errors = validate_pack_dir(pack_dir)
    assert any("unsafe" in e.lower() for e in errors), (
        f"pack_id {bad_id!r} should have been rejected; got: {errors}"
    )


def test_empty_pack_id_rejected(tmp_path):
    """pack_id '' would cause _install_from_dir to compute pack_dest == packs_base_dir,
    causing shutil.rmtree to wipe the entire packs directory before the atomic move."""
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": ""})
    _, errors = validate_pack_dir(pack_dir)
    assert any("empty" in e.lower() or "pack_id" in e.lower() for e in errors), (
        f"Expected empty pack_id to be rejected; got: {errors}"
    )


def test_dot_pack_id_rejected(tmp_path):
    """pack_id '.' resolves pack_dest to packs_base_dir itself (Path(d) / '.' == Path(d)),
    which would cause shutil.rmtree to delete the entire packs directory."""
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": "."})
    _, errors = validate_pack_dir(pack_dir)
    assert any("pack_id" in e.lower() or "valid" in e.lower() for e in errors), (
        f"Expected pack_id '.' to be rejected; got: {errors}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation requires elevated privileges on Windows")
def test_symlink_in_pack_dir_rejected(tmp_path):
    """A pack directory containing a symlink must be rejected.

    Consistent with safe_extract_zip which rejects symlinks in zip archives.
    Prevents shutil.copytree from following symlinks to files outside the pack.
    """
    pack_dir = make_pack_dir(tmp_path)
    external = tmp_path / "external_secret.txt"
    external.write_text("secret content outside pack")
    (pack_dir / "link_to_outside").symlink_to(external)

    _, errors = validate_pack_dir(pack_dir)
    assert any("symlink" in e.lower() for e in errors), (
        f"Expected a symlink rejection error; got: {errors}"
    )


def test_entry_scenario_pointing_to_directory_rejected(tmp_path):
    """entry_scenarios must reference a file, not a directory.

    Previously the check used resolved.exists() which accepted a directory path,
    silently registering the directory's stem as a bogus scenario slug.
    """
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"entry_scenarios": ["scenarios"]},  # "scenarios" is a directory
    )
    _, errors = validate_pack_dir(pack_dir)
    assert any("not found" in e.lower() or "file" in e.lower() for e in errors), (
        f"Expected entry_scenarios pointing to a directory to be rejected; got: {errors}"
    )
