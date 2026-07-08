# SPDX-License-Identifier: Apache-2.0
"""Pack directory validation: schemas, asset existence, security, and policy checks.

``validate_pack_dir(pack_dir)`` → :class:`ValidationResult`
  Validates both ``manifest.yaml`` (YAML format) and ``pack.json`` (JSON format)
  packs.  All issues are collected in a single pass — the validator never
  short-circuits on the first error.  Pack content is never executed.

``validate_pack_cached(pack_dir)`` → :class:`ValidationResult`
  Same, with in-memory caching keyed by ``(resolved_path, version, max_mtime)``.
  Safe to call from hot paths (UI polling, workbench preview).

Severity levels
---------------
ERROR   — blocks import and contribution.
WARNING — allows local development; blocks official-pack contribution.
"""
import json
import re as _re
from pathlib import Path
from typing import Optional

import jsonschema
import yaml

from convsim_core.packs.models import (
    PackManifest,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from convsim_core.schema_paths import get_schema

# ---------------------------------------------------------------------------
# Schema validators — compiled once at import time (schemas are immutable).
# ---------------------------------------------------------------------------
_VALIDATORS: dict[str, jsonschema.Draft202012Validator] = {
    name: jsonschema.Draft202012Validator(get_schema(f"{name}.schema.json"))
    for name in ("pack", "scenario", "npc", "rubric", "safety", "scene", "pack-test")
}

CONTENT_RATINGS = frozenset({"G", "PG", "PG-13"})

# File extensions that are never permitted inside a pack directory or archive.
FORBIDDEN_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".py", ".js", ".mjs", ".cjs",
    ".ts", ".rb", ".pl", ".php", ".jar", ".class", ".so", ".dll", ".dylib",
    ".vbs", ".ws", ".wsf", ".com", ".scr", ".pif", ".msi", ".deb", ".rpm",
    ".pkg", ".app",
})

# Recognised SPDX license identifiers.  An unrecognised value triggers a
# WARNING so scenario authors know to use a standard identifier.
_SPDX_LICENSES = frozenset({
    "MIT", "Apache-2.0", "GPL-2.0-only", "GPL-2.0-or-later",
    "GPL-3.0-only", "GPL-3.0-or-later", "LGPL-2.1-only", "LGPL-2.1-or-later",
    "LGPL-3.0-only", "LGPL-3.0-or-later", "BSD-2-Clause", "BSD-3-Clause",
    "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-ND-4.0",
    "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0", "CC0-1.0",
    "ISC", "MPL-2.0", "EUPL-1.2", "AGPL-3.0-only", "AGPL-3.0-or-later",
    "Unlicense", "WTFPL", "Proprietary",
})


