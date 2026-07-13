# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from convsim_core.storage.database import Database
from convsim_core.storage.migrations import MIGRATIONS
from convsim_core.storage.repositories.settings_repo import load_settings, save_settings
from convsim_core.models import AppSettings


def test_migration_from_empty_directory(tmp_path):
    """First run creates the database and applies all migrations."""
    db = Database.open(str(tmp_path / "db"))
    try:
        assert Path(db.path).exists()
        assert db.migrations_applied == len(MIGRATIONS)
    finally:
        db.close()


def test_migration_creates_all_expected_tables(tmp_path):
    """All schema tables exist after the initial migration."""
    db = Database.open(str(tmp_path / "db"))
    try:
        tables = {
            row["name"]
            for row in db.connection().execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "schema_migrations",
            "packs",
            "scenarios",
            "scenario_versions",
            "sessions",
            "turns",
            "turn_events",
            "debriefs",
            "user_settings",
            "model_registry",
            "installed_models",
            "asset_index",
        }
        assert expected.issubset(tables)
    finally:
        db.close()


def test_migration_is_idempotent(tmp_path):
    """Opening the database a second time does not re-apply migrations."""
    db_dir = str(tmp_path / "db")

    db1 = Database.open(db_dir)
    count_after_first = db1.migrations_applied
    db1.close()

    db2 = Database.open(db_dir)
    count_after_second = db2.migrations_applied
    db2.close()

    assert count_after_first == count_after_second == len(MIGRATIONS)


def test_migration_records_applied_migrations(tmp_path):
    """schema_migrations table records each migration by name."""
    db = Database.open(str(tmp_path / "db"))
    try:
        recorded = {
            row["name"]
            for row in db.connection().execute("SELECT name FROM schema_migrations").fetchall()
        }
        expected = {name for name, _ in MIGRATIONS}
        assert recorded == expected
    finally:
        db.close()


def test_sqlite_integrity_check(tmp_path):
    """integrity_check passes on a freshly migrated database."""
    db = Database.open(str(tmp_path / "db"))
    try:
        assert db.integrity_check() is True
    finally:
        db.close()


def test_fts_tables_created(tmp_path):
    """FTS5 virtual tables are present after migration."""
    db = Database.open(str(tmp_path / "db"))
    try:
        vtables = {
            row["name"]
            for row in db.connection().execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
            ).fetchall()
        }
        assert "scenario_fts" in vtables
        assert "transcript_fts" in vtables
        assert "pack_readme_fts" in vtables
    finally:
        db.close()


def test_scenario_fts_backfill_indexes_pre_existing_scenarios(tmp_path):
    """Scenarios inserted before migration 0009 must appear in scenario_fts after migration."""
    import sqlite3
    from convsim_core.storage.migrations import MIGRATIONS, _BOOTSTRAP_SQL

    # Apply all migrations up to but not including 0009.
    db_path = str(tmp_path / "db" / "app.db")
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cutoff = "0009_scenario_library_schema"
    conn.executescript(_BOOTSTRAP_SQL)
    for name, sql in MIGRATIONS:
        if name == cutoff:
            break
        conn.executescript(
            f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(name) VALUES('{name}');\nCOMMIT;\n"
        )

    # Insert a pack and scenario using the pre-0009 schema (no title/summary columns yet).
    conn.execute(
        "INSERT INTO packs (slug, name, version, description) VALUES ('old.pack', 'Old Pack', '1.0.0', 'Old description')"
    )
    pack_id = conn.execute("SELECT id FROM packs WHERE slug='old.pack'").fetchone()[0]
    conn.execute(
        "INSERT INTO scenarios (pack_id, slug, name, description) VALUES (?, 'old_scenario', 'Old Scenario', 'Old summary')",
        (pack_id,),
    )
    conn.commit()

    # Now apply migration 0009, which should backfill scenario_fts.
    name, sql = next((n, s) for n, s in MIGRATIONS if n == cutoff)
    conn.executescript(
        f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(name) VALUES('{name}');\nCOMMIT;\n"
    )

    rows = conn.execute(
        "SELECT rowid FROM scenario_fts WHERE scenario_fts MATCH '\"Old\"*'"
    ).fetchall()
    assert len(rows) > 0, "Pre-existing scenario must be indexed in scenario_fts after migration 0009"
    conn.close()


def test_pack_readme_fts_backfill_indexes_pre_existing_packs(tmp_path):
    """Packs inserted before migration 0009 must appear in pack_readme_fts after migration."""
    import sqlite3
    from convsim_core.storage.migrations import MIGRATIONS, _BOOTSTRAP_SQL

    db_path = str(tmp_path / "db" / "app.db")
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cutoff = "0009_scenario_library_schema"
    conn.executescript(_BOOTSTRAP_SQL)
    for name, sql in MIGRATIONS:
        if name == cutoff:
            break
        conn.executescript(
            f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(name) VALUES('{name}');\nCOMMIT;\n"
        )

    conn.execute(
        "INSERT INTO packs (slug, name, version, description) VALUES ('legacy.pack', 'Legacy Pack', '1.0.0', 'A legacy description')"
    )
    conn.commit()

    name, sql = next((n, s) for n, s in MIGRATIONS if n == cutoff)
    conn.executescript(
        f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(name) VALUES('{name}');\nCOMMIT;\n"
    )

    rows = conn.execute(
        "SELECT rowid FROM pack_readme_fts WHERE pack_readme_fts MATCH '\"Legacy\"*'"
    ).fetchall()
    assert len(rows) > 0, "Pre-existing pack must be indexed in pack_readme_fts after migration 0009"
    conn.close()


