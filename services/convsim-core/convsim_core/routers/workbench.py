# SPDX-License-Identifier: Apache-2.0
"""Creator Workbench endpoints: browse and edit scenario pack files.

Official packs (the repo's bundled ``packs/official``) are browse-only; the
local-dev root is editable.  Write endpoints enforce local-dev-only access,
path-traversal rejection, and an editable-extension whitelist so the
unauthenticated local endpoint cannot be used to write arbitrary files.
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from convsim_core.config import ServiceConfig
from convsim_core.errors import ConvsimError
from convsim_core.runtime.active import unpinned_session_runtime_is_model_free
from convsim_core.packs.importer import safe_extract_zip
from convsim_core.packs.models import ValidationResult
from convsim_core.packs.validator import validate_pack_cached, validate_pack_dir

router = APIRouter(prefix="/api/workbench", tags=["workbench"])

PackKind = Literal["official", "local-dev"]

_EDITABLE_EXTENSIONS = {".yaml", ".yml", ".md", ".txt"}

_PACK_ID_RE = re.compile(r"^pack_id:\s*['\"]?([^'\"\n]+)['\"]?\s*$")
_NAME_RE = re.compile(r"^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$")


class WorkbenchPackSummary(BaseModel):
    kind: PackKind
    slug: str
    pack_id: Optional[str] = None
    name: Optional[str] = None
    editable: bool


class FileNode(BaseModel):
    name: str
    path: str
    kind: Literal["yaml", "markdown", "text", "dir", "other"]
    children: Optional[list["FileNode"]] = None


class FileTreeResponse(BaseModel):
    tree: list[FileNode]


class FileContentResponse(BaseModel):
    content: str
    editable: bool


class WriteFileBody(BaseModel):
    content: str


class WriteFileResponse(BaseModel):
    ok: bool
    # Validation is re-run against the whole pack after a successful save so the
    # editor can surface schema/policy problems introduced by the edit.
    validation: Optional[ValidationResult] = None


def _official_root(config: ServiceConfig) -> Path:
    return Path(config.official_packs_dir)


def _local_dev_root(config: ServiceConfig) -> Path:
    if config.local_dev_packs_dir:
        return Path(config.local_dev_packs_dir)
    return Path(config.packs_dir) / "local-dev"


def _root_for_kind(config: ServiceConfig, kind: PackKind) -> Path:
    return _official_root(config) if kind == "official" else _local_dev_root(config)


def _assert_valid_kind(kind: str) -> PackKind:
    if kind not in ("official", "local-dev"):
        raise ConvsimError(
            "INVALID_KIND",
            f'Invalid kind "{kind}": must be "official" or "local-dev"',
            status_code=400,
        )
    return kind  # type: ignore[return-value]


def _is_strictly_within(path: Path, base: Path) -> bool:
    """True if ``path`` is a descendant of ``base`` (and not ``base`` itself)."""
    if path == base:
        return False
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _pack_root(config: ServiceConfig, kind: PackKind, slug: str) -> Path:
    root = _root_for_kind(config, kind).resolve()
    pack_root = (root / slug).resolve()
    if not _is_strictly_within(pack_root, root):
        raise ConvsimError("INVALID_SLUG", "Invalid pack slug", status_code=400)
    return pack_root


def _resolve_file_path(pack_root: Path, rel_path: str) -> Path:
    abs_path = (pack_root / rel_path).resolve()
    if not _is_strictly_within(abs_path, pack_root):
        raise ConvsimError("PATH_TRAVERSAL", "Path traversal not allowed", status_code=400)
    return abs_path


def _read_manifest_basics(pack_dir: Path) -> tuple[Optional[str], Optional[str]]:
    pack_id: Optional[str] = None
    name: Optional[str] = None
    try:
        content = (pack_dir / "manifest.yaml").read_text(encoding="utf-8")
    except OSError:
        return None, None
    for line in content.splitlines():
        if pack_id is None:
            m = _PACK_ID_RE.match(line)
            if m:
                pack_id = m.group(1).strip()
        if name is None:
            m = _NAME_RE.match(line)
            if m:
                name = m.group(1).strip()
        if pack_id is not None and name is not None:
            break
    return pack_id, name


def _scan_root(config: ServiceConfig, kind: PackKind) -> list[WorkbenchPackSummary]:
    root = _root_for_kind(config, kind)
    if not root.is_dir():
        return []
    summaries: list[WorkbenchPackSummary] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        pack_id, name = _read_manifest_basics(entry)
        summaries.append(
            WorkbenchPackSummary(
                kind=kind,
                slug=entry.name,
                pack_id=pack_id,
                name=name or entry.name,
                editable=(kind == "local-dev"),
            )
        )
    return summaries


def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext == ".md":
        return "markdown"
    if ext == ".txt":
        return "text"
    return "other"


def _build_tree(directory: Path, pack_root: Path) -> list[FileNode]:
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []

    nodes: list[FileNode] = []
    for entry in entries:
        rel_path = entry.relative_to(pack_root).as_posix()
        if entry.is_dir():
            nodes.append(
                FileNode(
                    name=entry.name,
                    path=rel_path,
                    kind="dir",
                    children=_build_tree(entry, pack_root),
                )
            )
        elif entry.is_file():
            nodes.append(FileNode(name=entry.name, path=rel_path, kind=_file_kind(entry)))  # type: ignore[arg-type]

    nodes.sort(key=lambda n: (n.kind != "dir", n.name.lower()))
    return nodes


def _config(request: Request) -> ServiceConfig:
    return request.app.state.service_config


@router.get("/packs", response_model=list[WorkbenchPackSummary])
async def list_packs(request: Request) -> list[WorkbenchPackSummary]:
    """List official and local-dev packs by scanning their root directories."""
    config = _config(request)
    return [*_scan_root(config, "official"), *_scan_root(config, "local-dev")]


@router.get("/packs/{kind}/{slug}/files", response_model=FileTreeResponse)
async def list_files(request: Request, kind: str, slug: str) -> FileTreeResponse:
    """Return a recursive file tree for a pack."""
    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    pack_root = _pack_root(config, valid_kind, slug)
    if not pack_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)
    return FileTreeResponse(tree=_build_tree(pack_root, pack_root))


@router.get("/packs/{kind}/{slug}/file", response_model=FileContentResponse)
async def read_file(
    request: Request,
    kind: str,
    slug: str,
    path: str = Query(default=""),
) -> FileContentResponse:
    """Read a single file within a pack."""
    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    if not path:
        raise ConvsimError("MISSING_PATH", "Missing required query parameter: path", status_code=400)
    pack_root = _pack_root(config, valid_kind, slug)
    abs_path = _resolve_file_path(pack_root, path)
    if not abs_path.exists():
        raise ConvsimError("FILE_NOT_FOUND", f"File not found: {path}", status_code=404)
    if not abs_path.is_file():
        raise ConvsimError("NOT_A_FILE", f"Path is not a file: {path}", status_code=400)
    content = abs_path.read_text(encoding="utf-8")
    return FileContentResponse(content=content, editable=(valid_kind == "local-dev"))


@router.put("/packs/{kind}/{slug}/file", response_model=WriteFileResponse)
async def write_file(
    request: Request,
    kind: str,
    slug: str,
    body: WriteFileBody,
    path: str = Query(default=""),
) -> WriteFileResponse:
    """Write a single file within a local-dev pack (official packs are read-only)."""
    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    if valid_kind != "local-dev":
        raise ConvsimError(
            "READ_ONLY_PACK",
            "Official packs are read-only. Copy to local-dev first.",
            status_code=403,
        )
    if not path:
        raise ConvsimError("MISSING_PATH", "Missing required query parameter: path", status_code=400)
    pack_root = _pack_root(config, valid_kind, slug)
    abs_path = _resolve_file_path(pack_root, path)
    if abs_path.suffix.lower() not in _EDITABLE_EXTENSIONS:
        raise ConvsimError(
            "NOT_EDITABLE",
            f'File type "{abs_path.suffix}" is not editable via the workbench',
            status_code=400,
        )
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically so a failed write cannot corrupt an existing file.
    tmp_path = abs_path.with_name(f"{abs_path.name}.tmp.{secrets.token_hex(4)}")
    try:
        tmp_path.write_text(body.content, encoding="utf-8")
        os.replace(tmp_path, abs_path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    # Re-run validation so the save "refreshes" the pack's validation state.
    # validate_pack_cached keys on file mtimes, so the just-written change forces
    # a fresh pass. Never let a validation failure mask a successful write.
    validation: Optional[ValidationResult] = None
    try:
        validation = validate_pack_cached(pack_root)
    except Exception:  # noqa: BLE001 — validation is best-effort feedback
        validation = None
    return WriteFileResponse(ok=True, validation=validation)


@router.get("/packs/{kind}/{slug}/validate", response_model=ValidationResult)
async def validate_pack(request: Request, kind: str, slug: str) -> ValidationResult:
    """Validate a pack directory and return schema/policy findings.

    Used by the workbench to show a pack's validation state when it is opened
    and to refresh it after a save.
    """
    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    pack_root = _pack_root(config, valid_kind, slug)
    if not pack_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)
    return validate_pack_cached(pack_root)


@router.post("/packs/{kind}/{slug}/copy-to-local", response_model=WorkbenchPackSummary)
async def copy_to_local(request: Request, kind: str, slug: str) -> WorkbenchPackSummary:
    """Copy an official pack into the local-dev root, avoiding slug collisions."""
    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    if valid_kind == "local-dev":
        raise ConvsimError("ALREADY_LOCAL", "Pack is already in local-dev", status_code=400)
    src_root = _pack_root(config, valid_kind, slug)
    if not src_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)

    local_root = _local_dev_root(config)
    local_root.mkdir(parents=True, exist_ok=True)

    dest_slug = slug
    dest_path = local_root / dest_slug
    if dest_path.exists():
        dest_slug = f"{slug}-copy"
        dest_path = local_root / dest_slug
    if dest_path.exists():
        n = 2
        while (local_root / f"{slug}-copy-{n}").exists():
            n += 1
        dest_slug = f"{slug}-copy-{n}"
        dest_path = local_root / dest_slug

    shutil.copytree(src_root, dest_path)
    pack_id, name = _read_manifest_basics(dest_path)
    return WorkbenchPackSummary(
        kind="local-dev",
        slug=dest_slug,
        pack_id=pack_id,
        name=name or dest_slug,
        editable=True,
    )


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

_MAX_IMPORT_BYTES = 100 * 1024 * 1024  # 100 MB


class WorkbenchImportResult(BaseModel):
    """Successful pack import result — a WorkbenchPackSummary plus an optional rename notice."""

    kind: Literal["official", "local-dev"]
    slug: str
    pack_id: Optional[str] = None
    name: Optional[str] = None
    editable: bool
    # Set when the slug was changed to avoid a collision with an existing local-dev pack.
    renamed_from: Optional[str] = None


def _slugify_pack_id(pack_id: str) -> str:
    """Derive a filesystem-safe slug from a pack_id."""
    return pack_id.replace("/", "_").replace("\\", "_")


def _unique_local_slug(local_root: Path, base_slug: str) -> tuple[str, Optional[str]]:
    """Return (slug, renamed_from) where renamed_from is the original if a collision occurred."""
    dest = local_root / base_slug
    if not dest.exists():
        return base_slug, None
    # Collision: find a unique name by appending -2, -3, …
    n = 2
    while (local_root / f"{base_slug}-{n}").exists():
        n += 1
    return f"{base_slug}-{n}", base_slug


@router.post("/packs/import", response_model=WorkbenchImportResult, status_code=201)
async def import_pack(request: Request) -> WorkbenchImportResult:
    """Import a pack from a raw zip body into the local-dev directory.

    The zip is validated before extraction. If the pack content fails schema
    validation, a 422 with the ValidationResult is returned so the UI can show
    actionable errors.  Slug collisions are resolved by renaming the incoming
    pack (appending -2, -3, …) and recording the original name in
    ``renamed_from``.
    """
    config = _config(request)
    zip_bytes = await request.body()

    if len(zip_bytes) > _MAX_IMPORT_BYTES:
        raise ConvsimError(
            "FILE_TOO_LARGE",
            f"Uploaded file exceeds the {_MAX_IMPORT_BYTES // (1024 * 1024)} MB limit.",
            status_code=413,
        )

    if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
        raise ConvsimError(
            "INVALID_ZIP",
            "Uploaded file is not a valid .zip archive.",
            status_code=422,
        )

    local_root = _local_dev_root(config)
    local_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="convsim_wb_import_") as tmp_root:
        extract_dir = Path(tmp_root) / "extracted"
        extract_dir.mkdir()
        safe_extract_zip(zip_bytes, extract_dir)

        top_level = list(extract_dir.iterdir())
        pack_source = top_level[0] if len(top_level) == 1 and top_level[0].is_dir() else extract_dir

        validation = validate_pack_dir(pack_source)
        if validation.errors:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=422,
                content=validation.model_dump(exclude={"manifest"}),
            )

        pack_id, name = _read_manifest_basics(pack_source)
        base_slug = _slugify_pack_id(pack_id) if pack_id else pack_source.name
        dest_slug, renamed_from = _unique_local_slug(local_root, base_slug)
        dest_path = local_root / dest_slug

        shutil.copytree(str(pack_source), str(dest_path))

    return WorkbenchImportResult(
        kind="local-dev",
        slug=dest_slug,
        pack_id=pack_id,
        name=name or dest_slug,
        editable=True,
        renamed_from=renamed_from,
    )


@router.get("/packs/{kind}/{slug}/export")
async def export_pack(request: Request, kind: str, slug: str) -> Response:
    """Export a pack directory as a zip archive.

    Runs a validation preflight: if the pack has schema errors the request
    returns 422 with the ValidationResult body so the client can surface them
    before the download starts.  Warnings do not block export.
    """
    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    pack_root = _pack_root(config, valid_kind, slug)
    if not pack_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)

    validation = validate_pack_dir(pack_root)
    if validation.errors:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=422,
            content=validation.model_dump(exclude={"manifest"}),
        )

    # Determine a version string for the filename from manifest if possible.
    import yaml as _yaml  # local import — only needed here
    version = "0.1.0"
    manifest_path = pack_root / "manifest.yaml"
    if manifest_path.is_file():
        try:
            manifest_raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest_raw, dict):
                version = str(manifest_raw.get("version") or version)
        except Exception:  # noqa: BLE001
            pass

    # Build the zip in memory.
    _slug_safe = "".join(c for c in slug.replace("/", "_") if c not in ('"', "\r", "\n"))
    _ver_safe = "".join(c for c in version if c not in ('"', "\\", "/", "\r", "\n"))
    filename = f"{_slug_safe}-{_ver_safe}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(pack_root.rglob("*")):
            if file_path.is_file():
                rel = str(file_path.relative_to(pack_root)).replace("\\", "/")
                zf.write(file_path, f"{_slug_safe}/{rel}")

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Test session
# ---------------------------------------------------------------------------


class WorkbenchTestSessionResponse(BaseModel):
    """Response from starting a workbench test session."""

    session_id: str
    state: str
    npc_opening: str
    state_vars: Dict[str, int]


def _first_scenario_path(pack_root: Path) -> Optional[str]:
    """Return the relative path of the first usable scenario file in the pack."""
    import yaml as _yaml

    manifest_path = pack_root / "manifest.yaml"
    if manifest_path.is_file():
        try:
            raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                entries: List[str] = list(raw.get("entry_scenarios") or [])
                for ref in entries:
                    if (pack_root / ref).is_file():
                        return ref
        except Exception:  # noqa: BLE001
            pass

    scenarios_dir = pack_root / "scenarios"
    if scenarios_dir.is_dir():
        for f in sorted(scenarios_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".yaml", ".yml"):
                return f"scenarios/{f.name}"

    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/packs/{kind}/{slug}/test-session", response_model=WorkbenchTestSessionResponse)
async def start_test_session(request: Request, kind: str, slug: str) -> WorkbenchTestSessionResponse:
    """Start a temporary text-only test session for a workbench pack.

    Finds the first entry scenario in the pack, loads it from disk, registers
    it in the process-local scenario registry, and creates a DB session that
    can be used with the standard ``/api/sessions/{id}/turn`` endpoint.

    The session is flagged with ``save_transcript: false`` so it never appears
    in the player's session history.
    """
    from convsim_core.scenarios import load_scenario_info_from_pack, register_dynamic_scenario
    from convsim_core.scenario_state import build_variable_defs, initialize_state

    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    pack_root = _pack_root(config, valid_kind, slug)
    if not pack_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)

    scenario_rel = _first_scenario_path(pack_root)
    if scenario_rel is None:
        raise ConvsimError(
            "NO_SCENARIO",
            "No scenario found in pack. Add a .yaml file under scenarios/ to test.",
            status_code=422,
        )

    try:
        scenario_info = load_scenario_info_from_pack(pack_root, scenario_rel)
    except Exception as exc:
        raise ConvsimError(
            "SCENARIO_LOAD_ERROR",
            f"Could not load scenario '{scenario_rel}': {exc}",
            status_code=422,
        ) from exc

    # A scenario preview is only meaningful against a real model (issue #476).
    # The setup dict below carries no runtime_id pin, so turns on this session
    # resolve to the shared app runtime — the config-default "fake" on a
    # profile with no model installed, whose every reply is canned. Refuse
    # loudly instead, the same rule create_session applies to player sessions
    # (issue #473).
    conn = request.app.state.db.connection()
    if unpinned_session_runtime_is_model_free(request.app, conn):
        raise ConvsimError(
            "MODEL_REQUIRED",
            "No AI model is configured, so the scenario cannot be previewed. "
            "Finish setup (install the recommended model, or connect Ollama "
            "or a local GGUF file) and try again.",
            status_code=409,
        )

    # Register under a unique ID so the standard turn endpoint can find it.
    dynamic_id = f"__wbtest__{uuid.uuid4().hex}"
    register_dynamic_scenario(dynamic_id, scenario_info)

    # Compute initial state (shown in the state inspector immediately on start).
    var_defs = build_variable_defs(scenario_info.state_variable_overrides)
    initial_state = initialize_state(var_defs)
    opening_text = scenario_info.opening_npc_says or "Hello. Let's begin."

    session_id = f"wbtest-{secrets.token_hex(8)}"
    now = _now_iso()

    setup = {
        "scenario_id": dynamic_id,
        "difficulty": "standard",
        "player_role_name": "Workbench Tester",
        "language": "en",
        "input_mode": "text-only",
        "tts_enabled": False,
        "tts_voice_id": "af_heart",
        "show_state_meters": True,
        "save_transcript": False,
        "_workbench_test": True,
    }

    with conn:
        conn.execute(
            "INSERT INTO turn_sessions "
            "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, turn_count, setup_json, created_at) "
            "VALUES (?, ?, 'PlayerTurnListening', ?, '[]', 0, ?, ?)",
            (session_id, dynamic_id, json.dumps(initial_state), json.dumps(setup), now),
        )
        conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, flow_state_after, created_at) "
            "VALUES (?, 0, 'npc_opening', ?, 'PlayerTurnListening', ?)",
            (session_id, opening_text, now),
        )

    return WorkbenchTestSessionResponse(
        session_id=session_id,
        state="PlayerTurnListening",
        npc_opening=opening_text,
        state_vars=initial_state,
    )


# ---------------------------------------------------------------------------
# Flyting authoring: draft scenarios, and a test volley against them
# ---------------------------------------------------------------------------


class WorkbenchAttackSurfaceTrait(BaseModel):
    id: str
    brief: str
    visibility: Literal["visible", "discoverable"]
    themes: List[str] = []


class WorkbenchFlytingScenario(BaseModel):
    """A flyting scenario as the author's own files currently define it."""

    scenario_id: str
    path: str
    title: str
    target_name: str
    # The whole surface, discoverable traits included — unlike the play payload,
    # which hides them so that finding one can be worth double. The author is
    # the one person who must see everything they wrote.
    attack_surface: List[WorkbenchAttackSurfaceTrait]
    difficulty_multiplier: float
    verse_required: bool
    # Two separate register knobs, reported separately. Surface politeness caps
    # fidelity at 3; whether dropping the gloves is also a *foul* that zeroes
    # the volley is `overt_rudeness_is_foul`, and a pack may set either without
    # the other — so an authoring screen that showed one and labelled it as the
    # other would describe rules the author did not write.
    requires_surface_politeness: bool
    overt_rudeness_is_foul: bool
    anachronism_policy: str
    judge_flavor: str
    lexicon_encouraged: List[str]


