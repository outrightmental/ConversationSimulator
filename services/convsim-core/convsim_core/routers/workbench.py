# SPDX-License-Identifier: Apache-2.0
"""Creator Workbench endpoints: browse and edit scenario pack files.

Official packs (the repo's bundled ``packs/official``) are browse-only; the
local-dev root is editable.  Write endpoints enforce local-dev-only access,
path-traversal rejection, and an editable-extension whitelist so the
unauthenticated local endpoint cannot be used to write arbitrary files.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from convsim_core.config import ServiceConfig
from convsim_core.errors import ConvsimError
from convsim_core.packs.models import ValidationResult
from convsim_core.packs.validator import validate_pack_cached

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
