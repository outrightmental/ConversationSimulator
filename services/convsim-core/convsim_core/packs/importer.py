# SPDX-License-Identifier: Apache-2.0
"""Safe pack import from folder or zip archive with atomic rollback on failure."""
import io
import logging
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path

from convsim_core.errors import ConvsimError
from convsim_core.packs.asset_indexer import index_pack_assets
from convsim_core.packs.models import ImportResult, PackManifest
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


def _discover_scenarios(pack_dir: Path, manifest: PackManifest) -> list[tuple[str, str]]:
    """Return (slug, name) pairs for scenario files found in the pack."""
    seen: set[str] = set()
    scenarios: list[tuple[str, str]] = []

    for ref in manifest.entry_scenarios:
        path = pack_dir / ref
        if path.exists():
            slug = path.stem
            if slug not in seen:
                seen.add(slug)
                scenarios.append((slug, _slug_to_name(slug)))

    scenarios_dir = pack_dir / "scenarios"
    if scenarios_dir.is_dir():
        for f in sorted(scenarios_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".yaml", ".yml", ".json"):
                slug = f.stem
                if slug not in seen:
                    seen.add(slug)
                    scenarios.append((slug, _slug_to_name(slug)))

    return scenarios


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
    manifest, errors = validate_pack_dir(source_dir)
    if errors:
        raise ConvsimError(
            "PACK_INVALID",
            f"Pack validation failed: {'; '.join(errors)}",
            status_code=422,
        )
    if manifest is None:
        raise ConvsimError("PACK_INVALID", "Pack manifest could not be loaded.", status_code=422)

    # Safety: ensure the computed install path stays within packs_base_dir.
    safe_name = manifest.pack_id.replace("/", "_").replace("\\", "_")
    pack_dest = packs_base_dir / safe_name
    try:
        pack_dest.resolve().relative_to(packs_base_dir.resolve())
    except ValueError:
        raise ConvsimError(
            "PATH_ESCAPE",
            f"Pack id would install outside packs directory: {manifest.pack_id!r}",
            status_code=422,
        )

    # Conflict: any existing pack with the same id blocks import regardless of version.
    # A pack directory is keyed by id, so a different version would silently overwrite it.
    existing = get_pack_by_slug(conn, manifest.pack_id)
    if existing is not None:
        raise PackConflictError(manifest.pack_id, existing.version)

    tmp_dest = packs_base_dir / f"._tmp_{safe_name}"
    if tmp_dest.exists():
        shutil.rmtree(tmp_dest)

    try:
        shutil.copytree(source_dir, tmp_dest)

        pack_db_id = insert_pack(conn, manifest, str(pack_dest))

        scenarios = _discover_scenarios(tmp_dest, manifest)
        for slug, name in scenarios:
            insert_scenario(conn, pack_db_id, slug, name)

        # Move staging copy to final destination before indexing so that
        # absolute file_path values stored in asset_index reflect the real location.
        if pack_dest.exists():
            shutil.rmtree(pack_dest)
        pack_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_dest), str(pack_dest))

        assets_count = index_pack_assets(conn, pack_dest, pack_db_id, manifest.license)

        conn.commit()
        logger.info(
            "Installed pack '%s' v%s (%d scenarios, %d assets)",
            manifest.pack_id,
            manifest.version,
            len(scenarios),
            assets_count,
        )
        return ImportResult(
            pack_slug=manifest.pack_id,
            pack_name=manifest.name,
            pack_version=manifest.version,
            scenarios_indexed=len(scenarios),
            assets_indexed=assets_count,
        )

    except Exception:
        conn.rollback()
        if tmp_dest.exists():
            shutil.rmtree(tmp_dest, ignore_errors=True)
        # If the move already completed, undo it to leave no partial install.
        if pack_dest.exists() and not (source_dir == pack_dest):
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
