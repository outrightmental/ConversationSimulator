# SPDX-License-Identifier: Apache-2.0
"""Tests for the one-click install pipeline API.

Covers the happy path (all stages complete), resume/reattach behaviour,
cancel, each terminal failure class (disk, offline, checksum), and the
GET /api/setup/status ``pending_setup_job_id`` field.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import convsim_core.runtime  # noqa: F401 — register built-in adapters
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services.model_registry_service import load_and_persist_registry
from convsim_core.services.setup_install_service import (
    create_job,
    get_active_job,
    get_job,
    update_job_status,
)
from convsim_core.storage.database import Database

_REGISTRY_PATH = Path(__file__).parent.parent.parent.parent / "model-registry" / "registry.yaml"


def _load_registry(conn: Any) -> None:
    if _REGISTRY_PATH.exists():
        load_and_persist_registry(conn, str(_REGISTRY_PATH))


def _pick_registry_id(conn: Any) -> str | None:
    row = conn.execute(
        "SELECT id FROM model_registry WHERE sha256 IS NOT NULL AND sha256 != 'PENDING' "
        "AND download_url IS NOT NULL LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"),
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
        models_dir=str(tmp_path / "models" / "llm"),
        official_packs_dir=str(tmp_path / "no-official-packs"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_with_registry(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        _load_registry(app.state.db.connection())
        yield c, app


# ── GET /api/setup/status includes pending_setup_job_id ───────────────────────


def test_setup_status_includes_pending_setup_job_id_when_job_active(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    job_id = create_job(conn, registry_id="test-model", model_label="Downloading test")
    # Status should report the job as pending
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_setup_job_id"] == job_id


def test_setup_status_no_setup_job_id_when_none_active(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    # Create a terminal (complete) job — should not appear
    job_id = create_job(conn, registry_id="old", model_label="Old model")
    update_job_status(conn, job_id, "complete")
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json()["pending_setup_job_id"] is None


# ── POST /api/setup/install ───────────────────────────────────────────────────


def test_start_install_unknown_model_returns_404(client):
    resp = client.post("/api/setup/install", json={"registry_id": "nonexistent-model"})
    assert resp.status_code == 404


def test_start_install_creates_job_and_returns_stages(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    registry_id = _pick_registry_id(conn)
    if registry_id is None:
        pytest.skip("No registry models with sha256 available")

    # Suppress the actual pipeline so we can inspect the created job synchronously.
    with patch(
        "convsim_core.routers.setup_install._run_pipeline",
        new_callable=AsyncMock,
    ):
        resp = client.post("/api/setup/install", json={"registry_id": registry_id})

    assert resp.status_code == 200
    body = resp.json()
    assert body["registry_id"] == registry_id
    assert body["status"] in ("pending", "running")
    stage_ids = [s["id"] for s in body["stages"]]
    assert stage_ids == ["engine", "model", "verify", "warmup", "packs"]
    for s in body["stages"]:
        assert s["state"] == "pending"


def test_start_install_reattaches_to_in_progress_job(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    registry_id = _pick_registry_id(conn)
    if registry_id is None:
        pytest.skip("No registry models with sha256 available")

    with patch(
        "convsim_core.routers.setup_install._run_pipeline",
        new_callable=AsyncMock,
    ):
        r1 = client.post("/api/setup/install", json={"registry_id": registry_id})
        r2 = client.post("/api/setup/install", json={"registry_id": registry_id})

    assert r1.json()["id"] == r2.json()["id"]


# ── GET /api/setup/install/{id} ───────────────────────────────────────────────


def test_get_install_status_not_found(client):
    resp = client.get("/api/setup/install/9999")
    assert resp.status_code == 404


def test_get_install_status_returns_job(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    job_id = create_job(conn, registry_id="any", model_label="Any model")

    resp = client.get(f"/api/setup/install/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "pending"
    assert len(body["stages"]) == 5


# ── DELETE /api/setup/install/{id} ───────────────────────────────────────────


def test_cancel_not_found(client):
    resp = client.delete("/api/setup/install/9999")
    assert resp.status_code == 404


def test_cancel_terminal_job_returns_409(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    job_id = create_job(conn, registry_id="any", model_label="Any model")
    update_job_status(conn, job_id, "complete")

    resp = client.delete(f"/api/setup/install/{job_id}")
    assert resp.status_code == 409


def test_cancel_pending_job_no_task(client_with_registry):
    """Cancel a job that has no running asyncio task — marks it cancelled directly."""
    client, app = client_with_registry
    conn = app.state.db.connection()
    job_id = create_job(conn, registry_id="any", model_label="Any model")

    resp = client.delete(f"/api/setup/install/{job_id}")
    assert resp.status_code == 204

    updated = get_job(conn, job_id)
    assert updated["status"] == "cancelled"


# ── Failure taxonomy ──────────────────────────────────────────────────────────


def test_disk_space_failure_marks_model_stage_failed(client_with_registry):
    """When available disk space is insufficient, the model stage fails immediately."""
    client, app = client_with_registry
    conn = app.state.db.connection()
    registry_id = _pick_registry_id(conn)
    if registry_id is None:
        pytest.skip("No registry models with sha256 available")

    # Ensure model_row.size_gb is non-zero so the check fires.
    conn.execute(
        "UPDATE model_registry SET size_gb = 999.0 WHERE id = ?", (registry_id,)
    )
    conn.commit()

    # Return 0 free bytes — always insufficient.
    # Also skip the engine stage: fake find_executable so the pipeline doesn't
    # try to download the llama-server binary in the test environment (which
    # would fail and exit before reaching the disk check).
    # Keep both patches active through the polling loop: the checks run inside
    # an asyncio task that the background event loop processes after the POST
    # response is sent, so patches must stay in scope until the task completes.
    with patch("shutil.disk_usage") as mock_du, \
         patch("convsim_core.routers.setup_install.find_executable", return_value="/fake/llama-server"):
        mock_du.return_value = MagicMock(free=0)
        resp = client.post("/api/setup/install", json={"registry_id": registry_id})

        assert resp.status_code == 200
        job_id = resp.json()["id"]

        # Poll until the pipeline task updates the job (give it up to 3 s).
        import time
        deadline = time.monotonic() + 3.0
        final_body = None
        while time.monotonic() < deadline:
            r = client.get(f"/api/setup/install/{job_id}")
            b = r.json()
            if b["status"] in ("failed", "complete", "cancelled"):
                final_body = b
                break
            time.sleep(0.1)

    assert final_body is not None, "Pipeline did not reach a terminal state in time"
    assert final_body["status"] == "failed"
    model_stage = next(s for s in final_body["stages"] if s["id"] == "model")
    assert model_stage["state"] == "failed"
    assert "disk space" in (model_stage["error"] or "").lower()


# ── Restart recovery: resume_orphaned_jobs ───────────────────────────────────


def test_resume_orphaned_jobs_relaunches_newest_and_retires_older(client_with_registry):
    """After a restart, only the newest non-terminal job is re-driven; older
    orphans are retired so they don't linger as 'active' forever."""
    client, app = client_with_registry
    conn = app.state.db.connection()
    registry_id = _pick_registry_id(conn)
    if registry_id is None:
        pytest.skip("No registry models with sha256 available")

    from convsim_core.routers import setup_install

    old_job = create_job(conn, registry_id=registry_id, model_label="old")
    update_job_status(conn, old_job, "running")
    new_job = create_job(conn, registry_id=registry_id, model_label="new")
    update_job_status(conn, new_job, "running")

    with patch.object(setup_install, "_launch_pipeline_task") as launch:
        setup_install.resume_orphaned_jobs(app)

    launch.assert_called_once()
    assert launch.call_args.kwargs["job_id"] == new_job
    # The stale older job is retired rather than left as a phantom active job.
    assert get_job(conn, old_job)["status"] == "failed"