def test_pack_readme_fts_delete_trigger_removes_entry_on_pack_delete(tmp_path):
    """Deleting a pack must remove its pack_readme_fts entry to avoid ghost FTS results."""
    from convsim_core.storage.database import Database

    db = Database.open(str(tmp_path / "db"))
    try:
        conn = db.connection()
        conn.execute(
            "INSERT INTO packs (slug, name, version) VALUES ('ghost.pack', 'Ghost Pack', '1.0.0')"
        )
        pack_id = conn.execute("SELECT id FROM packs WHERE slug='ghost.pack'").fetchone()[0]
        conn.execute(
            "INSERT INTO pack_readme_fts(rowid, name, description) VALUES (?, ?, ?)",
            (pack_id, "Ghost Pack", ""),
        )
        conn.commit()

        before = conn.execute(
            "SELECT rowid FROM pack_readme_fts WHERE pack_readme_fts MATCH '\"Ghost\"*'"
        ).fetchall()
        assert len(before) == 1

        conn.execute("DELETE FROM packs WHERE id = ?", (pack_id,))
        conn.commit()

        after = conn.execute(
            "SELECT rowid FROM pack_readme_fts WHERE pack_readme_fts MATCH '\"Ghost\"*'"
        ).fetchall()
        assert len(after) == 0, "pack_readme_fts must not retain entries for deleted packs"
    finally:
        db.close()


def test_settings_persist_across_restarts(tmp_path):
    """Settings written to the DB survive a close/reopen cycle."""
    db_dir = str(tmp_path / "db")
    data_dir = str(tmp_path / "data")
    log_dir = str(tmp_path / "logs")

    db1 = Database.open(db_dir)
    settings_in = AppSettings(
        data_dir=data_dir,
        log_dir=log_dir,
        save_transcripts=True,
        tts_cache_enabled=False,
    )
    save_settings(db1.connection(), settings_in)
    db1.close()

    db2 = Database.open(db_dir)
    settings_out = load_settings(db2.connection(), data_dir, log_dir)
    db2.close()

    assert settings_out.save_transcripts is True
    assert settings_out.tts_cache_enabled is False


def _apply_migrations_before(conn, cutoff):
    """Apply the bootstrap and every migration preceding `cutoff` (exclusive)."""
    from convsim_core.storage.migrations import MIGRATIONS, _BOOTSTRAP_SQL

    conn.executescript(_BOOTSTRAP_SQL)
    for name, sql in MIGRATIONS:
        if name == cutoff:
            break
        conn.executescript(
            f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(name) VALUES('{name}');\nCOMMIT;\n"
        )


def test_0017_backfills_onboarding_outcome_for_configured_model(tmp_path):
    """An upgrade with an active model already configured must not be dragged
    back through the first-run wizard: migration 0017 synthesizes a
    completed-with-model outcome so the server no longer reports never-run."""
    import sqlite3

    db_path = str(tmp_path / "db" / "app.db")
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cutoff = "0017_onboarding_outcome"
    _apply_migrations_before(conn, cutoff)

    # Simulate a returning user who already selected a model under the old scheme.
    conn.execute(
        "INSERT INTO user_settings (key, value, updated_at) "
        "VALUES ('active_model_id', 'qwen3-4b-q4', datetime('now'))"
    )
    conn.commit()

    from convsim_core.storage.migrations import run_migrations

    run_migrations(conn)

    rows = conn.execute("SELECT outcome FROM onboarding_outcomes").fetchall()
    assert [r["outcome"] for r in rows] == ["completed-with-model"]
    conn.close()


def test_0017_backfills_onboarding_outcome_for_installed_model(tmp_path):
    """A finished model download also counts as prior onboarding for the backfill."""
    import sqlite3

    db_path = str(tmp_path / "db" / "app.db")
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cutoff = "0017_onboarding_outcome"
    _apply_migrations_before(conn, cutoff)

    conn.execute(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status) "
        "VALUES ('qwen3-4b-q4', 'qwen3-4b-q4.gguf', '/models/qwen3-4b-q4.gguf', 'ready')"
    )
    conn.commit()

    from convsim_core.storage.migrations import run_migrations

    run_migrations(conn)

    rows = conn.execute("SELECT COUNT(*) AS cnt FROM onboarding_outcomes").fetchone()
    assert rows["cnt"] == 1
    conn.close()


def test_0017_does_not_backfill_for_fresh_install(tmp_path):
    """A fresh install (no active model, no completed download) must still report
    never-run after migration — the backfill must not fire for it."""
    import sqlite3

    db_path = str(tmp_path / "db" / "app.db")
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cutoff = "0017_onboarding_outcome"
    _apply_migrations_before(conn, cutoff)

    # A pending (not-yet-complete) download must not count as prior onboarding.
    conn.execute(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status) "
        "VALUES ('qwen3-4b-q4', 'qwen3-4b-q4.gguf', '/models/qwen3-4b-q4.gguf', 'downloading')"
    )
    conn.commit()

    from convsim_core.storage.migrations import run_migrations

    run_migrations(conn)

    rows = conn.execute("SELECT COUNT(*) AS cnt FROM onboarding_outcomes").fetchone()
    assert rows["cnt"] == 0
    conn.close()
