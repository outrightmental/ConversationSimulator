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
-- license and tags added in 0004_extend_pack_assets

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

_MODEL_MANAGER_API_SQL = """
ALTER TABLE installed_models ADD COLUMN install_status TEXT NOT NULL DEFAULT 'complete';
ALTER TABLE installed_models ADD COLUMN progress_bytes INTEGER;
ALTER TABLE installed_models ADD COLUMN error_message TEXT;

CREATE TABLE benchmark_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id       TEXT    NOT NULL,
    runtime_id     TEXT    NOT NULL,
    tokens_per_sec REAL    NOT NULL,
    context_length INTEGER,
    warnings_json  TEXT    NOT NULL DEFAULT '[]',
    prompt_used    TEXT,
    output_tokens  INTEGER,
    benchmarked_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_EXTEND_PACK_ASSETS_SQL = """
ALTER TABLE packs ADD COLUMN license TEXT;
ALTER TABLE packs ADD COLUMN tags_json TEXT;

ALTER TABLE asset_index ADD COLUMN relative_path TEXT;
ALTER TABLE asset_index ADD COLUMN media_type TEXT;
ALTER TABLE asset_index ADD COLUMN license TEXT;
ALTER TABLE asset_index ADD COLUMN pack_id INTEGER REFERENCES packs(id) ON DELETE CASCADE;
ALTER TABLE asset_index ADD COLUMN scenario_id INTEGER REFERENCES scenarios(id) ON DELETE SET NULL;
"""

_TURN_PIPELINE_SQL = """
CREATE TABLE turn_sessions (
    session_id        TEXT PRIMARY KEY,
    scenario_id       TEXT NOT NULL,
    flow_state        TEXT NOT NULL DEFAULT 'NotStarted',
    ending_type       TEXT,
    state_vars_json   TEXT NOT NULL DEFAULT '{}',
    fired_events_json TEXT NOT NULL DEFAULT '[]',
    turn_count        INTEGER NOT NULL DEFAULT 0,
    setup_json        TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE turn_session_turns (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT NOT NULL REFERENCES turn_sessions(session_id) ON DELETE CASCADE,
    turn_number      INTEGER NOT NULL,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    emotion          TEXT,
    state_delta_json TEXT,
    event_flags_json TEXT,
    safety_json      TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id, turn_number)
);
"""

_TURN_TRANSCRIPT_AND_EVENTS_SQL = """
ALTER TABLE turn_session_turns ADD COLUMN source_mode TEXT;
ALTER TABLE turn_session_turns ADD COLUMN raw_output_json TEXT;
ALTER TABLE turn_session_turns ADD COLUMN flow_state_after TEXT;

CREATE TABLE turn_session_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL REFERENCES turn_sessions(session_id) ON DELETE CASCADE,
    turn_number  INTEGER,
    event_type   TEXT    NOT NULL,
    payload_json TEXT    NOT NULL DEFAULT '{}',
    occurred_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE session_transcript_fts USING fts5(
    session_id UNINDEXED,
    turn_number UNINDEXED,
    role UNINDEXED,
    content
);
"""

_DEBRIEF_TABLE_SQL = """
CREATE TABLE session_debriefs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL REFERENCES turn_sessions(session_id) ON DELETE CASCADE,
    content_json TEXT    NOT NULL,
    generated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX session_debriefs_session_id ON session_debriefs(session_id);
"""

_DEBRIEF_UNIQUE_IDX_SQL = """
DROP INDEX IF EXISTS session_debriefs_session_id;
CREATE UNIQUE INDEX session_debriefs_session_id ON session_debriefs(session_id);
"""

_USER_GGUF_PROFILES_SQL = """
ALTER TABLE installed_models ADD COLUMN display_name TEXT;
ALTER TABLE installed_models ADD COLUMN family_guess TEXT;
ALTER TABLE installed_models ADD COLUMN context_length_default INTEGER;
ALTER TABLE installed_models ADD COLUMN source TEXT NOT NULL DEFAULT 'registry';
"""

_SCENARIO_LIBRARY_SCHEMA_SQL = """
ALTER TABLE packs ADD COLUMN content_rating TEXT;
ALTER TABLE packs ADD COLUMN supported_languages_json TEXT;
ALTER TABLE packs ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE packs ADD COLUMN last_validated_at TEXT;

ALTER TABLE scenarios ADD COLUMN title TEXT;
ALTER TABLE scenarios ADD COLUMN summary TEXT;
ALTER TABLE scenarios ADD COLUMN content_rating TEXT;
ALTER TABLE scenarios ADD COLUMN difficulty_default TEXT;
ALTER TABLE scenarios ADD COLUMN max_turns INTEGER;
ALTER TABLE scenarios ADD COLUMN soft_time_limit_minutes INTEGER;
ALTER TABLE scenarios ADD COLUMN tags_json TEXT;
ALTER TABLE scenarios ADD COLUMN voice_support INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN model_recommendation TEXT;
ALTER TABLE scenarios ADD COLUMN rel_path TEXT;

