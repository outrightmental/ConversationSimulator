# SPDX-License-Identifier: Apache-2.0
"""P6 Resume: kill mid-download → relaunch → resumes, lands on progress.

Journey:
  fresh profile → start install job → simulate kill (leave job in 'running'
  state without a background task) → create new app instance with same DB →
  resume_orphaned_jobs picks up the orphan → setup/status reports the pending
  job ID → the user lands on the progress screen, not the Welcome screen.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services.setup_install_service import (
    create_job,
    get_job,
    update_job_status,
)

from .helpers import assert_no_forbidden_in_preflight

_REPO_ROOT = Path(__file__).parent.parent.parent
_OFFICIAL_PACKS_DIR = _REPO_ROOT / "packs" / "official"


class TestP6Resume:
    """P6: an orphaned running job is picked up on relaunch."""

    def test_orphaned_running_job_appears_in_status(self, fresh_profile):
        """A job left in 'running' state (simulating a kill) must appear as pending_setup_job_id."""
        client, app = fresh_profile
        conn = app.state.db.connection()

        job_id = create_job(conn, registry_id="fixture-model", model_label="Test model")
        update_job_status(conn, job_id, "running")

        status = client.get("/api/setup/status").json()
        assert status.get("pending_setup_job_id") == job_id, (
            f"An orphaned running job (id={job_id}) must appear as pending_setup_job_id; "
            f"got {status.get('pending_setup_job_id')!r}"
        )

    def test_relaunch_pending_job_id_survives_app_restart(self, fresh_profile):
        """An orphaned running job must survive an app restart and appear as pending_setup_job_id.

        The frontend uses pending_setup_job_id in the first-run redirect URL
        (/first-run?resume_install=<id>) to navigate the user to the install
        progress screen rather than starting from the beginning of the wizard.

        resume_orphaned_jobs calls _launch_pipeline_task for the newest job
        (patched here) and keeps the job in a non-terminal state so
        get_active_job returns it on the first status poll after relaunch.
        """
        client, app = fresh_profile
        conn = app.state.db.connection()

        # Seed the model registry so resume_orphaned_jobs can find the model
        # and call _launch_pipeline_task (rather than failing the job).
        conn.execute(
            "INSERT OR REPLACE INTO model_registry "
            "(id, name, provider, source_type, download_url, sha256, size_gb) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("fixture-model", "Fixture", "fixture", "huggingface",
             "http://127.0.0.1:9999/model.gguf", "a" * 64, 0.001),
        )
        conn.commit()

        job_id = create_job(conn, registry_id="fixture-model", model_label="Test model")
        update_job_status(conn, job_id, "running")

        # Relaunch: create a new app with the same db_dir.
        db_dir = app.state.service_config.db_dir
        new_config = ServiceConfig(
            host="127.0.0.1",
            port=7355,
            db_dir=db_dir,
            data_dir=str(Path(db_dir).parent / "data"),
            log_dir=str(Path(db_dir).parent / "logs"),
            packs_dir=str(Path(db_dir).parent / "packs"),
            official_packs_dir=str(_OFFICIAL_PACKS_DIR),
            models_dir=str(Path(db_dir).parent / "models" / "llm"),
            exports_dir=str(Path(db_dir).parent / "exports"),
            cache_dir=str(Path(db_dir).parent / "cache"),
            crash_bundles_dir=str(Path(db_dir).parent / "crashes"),
        )

        from convsim_core.routers import setup_install as si
        from fastapi.testclient import TestClient

        # resume_orphaned_jobs runs inside the app lifespan (TestClient __enter__),
        # NOT at create_app(). The patch must therefore stay active across both
        # create_app AND the TestClient context; otherwise the real pipeline task
        # launches in the background and races the status poll (flaky), instead of
        # leaving the orphaned job cleanly in 'running' for get_active_job to
        # return. With the mock in place resume_orphaned_jobs finds the job and
        # calls it (a no-op), so the job stays 'running' deterministically.
        with patch.object(si, "_launch_pipeline_task") as launch:
            new_app = create_app(new_config)
            with TestClient(new_app, raise_server_exceptions=True) as new_client:
                status = new_client.get("/api/setup/status").json()

        assert launch.call_count == 1, (
            "resume_orphaned_jobs must re-drive exactly the orphaned job on relaunch; "
            f"_launch_pipeline_task was called {launch.call_count} times"
        )
        assert launch.call_args[1].get("job_id") == job_id, (
            "resume must re-drive the orphaned job, not a different one; "
            f"got job_id={launch.call_args[1].get('job_id')!r}"
        )

        assert status.get("pending_setup_job_id") == job_id, (
            f"After relaunch the orphaned job (id={job_id}) must appear as "
            f"pending_setup_job_id so the frontend can offer 'resume install' "
            f"via /first-run?resume_install={job_id}. Got: {status.get('pending_setup_job_id')!r}"
        )

    def test_cancelled_job_does_not_appear_as_pending(self, fresh_profile):
        """A user-cancelled job must not revive on relaunch."""
        client, app = fresh_profile
        conn = app.state.db.connection()

        job_id = create_job(conn, registry_id="fixture-model", model_label="Test model")
        update_job_status(conn, job_id, "cancelled")

        status = client.get("/api/setup/status").json()
        assert status.get("pending_setup_job_id") is None, (
            "A cancelled job must not appear as pending_setup_job_id on the next launch"
        )

    def test_resume_orphaned_jobs_launches_newest_running_job(self, fresh_profile):
        """After simulating kill+relaunch, resume_orphaned_jobs must re-drive the newest job."""
        _, app = fresh_profile
        conn = app.state.db.connection()

        conn.execute(
            "INSERT OR REPLACE INTO model_registry "
            "(id, name, provider, source_type, download_url, sha256, size_gb) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("fixture-model", "Fixture", "fixture", "huggingface",
             "http://127.0.0.1:9999/model.gguf", "a" * 64, 0.001),
        )
        conn.commit()

        old_job = create_job(conn, registry_id="fixture-model", model_label="old")
        update_job_status(conn, old_job, "running")
        new_job = create_job(conn, registry_id="fixture-model", model_label="new")
        update_job_status(conn, new_job, "running")

        from convsim_core.routers import setup_install as si
        with patch.object(si, "_launch_pipeline_task") as launch:
            si.resume_orphaned_jobs(app)

        assert launch.call_count == 1, (
            "resume_orphaned_jobs must launch exactly one pipeline task "
            "(the newest non-terminal job); older orphans should be retired"
        )
        call_kwargs = launch.call_args[1]
        assert call_kwargs.get("job_id") == new_job, (
            f"resume_orphaned_jobs must re-drive the newest job (id={new_job}); "
            f"got job_id={call_kwargs.get('job_id')!r}"
        )

    def test_preflight_no_forbidden_vocabulary(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)
