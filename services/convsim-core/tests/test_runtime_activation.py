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
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.runtime.active import (
    ensure_llama_sidecar_running,
    resolve_startup_runtime_id,
)
from convsim_core.runtime.launch import LaunchConfig, resolve_launch_config
from convsim_core.runtime.sidecar import SidecarState
from convsim_core.services.model_manager_service import set_active_config
from convsim_core.storage.database import Database


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


# ── Engine launch configuration (issue #523) ─────────────────────────────────


def _seed_registry_model(conn, *, registry_id: str, context_length: int, file_path: str) -> None:
    conn.execute(
        "INSERT INTO model_registry (id, name, provider, context_length) VALUES (?, ?, ?, ?)",
        (registry_id, "Registry Model", "test", context_length),
    )
    conn.execute(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status) "
        "VALUES (?, ?, ?, 'ready')",
        (registry_id, Path(file_path).name, file_path),
    )
    conn.commit()


def _stopped_sidecar() -> MagicMock:
    sidecar = MagicMock()
    sidecar.state = SidecarState.STOPPED
    sidecar.start = AsyncMock()
    return sidecar


@pytest.mark.asyncio
async def test_autostart_launches_with_the_registry_launch_config(tmp_path, monkeypatch):
    """ensure_llama_sidecar_running — the autostart behind /api/models/use, the
    benchmark and app startup — resolves the same launch configuration as the
    other two start sites (issue #523): the registry's context size for the
    model, one slot, small batches."""
    db = Database.open(str(tmp_path / "db"))
    try:
        conn = db.connection()
        model = tmp_path / "registry-model.gguf"
        model.write_bytes(b"gguf")
        _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))

        sidecar = _stopped_sidecar()
        app = SimpleNamespace(state=SimpleNamespace(db=db, sidecar=sidecar))
        monkeypatch.setattr(
            "convsim_core.runtime.sidecar.find_executable", lambda: "/fake/llama-server"
        )

        started = await ensure_llama_sidecar_running(app, model_path=str(model))

        assert started == str(model)
        sidecar.start.assert_awaited_once()
        kwargs = sidecar.start.await_args.kwargs
        assert kwargs["model_path"] == str(model)
        assert kwargs["executable"] == "/fake/llama-server"
        assert kwargs["launch"] == resolve_launch_config(str(model), conn)
        assert kwargs["launch"] == LaunchConfig(context_length=6144)
    finally:
        db.close()


@pytest.mark.asyncio
async def test_autostart_without_a_model_path_resolves_the_ready_model(tmp_path, monkeypatch):
    """App-startup autostart passes no path; the newest ready install is used
    and its registry context size still reaches the launch configuration."""
    db = Database.open(str(tmp_path / "db"))
    try:
        conn = db.connection()
        model = tmp_path / "registry-model.gguf"
        model.write_bytes(b"gguf")
        _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))

        sidecar = _stopped_sidecar()
        app = SimpleNamespace(state=SimpleNamespace(db=db, sidecar=sidecar))
        monkeypatch.setattr(
            "convsim_core.runtime.sidecar.find_executable", lambda: "/fake/llama-server"
        )

        started = await ensure_llama_sidecar_running(app)

        assert started == str(model)
        assert sidecar.start.await_args.kwargs["launch"] == LaunchConfig(context_length=6144)
    finally:
        db.close()
