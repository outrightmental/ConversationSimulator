# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the onboarding e2e suite (issue #387).

Every test starts from a wiped profile: a fresh temporary data directory with
no recorded onboarding outcome, no installed models, and no localStorage state
(the API is the authoritative source of truth per issue #380).

One-line usage in a test module::

    def test_something(fresh_profile):
        client, app = fresh_profile
        resp = client.get("/api/setup/status")
        assert resp.json()["kind"] == "never-run"

The fixture_server fixture provides an offline-safe local HTTP server so no
test depends on Hugging Face or GitHub availability.

Module structure mirrors tests/e2e/ so CI scripts can locate tests by path.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig

from .fixture_server import FixtureServer, start_fixture_server

_REPO_ROOT = Path(__file__).parent.parent.parent
_OFFICIAL_PACKS_DIR = _REPO_ROOT / "packs" / "official"


@pytest.fixture()
def fixture_server() -> FixtureServer:  # type: ignore[override]
    """Start a local HTTP server that serves a tiny deterministic model file.

    Port 0 lets the OS assign a free port — tests never collide.
    Stopped automatically at the end of the test that requested it.
    """
    srv = start_fixture_server()
    yield srv
    srv.stop()


@pytest.fixture()
def fresh_profile(tmp_path, monkeypatch):
    """Wiped-profile harness: one-line access to a clean first-run state.

    Creates a fresh temporary data directory (no onboarding outcome, no
    installed models) and wraps a TestClient around a newly created app.
    Sets the environment variables the Tauri shell sets so the app behaves
    as it does for a real first-run user.

    Yields ``(client, app)`` so tests can also inspect app state directly
    (e.g. to seed the database or read sidecar state).
    """
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path / "runtimes"))

    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_OFFICIAL_PACKS_DIR),
        models_dir=str(tmp_path / "models" / "llm"),
        exports_dir=str(tmp_path / "exports"),
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
    )
    app = create_app(config)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, app