def test_resume_orphaned_jobs_noop_when_none_active(client_with_registry):
    client, app = client_with_registry
    conn = app.state.db.connection()
    job_id = create_job(conn, registry_id="x", model_label="x")
    update_job_status(conn, job_id, "complete")

    from convsim_core.routers import setup_install

    with patch.object(setup_install, "_launch_pipeline_task") as launch:
        setup_install.resume_orphaned_jobs(app)

    launch.assert_not_called()


def test_resume_orphaned_jobs_fails_job_with_unknown_registry(client):
    """A resumable job whose model vanished from the registry is failed, not
    relaunched (which would crash immediately)."""
    app = client.app
    conn = app.state.db.connection()
    job_id = create_job(conn, registry_id="ghost-model", model_label="ghost")
    update_job_status(conn, job_id, "running")

    from convsim_core.routers import setup_install

    with patch.object(setup_install, "_launch_pipeline_task") as launch:
        setup_install.resume_orphaned_jobs(app)

    launch.assert_not_called()
    assert get_job(conn, job_id)["status"] == "failed"


# ── get_active_job unit test ──────────────────────────────────────────────────


def test_get_active_job_returns_none_when_all_terminal():
    """get_active_job skips complete/failed/cancelled rows."""
    import sqlite3 as _sqlite3
    from convsim_core.storage.database import Database
    import tempfile, os

    with tempfile.TemporaryDirectory() as td:
        db = Database.open(td)
        conn = db.connection()
        jid = create_job(conn, registry_id="x", model_label="X")
        update_job_status(conn, jid, "complete")
        assert get_active_job(conn) is None
        db.close()


# ── Checksum mismatch: one silent retry, then surface ─────────────────────────


