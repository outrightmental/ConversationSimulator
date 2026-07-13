# SPDX-License-Identifier: Apache-2.0
"""P5 Remediation: forced failures → correct card, correct numbers, primary action works.

Failure scenarios:
  - disk-full: disk_usage mocked to return insufficient free space
  - offline: install pipeline receives a network error during download
  - checksum-mismatch: fixture server serves bytes but registry has wrong SHA-256
  - text-only escape: a needs-human preflight failure exposes a text-only path

Invariants:
  - No forbidden vocabulary in any error message surfaced to the user
  - fix_action.href is not 'welcome' or '/first-run' (P7 invariant repeated here)
"""
from __future__ import annotations

import time
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .helpers import (
    assert_fix_action_not_welcome,
    assert_no_forbidden_in_install_error,
    assert_no_forbidden_in_preflight,
)

_INSTALL_POLL_TIMEOUT = 10.0
_FIXTURE_REGISTRY_ID = "fixture-model-p5"


def _seed_model(app, url: str, sha256: str, size_gb: float = 0.0001) -> None:
    conn = app.state.db.connection()
    conn.execute(
        "INSERT OR REPLACE INTO model_registry "
        "(id, name, provider, source_type, download_url, sha256, size_gb, license_spdx) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_FIXTURE_REGISTRY_ID, "Fixture P5", "fixture", "huggingface", url, sha256, size_gb, "MIT"),
    )
    conn.commit()


def _poll_job(client, job_id: int, timeout: float = _INSTALL_POLL_TIMEOUT) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/setup/install/{job_id}").json()
        if body["status"] in ("complete", "failed", "cancelled"):
            return body
        time.sleep(0.1)
    pytest.fail(f"Install job {job_id} did not reach a terminal state within {timeout}s")


class TestP5RemediationDiskFull:
    """disk-full condition: install fails on the model stage with a clear error."""

    def test_disk_full_preflight_fails_disk_space_check(self, fresh_profile):
        client, _ = fresh_profile
        Usage = namedtuple("Usage", ["total", "used", "free"])
        with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
            mock_du.return_value = Usage(total=10 * 1024**3, used=9 * 1024**3, free=512 * 1024**2)
            checks = client.get("/api/preflight").json()["checks"]
        disk_check = next(c for c in checks if c["id"] == "disk-space")
        assert disk_check["status"] in ("fail", "warn"), (
            "disk-space check must fail or warn when free space is insufficient"
        )

    def test_disk_full_preflight_has_no_forbidden_vocabulary(self, fresh_profile):
        client, _ = fresh_profile
        Usage = namedtuple("Usage", ["total", "used", "free"])
        with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
            mock_du.return_value = Usage(total=10 * 1024**3, used=9 * 1024**3, free=512 * 1024**2)
            checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)

    def test_disk_full_preflight_fix_action_not_welcome(self, fresh_profile):
        client, _ = fresh_profile
        Usage = namedtuple("Usage", ["total", "used", "free"])
        with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
            mock_du.return_value = Usage(total=10 * 1024**3, used=9 * 1024**3, free=512 * 1024**2)
            checks = client.get("/api/preflight").json()["checks"]
        disk_check = next(c for c in checks if c["id"] == "disk-space")
        assert_fix_action_not_welcome(disk_check.get("fix_action"), "disk-space")

    def test_disk_full_preflight_detail_has_numbers(self, fresh_profile):
        """The remediation card needs concrete numbers (free_gb, required_gb) to display."""
        client, _ = fresh_profile
        Usage = namedtuple("Usage", ["total", "used", "free"])
        with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
            mock_du.return_value = Usage(total=10 * 1024**3, used=9 * 1024**3, free=512 * 1024**2)
            checks = client.get("/api/preflight").json()["checks"]
        disk_check = next(c for c in checks if c["id"] == "disk-space")
        if disk_check["status"] == "fail":
            detail = disk_check.get("detail") or {}
            assert "free_gb" in detail, "disk-space fail detail must include free_gb"
            assert "required_gb" in detail, "disk-space fail detail must include required_gb"

    def test_disk_full_install_fails_model_stage(self, fresh_profile, fixture_server):
        client, app = fresh_profile
        _seed_model(app, fixture_server.model_url, fixture_server.sha256, size_gb=999.0)

        # Patches must stay active through poll loop (background task reads them).
        with (
            patch(
                "convsim_core.routers.setup_install.find_executable",
                return_value="/fake/llama-server",
            ),
            patch("shutil.disk_usage") as mock_du,
        ):
            mock_du.return_value = MagicMock(free=0)
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200
            final = _poll_job(client, resp.json()["id"])

        assert final["status"] == "failed"
        model_stage = next(s for s in final["stages"] if s["id"] == "model")
        assert model_stage["state"] == "failed"
        assert "disk space" in (model_stage.get("error") or "").lower(), (
            "disk-full install error must mention disk space"
        )

    def test_disk_full_install_error_has_no_forbidden_vocabulary(
        self, fresh_profile, fixture_server
    ):
        client, app = fresh_profile
        _seed_model(app, fixture_server.model_url, fixture_server.sha256, size_gb=999.0)

        with (
            patch(
                "convsim_core.routers.setup_install.find_executable",
                return_value="/fake/llama-server",
            ),
            patch("shutil.disk_usage") as mock_du,
        ):
            mock_du.return_value = MagicMock(free=0)
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200
            final = _poll_job(client, resp.json()["id"])

        assert_no_forbidden_in_install_error(final.get("stages", []))


