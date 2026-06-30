# SPDX-License-Identifier: Apache-2.0
"""Pack directory validation: manifest parsing, path safety, and executable rejection."""
import json
from pathlib import Path
from typing import Optional

from convsim_core.packs.models import PackManifest

CONTENT_RATINGS = frozenset({"G", "PG", "PG-13"})

# File extensions that are never permitted inside a pack archive.
FORBIDDEN_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".py", ".js", ".mjs", ".cjs",
    ".ts", ".rb", ".pl", ".php", ".jar", ".class", ".so", ".dll", ".dylib",
    ".vbs", ".ws", ".wsf", ".com", ".scr", ".pif", ".msi", ".deb", ".rpm",
    ".pkg", ".app",
})


def load_manifest(pack_dir: Path) -> tuple[Optional[PackManifest], list[str]]:
    """Parse pack.json from pack_dir. Returns (manifest, errors)."""
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        return None, ["Missing pack.json at pack root"]

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"pack.json is not valid JSON: {exc}"]

    try:
        manifest = PackManifest.model_validate(raw)
    except Exception as exc:
        return None, [f"pack.json failed schema validation: {exc}"]

    return manifest, []


def validate_pack_dir(pack_dir: Path) -> tuple[Optional[PackManifest], list[str]]:
    """
    Validate a pack directory for safe installation.

    Returns (manifest, errors). An empty error list means the pack is valid.
    Does NOT install anything — purely read-only.
    """
    errors: list[str] = []

    manifest, manifest_errors = load_manifest(pack_dir)
    if manifest_errors:
        return None, manifest_errors

    assert manifest is not None
    pack_dir_resolved = str(pack_dir.resolve())

    # Content rating must be in the permitted set.
    if manifest.content_rating and manifest.content_rating not in CONTENT_RATINGS:
        errors.append(
            f"Invalid content_rating '{manifest.content_rating}'. "
            f"Allowed values: {', '.join(sorted(CONTENT_RATINGS))}"
        )

    # pack_id must not contain path-traversal characters.
    if ".." in manifest.pack_id or manifest.pack_id.startswith("/"):
        errors.append(f"pack_id contains unsafe characters: {manifest.pack_id!r}")

    # Each entry scenario must reference a file that exists within the pack dir.
    for ref in manifest.entry_scenarios:
        norm = ref.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            errors.append(f"Entry scenario path is unsafe: {ref!r}")
            continue
        resolved = str((pack_dir / ref).resolve())
        if not resolved.startswith(pack_dir_resolved):
            errors.append(f"Entry scenario escapes pack directory: {ref!r}")
        elif not Path(resolved).exists():
            errors.append(f"Entry scenario file not found: {ref!r}")

    # Scan every file for forbidden extensions (no executables allowed in packs).
    for file_path in pack_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in FORBIDDEN_EXTENSIONS:
            rel = file_path.relative_to(pack_dir)
            errors.append(f"Executable file not allowed in pack: {rel}")

    return manifest, errors
