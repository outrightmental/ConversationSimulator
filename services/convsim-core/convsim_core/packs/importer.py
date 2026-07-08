# SPDX-License-Identifier: Apache-2.0
"""Safe pack import from folder or zip archive with atomic rollback on failure."""
import io
import json
import logging
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import yaml

from convsim_core.errors import ConvsimError
from convsim_core.packs.asset_indexer import index_pack_assets
from convsim_core.packs.models import ImportResult, PackManifest, ScenarioInsertData
from convsim_core.packs.validator import validate_pack_dir
from convsim_core.storage.repositories.pack_repo import get_pack_by_slug, insert_pack, insert_scenario

logger = logging.getLogger(__name__)


class PackConflictError(ConvsimError):
    """Raised when a pack with the same id is already installed."""

    def __init__(self, pack_id: str, installed_version: str) -> None:
        super().__init__(
            "PACK_CONFLICT",
            f"Pack '{pack_id}' (version '{installed_version}') is already installed.",
            status_code=409,
        )


_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB


def safe_extract_zip(zip_bytes: bytes, dest: Path) -> None:
    """
    Extract zip_bytes into dest, rejecting any member whose resolved path would
    land outside dest (zip-slip attack prevention).
    """
    dest_resolved = dest.resolve()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            total_size = sum(m.file_size for m in zf.infolist())
            if total_size > _MAX_UNCOMPRESSED_BYTES:
                raise ConvsimError(
                    "ZIP_TOO_LARGE",
                    f"Archive expands to {total_size // (1024 * 1024)} MB, "
                    f"exceeding the {_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB limit.",
                    status_code=422,
                )
            for member in zf.infolist():
                name = member.filename.replace("\\", "/")
                parts = [p for p in name.split("/") if p]
                if ".." in parts:
                    raise ConvsimError(
                        "ZIP_SLIP",
                        f"Directory traversal detected in archive: {member.filename!r}",
                        status_code=422,
                    )
                if name.startswith("/"):
                    raise ConvsimError(
                        "ZIP_SLIP",
                        f"Absolute path in archive: {member.filename!r}",
                        status_code=422,
                    )
                unix_mode = member.external_attr >> 16
                if unix_mode and stat.S_ISLNK(unix_mode):
                    raise ConvsimError(
                        "ZIP_SLIP",
                        f"Symlinks are not permitted in pack archives: {member.filename!r}",
                        status_code=422,
                    )
                try:
                    (dest / name).resolve().relative_to(dest_resolved)
                except ValueError:
                    raise ConvsimError(
                        "ZIP_SLIP",
                        f"Path escape detected in archive member: {member.filename!r}",
                        status_code=422,
                    )
            zf.extractall(dest)
    except ConvsimError:
        raise
    except zipfile.BadZipFile as exc:
        raise ConvsimError(
            "INVALID_ZIP",
            f"Corrupt zip archive: {exc}",
            status_code=422,
        ) from exc
    except Exception as exc:
        raise ConvsimError(
            "INVALID_ZIP",
            f"Could not read zip archive: {type(exc).__name__}: {exc}",
            status_code=422,
        ) from exc
    actual_size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    if actual_size > _MAX_UNCOMPRESSED_BYTES:
        raise ConvsimError(
            "ZIP_TOO_LARGE",
            f"Archive expands to {actual_size // (1024 * 1024)} MB, "
            f"exceeding the {_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB limit.",
            status_code=422,
        )


