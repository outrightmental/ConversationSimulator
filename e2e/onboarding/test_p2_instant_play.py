# SPDX-License-Identifier: Apache-2.0
"""P2 Instant play: "Try it right now" → scripted conversation < 15 s → debrief → upgrade CTA.

Journey:
  fresh profile → create first_words_tutorial session (scripted runtime, no
  model required) → 3 scripted turns → end session → debrief generated in
  < 15 s wall-clock → record demo outcome → status shows demo choice (upgrade
  CTA path).

The 15 s budget is the acceptance-criteria wall-clock assertion from issue #387.
"""
from __future__ import annotations

import time

from .helpers import assert_no_forbidden_in_preflight

_TUTORIAL_SCENARIO = "first_words_tutorial"
_SCRIPTED_TURNS = [
    "Hello, I'm ready to practice.",
    "I understand, please continue.",
    "That's helpful, thank you.",
]
_TIME_BUDGET_SECONDS = 15.0

_SESSION_SETUP = {
    "scenario_id": _TUTORIAL_SCENARIO,
    "difficulty": "standard",
    "player_role_name": "P2 Instant Play Tester",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": False,
}


class TestP2InstantPlay:
    """P2: scripted tutorial is reachable and completes well under 15 s."""

    def test_fresh_profile_is_never_run(self, fresh_profile):
        client, _ = fresh_profile
        assert client.get("/api/setup/status").json()["kind"] == "never-run"

    def test_tutorial_session_creates_successfully(self, fresh_profile):
        client, _ = fresh_profile
        resp = client.post("/api/sessions", json=_SESSION_SETUP)
        assert resp.status_code == 201, (
            f"Tutorial session creation failed (status {resp.status_code})"
        )
        assert resp.json().get("session_id", "").startswith("sess-")

    def test_tutorial_starts_and_delivers_npc_opening(self, fresh_profile):
        client, _ = fresh_profile
        session_id = client.post("/api/sessions", json=_SESSION_SETUP).json()["session_id"]
        start_resp = client.post(f"/api/sessions/{session_id}/start")
        assert start_resp.status_code == 200, (
            f"Tutorial session start failed (status {start_resp.status_code})"
        )
        state_resp = client.get(f"/api/sessions/{session_id}")
        assert state_resp.status_code == 200
        assert state_resp.json().get("state") == "PlayerTurnListening", (
            "After start the tutorial must be in PlayerTurnListening state"
        )

    def test_tutorial_completes_within_15s_wall_clock(self, fresh_profile):
        """Acceptance criterion: first-conversation budget ≤ 15 s in CI."""
        client, _ = fresh_profile

        t0 = time.monotonic()

        session_id = client.post("/api/sessions", json=_SESSION_SETUP).json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")

        for turn_text in _SCRIPTED_TURNS:
            resp = client.post(
                f"/api/sessions/{session_id}/turn", json={"content": turn_text}
            )
            assert resp.status_code == 200, (
                f"Turn failed (status {resp.status_code})"
            )

        client.post(f"/api/sessions/{session_id}/end")

        elapsed = time.monotonic() - t0
        assert elapsed < _TIME_BUDGET_SECONDS, (
            f"Tutorial took {elapsed:.1f}s, exceeds the {_TIME_BUDGET_SECONDS}s budget. "
            "The scripted tutorial must be fast enough for instant play."
        )

    def test_debrief_reachable_after_tutorial(self, fresh_profile):
        client, _ = fresh_profile
        session_id = client.post("/api/sessions", json=_SESSION_SETUP).json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        for turn_text in _SCRIPTED_TURNS:
            client.post(f"/api/sessions/{session_id}/turn", json={"content": turn_text})
        client.post(f"/api/sessions/{session_id}/end")

        debrief_resp = client.post(f"/api/sessions/{session_id}/debrief")
        assert debrief_resp.status_code == 200, (
            f"Debrief generation failed (status {debrief_resp.status_code})"
        )
        body = debrief_resp.json()
        assert body.get("session_id") == session_id
        assert "summary" in body

    def test_demo_outcome_enables_upgrade_cta(self, fresh_profile):
        """Recording demo outcome must not produce 'never-run' (that would hide the upgrade CTA)."""
        client, _ = fresh_profile

        session_id = client.post("/api/sessions", json=_SESSION_SETUP).json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        for turn_text in _SCRIPTED_TURNS:
            client.post(f"/api/sessions/{session_id}/turn", json={"content": turn_text})
        client.post(f"/api/sessions/{session_id}/end")

        rec_resp = client.post("/api/setup/outcome", json={"outcome": "demo"})
        assert rec_resp.status_code == 204

        status = client.get("/api/setup/status").json()
        assert status["kind"] != "never-run", (
            "After a demo session the status must not be 'never-run' — "
            "the upgrade CTA (finish setup prompt) would be invisible"
        )
        assert status.get("onboarding_outcome", {}).get("outcome") == "demo", (
            "Status must reflect the demo outcome for upgrade CTA routing"
        )

    def test_preflight_needs_human_no_forbidden_vocabulary(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)