def _insert_downloadable_model(conn: Any, registry_id: str = "cm") -> None:
    """Insert a registry row the pipeline treats as downloadable (verified sha,
    URL present, size_gb 0 so the disk pre-flight is skipped)."""
    conn.execute(
        "INSERT INTO model_registry (id, name, provider, sha256, download_url, "
        "source_type, license_spdx, size_gb) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (registry_id, "Checksum Model", "test", "a" * 64,
         "http://example.test/model.gguf", "huggingface", "mit", 0.0),
    )
    conn.commit()


async def _drive_pipeline(db, tmp_path, download_side_effect, cancel_event=None):
    """Run _run_pipeline with the engine + warmup + packs stages stubbed out so
    only the model/verify download behaviour under test executes."""
    import types
    from convsim_core.routers import setup_install
    from convsim_core.runtime.sidecar import SidecarState

    conn = db.connection()
    _insert_downloadable_model(conn)
    job_id = create_job(conn, registry_id="cm", model_label="Downloading Checksum Model")

    config = types.SimpleNamespace(models_dir=str(tmp_path / "models"))
    sidecar = MagicMock()
    sidecar.state = SidecarState.RUNNING  # warmup start is skipped

    with patch.object(setup_install, "find_executable", return_value="/fake/llama-server"), \
         patch.object(setup_install, "seed_official_packs", return_value=0), \
         patch.object(
             setup_install, "execute_download",
             new=AsyncMock(side_effect=download_side_effect),
         ):
        await setup_install._run_pipeline(
            job_id=job_id,
            registry_id="cm",
            model_label="Downloading Checksum Model",
            conn=conn,
            config=config,
            sidecar=sidecar,
            model_cancel_events={},
            cancel_event=cancel_event or asyncio.Event(),
        )
    return job_id


@pytest.mark.asyncio
async def test_checksum_mismatch_retries_once_then_succeeds(tmp_path):
    """First download mismatches, the silent retry succeeds → job completes."""
    from convsim_core.services.model_manager_service import get_install_record

    db = Database.open(str(tmp_path / "db"))
    try:
        calls = {"n": 0}

        async def _dl(conn, install_id, url, sha, models_dir, filename, *, cancel_event=None):
            calls["n"] += 1
            if calls["n"] == 1:
                conn.execute(
                    "UPDATE installed_models SET install_status = 'checksum_mismatch', "
                    "error_message = 'bad hash' WHERE id = ?", (install_id,))
            else:
                conn.execute(
                    "UPDATE installed_models SET install_status = 'ready', "
                    "file_path = ?, size_bytes = 10 WHERE id = ?",
                    (str(models_dir / filename), install_id))
            conn.commit()

        job_id = await _drive_pipeline(db, tmp_path, _dl)

        assert calls["n"] == 2, "expected exactly one silent retry"
        job = get_job(db.connection(), job_id)
        assert job["status"] == "complete"
        stages = {s["id"]: s for s in job["stages"]}
        assert stages["model"]["state"] == "complete"
        assert stages["verify"]["state"] == "complete"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_user_cancel_marks_job_cancelled_not_failed(tmp_path):
    """A cancel signalled while the pipeline runs lands the job in 'cancelled'
    (matching the DELETE-with-no-task path) — never 'failed', so consumers can
    distinguish a user abort from a real error."""
    db = Database.open(str(tmp_path / "db"))
    try:
        cancel_event = asyncio.Event()

        async def _dl(conn, install_id, url, sha, models_dir, filename, *, cancel_event=None):
            # Simulate the download aborting because the pipeline was cancelled.
            conn.execute(
                "UPDATE installed_models SET install_status = 'cancelled', "
                "error_message = 'Download cancelled by user.' WHERE id = ?", (install_id,))
            conn.commit()

        cancel_event.set()
        job_id = await _drive_pipeline(db, tmp_path, _dl, cancel_event=cancel_event)

        job = get_job(db.connection(), job_id)
        assert job["status"] == "cancelled"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_checksum_mismatch_twice_fails_verify_stage(tmp_path):
    """Two consecutive mismatches surface a verify-stage failure — a corrupt
    model is never registered as ready."""
    db = Database.open(str(tmp_path / "db"))
    try:
        async def _dl(conn, install_id, url, sha, models_dir, filename, *, cancel_event=None):
            conn.execute(
                "UPDATE installed_models SET install_status = 'checksum_mismatch', "
                "error_message = 'bad hash' WHERE id = ?", (install_id,))
            conn.commit()

        job_id = await _drive_pipeline(db, tmp_path, _dl)

        job = get_job(db.connection(), job_id)
        assert job["status"] == "failed"
        stages = {s["id"]: s for s in job["stages"]}
        assert stages["verify"]["state"] == "failed"
    finally:
        db.close()
