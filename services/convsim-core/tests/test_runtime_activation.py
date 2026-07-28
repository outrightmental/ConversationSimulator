# SPDX-License-Identifier: Apache-2.0
"""Regression tests for live runtime activation (the fake-runtime-forever bug).

``POST /api/models/use`` and the setup pipeline used to persist the selection
with ``set_active_config`` only — but sessions read ``app.state.runtime``,
which was built once at startup from ``config.runtime_id`` (default: fake) and
never swapped. Result: in packaged builds every conversation ran on the fake
runtime no matter what the user installed or selected, and a restart reverted
any selection. These tests pin the three guarantees that fix it:

1. a successful /api/models/use swaps the LIVE runtime object;
2. the persisted selection survives a restart (startup reads the DB);
3. an unknown persisted runtime id falls back to the config default.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.runtime.active import resolve_startup_runtime_id
from convsim_core.services.model_manager_service import set_active_config


def _config(tmp_path: Path) -> ServiceConfig:
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
    )


def test_use_model_swaps_live_runtime(tmp_path):
    config = _config(tmp_path)
    app = create_app(config)
    with TestClient(app) as client:
        assert app.state.runtime.id == "fake"  # config default

        resp = client.post(
            "/api/models/use", json={"runtime_id": "scripted", "model_id": None}
        )
        assert resp.status_code == 200, resp.text

        # The LIVE runtime object sessions use must have been swapped —
        # persisting the config alone is the exact historical bug.
        assert app.state.runtime.id == "scripted"


def test_selection_survives_restart(tmp_path):
    config = _config(tmp_path)
    app = create_app(config)
    with TestClient(app) as client:
        resp = client.post(
            "/api/models/use", json={"runtime_id": "scripted", "model_id": None}
        )
        assert resp.status_code == 200, resp.text

    # Simulate an app restart on the same profile: the persisted selection —
    # not the config default — must win.
    app2 = create_app(config)
    with TestClient(app2):
        assert app2.state.runtime.id == "scripted"


def test_unknown_persisted_runtime_falls_back_to_config(tmp_path):
    config = _config(tmp_path)
    app = create_app(config)
    with TestClient(app):
        conn = app.state.db.connection()
        set_active_config(conn, runtime_id="does-not-exist", model_id=None)
        assert resolve_startup_runtime_id(conn, "fake") == "fake"
