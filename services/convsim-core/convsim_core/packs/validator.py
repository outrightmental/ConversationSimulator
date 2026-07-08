# SPDX-License-Identifier: Apache-2.0
"""Pack directory validation: manifest parsing, path safety, and executable rejection."""
import json
from pathlib import Path
from typing import Optional

import jsonschema
import yaml

from convsim_core.packs.models import PackManifest
from convsim_core.schema_paths import get_schema

# Compiled once at import time; schema is bundled and immutable.
_PACK_SCHEMA_VALIDATOR = jsonschema.Draft202012Validator(get_schema("pack.schema.json"))

CONTENT_RATINGS = frozenset({"G", "PG", "PG-13"})

# File extensions that are never permitted inside a pack archive.
FORBIDDEN_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".py", ".js", ".mjs", ".cjs",
    ".ts", ".rb", ".pl", ".php", ".jar", ".class", ".so", ".dll", ".dylib",
    ".vbs", ".ws", ".wsf", ".com", ".scr", ".pif", ".msi", ".deb", ".rpm",
    ".pkg", ".app",
})

# Rule ID constants (also used by CLI tools for parity).
RULE_MISSING_MANIFEST = "MISSING_MANIFEST"
RULE_INVALID_MANIFEST_JSON = "INVALID_MANIFEST_JSON"
RULE_INVALID_MANIFEST_YAML = "INVALID_MANIFEST_YAML"
RULE_SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
RULE_INVALID_CONTENT_RATING = "INVALID_CONTENT_RATING"
RULE_INVALID_PACK_ID = "INVALID_PACK_ID"
RULE_UNSAFE_ENTRY_SCENARIO = "UNSAFE_ENTRY_SCENARIO"
RULE_MISSING_ENTRY_SCENARIO = "MISSING_ENTRY_SCENARIO"
RULE_SYMLINK_DETECTED = "SYMLINK_DETECTED"
RULE_FORBIDDEN_EXTENSION = "FORBIDDEN_EXTENSION"


def _fmt_schema_err(exc: jsonschema.ValidationError, filename: str = "pack.json") -> str:
    path = list(exc.absolute_path)
    if path:
        return f"{filename} [{'.'.join(str(p) for p in path)}]: {exc.message}"
    return f"{filename}: {exc.message}"


def errors_to_rule_ids(errors: list[str]) -> list[str]:
    """Derive unique rule IDs from error message strings."""
    ids: set[str] = set()
    for e in errors:
        el = e.lower()
        if "missing" in el and ("pack.json" in el or "manifest" in el):
            ids.add(RULE_MISSING_MANIFEST)
        elif "not valid json" in el:
            ids.add(RULE_INVALID_MANIFEST_JSON)
        elif "not valid yaml" in el or "must be a yaml mapping" in el:
            ids.add(RULE_INVALID_MANIFEST_YAML)
        elif "pack.json [" in el or "pack.json:" in el or "manifest.yaml [" in el or "manifest.yaml:" in el or "schema" in el:
            ids.add(RULE_SCHEMA_VIOLATION)
        elif "content_rating" in el:
            ids.add(RULE_INVALID_CONTENT_RATING)
        elif "pack_id" in el and ("unsafe" in el or "empty" in el or "valid" in el or "separator" in el):
            ids.add(RULE_INVALID_PACK_ID)
        elif "unsafe" in el or ("escape" in el and "entry" in el):
            ids.add(RULE_UNSAFE_ENTRY_SCENARIO)
        elif "not found" in el or "file not found" in el:
            ids.add(RULE_MISSING_ENTRY_SCENARIO)
        elif "symlink" in el:
            ids.add(RULE_SYMLINK_DETECTED)
        elif "executable" in el or "not allowed" in el or "forbidden" in el:
            ids.add(RULE_FORBIDDEN_EXTENSION)
        elif "null byte" in el:
            # Null bytes in entry scenario paths are an unsafe path error, not a pack_id error.
            ids.add(RULE_UNSAFE_ENTRY_SCENARIO)
        else:
            ids.add(RULE_SCHEMA_VIOLATION)
    return sorted(ids)


def load_manifest(pack_dir: Path) -> tuple[Optional[PackManifest], list[str]]:
    """Parse pack.json or manifest.yaml from pack_dir. Returns (manifest_or_None, errors).

    Tries pack.json (JSON format) first, then falls back to manifest.yaml (YAML format).
    When the manifest can be parsed but fails the JSON Schema, the manifest is
    still returned so that validate_pack_dir can continue its path-safety and
    executable-rejection checks and surface ALL problems in one pass.
    """
    json_path = pack_dir / "pack.json"
    yaml_path = pack_dir / "manifest.yaml"

    manifest_filename = "pack.json"
    if json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return None, [f"pack.json is not valid JSON: {exc}"]
    elif yaml_path.exists():
        manifest_filename = "manifest.yaml"
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            return None, [f"manifest.yaml is not valid YAML: {exc}"]
        if not isinstance(raw, dict):
            return None, ["manifest.yaml must be a YAML mapping"]
    else:
        return None, ["Missing pack.json or manifest.yaml at pack root"]

    # Validate against the authoritative JSON Schema.
    schema_errs = [_fmt_schema_err(e, manifest_filename) for e in _PACK_SCHEMA_VALIDATOR.iter_errors(raw)]

    try:
        manifest = PackManifest.model_validate(raw)
    except Exception as exc:
        return None, schema_errs + [f"{manifest_filename} failed schema validation: {exc}"]

    return manifest, schema_errs


def validate_pack_dir(pack_dir: Path) -> tuple[Optional[PackManifest], list[str]]:
    """
    Validate a pack directory for safe installation.

    Returns (manifest, errors). An empty error list means the pack is valid.
    Does NOT install anything — purely read-only.
    """
    errors: list[str] = []

    manifest, manifest_errors = load_manifest(pack_dir)
    errors.extend(manifest_errors)
    if manifest is None:
        return None, errors
    pack_dir_resolved = pack_dir.resolve()

    if manifest.content_rating and manifest.content_rating not in CONTENT_RATINGS:
        errors.append(
            f"Invalid content_rating '{manifest.content_rating}'. "
            f"Allowed values: {', '.join(sorted(CONTENT_RATINGS))}"
        )

    # pack_id must be non-empty and must not contain path-traversal, header-injection,
    # null characters, or path separators.  Path separators (/ and \) are rejected because
    # _install_from_dir maps pack_id directly to a directory name after stripping them; two
    # different ids (e.g. "foo/bar" and "foo_bar") would collide to the same directory,
    # causing the importer to silently overwrite the first pack's files with the second's.
    # Null bytes (\x00) are included because os.path on POSIX silently truncates paths at
    # the first null byte, which could redirect installs to an unintended directory.
    # "." is rejected because Path(packs_dir) / "." resolves back to packs_dir itself,
    # which would cause the importer to rmtree the entire packs directory.
    _PACK_ID_FORBIDDEN = {'"', "/", "\\", "\r", "\n", "\x00"}
    if not manifest.pack_id:
        errors.append("pack_id must not be empty")
    elif manifest.pack_id == ".":
        errors.append("pack_id '.' is not a valid pack identifier")
    elif ".." in manifest.pack_id or any(c in manifest.pack_id for c in _PACK_ID_FORBIDDEN):
        errors.append(f"pack_id contains unsafe characters: {manifest.pack_id!r}")

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
        if not resolved.is_file():
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
