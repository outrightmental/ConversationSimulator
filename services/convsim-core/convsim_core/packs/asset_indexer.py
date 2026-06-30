# SPDX-License-Identifier: Apache-2.0
"""Index pack assets into the asset_index table after installation."""
import hashlib
import mimetypes
import sqlite3
from pathlib import Path
from typing import Optional


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _detect_media_type(path: Path) -> Optional[str]:
    mime, _ = mimetypes.guess_type(str(path))
    return mime


def _classify_asset(path: Path) -> str:
    """Return a broad asset_type label from the file's extension and location."""
    ext = path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        return "image"
    if ext in (".mp3", ".ogg", ".wav", ".flac", ".aac"):
        return "audio"
    if path.name == "pack.json":
        return "manifest"
    if ext in (".yaml", ".yml", ".json"):
        return "data"
    if ext in (".md", ".txt"):
        return "text"
    return "other"


def index_pack_assets(
    conn: sqlite3.Connection,
    pack_dir: Path,
    pack_db_id: int,
    pack_license: Optional[str] = None,
) -> int:
    """
    Insert an asset_index row for every file in pack_dir.
    Returns the number of assets indexed.
    Does not commit — caller is responsible for the transaction boundary.
    """
    count = 0
    for file_path in sorted(pack_dir.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = str(file_path.relative_to(pack_dir)).replace("\\", "/")
        conn.execute(
            """
            INSERT INTO asset_index
                (asset_type, filename, file_path, relative_path,
                 content_hash, size_bytes, media_type, license, pack_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _classify_asset(file_path),
                file_path.name,
                str(file_path),
                relative_path,
                _sha256(file_path),
                file_path.stat().st_size,
                _detect_media_type(file_path),
                pack_license,
                pack_db_id,
            ),
        )
        count += 1
    return count
