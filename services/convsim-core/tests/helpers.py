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
    "license": "CC BY 4.0",
    "content_rating": "G",
    "tags": ["test"],
    "supported_languages": ["en"],
    "entry_scenarios": ["scenarios/intro.yaml"],
    "safety": {"policy": "safety/default.yaml"},
}


def make_pack_dir(base: Path, manifest: dict | None = None, extra_files: dict | None = None) -> Path:
    """
    Create a minimal valid pack directory under base/.
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
    (safety_dir / "default.yaml").write_text(
        "schema_version: '0.1'\n"
        "policy_id: default\n"
        "content_categories:\n"
        "  nsfw_sexual: block\n"
        "  real_person_impersonation: block\n"
        "  instructional_criminal: block\n"
        "  crisis_content: redirect\n"
        "redirect_message: \"I can't help with that in this context.\"\n"
        "content_rating_cap: G\n",
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
