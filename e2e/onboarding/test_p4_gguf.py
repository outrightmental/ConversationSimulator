# SPDX-License-Identifier: Apache-2.0
"""P4 GGUF path: local fixture .gguf → registered → ready.

Journey:
  fresh profile → write a fixture .gguf file to disk → insert it into
  installed_models as ready → preflight shows llm-present pass → record
  outcome → status ready.

This simulates the GgufPathStep flow where the user supplies a local GGUF file
and it is registered without a download.
"""
from __future__ import annotations

from pathlib import Path

from .helpers import assert_no_forbidden_in_preflight


class TestP4GgufPath:
    """P4: user-supplied local GGUF file is registered and makes the profile ready."""

    def test_fresh_profile_is_never_run(self, fresh_profile):
        client, _ = fresh_profile
        assert client.get("/api/setup/status").json()["kind"] == "never-run"

    def test_llm_check_fails_before_gguf_registered(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        llm_check = next(c for c in checks if c["id"] == "llm-present")
        assert llm_check["status"] == "fail"

    def test_registered_gguf_satisfies_llm_present(self, fresh_profile, tmp_path):
        """An installed_models row for a local .gguf file makes llm-present pass."""
        client, app = fresh_profile

        gguf_path = tmp_path / "user-model.gguf"
        gguf_path.write_bytes(b"\x00" * 1024)

        conn = app.state.db.connection()
        conn.execute(
            "INSERT INTO installed_models "
            "(registry_id, filename, file_path, install_status) VALUES (?, ?, ?, ?)",
            (None, "user-model.gguf", str(gguf_path), "ready"),
        )
        conn.commit()

        checks = client.get("/api/preflight").json()["checks"]
        llm_check = next(c for c in checks if c["id"] == "llm-present")
        assert llm_check["status"] == "pass", (
            f"llm-present must pass after a GGUF is registered; "
            f"got {llm_check['status']!r}: {llm_check.get('message')!r}"
        )

    def test_status_ready_after_gguf_and_outcome(self, fresh_profile, tmp_path):
        client, app = fresh_profile

        gguf_path = tmp_path / "user-model.gguf"
        gguf_path.write_bytes(b"\x00" * 1024)

        conn = app.state.db.connection()
        conn.execute(
            "INSERT INTO installed_models "
            "(registry_id, filename, file_path, install_status) VALUES (?, ?, ?, ?)",
            (None, "user-model.gguf", str(gguf_path), "ready"),
        )
        conn.execute(
            "INSERT INTO packs (slug, name, version) VALUES (?, ?, ?)",
            ("starter.pack", "Starter", "1.0.0"),
        )
        conn.commit()

        client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})
        status = client.get("/api/setup/status").json()
        assert status["kind"] == "ready", (
            f"Expected 'ready' after GGUF + outcome + packs; got {status['kind']!r}. "
            f"Missing: {status.get('missing')}"
        )

    def test_no_forbidden_vocabulary_in_preflight(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)
