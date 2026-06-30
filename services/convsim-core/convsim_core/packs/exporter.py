# SPDX-License-Identifier: Apache-2.0
"""Export an installed pack to a zip archive that can be re-imported and re-validated."""
import io
import sqlite3
import zipfile
from pathlib import Path

from convsim_core.errors import ConvsimError
from convsim_core.storage.repositories.pack_repo import get_pack_by_slug


def export_to_zip(pack_slug: str, conn: sqlite3.Connection) -> tuple[bytes, str]:
    """
    Build a zip archive for the installed pack identified by pack_slug.

    Files are stored under a top-level directory named after the pack slug so
    that re-importing the exported zip works with the single-top-level-dir logic
    in the importer.

    Returns (zip_bytes, suggested_filename).
    """
    pack = get_pack_by_slug(conn, pack_slug)
    if pack is None:
        raise ConvsimError("NOT_FOUND", f"Pack not found: {pack_slug!r}", status_code=404)

    if not pack.source_path:
        raise ConvsimError(
            "EXPORT_ERROR",
            f"Pack '{pack_slug}' has no source path recorded.",
            status_code=500,
        )

    pack_dir = Path(pack.source_path)
    if not pack_dir.is_dir():
        raise ConvsimError(
            "EXPORT_ERROR",
            f"Pack directory missing on disk: {pack.source_path}",
            status_code=500,
        )

    buf = io.BytesIO()
    safe_slug = pack.slug.replace("/", "_").replace("\\", "_")

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(pack_dir.rglob("*")):
            if file_path.is_file():
                rel = str(file_path.relative_to(pack_dir)).replace("\\", "/")
                arcname = f"{safe_slug}/{rel}"
                zf.write(file_path, arcname)

    filename = f"{safe_slug}-{pack.version}.zip"
    return buf.getvalue(), filename
