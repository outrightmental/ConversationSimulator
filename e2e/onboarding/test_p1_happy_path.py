# SPDX-License-Identifier: Apache-2.0
"""P1 Happy path: Welcome → Set me up → install pipeline → ready → first session.

Journey:
  fresh profile → status never-run → start install job (fixture model, engine
  and warmup mocked so no binary needed) → poll to completion → record outcome
  → status ready → create a session (real-runtime conversation reachable).

Invariants checked in every step:
  - No forbidden vocabulary in any user-visible API message
  - No network request escapes localhost (fixture server is localhost)
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from .helpers import (
    assert_no_forbidden_in_install_error,
    assert_no_forbidden_in_preflight,
    assert_no_forbidden_vocabulary,
)

_FIXTURE_REGISTRY_ID = "fixture-model-p1"
_INSTALL_POLL_TIMEOUT = 15.0  # seconds


def _seed_fixture_model(app, fixture_server) -> None:
    """Insert a model registry row pointing at the fixture HTTP server."""
    conn = app.state.db.connection()
    conn.execute(
        "INSERT OR REPLACE INTO model_registry "
        "(id, name, provider, source_type, download_url, sha256, size_gb, license_spdx) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _FIXTURE_REGISTRY_ID,
            "Fixture Model (P1)",
            "fixture",
            "huggingface",
            fixture_server.model_url,
            fixture_server.sha256,
            0.0001,  # tiny; disk check uses 2.2× so ~0 GB needed
            "MIT",
        ),
    )
    conn.commit()


def _poll_job(client, job_id: int, timeout: float = _INSTALL_POLL_TIMEOUT) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/setup/install/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("complete", "failed", "cancelled"):
            return body
        time.sleep(0.1)
    pytest.fail(f"Install job {job_id} did not reach terminal state within {timeout}s")


class TestP1HappyPath:
    """P1: happy-path onboarding journey from wiped profile to ready state."""

    def test_fresh_profile_is_never_run(self, fresh_profile):
        client, _ = fresh_profile
        resp = client.get("/api/setup/status")
        assert resp.status_code == 200
        assert resp.json()["kind"] == "never-run", (
            "A fresh profile must report 'never-run' before any onboarding outcome is recorded"
        )

    def test_preflight_returns_200_on_fresh_profile(self, fresh_profile):
        client, _ = fresh_profile
        resp = client.get("/api/preflight")
        assert resp.status_code == 200
        assert resp.json()["overall"] in ("pass", "warn", "fail")

    def test_preflight_needs_human_checks_have_no_forbidden_vocabulary(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)

    def test_install_pipeline_completes_with_fixture_model(
        self, fresh_profile, fixture_server
    ):
        client, app = fresh_profile
        _seed_fixture_model(app, fixture_server)

        # Set the sidecar to RUNNING so the warmup stage is skipped.
        from convsim_core.runtime.sidecar import SidecarState
        app.state.sidecar._state = SidecarState.RUNNING

        # Patches must stay active through the whole poll loop because the
        # background asyncio task reads find_executable during its execution.
        with (
            patch(
                "convsim_core.routers.setup_install.find_executable",
                return_value="/fake/llama-server",
            ),
            patch(
                "convsim_core.routers.setup_install.download_binary",
                new_callable=AsyncMock,
            ),
        ):
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200, f"Install start failed: {resp.text}"
            job_id = resp.json()["id"]
            final = _poll_job(client, job_id)

        assert final["status"] == "complete", (
            f"Install pipeline did not complete. Status: {final['status']}. "
            f"Stages: {final['stages']}"
        )

    def test_install_error_messages_have_no_forbidden_vocabulary(
        self, fresh_profile, fixture_server
    ):
        client, app = fresh_profile
        _seed_fixture_model(app, fixture_server)

        from convsim_core.runtime.sidecar import SidecarState
        app.state.sidecar._state = SidecarState.RUNNING

        with (
            patch(
                "convsim_core.routers.setup_install.find_executable",
                return_value="/fake/llama-server",
            ),
            patch(
                "convsim_core.routers.setup_install.download_binary",
                new_callable=AsyncMock,
            ),
        ):
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200
            job_id = resp.json()["id"]
            final = _poll_job(client, job_id)

        assert_no_forbidden_in_install_error(final.get("stages", []))

    def test_status_ready_after_completed_install_and_outcome(
        self, fresh_profile, fixture_server
    ):
        client, app = fresh_profile
        _seed_fixture_model(app, fixture_server)

        conn = app.state.db.connection()
        conn.execute(
            "INSERT INTO packs (slug, name, version) VALUES (?, ?, ?)",
            ("starter.pack", "Starter", "1.0.0"),
        )
        conn.execute(
            "INSERT INTO installed_models "
            "(registry_id, filename, file_path, install_status) VALUES (?, ?, ?, ?)",
            (_FIXTURE_REGISTRY_ID, "fixture-model-p1.gguf", "/models/fixture-model-p1.gguf", "ready"),
        )
        conn.commit()

        outcome_resp = client.post(
            "/api/setup/outcome", json={"outcome": "completed-with-model"}
        )
        assert outcome_resp.status_code == 204

        status = client.get("/api/setup/status").json()
        assert status["kind"] == "ready", (
            f"Expected 'ready' after install + outcome; got {status['kind']!r}. "
            f"Missing: {status.get('missing')}"
        )

    def test_session_reachable_after_setup(self, fresh_profile, fixture_server):
        """After setup the tutorial scenario is reachable (proxy for real-runtime access)."""
        client, app = fresh_profile
        _seed_fixture_model(app, fixture_server)

        resp = client.post(
            "/api/sessions",
            json={
                "scenario_id": "first_words_tutorial",
                "difficulty": "standard",
                "player_role_name": "P1 Tester",
                "language": "en",
                "input_mode": "text-only",
                "tts_enabled": False,
                "show_state_meters": False,
                "save_transcript": False,
            },
        )
        assert resp.status_code == 201, (
            f"Session creation failed after setup (status {resp.status_code})"
        )
        assert "session_id" in resp.json()

    def test_network_allowlist_guard_blocks_external_connections(self, fresh_profile):
        """The autouse network guard must actively block non-loopback connections.

        The whole suite's offline-safe / privacy guarantee (issue #387) rests on
        the ``network_allowlist_guard`` fixture. This self-check proves the guard
        is armed in every path — if it silently degraded to a no-op, the
        "no network request escapes the fixture allowlist" invariant would pass
        vacuously. A real external connection is never made: the guard raises
        before delegating to the real socket connect.
        """
        import socket

        with pytest.raises(AssertionError, match="non-allowlisted host"):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(("93.184.216.34", 80))  # example.com — must be blocked
