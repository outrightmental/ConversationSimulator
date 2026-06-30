# SPDX-License-Identifier: Apache-2.0
import sqlite3

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_INITIAL_SCHEMA_SQL = """
CREATE TABLE packs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    description TEXT,
    author      TEXT,
    source_path TEXT,
    installed_at TEXT   NOT NULL DEFAULT (datetime('now'))
);
-- license and tags added in 0003_extend_pack_assets

CREATE TABLE scenarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id     INTEGER NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
    slug        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    description TEXT,
    UNIQUE(pack_id, slug)
);

CREATE TABLE scenario_versions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id    INTEGER NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    version        TEXT    NOT NULL,
    schema_version TEXT    NOT NULL,
    content_json   TEXT    NOT NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(scenario_id, version)
);

CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    scenario_id INTEGER REFERENCES scenarios(id),
    title       TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at    TEXT
);

CREATE TABLE turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id, turn_number)
);

CREATE TABLE turn_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id      INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    event_type   TEXT    NOT NULL,
    payload_json TEXT,
    occurred_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE debriefs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    content_json TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE user_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE model_registry (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    provider          TEXT NOT NULL,
    capabilities_json TEXT,
    metadata_json     TEXT,
    registered_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE installed_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    registry_id TEXT REFERENCES model_registry(id),
    filename    TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    size_bytes  INTEGER,
    installed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE asset_index (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type   TEXT NOT NULL,
    filename     TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    content_hash TEXT,
    size_bytes   INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE scenario_fts USING fts5(
    name, description,
    content='scenarios', content_rowid='id'
);

CREATE VIRTUAL TABLE transcript_fts USING fts5(
    content,
    content='turns', content_rowid='id'
);

CREATE VIRTUAL TABLE pack_readme_fts USING fts5(
    name, description,
    content='packs', content_rowid='id'
);
"""

_MODEL_REGISTRY_V2_SQL = """
ALTER TABLE model_registry ADD COLUMN family TEXT;
ALTER TABLE model_registry ADD COLUMN role TEXT;
ALTER TABLE model_registry ADD COLUMN format TEXT;
ALTER TABLE model_registry ADD COLUMN license_spdx TEXT;
ALTER TABLE model_registry ADD COLUMN license_url TEXT;
ALTER TABLE model_registry ADD COLUMN source_type TEXT;
ALTER TABLE model_registry ADD COLUMN download_url TEXT;
ALTER TABLE model_registry ADD COLUMN sha256 TEXT;
ALTER TABLE model_registry ADD COLUMN size_gb REAL;
ALTER TABLE model_registry ADD COLUMN min_vram_gb REAL;
ALTER TABLE model_registry ADD COLUMN recommended_vram_gb REAL;
ALTER TABLE model_registry ADD COLUMN context_length INTEGER;
"""

_EXTEND_PACK_ASSETS_SQL = """
ALTER TABLE packs ADD COLUMN license TEXT;
ALTER TABLE packs ADD COLUMN tags_json TEXT;
ALTER TABLE asset_index ADD COLUMN relative_path TEXT;
ALTER TABLE asset_index ADD COLUMN media_type TEXT;
ALTER TABLE asset_index ADD COLUMN license TEXT;
ALTER TABLE asset_index ADD COLUMN pack_id INTEGER;
ALTER TABLE asset_index ADD COLUMN scenario_id INTEGER;
"""

MIGRATIONS: list[tuple[str, str]] = [
    ("0001_initial_schema", _INITIAL_SCHEMA_SQL),
    ("0002_model_registry_v2", _MODEL_REGISTRY_V2_SQL),
    ("0003_extend_pack_assets", _EXTEND_PACK_ASSETS_SQL),
]


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations. Returns total count of applied migrations."""
    conn.executescript(_BOOTSTRAP_SQL)
    applied = {row[0] for row in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    for name, sql in MIGRATIONS:
        if name not in applied:
            # Wrap the migration DDL and the tracking INSERT in one atomic transaction so
            # a crash mid-migration cannot leave tables created but the migration unrecorded
            # (which would break the next startup with "table already exists").
            conn.executescript(
                f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(name) VALUES('{name}');\nCOMMIT;\n"
            )
    return conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