class _PackValidator:
    """Accumulates all validation issues for a single pack directory.

    Never executes any content from the pack — all operations are read-only
    YAML/JSON parsing and JSON Schema validation.
    """

    def __init__(self, pack_dir: Path) -> None:
        self._pack_dir = pack_dir.resolve()
        self._issues: list[ValidationIssue] = []
        # Track resolved paths whose content has already been validated so that
        # _check_scenario_ref does not re-emit errors for files already covered
        # by _validate_all_npcs (or any future bulk scan).
        self._validated_content: set[Path] = set()

    # ------------------------------------------------------------------
    # Issue builders
    # ------------------------------------------------------------------

    def _error(
        self,
        rule_id: str,
        file: str,
        pointer: str,
        message: str,
        suggested_fix: str,
    ) -> None:
        self._issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            rule_id=rule_id,
            file=file,
            pointer=pointer,
            message=message,
            suggested_fix=suggested_fix,
        ))

    def _warning(
        self,
        rule_id: str,
        file: str,
        pointer: str,
        message: str,
        suggested_fix: str,
    ) -> None:
        self._issues.append(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            rule_id=rule_id,
            file=file,
            pointer=pointer,
            message=message,
            suggested_fix=suggested_fix,
        ))

    def _schema_errors(self, data: dict, schema_key: str, file_rel: str) -> None:
        """Emit an ERROR for each JSON Schema violation in *data*."""
        for exc in _VALIDATORS[schema_key].iter_errors(data):
            path = list(exc.absolute_path)
            pointer = "/" + "/".join(str(p) for p in path) if path else "(root)"
            self._error(
                "SCHEMA_VIOLATION",
                file_rel,
                pointer,
                exc.message,
                (
                    f"Fix the value at '{pointer}' in {file_rel} to satisfy the "
                    f"'{schema_key}' schema."
                ),
            )

    # ------------------------------------------------------------------
    # File loaders
    # ------------------------------------------------------------------

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._pack_dir))
        except ValueError:
            return str(path)

    def _load_yaml(self, path: Path) -> Optional[dict]:
        rel = self._rel(path)
        if not path.exists():
            self._error(
                "MISSING_FILE",
                rel,
                "(root)",
                f"File not found: '{rel}'",
                f"Create the missing file at '{rel}'.",
            )
            return None
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            self._error(
                "INVALID_YAML",
                rel,
                "(root)",
                f"YAML parse error in '{rel}': {exc}",
                f"Fix the YAML syntax error in '{rel}'.",
            )
            return None
        if not isinstance(raw, dict):
            self._error(
                "INVALID_YAML",
                rel,
                "(root)",
                f"Expected a YAML mapping in '{rel}', got {type(raw).__name__}.",
                f"The top-level element of '{rel}' must be a mapping (key: value pairs).",
            )
            return None
        return raw

    def _load_json(self, path: Path) -> Optional[dict]:
        rel = self._rel(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._error(
                "INVALID_JSON",
                rel,
                "(root)",
                f"'{rel}' is not valid JSON: {exc}",
                f"Fix the JSON syntax error in '{rel}'.",
            )
            return None
        if not isinstance(raw, dict):
            self._error(
                "INVALID_JSON",
                rel,
                "(root)",
                f"Expected a JSON object in '{rel}'.",
                f"The root element of '{rel}' must be a JSON object.",
            )
            return None
        return raw

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def validate(self) -> ValidationResult:
        manifest_raw, manifest_file, manifest = self._load_manifest()
        is_yaml_pack = (self._pack_dir / "manifest.yaml").exists()

        if manifest_raw is None:
            return self._build_result(None)

        self._validate_manifest_semantics(manifest_raw, manifest_file)
        self._validate_safety_policy(manifest_raw, manifest_file)
        self._validate_all_npcs()
        self._validate_entry_scenarios(manifest_raw, manifest_file)

        if is_yaml_pack:
            self._validate_yaml_pack_scenarios()
            self._validate_smoke_tests(manifest_raw, manifest_file)

        self._scan_for_forbidden_files()

        return self._build_result(manifest)

    def _build_result(self, manifest: Optional[PackManifest]) -> ValidationResult:
        errors = [i for i in self._issues if i.severity == ValidationSeverity.ERROR]
        warnings = [i for i in self._issues if i.severity == ValidationSeverity.WARNING]
        rule_ids = list(dict.fromkeys(e.rule_id for e in errors))
        return ValidationResult(
            valid=len(errors) == 0,
            pack_id=manifest.pack_id if manifest else None,
            name=manifest.name if manifest else None,
            version=manifest.version if manifest else None,
            errors=errors,
            warnings=warnings,
            rule_ids=rule_ids,
            manifest=manifest,
        )

    # ------------------------------------------------------------------
    # Manifest loading
    # ------------------------------------------------------------------

    def _load_manifest(
        self,
    ) -> tuple[Optional[dict], str, Optional[PackManifest]]:
        yaml_path = self._pack_dir / "manifest.yaml"
        json_path = self._pack_dir / "pack.json"

        if yaml_path.exists():
            manifest_file = "manifest.yaml"
            raw = self._load_yaml(yaml_path)
        elif json_path.exists():
            manifest_file = "pack.json"
            raw = self._load_json(json_path)
        else:
            self._error(
                "MISSING_MANIFEST",
                ".",
                "(root)",
                "No manifest found. Expected 'manifest.yaml' or 'pack.json' at the pack root.",
                "Create a 'manifest.yaml' file at the root of your pack directory.",
            )
            return None, "", None

        if raw is None:
            return None, manifest_file, None

        self._schema_errors(raw, "pack", manifest_file)

        try:
            manifest = PackManifest.model_validate(raw)
        except Exception:
            manifest = None

        return raw, manifest_file, manifest

    # ------------------------------------------------------------------
    # Semantic manifest checks
    # ------------------------------------------------------------------

    def _validate_manifest_semantics(self, raw: dict, manifest_file: str) -> None:
        self._check_pack_id(raw.get("pack_id", ""), manifest_file)
        self._check_content_rating(raw, manifest_file)
        self._check_license(raw, manifest_file)
        self._check_external_url_policy(raw, manifest_file)

    def _check_pack_id(self, pack_id: str, manifest_file: str) -> None:
        _FORBIDDEN = {'"', "/", "\\", "\r", "\n", "\x00"}
        if not pack_id:
            self._error(
                "INVALID_PACK_ID",
                manifest_file,
                "/pack_id",
                "pack_id must not be empty.",
                "Set pack_id to a reverse-domain identifier such as 'yourname.pack_name'.",
            )
        elif pack_id == ".":
            self._error(
                "INVALID_PACK_ID",
                manifest_file,
                "/pack_id",
                "pack_id '.' is not a valid identifier.",
                "Set pack_id to a reverse-domain identifier such as 'yourname.pack_name'.",
            )
        elif ".." in pack_id or any(c in pack_id for c in _FORBIDDEN):
            self._error(
                "INVALID_PACK_ID",
                manifest_file,
                "/pack_id",
                f"pack_id contains unsafe characters: {pack_id!r}",
                "Use only lowercase letters, digits, underscores, and dots "
                "(e.g. 'yourname.pack_name').",
            )

    def _check_content_rating(self, raw: dict, manifest_file: str) -> None:
        rating = raw.get("content_rating", "")
        if rating and rating not in CONTENT_RATINGS:
            self._error(
                "INVALID_CONTENT_RATING",
                manifest_file,
                "/content_rating",
                f"Invalid content_rating '{rating}'. Allowed values: G, PG, PG-13.",
                "Change content_rating to G (all ages), PG (mild), or PG-13 (teen).",
            )

    def _check_license(self, raw: dict, manifest_file: str) -> None:
        lic = raw.get("license", "")
        if lic and lic not in _SPDX_LICENSES:
            self._warning(
                "UNKNOWN_LICENSE",
                manifest_file,
                "/license",
                f"'{lic}' is not a recognised SPDX license identifier.",
                "Use a standard SPDX identifier such as 'CC-BY-4.0', 'MIT', or 'Apache-2.0'. "
                "A full list is at https://spdx.org/licenses/",
            )

    def _check_external_url_policy(self, raw: dict, manifest_file: str) -> None:
        assets = raw.get("assets")
        if isinstance(assets, dict) and assets.get("allow_external_urls") is True:
            self._error(
                "EXTERNAL_URLS_ALLOWED",
                manifest_file,
                "/assets/allow_external_urls",
                "allow_external_urls must be false — packs must not load external resources.",
                "Set 'assets:\n  allow_external_urls: false' in your manifest.",
            )

    # ------------------------------------------------------------------
    # Safety policy file
    # ------------------------------------------------------------------

    def _validate_safety_policy(self, raw: dict, manifest_file: str) -> None:
        safety = raw.get("safety") or {}
        policy_str = safety.get("policy", "") if isinstance(safety, dict) else ""
        if not policy_str:
            return

        policy_path = (self._pack_dir / policy_str).resolve()
        try:
            policy_path.relative_to(self._pack_dir)
        except ValueError:
            self._error(
                "PATH_TRAVERSAL",
                manifest_file,
                "/safety/policy",
                f"Safety policy path escapes pack directory: '{policy_str}'",
                "Use a relative path for safety.policy (e.g. 'safety/default.yaml').",
            )
            return

        if not policy_path.exists():
            self._error(
                "MISSING_FILE",
                manifest_file,
                "/safety/policy",
                f"Safety policy file not found: '{policy_str}'",
                f"Create the safety policy file at '{policy_str}' inside the pack.",
            )
            return

        safety_data = self._load_yaml(policy_path)
        if safety_data is not None:
            self._schema_errors(safety_data, "safety", self._rel(policy_path))

    # ------------------------------------------------------------------
    # NPC validation (all pack formats)
    # ------------------------------------------------------------------

    def _validate_all_npcs(self) -> None:
        npcs_dir = self._pack_dir / "npcs"
        if not npcs_dir.is_dir():
            return
        for npc_path in sorted(npcs_dir.glob("*.yaml")):
            self._validate_npc_file(npc_path)

    def _validate_npc_file(self, npc_path: Path) -> None:
        npc_data = self._load_yaml(npc_path)
        if npc_data is None:
            return
        rel = self._rel(npc_path)
        self._schema_errors(npc_data, "npc", rel)
        if npc_data.get("fictional") is not True:
            npc_id = npc_data.get("npc_id", rel)
            self._error(
                "NPC_NOT_FICTIONAL",
                rel,
                "/fictional",
                f"NPC '{npc_id}' is missing 'fictional: true'. All NPCs must be declared fictional.",
                "Add 'fictional: true' to this NPC file. "
                "Impersonating real people is not permitted.",
            )
        self._validated_content.add(npc_path.resolve())

    # ------------------------------------------------------------------
    # Entry scenario path checks (JSON-format packs)
    # ------------------------------------------------------------------

    def _validate_entry_scenarios(self, raw: dict, manifest_file: str) -> None:
        for ref in raw.get("entry_scenarios", []):
            self._check_scenario_path(ref, manifest_file, "/entry_scenarios")

    def _check_scenario_path(self, ref: str, from_file: str, pointer: str) -> None:
        if "\x00" in ref:
            self._error(
                "UNSAFE_PATH",
                from_file,
                pointer,
                f"Path contains a null byte: {ref!r}",
                "Remove null bytes from file paths.",
            )
            return
        norm = ref.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            self._error(
                "UNSAFE_PATH",
                from_file,
                pointer,
                f"Unsafe path: {ref!r}",
                "Use a relative path that does not escape the pack directory.",
            )
            return
        resolved = (self._pack_dir / ref).resolve()
        try:
            resolved.relative_to(self._pack_dir)
        except ValueError:
            self._error(
                "PATH_TRAVERSAL",
                from_file,
                pointer,
                f"Path escapes the pack directory: {ref!r}",
                "Ensure all file paths are relative and stay within the pack folder.",
            )
            return
        if not resolved.is_file():
            self._error(
                "MISSING_FILE",
                from_file,
                pointer,
                f"Entry scenario file not found: '{ref}'",
                f"Create the file at '{ref}' or remove it from entry_scenarios.",
            )

    # ------------------------------------------------------------------
    # Deep scenario validation (YAML-format packs only)
    # ------------------------------------------------------------------

    def _validate_yaml_pack_scenarios(self) -> None:
        scenarios_dir = self._pack_dir / "scenarios"
        if not scenarios_dir.is_dir():
            return
        for scenario_path in sorted(scenarios_dir.glob("*.yaml")):
            self._validate_scenario_file(scenario_path)

    def _validate_scenario_file(self, scenario_path: Path) -> None:
        scenario_data = self._load_yaml(scenario_path)
        if scenario_data is None:
            return
        rel = self._rel(scenario_path)
        self._schema_errors(scenario_data, "scenario", rel)
        self._check_scenario_ref(scenario_data, scenario_path, "npc", "npc")
        self._check_scenario_ref(scenario_data, scenario_path, "rubric", "rubric")
        self._check_scenario_ref(scenario_data, scenario_path, "scene", "scene")

    def _check_scenario_ref(
        self,
        scenario_data: dict,
        scenario_path: Path,
        section_key: str,
        schema_key: str,
    ) -> None:
        rel = self._rel(scenario_path)
        section = scenario_data.get(section_key)
        if not isinstance(section, dict):
            return
        ref_str = section.get("ref")
        if not ref_str:
            return

        ref_path = (scenario_path.parent / ref_str).resolve()
        try:
            ref_path.relative_to(self._pack_dir)
        except ValueError:
            self._error(
                "PATH_TRAVERSAL",
                rel,
                f"/{section_key}/ref",
                f"{section_key}.ref escapes pack directory: '{ref_str}'",
                f"Use a relative path for {section_key}.ref.",
            )
            return

        if not ref_path.exists():
            self._error(
                "MISSING_FILE",
                rel,
                f"/{section_key}/ref",
                f"{section_key.capitalize()} file not found: '{ref_str}'",
                f"Create the {section_key} file at the path specified by {section_key}.ref.",
            )
            return

        # Skip content validation if the file was already validated by a bulk
        # scan (e.g. _validate_all_npcs) — avoids duplicate errors for files
        # that appear both in a named directory and as scenario refs.
        if ref_path in self._validated_content:
            return

        ref_data = self._load_yaml(ref_path)
        if ref_data is None:
            return

        ref_rel = self._rel(ref_path)
        self._schema_errors(ref_data, schema_key, ref_rel)
        self._validated_content.add(ref_path)

        if schema_key == "npc" and ref_data.get("fictional") is not True:
            npc_id = ref_data.get("npc_id", ref_rel)
            self._error(
                "NPC_NOT_FICTIONAL",
                ref_rel,
                "/fictional",
                f"NPC '{npc_id}' is missing 'fictional: true'. All NPCs must be declared fictional.",
                "Add 'fictional: true' to this NPC file. "
                "Impersonating real people is not permitted.",
            )

    # ------------------------------------------------------------------
    # Smoke-test presence (official packs only)
    # ------------------------------------------------------------------

    def _validate_smoke_tests(self, raw: dict, manifest_file: str) -> None:
        pack_id = raw.get("pack_id", "")
        if not pack_id.startswith("official."):
            return

        tests_dir = self._pack_dir / "tests"
        test_files = list(tests_dir.glob("*.yaml")) if tests_dir.is_dir() else []

        if not test_files:
            self._error(
                "MISSING_SMOKE_TESTS",
                manifest_file,
                "/pack_id",
                (
                    f"Official pack '{pack_id}' has no smoke tests in the tests/ directory. "
                    "At least one smoke test is required for all official packs."
                ),
                "Add at least one test fixture YAML file in the 'tests/' directory. "
                "See schemas/pack-test.schema.json for the required format.",
            )
            return

        for test_path in sorted(test_files):
            test_data = self._load_yaml(test_path)
            if test_data is not None:
                self._schema_errors(test_data, "pack-test", self._rel(test_path))

    # ------------------------------------------------------------------
    # File-system security scan (all packs)
    # ------------------------------------------------------------------

    def _scan_for_forbidden_files(self) -> None:
        for path in self._pack_dir.rglob("*"):
            if path.is_symlink():
                rel = self._rel(path)
                self._error(
                    "SYMLINK_IN_PACK",
                    rel,
                    "(root)",
                    f"Symlinks are not permitted in a pack: '{rel}'",
                    "Remove the symlink and include the file content directly.",
                )
            elif path.is_file() and path.suffix.lower() in FORBIDDEN_EXTENSIONS:
                rel = self._rel(path)
                self._error(
                    "FORBIDDEN_EXTENSION",
                    rel,
                    "(root)",
                    f"Executable or script file not allowed in pack: '{rel}'",
                    (
                        f"Remove '{rel}'. Packs must contain only data files "
                        "(YAML, JSON, images, audio)."
                    ),
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_pack_dir(pack_dir: Path) -> ValidationResult:
    """Validate *pack_dir* and return a :class:`ValidationResult`.

    Supports both ``manifest.yaml`` (YAML format) and ``pack.json`` (JSON
    format) packs.  All issues are collected in a single pass — the validator
    never short-circuits on the first error and never executes any content from
    the pack.

    Returns:
        A :class:`ValidationResult` whose ``valid`` flag is ``True`` when there
        are no errors (warnings are permitted).  The ``manifest`` field is
        populated whenever the manifest could be parsed, regardless of other
        validation failures.
    """
    return _PackValidator(pack_dir).validate()


def errors_to_rule_ids(errors: list[str]) -> list[str]:
    """Map a list of error message strings to unique rule ID strings.

    Classifies error messages (from string-based validation output or CLI tools)
    into structured rule IDs for API and CLI responses.  Order is preserved;
    duplicates are removed.
    """
    seen: set[str] = set()
    result: list[str] = []
    for error in errors:
        rule_id = _classify_error_message(error)
        if rule_id not in seen:
            seen.add(rule_id)
            result.append(rule_id)
    return result


def _classify_error_message(error: str) -> str:
    """Return the rule ID for a single validation error message string."""
    # Null byte in an entry scenario path — checked before generic path checks.
    if "null byte" in error and (
        "entry scenario" in error.lower() or "scenarios/" in error.lower()
    ):
        return "UNSAFE_ENTRY_SCENARIO"
    # Manifest YAML must be a mapping (top-level element is not a dict).
    if "must be a YAML mapping" in error:
        return "INVALID_MANIFEST_YAML"
    # Missing entry scenario file — checked BEFORE schema-violation patterns so
    # that filenames containing the word 'required' are not misclassified.
    if "Entry scenario file not found:" in error:
        return "MISSING_ENTRY_SCENARIO"
    # Forbidden file extension (executable/script in pack).
    if "not allowed in pack" in error:
        return "FORBIDDEN_EXTENSION"
    # JSON Schema violations (e.g. "[field]: value does not match", "is a required property").
    if "does not match" in error or _re.search(r"\[[\w_-]+\]:", error):
        return "SCHEMA_VIOLATION"
    if "is a required property" in error:
        return "SCHEMA_VIOLATION"
    return "UNKNOWN"


# Module-level in-memory cache keyed by (resolved_path, version, max_mtime).
# Automatically invalidated when any file in the pack changes.
# Cleared on process restart — never persisted to disk.
_result_cache: dict[tuple, ValidationResult] = {}


def validate_pack_cached(pack_dir: Path) -> ValidationResult:
    """Return a cached :class:`ValidationResult`, re-validating on mtime change.

    The cache key includes the pack version and the maximum mtime of all files
    in the directory, so any modification triggers a fresh validation.
    """
    resolved = pack_dir.resolve()
    version = _read_version(resolved)
    try:
        max_mtime = max(f.stat().st_mtime for f in resolved.rglob("*") if f.is_file())
    except (ValueError, OSError):
        max_mtime = 0.0

    key = (str(resolved), version, max_mtime)
    if key in _result_cache:
        return _result_cache[key]

    result = validate_pack_dir(resolved)
    _result_cache[key] = result
    return result


def clear_validation_cache() -> None:
    """Clear the in-memory validation result cache (call from tests or after pack edits)."""
    _result_cache.clear()


def _read_version(pack_dir: Path) -> str:
    """Quick manifest read for the cache key — ignores parse errors."""
    yaml_path = pack_dir / "manifest.yaml"
    json_path = pack_dir / "pack.json"
    try:
        if yaml_path.exists():
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            return str(raw.get("version", ""))
        if json_path.exists():
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            return str(raw.get("version", ""))
    except Exception:
        pass
    return ""
