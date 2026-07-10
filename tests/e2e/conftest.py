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

By default checks run against an in-process app on the fake runtime — no model
download required.  When CONVSIM_LIVE_URL is set (release-smoke.sh --full), the
same tests run against an already-running convsim-core server at that URL
instead, so --full genuinely exercises a live (packaged) sidecar rather than a
fresh in-process app.  For real-model packaged-app testing see Part F of
docs/release-checklist.md.

Fixtures are module-scoped so the app starts once per test module rather than
once per test.  This is significant on Windows where process startup is slower;
sharing the app across all tests in a module keeps CI wall-clock time predictable
across runner generations.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig

# The repo root is three levels above tests/e2e/
_REPO_ROOT = Path(__file__).parent.parent.parent
_OFFICIAL_PACKS_DIR = _REPO_ROOT / "packs" / "official"


@pytest.fixture(scope="module")
def packaged_config(tmp_path_factory):
    """ServiceConfig that simulates the environment the Tauri shell sets.

    Sets CONVSIM_BUNDLED_RUNTIME_DIR (the sidecar launch signal) and routes
    official_packs_dir to the real packs/official/ directory in the repo,
    mirroring how the packaged .app / AppImage / installer loads bundled packs.

    Module-scoped: one config (and temp directory) is shared across all tests
    in the module so the app is only started and torn down once.
    """
    tmp_path = tmp_path_factory.mktemp("e2e")
    os.environ["CONVSIM_BUNDLED_RUNTIME_DIR"] = str(tmp_path / "runtimes")
    os.environ["CONVSIM_WHISPER_CPP_BINARY_PATH"] = str(tmp_path / "no-whisper-cli")
    try:
        yield ServiceConfig(
            host="127.0.0.1",
            port=7355,
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
            db_dir=str(tmp_path / "db"),
            packs_dir=str(tmp_path / "packs"),
            official_packs_dir=str(_OFFICIAL_PACKS_DIR),
        )
    finally:
        os.environ.pop("CONVSIM_BUNDLED_RUNTIME_DIR", None)
        os.environ.pop("CONVSIM_WHISPER_CPP_BINARY_PATH", None)


@pytest.fixture(scope="module")
def client(packaged_config):
    """HTTP client for a convsim-core server in packaged-environment mode.

    When CONVSIM_LIVE_URL is set, yield an httpx.Client pointed at that live
    server (release-smoke.sh --full runs the playthrough against a real running
    sidecar).  Otherwise wrap a fresh in-process app on the fake runtime.  Both
    expose the same relative-path request API the tests use, so the test body is
    identical either way.

    Module-scoped: the app lifespan runs once for all tests in the module,
    avoiding repeated startup/teardown overhead on slow runners.
    """
    live_url = os.environ.get("CONVSIM_LIVE_URL", "").strip()
    if live_url:
        with httpx.Client(base_url=live_url.rstrip("/"), timeout=120.0) as c:
            yield c
        return
    app = create_app(packaged_config)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
