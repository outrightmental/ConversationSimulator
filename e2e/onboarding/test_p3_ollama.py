# SPDX-License-Identifier: Apache-2.0
"""P3 Ollama path: fixture Ollama endpoint → connect → model listed → selected → ready.

Journey:
  fresh profile → set active_model_id to an Ollama model (simulates "Connect"
  action after detecting a fixture Ollama endpoint) → preflight shows
  llm-present pass → record outcome → status ready.

The Ollama server itself is not started; we simulate the "connect" outcome by
setting the active_model_id in the runtime config, which is exactly what the
frontend does when the user selects an Ollama model in OllamaSelectStep.
"""
from __future__ import annotations

from .helpers import assert_no_forbidden_in_preflight

_OLLAMA_MODEL_ID = "ollama-llama3"


class TestP3OllamaPath:
    """P3: Ollama model path from wiped profile to ready state."""

    def test_fresh_profile_is_never_run(self, fresh_profile):
        client, _ = fresh_profile
        assert client.get("/api/setup/status").json()["kind"] == "never-run"

    def test_preflight_llm_check_fails_before_ollama_connected(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        llm_check = next((c for c in checks if c["id"] == "llm-present"), None)
        assert llm_check is not None, "llm-present check must be present in preflight"
        assert llm_check["status"] == "fail", (
            "llm-present must fail on a fresh profile with no model"
        )

    def test_ollama_active_model_satisfies_llm_present(self, fresh_profile):
        """Setting an active_model_id (as OllamaSelectStep does) makes llm-present pass."""
        client, app = fresh_profile
        conn = app.state.db.connection()

        from convsim_core.services.model_manager_service import set_active_config
        set_active_config(conn, runtime_id="ollama", model_id=_OLLAMA_MODEL_ID)

        checks = client.get("/api/preflight").json()["checks"]
        llm_check = next((c for c in checks if c["id"] == "llm-present"), None)
        assert llm_check is not None
        assert llm_check["status"] == "pass", (
            f"llm-present must pass when active_model_id is set to an Ollama model; "
            f"got {llm_check['status']!r} with message: {llm_check.get('message')!r}"
        )

    def test_status_ready_with_ollama_model_and_packs(self, fresh_profile):
        client, app = fresh_profile
        conn = app.state.db.connection()

        from convsim_core.services.model_manager_service import set_active_config
        set_active_config(conn, runtime_id="ollama", model_id=_OLLAMA_MODEL_ID)

        conn.execute(
            "INSERT INTO packs (slug, name, version) VALUES (?, ?, ?)",
            ("starter.pack", "Starter", "1.0.0"),
        )
        conn.commit()

        client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})
        status = client.get("/api/setup/status").json()
        assert status["kind"] == "ready", (
            f"Expected 'ready' with Ollama + packs; got {status['kind']!r}. "
            f"Missing: {status.get('missing')}"
        )

    def test_no_forbidden_vocabulary_in_preflight_messages(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)

    def test_ollama_fix_action_does_not_loop_to_welcome(self, fresh_profile):
        """llm-present fix_action when no model is present must not be the welcome step."""
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        llm_check = next((c for c in checks if c["id"] == "llm-present"), None)
        assert llm_check is not None

        fix = llm_check.get("fix_action")
        if fix is not None:
            assert fix.get("href") != "welcome", (
                "fix_action.href must not be 'welcome' — that recreates the v0.2.2 loop"
            )
            assert fix.get("href") != "/first-run", (
                "fix_action.href must not be '/first-run' — that reloads the Welcome screen"
            )
