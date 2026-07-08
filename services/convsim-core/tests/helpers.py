# SPDX-License-Identifier: Apache-2.0
"""Test helpers: build minimal valid pack fixtures on disk."""
import io
import json
import zipfile
from pathlib import Path


_VALID_MANIFEST = {
    "schema_version": "0.1",
    "pack_id": "test.sample_pack",
    "name": "Sample Pack",
    "version": "1.0.0",
    "description": "A minimal test pack",
    "author": "Test Suite",
    "license": "CC-BY-4.0",
    "content_rating": "G",
    "tags": ["test"],
    "supported_languages": ["en"],
    "entry_scenarios": ["scenarios/intro.yaml"],
    "safety": {"policy": "safety/default.yaml"},
}

_VALID_SAFETY_YAML = (
    "schema_version: '0.1'\n"
    "policy_id: default\n"
    "content_categories:\n"
    "  nsfw_sexual: block\n"
    "  real_person_impersonation: block\n"
    "  instructional_criminal: block\n"
    "  crisis_content: redirect\n"
    "redirect_message: \"I can't help with that in this context.\"\n"
    "content_rating_cap: G\n"
)

# ---------------------------------------------------------------------------
# Minimal valid YAML fixtures used by make_yaml_pack_dir
# ---------------------------------------------------------------------------

_VALID_MANIFEST_YAML = """\
schema_version: "0.1"
pack_id: test.yaml_pack
name: Test YAML Pack
version: 1.0.0
description: A minimal test pack in YAML format for unit tests.
author: Test Suite
license: CC-BY-4.0
content_rating: G
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

_VALID_SCENARIO_YAML = """\
schema_version: "0.1"
scenario_id: intro
title: Introduction
summary: A minimal test scenario for unit tests.
player_role:
  label: Tester
  brief: You are testing the validation system.
npc:
  ref: ../npcs/test_npc.yaml
rubric:
  ref: ../rubrics/test_rubric.yaml
duration:
  max_turns: 5
opening:
  npc_says: Hello, this is a test.
goals:
  player_visible:
    - Complete the test scenario
"""

_VALID_NPC_YAML = """\
schema_version: "0.1"
npc_id: test_npc
display_name: Test NPC
archetype: generic
fictional: true
age_band: adult
public_persona:
  occupation: Test character for unit tests
  speaking_style: Neutral and direct
  demeanor: Professional
private_persona: {}
"""

_VALID_RUBRIC_YAML = """\
schema_version: "0.1"
rubric_id: test_rubric
title: Test Rubric
dimensions:
  - id: quality
    name: Response Quality
    description: How well the player responded
    scoring:
      low: Poor response
      medium: Adequate response
      high: Excellent response
"""


def make_pack_dir(base: Path, manifest: dict | None = None, extra_files: dict | None = None) -> Path:
    """
    Create a minimal valid JSON-format pack directory under base/.
    manifest overrides the default manifest fields.
    extra_files maps relative path -> bytes content (use to inject bad files).
    """
    pack_dir = base / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    merged = {**_VALID_MANIFEST, **(manifest or {})}
    (pack_dir / "pack.json").write_text(json.dumps(merged), encoding="utf-8")

    scenarios_dir = pack_dir / "scenarios"
    scenarios_dir.mkdir(exist_ok=True)
    (scenarios_dir / "intro.yaml").write_text("scenario_id: intro\ntitle: Intro\n", encoding="utf-8")
    (scenarios_dir / "advanced.yaml").write_text("scenario_id: advanced\ntitle: Advanced\n", encoding="utf-8")

    portraits_dir = pack_dir / "assets" / "portraits"
    portraits_dir.mkdir(parents=True, exist_ok=True)
    (portraits_dir / "npc.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    safety_dir = pack_dir / "safety"
    safety_dir.mkdir(exist_ok=True)
    (safety_dir / "default.yaml").write_text(_VALID_SAFETY_YAML, encoding="utf-8")

    if extra_files:
        for rel, content in extra_files.items():
            target = pack_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                target.write_text(content, encoding="utf-8")
            else:
                target.write_bytes(content)

    return pack_dir


def make_yaml_pack_dir(
    base: Path,
    manifest_yaml: str | None = None,
    npc_yaml: str | None = None,
    extra_files: dict | None = None,
    include_tests: bool = False,
) -> Path:
    """Create a minimal valid YAML-format pack directory under base/.

    Args:
        base: Parent directory; the pack is created at ``base/yaml_pack/``.
        manifest_yaml: Complete manifest YAML string (overrides default).
        npc_yaml: Complete NPC YAML string (overrides default valid NPC).
        extra_files: ``{relative_path: bytes_or_str}`` injected after defaults.
        include_tests: If True, add a minimal smoke-test fixture in tests/.
    """
    pack_dir = base / "yaml_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    (pack_dir / "manifest.yaml").write_text(
        manifest_yaml or _VALID_MANIFEST_YAML, encoding="utf-8"
    )

    scenarios_dir = pack_dir / "scenarios"
    scenarios_dir.mkdir(exist_ok=True)
    (scenarios_dir / "intro.yaml").write_text(_VALID_SCENARIO_YAML, encoding="utf-8")

    npcs_dir = pack_dir / "npcs"
    npcs_dir.mkdir(exist_ok=True)
    (npcs_dir / "test_npc.yaml").write_text(npc_yaml or _VALID_NPC_YAML, encoding="utf-8")

    rubrics_dir = pack_dir / "rubrics"
    rubrics_dir.mkdir(exist_ok=True)
    (rubrics_dir / "test_rubric.yaml").write_text(_VALID_RUBRIC_YAML, encoding="utf-8")

    safety_dir = pack_dir / "safety"
    safety_dir.mkdir(exist_ok=True)
    (safety_dir / "default.yaml").write_text(_VALID_SAFETY_YAML, encoding="utf-8")

    if include_tests:
        tests_dir = pack_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "smoke_intro.yaml").write_text(
            'schema_version: "0.1"\n'
            "fixture_id: smoke_intro\n"
            "scenario_id: intro\n"
            "description: Smoke test for the intro scenario.\n"
            "turns:\n"
            "  - turn: 1\n"
            "    player_input: Hello!\n",
            encoding="utf-8",
        )

    if extra_files:
        for rel, content in extra_files.items():
            target = pack_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                target.write_text(content, encoding="utf-8")
            else:
                target.write_bytes(content)

    return pack_dir


def pack_dir_to_zip(pack_dir: Path, top_level_dir: str = "pack") -> bytes:
    """Zip up pack_dir contents under top_level_dir/ in the archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(pack_dir.rglob("*")):
            if f.is_file():
                arcname = top_level_dir + "/" + str(f.relative_to(pack_dir)).replace("\\", "/")
                zf.write(f, arcname)
    return buf.getvalue()


def make_pack_zip(
    base: Path,
    manifest: dict | None = None,
    extra_files: dict | None = None,
    top_level_dir: str = "pack",
) -> bytes:
    """Convenience: create a pack directory and return it as zip bytes."""
    pack_dir = make_pack_dir(base, manifest, extra_files)
    return pack_dir_to_zip(pack_dir, top_level_dir)
