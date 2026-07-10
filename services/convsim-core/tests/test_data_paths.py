# SPDX-License-Identifier: Apache-2.0
"""Tests for platform-specific data directory resolution and data migration.

These tests cover path resolution on Windows, macOS, Linux, and the Steam Deck
by monkeypatching sys.platform and relevant environment variables.  No
filesystem access is needed for path-resolution tests; migration tests use
tmp_path.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _reload_paths():
    """Force a fresh import of paths so module-level defaults are recomputed."""
    import convsim_core.paths as p
    importlib.reload(p)
    return p


# ── platform_data_root ────────────────────────────────────────────────────────


class TestPlatformDataRoot:
    """Verify platform_data_root() returns the correct directory per platform."""

    def test_env_override_takes_precedence(self, tmp_path):
        with patch.dict(os.environ, {"CONVSIM_DATA_ROOT": str(tmp_path)}):
            p = _reload_paths()
            assert p.platform_data_root() == tmp_path

    def test_env_override_beats_platform(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONVSIM_DATA_ROOT", str(tmp_path))
        monkeypatch.setattr("sys.platform", "darwin")
        p = _reload_paths()
        assert p.platform_data_root() == tmp_path

    # macOS ------------------------------------------------------------------

    def test_macos_uses_library_application_support(self, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "darwin")
        p = _reload_paths()
        root = p.platform_data_root()
        assert root == Path.home() / "Library" / "Application Support" / "com.outrightmental.convsim"

    def test_macos_root_contains_bundle_id(self, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "darwin")
        p = _reload_paths()
        assert "com.outrightmental.convsim" in str(p.platform_data_root())

    # Windows ----------------------------------------------------------------

    def test_windows_uses_localappdata(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        p = _reload_paths()
        root = p.platform_data_root()
        assert root == tmp_path / "outrightmental" / "convsim"

    def test_windows_falls_back_when_no_localappdata(self, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setattr("sys.platform", "win32")
        p = _reload_paths()
        root = p.platform_data_root()
        # Should still be under the home dir.
        assert root.is_relative_to(Path.home())
        assert "outrightmental" in str(root)
        assert "convsim" in str(root)

    def test_windows_does_not_use_appdata_roaming(self, tmp_path, monkeypatch):
        """Use LocalAppData to avoid roaming-profile sync."""
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
        monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
        p = _reload_paths()
        root = p.platform_data_root()
        assert "local" in str(root)
        assert "roaming" not in str(root)

    # Linux / Steam Deck -----------------------------------------------------

    def test_linux_uses_xdg_data_home(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        p = _reload_paths()
        assert p.platform_data_root() == tmp_path / "convsim"

    def test_linux_falls_back_to_local_share(self, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        p = _reload_paths()
        root = p.platform_data_root()
        assert root == Path.home() / ".local" / "share" / "convsim"

    def test_steam_deck_uses_same_linux_paths(self, monkeypatch):
        """Steam Deck is Linux; XDG paths must apply regardless of SteamDeck flag."""
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("SteamDeck", "1")
        p = _reload_paths()
        root = p.platform_data_root()
        assert root == Path.home() / ".local" / "share" / "convsim"

    def test_steam_deck_xdg_override_respected(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONVSIM_DATA_ROOT", raising=False)
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("SteamDeck", "1")
        p = _reload_paths()
        assert p.platform_data_root() == tmp_path / "convsim"


# ── is_steam_deck ─────────────────────────────────────────────────────────────


class TestIsSteamDeck:
    def test_false_without_env_var(self, monkeypatch):
        monkeypatch.delenv("SteamDeck", raising=False)
        from convsim_core.paths import is_steam_deck
        assert is_steam_deck() is False

    def test_true_with_steam_deck_eq_1(self, monkeypatch):
        monkeypatch.setenv("SteamDeck", "1")
        from convsim_core.paths import is_steam_deck
        assert is_steam_deck() is True

    def test_false_with_other_value(self, monkeypatch):
        monkeypatch.setenv("SteamDeck", "0")
        from convsim_core.paths import is_steam_deck
        assert is_steam_deck() is False


# ── legacy_convsim_dir ────────────────────────────────────────────────────────


class TestLegacyConvsimDir:
    def test_always_returns_home_dot_convsim(self):
        from convsim_core.paths import legacy_convsim_dir
        assert legacy_convsim_dir() == Path.home() / ".convsim"


# ── Data migration ────────────────────────────────────────────────────────────


class TestNeedsMigration:
    def test_false_when_legacy_absent(self, tmp_path):
        from convsim_core.data_migration import needs_migration
        assert not needs_migration(tmp_path / "new", tmp_path / "nonexistent")

    def test_false_when_marker_exists(self, tmp_path):
        from convsim_core.data_migration import needs_migration, _MIGRATED_MARKER
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "data").mkdir()
        (legacy / _MIGRATED_MARKER).touch()
        assert not needs_migration(tmp_path / "new", legacy)

    def test_false_when_new_root_has_content(self, tmp_path):
        from convsim_core.data_migration import needs_migration
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "data").mkdir()
        new = tmp_path / "new"
        new.mkdir()
        (new / "existing_file").touch()
        assert not needs_migration(new, legacy)

    def test_false_when_legacy_has_no_known_subdirs(self, tmp_path):
        from convsim_core.data_migration import needs_migration
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "something_else").mkdir()
        assert not needs_migration(tmp_path / "new", legacy)

    def test_true_when_legacy_has_data_subdir(self, tmp_path):
        from convsim_core.data_migration import needs_migration
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "data").mkdir()
        assert needs_migration(tmp_path / "new", legacy)

    def test_true_when_legacy_has_db_subdir(self, tmp_path):
        from convsim_core.data_migration import needs_migration
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "db").mkdir()
        assert needs_migration(tmp_path / "new", legacy)

    def test_true_when_new_root_absent(self, tmp_path):
        from convsim_core.data_migration import needs_migration
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "data").mkdir()
        assert needs_migration(tmp_path / "nonexistent_new", legacy)


class TestMigrate:
    def test_copies_data_subdir(self, tmp_path):
        from convsim_core.data_migration import migrate
        legacy = tmp_path / "legacy"
        (legacy / "data").mkdir(parents=True)
        (legacy / "data" / "file.txt").write_text("hello")
        new = tmp_path / "new"
        migrate(new, legacy)
        assert (new / "data" / "file.txt").read_text() == "hello"

    def test_writes_migration_marker(self, tmp_path):
        from convsim_core.data_migration import migrate, _MIGRATED_MARKER
        legacy = tmp_path / "legacy"
        (legacy / "logs").mkdir(parents=True)
        new = tmp_path / "new"
        result = migrate(new, legacy)
        assert result is True
        assert (legacy / _MIGRATED_MARKER).exists()

    def test_does_not_overwrite_existing_new_subdir(self, tmp_path):
        from convsim_core.data_migration import migrate
        legacy = tmp_path / "legacy"
        (legacy / "data").mkdir(parents=True)
        (legacy / "data" / "legacy.txt").write_text("old")
        new = tmp_path / "new"
        (new / "data").mkdir(parents=True)
        (new / "data" / "existing.txt").write_text("new")
        migrate(new, legacy)
        # existing file must be untouched
        assert (new / "data" / "existing.txt").read_text() == "new"
        # legacy file must NOT overwrite
        assert not (new / "data" / "legacy.txt").exists()

    def test_returns_false_on_copy_error(self, tmp_path):
        """Simulate a copy failure and verify migrate() returns False."""
        from convsim_core.data_migration import migrate
        import shutil

        legacy = tmp_path / "legacy"
        (legacy / "data").mkdir(parents=True)
        new = tmp_path / "new"

        original_copytree = shutil.copytree

        def fail_copytree(src, dst, **kw):
            raise OSError("simulated failure")

        with patch("convsim_core.data_migration.shutil.copytree", fail_copytree):
            result = migrate(new, legacy)
        assert result is False

    def test_original_data_preserved_on_failure(self, tmp_path):
        from convsim_core.data_migration import migrate
        import shutil

        legacy = tmp_path / "legacy"
        (legacy / "data").mkdir(parents=True)
        (legacy / "data" / "keep.txt").write_text("precious")
        new = tmp_path / "new"

        with patch("convsim_core.data_migration.shutil.copytree", side_effect=OSError("oops")):
            migrate(new, legacy)

        assert (legacy / "data" / "keep.txt").read_text() == "precious"

    def test_partial_failure_rolls_back_and_retries_next_launch(self, tmp_path):
        """A copy that fails partway must not orphan the un-copied subdirs.

        needs_migration() skips when new_root is non-empty, so a partial copy
        left in place would make migration never retry, stranding the rest of
        the legacy data. The failed run must roll back what it copied so the
        next launch sees an empty new_root and completes the migration.
        """
        from convsim_core.data_migration import needs_migration, migrate
        import shutil

        legacy = tmp_path / "legacy"
        # _MIGRATE_SUBDIRS order copies "data" before "logs"; make the "logs"
        # copy fail after "data" has already succeeded.
        (legacy / "data").mkdir(parents=True)
        (legacy / "data" / "keep.txt").write_text("precious")
        (legacy / "logs").mkdir(parents=True)
        (legacy / "logs" / "app.log").write_text("log")
        new = tmp_path / "new"

        real_copytree = shutil.copytree

        def flaky_copytree(src, dst, **kw):
            if Path(dst).name == "logs":
                raise OSError("simulated mid-migration failure")
            return real_copytree(src, dst, **kw)

        with patch("convsim_core.data_migration.shutil.copytree", flaky_copytree):
            assert migrate(new, legacy) is False

        # The successfully-copied "data" subdir must have been rolled back so
        # new_root is empty again and migration is re-attempted.
        assert not (new / "data").exists()
        assert needs_migration(new, legacy)

        # Second launch with a healthy filesystem completes the migration.
        assert migrate(new, legacy) is True
        assert (new / "data" / "keep.txt").read_text() == "precious"
        assert (new / "logs" / "app.log").read_text() == "log"
        assert not needs_migration(new, legacy)
        # Original legacy data preserved throughout.
        assert (legacy / "data" / "keep.txt").read_text() == "precious"

    def test_models_not_migrated(self, tmp_path):
        """Models directory is excluded from migration (can be many GBs)."""
        from convsim_core.data_migration import migrate
        legacy = tmp_path / "legacy"
        (legacy / "models").mkdir(parents=True)
        (legacy / "models" / "big.gguf").write_bytes(b"\x00" * 16)
        new = tmp_path / "new"
        migrate(new, legacy)
        assert not (new / "models").exists()

    def test_migration_runs_and_marker_prevents_rerun(self, tmp_path):
        from convsim_core.data_migration import needs_migration, migrate
        legacy = tmp_path / "legacy"
        (legacy / "data").mkdir(parents=True)
        new = tmp_path / "new"
        assert needs_migration(new, legacy)
        migrate(new, legacy)
        assert not needs_migration(new, legacy)


class TestMigrationDuringAppStartup:
    """End-to-end: create_app must migrate legacy data before configure_logging
    populates the (previously empty) platform root and defeats needs_migration.
    """

    def test_create_app_migrates_legacy_data_before_logging(self, tmp_path, monkeypatch):
        import convsim_core.app as app_mod
        from convsim_core.config import ServiceConfig

        new_root = tmp_path / "platform_root"  # does not exist yet
        legacy = tmp_path / "legacy"
        (legacy / "db").mkdir(parents=True)
        (legacy / "db" / "convsim.sqlite3").write_text("legacy-conversations")

        # Redirect the app's root/legacy resolution to our fixtures.
        monkeypatch.setattr(app_mod, "platform_data_root", lambda: new_root)
        monkeypatch.setattr(app_mod, "legacy_convsim_dir", lambda: legacy)

        # Config points every mutable dir under the (initially empty) new root,
        # mirroring a packaged install where log_dir == <root>/logs.
        cfg = ServiceConfig(
            data_dir=str(new_root / "data"),
            log_dir=str(new_root / "logs"),
            db_dir=str(new_root / "db"),
            packs_dir=str(new_root / "packs"),
            exports_dir=str(new_root / "exports"),
            cache_dir=str(new_root / "cache"),
            crash_bundles_dir=str(new_root / "crashes"),
            models_dir=str(new_root / "models" / "llm"),
            official_packs_dir=str(tmp_path / "no-official-packs"),
        )

        # create_app runs migration + configure_logging synchronously; the
        # lifespan (Database.open etc.) is not entered here.
        app_mod.create_app(cfg)

        migrated = new_root / "db" / "convsim.sqlite3"
        assert migrated.exists(), "legacy db was not migrated during startup"
        assert migrated.read_text() == "legacy-conversations"
        # Original legacy data must be preserved (copy, not move).
        assert (legacy / "db" / "convsim.sqlite3").read_text() == "legacy-conversations"
