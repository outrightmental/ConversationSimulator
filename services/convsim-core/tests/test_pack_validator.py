# SPDX-License-Identifier: Apache-2.0
"""Tests for the pack validator.

Each test covers a specific validation rule.  Helper assertions check the
structured ValidationIssue list rather than raw error strings so the test
coverage maps 1-to-1 to rule_ids.
"""
import json
import sys
from pathlib import Path

import pytest

from convsim_core.packs.validator import clear_validation_cache, validate_pack_cached, validate_pack_dir
from tests.helpers import make_pack_dir, make_yaml_pack_dir, _VALID_NPC_YAML


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def _has_error(result, *, rule_id: str | None = None, text: str | None = None) -> bool:
    for issue in result.errors:
        if rule_id and issue.rule_id != rule_id:
            continue
        if text and text.lower() not in issue.message.lower():
            continue
        return True
    return False


def _has_warning(result, *, rule_id: str | None = None, text: str | None = None) -> bool:
    for issue in result.warnings:
        if rule_id and issue.rule_id != rule_id:
            continue
        if text and text.lower() not in issue.message.lower():
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# JSON-format pack basics
# ---------------------------------------------------------------------------

def test_valid_pack_has_no_errors(tmp_path):
    pack_dir = make_pack_dir(tmp_path)
    result = validate_pack_dir(pack_dir)
    assert result.errors == []
    assert result.valid is True
    assert result.pack_id == "test.sample_pack"
    assert result.manifest is not None
    assert result.manifest.pack_id == "test.sample_pack"


def test_missing_manifest_returns_error(tmp_path):
    empty = tmp_path / "empty_pack"
    empty.mkdir()
    result = validate_pack_dir(empty)
    assert _has_error(result, rule_id="MISSING_MANIFEST")
    assert result.valid is False


def test_invalid_json_manifest_returns_error(tmp_path):
    pack_dir = tmp_path / "bad_pack"
    pack_dir.mkdir()
    (pack_dir / "pack.json").write_text("NOT JSON {{{{", encoding="utf-8")
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_JSON")
    assert result.valid is False


def test_missing_required_field_returns_error(tmp_path):
    pack_dir = tmp_path / "incomplete"
    pack_dir.mkdir()
    (pack_dir / "pack.json").write_text(
        json.dumps({"schema_version": "0.1", "name": "No ID Pack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    result = validate_pack_dir(pack_dir)
    assert result.errors  # schema violation for missing pack_id


def test_forbidden_extension_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, extra_files={"run_me.sh": b"#!/bin/bash\necho hi"})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="FORBIDDEN_FILE", text="run_me.sh")


def test_executable_extensions_rejected(tmp_path):
    for ext in (".exe", ".bat", ".ps1", ".py", ".js", ".dll"):
        sub = tmp_path / f"test_{ext.lstrip('.')}"
        pack_dir = make_pack_dir(sub, extra_files={f"bad{ext}": b""})
        result = validate_pack_dir(pack_dir)
        assert _has_error(result, rule_id="FORBIDDEN_FILE"), (
            f"Expected {ext!r} to trigger FORBIDDEN_FILE"
        )


def test_bad_content_rating_returns_error(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"content_rating": "NC-17"})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_CONTENT_RATING")


def test_valid_content_ratings_accepted(tmp_path):
    for rating in ("G", "PG", "PG-13"):
        sub = tmp_path / rating.replace("-", "")
        pack_dir = make_pack_dir(sub, manifest={"content_rating": rating})
        result = validate_pack_dir(pack_dir)
        assert not _has_error(result, rule_id="INVALID_CONTENT_RATING"), (
            f"Rating {rating!r} should be accepted"
        )


def test_missing_entry_scenario_file_returns_error(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"entry_scenarios": ["scenarios/nonexistent.yaml"]},
    )
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, text="nonexistent.yaml")


def test_traversal_in_entry_scenario_rejected(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"entry_scenarios": ["../escape.yaml"]},
    )
    result = validate_pack_dir(pack_dir)
    assert any(
        "unsafe" in e.message.lower() or "escape" in e.message.lower()
        for e in result.errors
    )