class WorkbenchFlytingResponse(BaseModel):
    scenarios: List[WorkbenchFlytingScenario]


class WorkbenchVolleyPreviewBody(BaseModel):
    """A draft volley, and the scenario file in this pack to score it against."""

    scenario_path: str
    content: str
    # Earlier volleys, so freshness and theme decay can be exercised from the
    # authoring screen the same way a run exercises them. Bounded like the play
    # route's preview: the novelty stage compares the draft against every one of
    # these, so an unbounded list is an unbounded amount of work asked of the
    # author's own machine.
    prior_volleys: List[str] = Field(default_factory=list, max_length=20)


class WorkbenchVolleyPreviewResponse(BaseModel):
    scenario_id: str
    volley: Dict[str, Any]
    judge_system_prompt: str


def _pack_flyting_scenario(pack_root: Path, rel_path: str) -> Any:
    """Load one flyting scenario straight from a workbench pack's files.

    Deliberately not ``resolve_flyting_scenario``: that reads the installed pack
    index, and the pack an author is editing is a local-dev copy that was never
    imported, so nothing in the index points at it. The Test Chat panel reads
    the pack from disk for the same reason. ``_resolve_file_path`` keeps the
    traversal guard that makes reading an author-supplied path safe.

    Returns None when the file parses but declares no ``mode: flyting``.
    """
    from convsim_core.flyting.loader import load_flyting_scenario

    abs_path = _resolve_file_path(pack_root, rel_path)
    if not abs_path.is_file():
        raise ConvsimError(
            "FILE_NOT_FOUND", f"File not found: {rel_path}", status_code=404
        )
    pack_id, _ = _read_manifest_basics(pack_root)
    try:
        return load_flyting_scenario(
            pack_root, abs_path.relative_to(pack_root).as_posix(), pack_id=pack_id
        )
    except Exception as exc:  # noqa: BLE001
        raise ConvsimError(
            "SCENARIO_LOAD_ERROR",
            f"Could not load scenario '{rel_path}': {exc}",
            status_code=422,
        ) from exc