DROP TABLE IF EXISTS scenario_fts;
CREATE VIRTUAL TABLE scenario_fts USING fts5(
    title, summary, tags, pack_name, pack_readme
);

CREATE TRIGGER scenario_fts_delete AFTER DELETE ON scenarios BEGIN
    DELETE FROM scenario_fts WHERE rowid = OLD.id;
END;

-- Backfill scenario_fts for any scenarios already in the DB before this migration.
-- Uses name/description as fallbacks because title/summary are NULL on pre-existing rows.
INSERT INTO scenario_fts(rowid, title, summary, tags, pack_name, pack_readme)
SELECT s.id,
       COALESCE(s.title, s.name, ''),
       COALESCE(s.summary, s.description, ''),
       '',
       COALESCE(p.name, ''),
       COALESCE(p.description, '')
FROM scenarios s
JOIN packs p ON s.pack_id = p.id;

-- Keep pack_readme_fts in sync when packs are deleted.  The insert path (insert_pack)
-- adds a row manually; we need a matching delete trigger so the FTS index doesn't
-- accumulate ghost entries for removed packs.
-- pack_readme_fts uses content='packs', so we must use the FTS5 'delete' command
-- (providing the old column values) instead of a plain DELETE, because by the time
-- an AFTER DELETE trigger fires the content-table row is already gone and SQLite
-- can no longer read the indexed terms from it.
CREATE TRIGGER pack_readme_fts_delete AFTER DELETE ON packs BEGIN
    INSERT INTO pack_readme_fts(pack_readme_fts, rowid, name, description)
    VALUES('delete', OLD.id, OLD.name, COALESCE(OLD.description, ''));
END;

-- Backfill pack_readme_fts for packs imported before this migration (the old
-- insert_pack did not insert into pack_readme_fts).
INSERT INTO pack_readme_fts(rowid, name, description)
SELECT id, name, COALESCE(description, '') FROM packs;
"""

_MODEL_DOWNLOAD_VERIFIED_SQL = """
ALTER TABLE installed_models ADD COLUMN verified_sha256 TEXT;
"""

_SESSION_METRICS_SQL = """
ALTER TABLE session_debriefs ADD COLUMN metrics_json TEXT;
"""

_BRANCH_SESSIONS_SQL = """
ALTER TABLE turn_session_turns ADD COLUMN state_snapshot_json TEXT;

CREATE TABLE session_branches (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_session_id TEXT    NOT NULL REFERENCES turn_sessions(session_id) ON DELETE CASCADE,
    parent_session_id TEXT    NOT NULL,
    fork_turn_number  INTEGER NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX session_branches_branch_idx ON session_branches(branch_session_id);
"""

# Conversational timing realism (issue #308): record whether a player turn
# barged in on NPC TTS playback so the debrief can count interruptions.
_BARGE_IN_SQL = """
ALTER TABLE turn_session_turns ADD COLUMN barged_in INTEGER NOT NULL DEFAULT 0;
"""

# Records when a session concluded so the Logbook can measure practice time and
# per-day streaks accurately. Populated by the /end handler and, for sessions
# that terminate mid-turn without an explicit /end, backfilled when the debrief
# is generated (see debrief_engine).
_TURN_SESSION_ENDED_AT_SQL = """
ALTER TABLE turn_sessions ADD COLUMN ended_at TEXT;
"""

MIGRATIONS: list[tuple[str, str]] = [
    ("0001_initial_schema", _INITIAL_SCHEMA_SQL),
    ("0002_model_registry_v2", _MODEL_REGISTRY_V2_SQL),
    ("0003_model_manager_api", _MODEL_MANAGER_API_SQL),
    ("0004_extend_pack_assets", _EXTEND_PACK_ASSETS_SQL),
    ("0005_turn_pipeline", _TURN_PIPELINE_SQL),
    ("0006_turn_transcript_and_events", _TURN_TRANSCRIPT_AND_EVENTS_SQL),
    ("0007_session_debriefs", _DEBRIEF_TABLE_SQL),
    ("0008_session_debriefs_unique_idx", _DEBRIEF_UNIQUE_IDX_SQL),
    ("0009_scenario_library_schema", _SCENARIO_LIBRARY_SCHEMA_SQL),
    ("0010_user_gguf_profiles", _USER_GGUF_PROFILES_SQL),
    ("0011_model_download_verified", _MODEL_DOWNLOAD_VERIFIED_SQL),
    ("0012_session_metrics", _SESSION_METRICS_SQL),
    ("0013_branch_sessions", _BRANCH_SESSIONS_SQL),
    ("0014_barge_in", _BARGE_IN_SQL),
    ("0015_turn_session_ended_at", _TURN_SESSION_ENDED_AT_SQL),
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