def test_unsafe_pack_id_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": "../../evil"})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_PACK_ID")


@pytest.mark.parametrize("bad_id", [
    'evil"; X-Injected: header',
    "evil\r\nX-Injected: header",
    "evil\rX-Injected: header",
    "evil\nX-Injected: header",
])
def test_pack_id_header_injection_chars_rejected(tmp_path, bad_id):
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": bad_id})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_PACK_ID"), (
        f"pack_id {bad_id!r} should have triggered INVALID_PACK_ID"
    )


def test_null_byte_in_pack_id_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": "evil\x00pack"})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_PACK_ID"), (
        f"Expected pack_id with null byte to be rejected; got: {result.errors}"
    )


def test_null_byte_in_entry_scenario_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"entry_scenarios": ["scenarios/intro\x00.yaml"]})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="UNSAFE_PATH"), (
        f"Expected entry_scenario with null byte to be rejected; got: {result.errors}"
    )


@pytest.mark.parametrize("bad_id", [
    "foo/bar",
    "foo\\bar",
    "/absolute",
    "a/b/c",
])
def test_pack_id_path_separator_rejected(tmp_path, bad_id):
    pack_dir = make_pack_dir(
        tmp_path / bad_id.replace("/", "_").replace("\\", "_"),
        manifest={"pack_id": bad_id},
    )
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_PACK_ID"), (
        f"pack_id {bad_id!r} should have triggered INVALID_PACK_ID; got: {result.errors}"
    )


def test_empty_pack_id_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": ""})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_PACK_ID"), (
        f"Expected empty pack_id to be rejected; got: {result.errors}"
    )


def test_dot_pack_id_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"pack_id": "."})
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="INVALID_PACK_ID"), (
        f"Expected pack_id '.' to be rejected; got: {result.errors}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation requires elevated privileges on Windows")
def test_symlink_in_pack_dir_rejected(tmp_path):
    pack_dir = make_pack_dir(tmp_path)
    external = tmp_path / "external_secret.txt"
    external.write_text("secret content outside pack")
    (pack_dir / "link_to_outside").symlink_to(external)

    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="SYMLINK_IN_PACK"), (
        f"Expected SYMLINK_IN_PACK error; got: {result.errors}"
    )


def test_entry_scenario_pointing_to_directory_rejected(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"entry_scenarios": ["scenarios"]},
    )
    result = validate_pack_dir(pack_dir)
    assert result.errors, (
        f"Expected entry_scenarios pointing to a directory to be rejected; got: {result.errors}"
    )


# ---------------------------------------------------------------------------
# Safety policy checks
# ---------------------------------------------------------------------------

def test_safety_policy_file_missing_returns_error(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"safety": {"policy": "safety/nonexistent.yaml"}},
    )
    # Remove the actual safety file the helper created
    (pack_dir / "safety" / "default.yaml").unlink()
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="MISSING_FILE", text="nonexistent.yaml")


def test_safety_policy_path_traversal_rejected(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"safety": {"policy": "../outside/policy.yaml"}},
    )
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="PATH_TRAVERSAL")


# ---------------------------------------------------------------------------
# License checks (warning only)
# ---------------------------------------------------------------------------

def test_known_spdx_license_no_warning(tmp_path):
    for lic in ("CC-BY-4.0", "MIT", "Apache-2.0", "CC0-1.0"):
        sub = tmp_path / lic.replace("-", "_").replace(".", "_")
        pack_dir = make_pack_dir(sub, manifest={"license": lic})
        result = validate_pack_dir(pack_dir)
        assert not _has_warning(result, rule_id="UNKNOWN_LICENSE"), (
            f"License {lic!r} should be recognised"
        )


def test_unknown_license_returns_warning(tmp_path):
    pack_dir = make_pack_dir(tmp_path, manifest={"license": "All Rights Reserved"})
    result = validate_pack_dir(pack_dir)
    assert _has_warning(result, rule_id="UNKNOWN_LICENSE")
    assert result.valid is True  # warning does not block validity


# ---------------------------------------------------------------------------
# External URL policy
# ---------------------------------------------------------------------------

