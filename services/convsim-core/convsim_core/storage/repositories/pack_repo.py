# SPDX-License-Identifier: Apache-2.0
"""Database operations for packs, scenarios, and asset_index."""
import sqlite3
from typing import Optional

from convsim_core.packs.models import PackManifest, PackSummary


def list_packs(conn: sqlite3.Connection) -> list[PackSummary]:
    rows = conn.execute(
        "SELECT id, slug, name, version, description, author, license, source_path, installed_at"
        " FROM packs ORDER BY installed_at DESC"
    ).fetchall()
    return [_row_to_summary(row) for row in rows]


def get_pack_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[PackSummary]:
    row = conn.execute(
        "SELECT id, slug, name, version, description, author, license, source_path, installed_at"
        " FROM packs WHERE slug = ?",
        (slug,),
    ).fetchone()
    return _row_to_summary(row) if row else None


def insert_pack(
    conn: sqlite3.Connection,
    manifest: PackManifest,
    source_path: str,
) -> int:
    """Insert a pack record. Returns the new pack DB id. Does not commit."""
    cursor = conn.execute(
        """
        INSERT INTO packs (slug, name, version, description, author, license, source_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manifest.pack_id,
            manifest.name,
            manifest.version,
            manifest.description,
            manifest.author,
            manifest.license,
            source_path,
        ),
    )
    return cursor.lastrowid  # type: ignore[return-value]


def insert_scenario(
    conn: sqlite3.Connection,
    pack_db_id: int,
    slug: str,
    name: str,
    description: Optional[str] = None,
) -> int:
    """Insert a scenario record. Returns the new scenario DB id. Does not commit."""
    cursor = conn.execute(
        "INSERT INTO scenarios (pack_id, slug, name, description) VALUES (?, ?, ?, ?)",
        (pack_db_id, slug, name, description),
    )
    return cursor.lastrowid  # type: ignore[return-value]


def _row_to_summary(row: sqlite3.Row) -> PackSummary:
    return PackSummary(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        version=row["version"],
        description=row["description"],
        author=row["author"],
        license=row["license"],
        source_path=row["source_path"],
        installed_at=row["installed_at"],
    )
