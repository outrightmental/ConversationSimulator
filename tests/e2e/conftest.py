# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for end-to-end scripted playthrough tests.

These tests simulate the environment the Tauri shell creates before launching
convsim-core as a sidecar.  Key differences from the acceptance test suite
(tests/acceptance/):

  - CONVSIM_BUNDLED_RUNTIME_DIR is set (simulates the sidecar launch signal).
  - official_packs_dir points to the real packs/official/ directory in the
    repo, mirroring the bundled-app path the Tauri shell sets via
    CONVSIM_OFFICIAL_PACKS_DIR.
  - Tests are smoke tests: minimal assertions, failure messages that do not
    expose transcript content.

All checks run against the fake runtime — no model download required.
For real-model packaged-app testing see Part F of docs/release-checklist.md.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig

# The repo root is three levels above tests/e2e/
_REPO_ROOT = Path(__file__).parent.parent.parent
_OFFICIAL_PACKS_DIR = _REPO_ROOT / "packs" / "official"


@pytest.fixture()
def packaged_config(tmp_path, monkeypatch):
    """ServiceConfig that simulates the environment the Tauri shell sets.

    Sets CONVSIM_BUNDLED_RUNTIME_DIR (the sidecar launch signal) and routes
    official_packs_dir to the real packs/official/ directory in the repo,
    mirroring how the packaged .app / AppImage / installer loads bundled packs.
    """
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path / "runtimes"))
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_OFFICIAL_PACKS_DIR),
    )


@pytest.fixture()
def client(packaged_config):
    """TestClient wrapping a convsim-core app in packaged-environment mode."""
    app = create_app(packaged_config)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