def test_external_urls_allowed_returns_error(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"assets": {"allow_external_urls": True}},
    )
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="EXTERNAL_URLS_ALLOWED")


def test_external_urls_false_is_ok(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={"assets": {"allow_external_urls": False}},
    )
    result = validate_pack_dir(pack_dir)
    assert not _has_error(result, rule_id="EXTERNAL_URLS_ALLOWED")


# ---------------------------------------------------------------------------
# NPC fictional flag
# ---------------------------------------------------------------------------

def test_npc_not_fictional_returns_error(tmp_path):
    non_fictional_npc = _VALID_NPC_YAML.replace("fictional: true", "fictional: false")
    pack_dir = make_yaml_pack_dir(tmp_path, npc_yaml=non_fictional_npc)
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="NPC_NOT_FICTIONAL")


def test_npc_fictional_missing_returns_error(tmp_path):
    missing_fictional_npc = "\n".join(
        line for line in _VALID_NPC_YAML.splitlines() if "fictional" not in line
    )
    pack_dir = make_yaml_pack_dir(tmp_path, npc_yaml=missing_fictional_npc)
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="NPC_NOT_FICTIONAL")


def test_npc_fictional_true_no_error(tmp_path):
    pack_dir = make_yaml_pack_dir(tmp_path)
    result = validate_pack_dir(pack_dir)
    assert not _has_error(result, rule_id="NPC_NOT_FICTIONAL")


# ---------------------------------------------------------------------------
# Official pack smoke-test presence
# ---------------------------------------------------------------------------

def test_official_pack_without_smoke_tests_returns_warning(tmp_path):
    official_manifest = _VALID_MANIFEST_YAML_OFFICIAL()
    pack_dir = make_yaml_pack_dir(tmp_path, manifest_yaml=official_manifest)
    result = validate_pack_dir(pack_dir)
    assert _has_warning(result, rule_id="MISSING_SMOKE_TESTS")
    assert result.valid is True  # warning, not error


def test_official_pack_with_smoke_tests_no_warning(tmp_path):
    official_manifest = _VALID_MANIFEST_YAML_OFFICIAL()
    pack_dir = make_yaml_pack_dir(
        tmp_path, manifest_yaml=official_manifest, include_tests=True
    )
    result = validate_pack_dir(pack_dir)
    assert not _has_warning(result, rule_id="MISSING_SMOKE_TESTS")


def test_community_pack_without_smoke_tests_no_warning(tmp_path):
    pack_dir = make_yaml_pack_dir(tmp_path)  # pack_id: test.yaml_pack (not official.)
    result = validate_pack_dir(pack_dir)
    assert not _has_warning(result, rule_id="MISSING_SMOKE_TESTS")


def _VALID_MANIFEST_YAML_OFFICIAL() -> str:
    from tests.helpers import _VALID_MANIFEST_YAML
    return _VALID_MANIFEST_YAML.replace("pack_id: test.yaml_pack", "pack_id: official.test_pack")


# ---------------------------------------------------------------------------
# YAML-format pack validation
# ---------------------------------------------------------------------------

def test_yaml_format_pack_validates_cleanly(tmp_path):
    pack_dir = make_yaml_pack_dir(tmp_path)
    result = validate_pack_dir(pack_dir)
    assert result.errors == [], f"Expected no errors; got: {result.errors}"
    assert result.valid is True
    assert result.pack_id == "test.yaml_pack"


def test_yaml_manifest_takes_precedence_over_json(tmp_path):
    """When both manifest.yaml and pack.json exist, manifest.yaml is used."""
    pack_dir = make_yaml_pack_dir(tmp_path)
    # Also drop a pack.json with bad content to confirm it's ignored
    (pack_dir / "pack.json").write_text("NOT JSON {{", encoding="utf-8")
    result = validate_pack_dir(pack_dir)
    assert result.errors == [], f"manifest.yaml should take precedence; got: {result.errors}"


def test_missing_npc_ref_file_returns_error(tmp_path):
    pack_dir = make_yaml_pack_dir(tmp_path)
    (pack_dir / "npcs" / "test_npc.yaml").unlink()
    result = validate_pack_dir(pack_dir)
    assert result.errors, "Expected an error for missing NPC ref file"