def _parse_scenario_yaml(path: Path) -> dict:
    """Load a scenario YAML file, returning {} on any parse error."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _discover_scenarios(
    pack_dir: Path,
    manifest: PackManifest,
) -> list[ScenarioInsertData]:
    """Return ScenarioInsertData list for scenario files found in the pack."""
    seen: set[str] = set()
    scenarios: list[ScenarioInsertData] = []

    def _process_file(path: Path, rel_path: str) -> None:
        slug = path.stem
        if slug in seen:
            return
        seen.add(slug)
        raw = _parse_scenario_yaml(path)
        scenarios.append(_scenario_data_from_raw(raw, slug, rel_path, manifest))

    for ref in manifest.entry_scenarios:
        path = pack_dir / ref
        if path.is_file():
            rel = ref.replace("\\", "/")
            _process_file(path, rel)

    scenarios_dir = pack_dir / "scenarios"
    if scenarios_dir.is_dir():
        for f in sorted(scenarios_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".yaml", ".yml", ".json"):
                rel = "scenarios/" + f.name
                _process_file(f, rel)

    return scenarios


def _scenario_data_from_raw(
    raw: dict,
    slug: str,
    rel_path: str,
    manifest: PackManifest,
) -> ScenarioInsertData:
    """Build a ScenarioInsertData from parsed YAML content and pack manifest."""
    title: Optional[str] = raw.get("title")
    summary: Optional[str] = raw.get("summary")

    duration = raw.get("duration") or {}
    max_turns: Optional[int] = duration.get("max_turns")
    soft_time_limit: Optional[int] = duration.get("soft_time_limit_minutes")

    difficulty = raw.get("difficulty") or {}
    difficulty_default: Optional[str] = difficulty.get("default")

    requirements = raw.get("requirements") or manifest.requirements or {}
    voice_support: bool = bool(requirements.get("voice_support", False))
    model_recommendation: Optional[str] = requirements.get("model_recommendation")

    return ScenarioInsertData(
        slug=slug,
        name=_slug_to_name(slug),
        title=title,
        summary=summary,
        content_rating=manifest.content_rating,
        difficulty_default=difficulty_default,
        max_turns=max_turns,
        soft_time_limit_minutes=soft_time_limit,
        tags_json=json.dumps(manifest.tags) if manifest.tags else None,
        voice_support=voice_support,
        model_recommendation=model_recommendation,
        rel_path=rel_path,
        pack_name=manifest.name,
        pack_description=manifest.description,
        pack_tags=manifest.tags,
    )


def _slug_to_name(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").title()


def _install_from_dir(
    source_dir: Path,
    packs_base_dir: Path,
    conn: sqlite3.Connection,
) -> ImportResult:
    """
    Validate and atomically install a pack from source_dir into packs_base_dir.

    On any failure: DB changes are rolled back and temp files are cleaned up,
    leaving the packs_base_dir in its prior state.
    """
    validation = validate_pack_dir(source_dir)
    if validation.errors:
        raise ConvsimError(
            "PACK_INVALID",
            f"Pack validation failed: {'; '.join(e.message for e in validation.errors)}",
            status_code=422,
        )
    if validation.manifest is None:
        raise ConvsimError("PACK_INVALID", "Pack manifest could not be loaded.", status_code=422)
    manifest = validation.manifest

    safe_name = manifest.pack_id.replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise ConvsimError(
            "PACK_INVALID",
            f"pack_id {manifest.pack_id!r} produces an empty install directory name.",
            status_code=422,
        )
    pack_dest = packs_base_dir / safe_name
    try:
        rel = pack_dest.resolve().relative_to(packs_base_dir.resolve())
    except ValueError:
        raise ConvsimError(
            "PATH_ESCAPE",
            f"Pack id would install outside packs directory: {manifest.pack_id!r}",
            status_code=422,
        )
    if str(rel) in {".", ""}:
        raise ConvsimError(
            "PATH_ESCAPE",
            f"Pack id resolves to the packs base directory itself: {manifest.pack_id!r}",
            status_code=422,
        )

    existing = get_pack_by_slug(conn, manifest.pack_id)
    if existing is not None:
        raise PackConflictError(manifest.pack_id, existing.version)

    tmp_dest = packs_base_dir / f"._tmp_{safe_name}"
    if tmp_dest.exists():
        shutil.rmtree(tmp_dest)

    try:
        shutil.copytree(source_dir, tmp_dest)

        pack_db_id = insert_pack(conn, manifest, str(pack_dest))

        scenario_list = _discover_scenarios(tmp_dest, manifest)
        slug_to_scenario_id: dict[str, int] = {}
        for scenario_data in scenario_list:
            scenario_db_id = insert_scenario(conn, pack_db_id, scenario_data)
            slug_to_scenario_id[scenario_data.slug] = scenario_db_id

        if pack_dest.exists():
            shutil.rmtree(pack_dest)
        pack_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_dest), str(pack_dest))

        assets_count = index_pack_assets(conn, pack_dest, pack_db_id, manifest.license, slug_to_scenario_id)

        conn.commit()
        logger.info(
            "Installed pack '%s' v%s (%d scenarios, %d assets)",
            manifest.pack_id,
            manifest.version,
            len(scenario_list),
            assets_count,
        )
        return ImportResult(
            pack_slug=manifest.pack_id,
            pack_name=manifest.name,
            pack_version=manifest.version,
            scenarios_indexed=len(scenario_list),
            assets_indexed=assets_count,
        )

    except Exception:
        conn.rollback()
        if tmp_dest.exists():
            shutil.rmtree(tmp_dest, ignore_errors=True)
        if pack_dest.exists() and not (source_dir.resolve() == pack_dest.resolve()):
            shutil.rmtree(pack_dest, ignore_errors=True)
        raise


def import_from_folder(
    folder_path: Path,
    packs_base_dir: Path,
    conn: sqlite3.Connection,
) -> ImportResult:
    """Import a pack from a local folder (read-only source; files are copied)."""
    if not folder_path.is_dir():
        raise ConvsimError("NOT_FOUND", f"Folder not found: {folder_path}", status_code=404)
    return _install_from_dir(folder_path, packs_base_dir, conn)


def import_from_zip(
    zip_bytes: bytes,
    packs_base_dir: Path,
    conn: sqlite3.Connection,
) -> ImportResult:
    """Import a pack from raw zip bytes, rejecting unsafe archives."""
    if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
        raise ConvsimError(
            "INVALID_ZIP",
            "Uploaded file is not a valid zip archive.",
            status_code=422,
        )

    with tempfile.TemporaryDirectory(prefix="convsim_pack_import_") as tmp_root:
        extract_dir = Path(tmp_root) / "extracted"
        extract_dir.mkdir()

        safe_extract_zip(zip_bytes, extract_dir)

        top_level = list(extract_dir.iterdir())
        pack_source = top_level[0] if len(top_level) == 1 and top_level[0].is_dir() else extract_dir

        return _install_from_dir(pack_source, packs_base_dir, conn)
