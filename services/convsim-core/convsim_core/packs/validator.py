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

    if manifest is None:
        return None, ["Internal error: manifest is None after successful load"]
    pack_dir_resolved = pack_dir.resolve()

    # Content rating must be in the permitted set.
    if manifest.content_rating and manifest.content_rating not in CONTENT_RATINGS:
        errors.append(
            f"Invalid content_rating '{manifest.content_rating}'. "
            f"Allowed values: {', '.join(sorted(CONTENT_RATINGS))}"
        )

    # pack_id must not contain path-traversal, header-injection, null characters, or
    # path separators.  Path separators (/ and \) are rejected because _install_from_dir
    # maps pack_id directly to a directory name after stripping them; two different ids
    # (e.g. "foo/bar" and "foo_bar") would collide to the same directory, causing the
    # importer to silently overwrite the first pack's files with the second's.
    # Null bytes (\x00) are included because os.path on POSIX silently truncates paths
    # at the first null byte, which could redirect installs to an unintended directory.
    _PACK_ID_FORBIDDEN = {'"', "/", "\\", "\r", "\n", "\x00"}
    if ".." in manifest.pack_id or any(c in manifest.pack_id for c in _PACK_ID_FORBIDDEN):
        errors.append(f"pack_id contains unsafe characters: {manifest.pack_id!r}")

    # Each entry scenario must reference a file that exists within the pack dir.
    for ref in manifest.entry_scenarios:
        if "\x00" in ref:
            errors.append(f"Entry scenario path contains null byte: {ref!r}")
            continue
        norm = ref.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            errors.append(f"Entry scenario path is unsafe: {ref!r}")
            continue
        resolved = (pack_dir / ref).resolve()
        try:
            resolved.relative_to(pack_dir_resolved)
        except ValueError:
            errors.append(f"Entry scenario escapes pack directory: {ref!r}")
            continue
        if not resolved.exists():
            errors.append(f"Entry scenario file not found: {ref!r}")

    # Scan every entry for symlinks and forbidden extensions.
    # Symlinks are rejected here (consistent with safe_extract_zip for zip archives)
    # to prevent shutil.copytree from following them to files outside the pack dir.
    for file_path in pack_dir.rglob("*"):
        if file_path.is_symlink():
            rel = file_path.relative_to(pack_dir)
            errors.append(f"Symlinks are not permitted in pack: {rel}")
        elif file_path.is_file() and file_path.suffix.lower() in FORBIDDEN_EXTENSIONS:
            rel = file_path.relative_to(pack_dir)
            errors.append(f"Executable file not allowed in pack: {rel}")

    return manifest, errors
