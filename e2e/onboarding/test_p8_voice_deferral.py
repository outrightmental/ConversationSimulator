# SPDX-License-Identifier: Apache-2.0
"""P8 Voice deferral: no voice errors in first-run; invite after first real debrief.

Journey:
  fresh profile → voice-ready check is informational (not needs-human) → first-run
  flow completes without voice blocking → after a real debrief the voice invite
  state is available → "Maybe later" path persists (invite is not re-shown after
  deferral).

The voice invite persistence lives in the frontend (localStorage), but the API
invariants we can assert here are:
  - voice-ready severity is "informational" (never "needs-human"), so it cannot
    block the first-run wizard
  - voice-ready never has status "fail" with needs-human severity
  - Preflight runs without raising on missing voice infrastructure
  - A real debrief completes (the hook point for showing the invite)
"""
from __future__ import annotations

from .helpers import assert_no_forbidden_in_preflight

_TUTORIAL_SCENARIO = "first_words_tutorial"

_SESSION_SETUP = {
    "scenario_id": _TUTORIAL_SCENARIO,
    "difficulty": "standard",
    "player_role_name": "P8 Voice Tester",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": False,
}


class TestP8VoiceDeferral:
    """P8: voice infrastructure issues are informational, never block first-run."""

    def test_voice_ready_check_is_present(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        check_ids = {c["id"] for c in checks}
        assert "voice-ready" in check_ids, (
            "voice-ready check must be present in preflight for P8 coverage"
        )

    def test_voice_ready_severity_is_informational(self, fresh_profile):
        """voice-ready must be informational — it must never block the first-run wizard."""
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        voice_check = next(c for c in checks if c["id"] == "voice-ready")
        assert voice_check["severity"] == "informational", (
            f"voice-ready severity must be 'informational', not {voice_check['severity']!r}. "
            "A needs-human severity would block the first-run wizard for users without "
            "voice hardware, which is the majority of desktop users."
        )

    def test_voice_ready_is_not_needs_human_fail(self, fresh_profile):
        """voice-ready must never be both status=fail and severity=needs-human."""
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        voice_check = next(c for c in checks if c["id"] == "voice-ready")
        is_blocking_fail = (
            voice_check["status"] == "fail"
            and voice_check["severity"] == "needs-human"
        )
        assert not is_blocking_fail, (
            "voice-ready check must not be a needs-human failure. "
            "Voice unavailability is expected on most machines and must not "
            "block the user from completing first-run setup."
        )

    def test_first_run_completes_without_voice(self, fresh_profile):
        """A first-run flow succeeds even when voice infrastructure is absent."""
        client, _ = fresh_profile

        resp = client.post("/api/sessions", json=_SESSION_SETUP)
        assert resp.status_code == 201, (
            f"Tutorial session creation failed in voice-absent environment "
            f"(status {resp.status_code})"
        )
        session_id = resp.json()["session_id"]

        start_resp = client.post(f"/api/sessions/{session_id}/start")
        assert start_resp.status_code == 200

        turn_resp = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Hello, I'm practicing."},
        )
        assert turn_resp.status_code == 200, (
            "First turn must succeed in text-only mode without voice"
        )

    def test_debrief_reachable_after_first_real_conversation(self, fresh_profile):
        """The debrief endpoint — the hook point for the voice invite — must succeed."""
        client, _ = fresh_profile

        session_id = client.post("/api/sessions", json=_SESSION_SETUP).json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        client.post(f"/api/sessions/{session_id}/turn", json={"content": "Practice turn."})
        client.post(f"/api/sessions/{session_id}/end")

        debrief_resp = client.post(f"/api/sessions/{session_id}/debrief")
        assert debrief_resp.status_code == 200, (
            f"Debrief (the voice-invite trigger point) failed (status {debrief_resp.status_code})"
        )

    def test_voice_check_autofix_is_false(self, fresh_profile):
        """voice-ready must have autofix=False — voice cannot be silently installed."""
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        voice_check = next(c for c in checks if c["id"] == "voice-ready")
        assert voice_check["autofix"] is False, (
            "voice-ready autofix must be False — voice hardware cannot be auto-installed"
        )

    def test_preflight_no_forbidden_vocabulary(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)