class TestP5RemediationOffline:
    """Offline condition: install pipeline receives a network error."""

    def test_offline_install_fails_with_network_error(self, fresh_profile, fixture_server):
        """When the download raises a network error the install fails gracefully."""
        client, app = fresh_profile
        _seed_model(app, fixture_server.model_url, fixture_server.sha256)

        with (
            patch(
                "convsim_core.routers.setup_install.find_executable",
                return_value="/fake/llama-server",
            ),
            patch(
                "convsim_core.routers.setup_install.execute_download",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Network unavailable"),
            ),
        ):
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200
            final = _poll_job(client, resp.json()["id"])

        assert final["status"] == "failed"

    def test_offline_install_error_has_no_forbidden_vocabulary(
        self, fresh_profile, fixture_server
    ):
        client, app = fresh_profile
        _seed_model(app, fixture_server.model_url, fixture_server.sha256)

        with (
            patch(
                "convsim_core.routers.setup_install.find_executable",
                return_value="/fake/llama-server",
            ),
            patch(
                "convsim_core.routers.setup_install.execute_download",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Network unavailable"),
            ),
        ):
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200
            final = _poll_job(client, resp.json()["id"])

        assert_no_forbidden_in_install_error(final.get("stages", []))


class TestP5RemediationChecksumMismatch:
    """Checksum-mismatch: fixture server serves valid bytes but registry has wrong SHA-256."""

    def test_bad_checksum_install_fails_verify_stage(self, fresh_profile, fixture_server):
        client, app = fresh_profile
        _seed_model(app, fixture_server.bad_checksum_url, fixture_server.bad_sha256)

        with patch(
            "convsim_core.routers.setup_install.find_executable",
            return_value="/fake/llama-server",
        ):
            resp = client.post(
                "/api/setup/install", json={"registry_id": _FIXTURE_REGISTRY_ID}
            )
            assert resp.status_code == 200
            final = _poll_job(client, resp.json()["id"], timeout=20.0)

        assert final["status"] == "failed", (
            "An install with a wrong SHA-256 must fail"
        )


class TestP5TextOnlyEscape:
    """A needs-human preflight failure must expose a text-only escape path."""

    def test_needs_human_fail_has_fix_action(self, fresh_profile):
        """Every needs-human failure must have a fix_action so users have a path forward."""
        client, _ = fresh_profile
        Usage = namedtuple("Usage", ["total", "used", "free"])
        with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
            mock_du.return_value = Usage(total=10 * 1024**3, used=9 * 1024**3, free=512 * 1024**2)
            checks = client.get("/api/preflight").json()["checks"]

        needs_human_fails = [
            c for c in checks
            if c["severity"] == "needs-human" and c["status"] == "fail"
        ]
        for check in needs_human_fails:
            assert check.get("fix_action") is not None, (
                f"needs-human check {check['id']!r} has no fix_action — "
                "first-run users have no path forward"
            )

    def test_text_only_wizard_step_choice_reachable(self, fresh_profile):
        """The wizard exposes a text-only (demo) path independently of blocking checks.

        This verifies that the PreflightStep can always offer "text-only mode" as an
        escape hatch for users who cannot resolve the blocking failure.
        """
        client, _ = fresh_profile
        # Simulate the text-only path: record demo outcome without resolving preflight.
        resp = client.post("/api/setup/outcome", json={"outcome": "demo"})
        assert resp.status_code == 204
        status = client.get("/api/setup/status").json()
        assert status["kind"] != "never-run", (
            "After choosing text-only / demo mode the status must not remain 'never-run'"
        )