@router.get("/packs/{kind}/{slug}/flyting", response_model=WorkbenchFlytingResponse)
async def list_pack_flyting_scenarios(
    request: Request, kind: str, slug: str
) -> WorkbenchFlytingResponse:
    """Every ``mode: flyting`` scenario in a workbench pack, read from its files."""
    from convsim_core.flyting.loader import load_flyting_scenario

    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    pack_root = _pack_root(config, valid_kind, slug)
    if not pack_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)

    pack_id, _ = _read_manifest_basics(pack_root)
    scenarios_dir = pack_root / "scenarios"
    out: List[WorkbenchFlytingScenario] = []
    if scenarios_dir.is_dir():
        for path in sorted(scenarios_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in (".yaml", ".yml"):
                continue
            rel = f"scenarios/{path.name}"
            try:
                scenario = load_flyting_scenario(pack_root, rel, pack_id=pack_id)
            except Exception:  # noqa: BLE001 — a broken draft is the validator's
                continue                # business to report, not this listing's
            if scenario is None:  # a conversation scenario
                continue
            flyting = scenario.flyting
            out.append(
                WorkbenchFlytingScenario(
                    scenario_id=scenario.scenario_id,
                    path=rel,
                    title=scenario.title,
                    target_name=scenario.npc.display_name,
                    attack_surface=[
                        WorkbenchAttackSurfaceTrait(
                            id=trait.id,
                            brief=trait.brief,
                            visibility=(
                                "discoverable" if trait.discoverable else "visible"
                            ),
                            themes=list(trait.themes),
                        )
                        for trait in scenario.attack_surface
                    ],
                    difficulty_multiplier=flyting.difficulty_multiplier,
                    verse_required=flyting.verse.required,
                    requires_surface_politeness=(
                        flyting.register.require_surface_politeness
                    ),
                    overt_rudeness_is_foul=flyting.register.overt_rudeness_is_foul,
                    anachronism_policy=flyting.lexicon.anachronism_policy,
                    judge_flavor=flyting.judge_flavor,
                    lexicon_encouraged=list(flyting.lexicon.encouraged),
                )
            )
    return WorkbenchFlytingResponse(scenarios=out)


@router.post(
    "/packs/{kind}/{slug}/volley-preview",
    response_model=WorkbenchVolleyPreviewResponse,
)
async def preview_pack_volley(
    request: Request, kind: str, slug: str, body: WorkbenchVolleyPreviewBody
) -> WorkbenchVolleyPreviewResponse:
    """Score a draft volley against a draft scenario, before the pack is exported.

    Deterministic stages only — gates, craft, novelty, composition — so no model
    is called and the answer is instant and repeatable. That is also exactly the
    part of a score an author controls by writing the pack: the gates their
    safety policy fires, the difficulty multiplier, the lexicon, the verse
    requirement, and which traits a hook could name. The judge's own rubric
    header is returned alongside so the prompt their scenario produces can be
    read rather than guessed at.
    """
    from convsim_prompt import compose_volley_judge_prompt

    from convsim_core.flyting.service import VolleyScoringService
    from convsim_core.flyting.volley import VolleyInputError

    config = _config(request)
    valid_kind = _assert_valid_kind(kind)
    pack_root = _pack_root(config, valid_kind, slug)
    if not pack_root.exists():
        raise ConvsimError("PACK_NOT_FOUND", f'Pack "{slug}" not found', status_code=404)
    if not body.content.strip():
        raise ConvsimError("EMPTY_VOLLEY", "A volley cannot be blank", status_code=400)

    scenario = _pack_flyting_scenario(pack_root, body.scenario_path)
    if scenario is None:
        raise ConvsimError(
            "NOT_A_FLYTING_SCENARIO",
            f"'{body.scenario_path}' declares no 'mode: flyting', so there is no "
            "volley pipeline to score it with.",
            status_code=422,
        )

    service = VolleyScoringService(scenario.scoring_context())
    try:
        result = service.score_mechanically(
            body.content, prior_volleys=body.prior_volleys
        )
        prepared = service.prepare(body.content)
    except VolleyInputError as exc:
        raise ConvsimError("INVALID_VOLLEY", str(exc), status_code=400) from exc

    bundle = compose_volley_judge_prompt(service.judge_input(prepared))
    return WorkbenchVolleyPreviewResponse(
        scenario_id=scenario.scenario_id,
        volley=result.to_dict(),
        judge_system_prompt=bundle.system_prompt,
    )