def test_missing_rubric_ref_file_returns_error(tmp_path):
    pack_dir = make_yaml_pack_dir(tmp_path)
    (pack_dir / "rubrics" / "test_rubric.yaml").unlink()
    result = validate_pack_dir(pack_dir)
    assert _has_error(result, rule_id="MISSING_FILE")


# ---------------------------------------------------------------------------
# All issues collected in one pass (no early exit)
# ---------------------------------------------------------------------------

def test_multiple_errors_reported_in_one_pass(tmp_path):
    pack_dir = make_pack_dir(
        tmp_path,
        manifest={
            "content_rating": "Adult",                     # INVALID_CONTENT_RATING
            "entry_scenarios": ["scenarios/missing.yaml"],  # MISSING_FILE
        },
        extra_files={"hack.sh": b"#!/bin/sh"},             # FORBIDDEN_FILE
    )
    result = validate_pack_dir(pack_dir)
    rule_ids = {e.rule_id for e in result.errors}
    assert "INVALID_CONTENT_RATING" in rule_ids
    assert "MISSING_FILE" in rule_ids
    assert "FORBIDDEN_FILE" in rule_ids


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def test_validate_pack_cached_returns_same_result(tmp_path):
    clear_validation_cache()
    pack_dir = make_pack_dir(tmp_path)
    result1 = validate_pack_cached(pack_dir)
    result2 = validate_pack_cached(pack_dir)
    assert result1 is result2  # same object from cache


def test_validate_pack_cached_invalidates_on_change(tmp_path):
    clear_validation_cache()
    pack_dir = make_pack_dir(tmp_path)
    result1 = validate_pack_cached(pack_dir)
    assert result1.valid is True

    # Inject a bad file to change mtime
    (pack_dir / "exploit.sh").write_bytes(b"#!/bin/sh")
    result2 = validate_pack_cached(pack_dir)
    assert result2 is not result1
    assert result2.valid is False


# ---------------------------------------------------------------------------
# Golden snapshot: deliberately broken pack
# ---------------------------------------------------------------------------

def test_broken_pack_golden_snapshot(tmp_path):
    """A pack with known flaws produces exactly the expected rule_id set."""
    pack_dir = make_yaml_pack_dir(
        tmp_path,
        manifest_yaml=_BROKEN_MANIFEST_YAML,
        npc_yaml=_BROKEN_NPC_YAML,
    )
    # Remove the safety policy file so we also trigger MISSING_FILE
    import shutil
    shutil.rmtree(pack_dir / "safety")

    result = validate_pack_dir(pack_dir)

    error_rule_ids = sorted(e.rule_id for e in result.errors)
    warning_rule_ids = sorted(w.rule_id for w in result.warnings)

    # Every issue has all required fields populated
    for issue in result.errors + result.warnings:
        assert issue.rule_id, "rule_id must not be empty"
        assert issue.file, "file must not be empty"
        assert issue.pointer, "pointer must not be empty"
        assert issue.message, "message must not be empty"
        assert issue.suggested_fix, "suggested_fix must not be empty"

    assert "INVALID_CONTENT_RATING" in error_rule_ids
    assert "MISSING_FILE" in error_rule_ids       # missing safety policy
    assert "NPC_NOT_FICTIONAL" in error_rule_ids
    assert "UNKNOWN_LICENSE" in warning_rule_ids
    assert result.valid is False


_BROKEN_MANIFEST_YAML = """\
schema_version: "0.1"
pack_id: test.broken_pack
name: Broken Pack
version: 1.0.0
description: A deliberately broken pack for snapshot testing.
author: Test Suite
license: All Rights Reserved
content_rating: Adult
tags:
  - test
supported_languages:
  - en
entry_scenarios:
  - scenarios/intro.yaml
assets:
  allow_external_urls: false
safety:
  policy: safety/default.yaml
"""

_BROKEN_NPC_YAML = """\
schema_version: "0.1"
npc_id: broken_npc
display_name: Broken NPC
archetype: generic
fictional: false
age_band: adult
public_persona:
  occupation: Test
  speaking_style: Direct
  demeanor: Neutral
private_persona: {}
"""
