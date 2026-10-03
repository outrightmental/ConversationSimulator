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

Deferral is only acceptable if there is a way back in, so the second class here
covers the other half of the journey (issue #487): the remedy the warning offers
leads to the flow that installs voice, that flow can name every missing piece,
and merely asking it what is missing downloads nothing.
"""
from __future__ import annotations

import sys

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
    # Model-free sessions must pin their runtime explicitly (issue #473).
    "runtime_id": "scripted",
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


class TestP8VoiceOnboardingPath:
    """P8 (issue #487): the player who deferred voice must have a route back in."""

    def test_voice_warning_leads_to_the_install_flow(self, fresh_profile):
        """The remedy must open the screen that installs voice, not the one that reports it."""
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        voice_check = next(c for c in checks if c["id"] == "voice-ready")

        assert voice_check["fix_action"] is not None, (
            "A voice-ready warning with no fix_action is the dead end issue #487 "
            "was filed about."
        )
        assert voice_check["fix_action"]["href"] == "/voice-setup", (
            "The remedy must route to the guided flow. /settings only restates "
            f"that voice is missing (got {voice_check['fix_action']['href']!r})."
        )

    def test_plan_names_every_missing_piece(self, fresh_profile):
        """The flow must enumerate capabilities and give each gap a concrete next action."""
        client, _ = fresh_profile
        plan = client.get("/api/voice/setup/plan").json()

        assert {c["id"] for c in plan["capabilities"]} == {"stt", "tts", "vad"}
        stt = next(c for c in plan["capabilities"] if c["id"] == "stt")
        assert stt["ready"] is False, (
            "The fixture profile points CONVSIM_WHISPER_CPP_BINARY_PATH at a file "
            "that does not exist, so speech-to-text cannot be ready."
        )

        whisper = next(e for e in plan["engines"] if e["id"] == "whisper-cli")
        assert whisper["installed"] is False
        assert whisper["why_manual"], "An engine the app refuses to fetch must say why."
        if sys.platform.startswith(("darwin", "linux", "win32")):
            assert whisper["command"], (
                "Every platform the app ships on must get a one-line install command, "
                "otherwise the row is just another dead end."
            )

    def test_plan_discloses_every_download_before_it_starts(self, fresh_profile):
        """All six disclosure fields must be present without starting anything."""
        client, _ = fresh_profile
        plan = client.get("/api/voice/setup/plan").json()

        assert plan["default_asset_ids"], "The one-click path must name what it installs."
        for asset in plan["assets"]:
            assert len(asset["sha256"]) == 64, f"{asset['id']} has no usable checksum"
            assert asset["size_bytes"] > 0
            assert asset["source_url"].startswith("https://")
            assert asset["license"] and asset["license_url"]
            assert asset["install_path"], f"{asset['id']} does not say where it lands"

    def test_reading_the_plan_downloads_nothing(self, fresh_profile):
        """Opening the screen must not move a byte — the POST is the consent."""
        client, _ = fresh_profile
        plan = client.get("/api/voice/setup/plan").json()
        assert plan["active_job_id"] is None
        # No job row can exist either; the network guard in conftest would have
        # failed the test had anything reached for the weights.
        assert client.get("/api/voice/setup/install/1").status_code == 404

    def test_unknown_asset_is_refused_without_creating_a_job(self, fresh_profile):
        client, _ = fresh_profile
        resp = client.post("/api/voice/setup/install", json={"asset_ids": ["not-an-asset"]})
        assert resp.status_code == 404
        assert client.get("/api/voice/setup/install/1").status_code == 404
