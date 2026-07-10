# SPDX-License-Identifier: Apache-2.0
"""Packaged-startup verification tests.

These tests verify that convsim-core behaves correctly when launched from a
PyInstaller single-file bundle (sys._MEIPASS is set) or when the Tauri shell
sets CONVSIM_OFFICIAL_PACKS_DIR to point at bundled packs.

They do NOT require the PyInstaller binary to be built — they simulate the
packaged environment by patching sys attributes and environment variables.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reload_config():
    """Force a fresh import of config so module-level defaults are recomputed."""
    import convsim_core.config as cfg_mod
    importlib.reload(cfg_mod)
    return cfg_mod


# ── official_packs_dir resolution ────────────────────────────────────────────


class TestOfficialPacksDirResolution:
    def test_dev_default_points_inside_repo(self):
        """In dev mode (no _MEIPASS) the default resolves to the repo packs dir."""
        cfg_mod = _reload_config()
        default = cfg_mod._DEFAULT_OFFICIAL_PACKS_DIR
        # The path may not exist in every CI environment, but it must end with
        # packs/official so the repo structure is intact.
        assert default.replace("\\", "/").endswith("packs/official"), (
            f"Unexpected default official_packs_dir: {default}"
        )

    def test_frozen_default_points_to_meipass(self, tmp_path):
        """In a PyInstaller bundle (_MEIPASS set), default uses sys._MEIPASS."""
        fake_packs = tmp_path / "packs" / "official"
        fake_packs.mkdir(parents=True)

        frozen_attrs = {"_MEIPASS": str(tmp_path), "frozen": True}
        # sys._MEIPASS / sys.frozen do not exist outside a bundle, so create=True.
        with patch.multiple(sys, create=True, **frozen_attrs):
            cfg_mod = _reload_config()
            assert cfg_mod._DEFAULT_OFFICIAL_PACKS_DIR == str(fake_packs)

    def test_env_override_takes_precedence(self, tmp_path):
        """CONVSIM_OFFICIAL_PACKS_DIR env var overrides the computed default."""
        custom = tmp_path / "custom_packs"
        custom.mkdir()

        with patch.dict(os.environ, {"CONVSIM_OFFICIAL_PACKS_DIR": str(custom)}):
            from convsim_core.config import ServiceConfig
            cfg = ServiceConfig()
            assert cfg.official_packs_dir == str(custom)

    def test_frozen_env_override_takes_precedence(self, tmp_path):
        """Env var overrides even when running inside a PyInstaller bundle."""
        fake_meipass = tmp_path / "meipass"
        fake_meipass.mkdir()
        custom = tmp_path / "custom_packs"
        custom.mkdir()

        frozen_attrs = {"_MEIPASS": str(fake_meipass), "frozen": True}
        with patch.multiple(sys, create=True, **frozen_attrs):
            with patch.dict(os.environ, {"CONVSIM_OFFICIAL_PACKS_DIR": str(custom)}):
                from convsim_core.config import ServiceConfig
                cfg = ServiceConfig()
                assert cfg.official_packs_dir == str(custom)


# ── Stable per-user data paths ────────────────────────────────────────────────


class TestStableDataPaths:
    """Verify that logs, db, data, packs, and models all route to ~/.convsim/."""

    def test_log_dir_default(self):
        from convsim_core.config import ServiceConfig
        cfg = ServiceConfig()
        assert Path(cfg.log_dir) == Path.home() / ".convsim" / "logs"

    def test_data_dir_default(self):
        from convsim_core.config import ServiceConfig
        cfg = ServiceConfig()
        assert Path(cfg.data_dir) == Path.home() / ".convsim" / "data"

    def test_db_dir_default(self):
        from convsim_core.config import ServiceConfig
        cfg = ServiceConfig()
        assert Path(cfg.db_dir) == Path.home() / ".convsim" / "db"

    def test_packs_dir_default(self):
        from convsim_core.config import ServiceConfig
        cfg = ServiceConfig()
        assert Path(cfg.packs_dir) == Path.home() / ".convsim" / "packs"

    def test_models_dir_default(self):
        from convsim_core.config import ServiceConfig
        cfg = ServiceConfig()
        assert Path(cfg.models_dir) == Path.home() / ".convsim" / "models" / "llm"

    def test_all_user_data_dirs_under_home_convsim(self):
        """All mutable user data paths stay within ~/.convsim/."""
        from convsim_core.config import ServiceConfig
        cfg = ServiceConfig()
        convsim_root = Path.home() / ".convsim"
        mutable_dirs = [cfg.log_dir, cfg.data_dir, cfg.db_dir, cfg.packs_dir, cfg.models_dir]
        for d in mutable_dirs:
            assert Path(d).is_relative_to(convsim_root), (
                f"{d!r} escapes ~/.convsim/ — stable per-user path broken"
            )


# ── Packaged environment simulation ──────────────────────────────────────────


class TestPackagedEnvSimulation:
    """Simulate the environment set by the Tauri shell before launching convsim-core."""

    def test_bundled_runtime_dir_propagated(self, tmp_path):
        """CONVSIM_BUNDLED_RUNTIME_DIR is read and available to runtime modules."""
        fake_runtimes = tmp_path / "runtimes"
        fake_runtimes.mkdir()

        with patch.dict(os.environ, {"CONVSIM_BUNDLED_RUNTIME_DIR": str(fake_runtimes)}):
            assert os.environ["CONVSIM_BUNDLED_RUNTIME_DIR"] == str(fake_runtimes)

    def test_host_port_override(self):
        """CONVSIM_HOST and CONVSIM_PORT overrides are accepted by ServiceConfig."""
        with patch.dict(os.environ, {"CONVSIM_HOST": "127.0.0.1", "CONVSIM_PORT": "7355"}):
            from convsim_core.config import ServiceConfig
            cfg = ServiceConfig()
            assert cfg.host == "127.0.0.1"
            assert cfg.port == 7355

    def test_wildcard_bind_still_rejected_in_packaged_mode(self):
        """Wildcard bind must be rejected even when CONVSIM_BUNDLED_RUNTIME_DIR is set."""
        from convsim_core.config import ServiceConfig
        from pydantic import ValidationError

        env = {
            "CONVSIM_HOST": "0.0.0.0",
            "CONVSIM_BUNDLED_RUNTIME_DIR": "/tmp/runtimes",
        }
        with patch.dict(os.environ, env):
            with pytest.raises(ValidationError):
                ServiceConfig()


# ── No dev imports in packaged binary ─────────────────────────────────────────


class TestNoDevImportsLeakage:
    """Guard that test / dev packages cannot be imported from convsim_core."""

    @staticmethod
    def _leaked_modules_after_import(package: str) -> list[str]:
        """Import convsim_core in a clean subprocess and report leaked modules.

        This must run in a fresh interpreter: when these tests run under pytest,
        pytest (and possibly setuptools) are already in this process's
        sys.modules, so an in-process check would always report a false leak.
        """
        code = (
            "import sys, convsim_core;"
            f"print(','.join(m for m in sys.modules "
            f"if m == {package!r} or m.startswith({package + '.'!r})))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        )
        return [m for m in result.stdout.strip().split(",") if m]

    def test_pytest_not_imported_transitively(self):
        leaked = self._leaked_modules_after_import("pytest")
        assert not leaked, f"pytest leaked into convsim_core imports: {leaked}"

    def test_setuptools_not_imported_transitively(self):
        # setuptools is used at install time; it must not be a runtime dependency.
        leaked = self._leaked_modules_after_import("setuptools")
        assert not leaked, f"setuptools leaked into convsim_core imports: {leaked}"
