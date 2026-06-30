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
