# SPDX-License-Identifier: Apache-2.0
"""Database operations for packs, scenarios, and asset_index."""
import json
import sqlite3
from typing import Optional

from convsim_core.packs.models import PackManifest, PackSummary, ScenarioInsertData


def list_packs(conn: sqlite3.Connection) -> list[PackSummary]:
    rows = conn.execute(
        "SELECT id, slug, name, version, description, author, license, content_rating,"
        " supported_languages_json, tags_json, source_path, installed_at,"
        " validation_status, last_validated_at"
        " FROM packs ORDER BY installed_at DESC"
    ).fetchall()
    return [_row_to_summary(row) for row in rows]


def get_pack_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[PackSummary]:
    row = conn.execute(
        "SELECT id, slug, name, version, description, author, license, content_rating,"
        " supported_languages_json, tags_json, source_path, installed_at,"
        " validation_status, last_validated_at"
        " FROM packs WHERE slug = ?",
        (slug,),
    ).fetchone()
    return _row_to_summary(row) if row else None


def insert_pack(
    conn: sqlite3.Connection,
    manifest: PackManifest,
    source_path: str,
) -> int:
    """Insert a pack record and its FTS entry. Returns the new pack DB id. Does not commit."""
    cursor = conn.execute(
        """
        INSERT INTO packs (slug, name, version, description, author, license, content_rating,
                           supported_languages_json, source_path, tags_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manifest.pack_id,
            manifest.name,
            manifest.version,
            manifest.description,
            manifest.author,
            manifest.license,
            manifest.content_rating,
            json.dumps(manifest.supported_languages) if manifest.supported_languages else None,
            source_path,
            json.dumps(manifest.tags) if manifest.tags else None,
        ),
    )
    pack_db_id: int = cursor.lastrowid  # type: ignore[assignment]
    conn.execute(
        "INSERT INTO pack_readme_fts(rowid, name, description) VALUES (?, ?, ?)",
        (pack_db_id, manifest.name, manifest.description or ""),
    )
    return pack_db_id


def insert_scenario(
    conn: sqlite3.Connection,
    pack_db_id: int,
    data: ScenarioInsertData,
) -> int:
    """Insert a scenario record and its FTS entry. Returns the new scenario DB id. Does not commit."""
    cursor = conn.execute(
        """
        INSERT INTO scenarios
            (pack_id, slug, name, title, summary, content_rating, difficulty_default,
             max_turns, soft_time_limit_minutes, tags_json, voice_support,
             model_recommendation, rel_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pack_db_id,
            data.slug,
            data.name,
            data.title,
            data.summary,
            data.content_rating,
            data.difficulty_default,
            data.max_turns,
            data.soft_time_limit_minutes,
            data.tags_json,
            1 if data.voice_support else 0,
            data.model_recommendation,
            data.rel_path,
        ),
    )
    scenario_db_id: int = cursor.lastrowid  # type: ignore[assignment]

    pack_tags = " ".join(data.pack_tags) if data.pack_tags else ""
    conn.execute(
        "INSERT INTO scenario_fts(rowid, title, summary, tags, pack_name, pack_readme)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            scenario_db_id,
            data.title or data.name,
            data.summary or "",
            pack_tags,
            data.pack_name,
            data.pack_description or "",
        ),
    )
    return scenario_db_id


def remove_pack_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[str]:
    """Remove a pack and all cascaded data by slug.

    Cascade deletes on the packs table remove scenarios, asset_index entries,
    and (via DB triggers) the scenario_fts and pack_readme_fts index entries.
    Returns the installed source_path so the caller can clean up the filesystem,
    or None when no pack with that slug exists.  Does NOT commit.
    """
    row = conn.execute(
        "SELECT id, source_path FROM packs WHERE slug = ?", (slug,)
    ).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM packs WHERE id = ?", (row["id"],))
    return row["source_path"]


def _row_to_summary(row: sqlite3.Row) -> PackSummary:
    return PackSummary(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        version=row["version"],
        description=row["description"],
        author=row["author"],
        license=row["license"],
        content_rating=row["content_rating"],
        supported_languages=json.loads(row["supported_languages_json"] or "[]"),
        tags=json.loads(row["tags_json"] or "[]"),
        source_path=row["source_path"],
        installed_at=row["installed_at"],
        validation_status=row["validation_status"] or "unknown",
        last_validated_at=row["last_validated_at"],
    )
