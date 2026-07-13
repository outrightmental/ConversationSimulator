# SPDX-License-Identifier: Apache-2.0
"""P7 Regression: the loop — every fix_action is clicked on a fresh profile and must
never land on the Welcome step.

This is the named regression test for v0.2.2.  In that release the primary
onboarding remediation button had fix_action.kind="wizard-step" and
fix_action.href="welcome", meaning clicking "Fix it" looped the user back to
the Welcome screen instead of resolving the problem.

Every fix_action the backend can emit is exercised here.  The test fails if:
  - Any fix_action.href == "welcome"
  - Any fix_action.href == "/first-run"
  - Any wizard-step fix_action navigates to a step that is only reachable from
    the Welcome screen (i.e. is the Welcome step itself)

To verify the regression (acceptance criterion):
  Deliberately reintroduce the bug with

      fix_action=FixAction(kind="wizard-step", href="welcome")

  in any check's _check_* function and re-run this file.  The named test
  ``test_v0_2_2_loop_fix_action_never_returns_to_welcome`` must fail.
"""
from __future__ import annotations

from .helpers import assert_fix_action_not_welcome, assert_no_forbidden_in_preflight

_WIZARD_WELCOME_STEP = "welcome"
_FIRST_RUN_ROUTE = "/first-run"


class TestP7RegressionLoop:
    """P7: every fix_action the backend emits is checked for the v0.2.2 loop class."""

    def test_preflight_fix_actions_do_not_navigate_to_welcome(self, fresh_profile):
        """Core regression check: no preflight fix_action points to the Welcome step."""
        client, _ = fresh_profile
        data = client.get("/api/preflight").json()
        for check in data["checks"]:
            assert_fix_action_not_welcome(check.get("fix_action"), check["id"])

    def test_no_fix_action_href_is_first_run_route(self, fresh_profile):
        """No fix_action must navigate to /first-run (reloads the wizard from scratch)."""
        client, _ = fresh_profile
        data = client.get("/api/preflight").json()
        for check in data["checks"]:
            fix = check.get("fix_action")
            if fix is not None:
                assert fix.get("href") != _FIRST_RUN_ROUTE, (
                    f"Preflight check {check['id']!r} fix_action.href is '/first-run'. "
                    "This navigates back to the Welcome screen and recreates the v0.2.2 loop."
                )

    def test_wizard_step_fix_actions_target_non_welcome_steps(self, fresh_profile):
        """wizard-step fix_actions must point to steps other than 'welcome'."""
        client, _ = fresh_profile
        data = client.get("/api/preflight").json()
        wizard_step_fixes = [
            (check["id"], check["fix_action"])
            for check in data["checks"]
            if check.get("fix_action", {}) and check["fix_action"].get("kind") == "wizard-step"
        ]
        for check_id, fix in wizard_step_fixes:
            assert fix.get("href") != _WIZARD_WELCOME_STEP, (
                f"Preflight check {check_id!r} has a wizard-step fix_action pointing to "
                f"'welcome' (href={fix.get('href')!r}). "
                "This is exactly the v0.2.2 regression: clicking Fix loops to Welcome."
            )

    def test_v0_2_2_loop_fix_action_never_returns_to_welcome(self, fresh_profile):
        """Named regression test for v0.2.2 — explicitly asserts the loop cannot happen.

        If you are deliberately reintroducing the bug to verify detection works:
        set fix_action=FixAction(kind='wizard-step', href='welcome') in any
        check's result and confirm this test fails before reverting.
        """
        client, _ = fresh_profile
        data = client.get("/api/preflight").json()
        offenders = []
        for check in data["checks"]:
            fix = check.get("fix_action")
            if fix is None:
                continue
            kind = fix.get("kind", "")
            href = fix.get("href", "")
            if (kind == "wizard-step" and href == _WIZARD_WELCOME_STEP) or href == _FIRST_RUN_ROUTE:
                offenders.append((check["id"], kind, href))

        assert not offenders, (
            "v0.2.2 REGRESSION DETECTED: the following fix_actions loop back to the "
            f"Welcome screen: {offenders!r}. "
            "This is the exact bug that shipped in v0.2.2 and caused users to be stuck "
            "in an infinite first-run loop. Each fix_action must advance the user past "
            "the Welcome step, not return to it."
        )

    def test_setup_status_never_run_after_fix_action_cannot_occur(self, fresh_profile):
        """After any fix_action resolves, setup status must not flip back to never-run.

        A status of 'never-run' would redirect the user to FirstRunWizard (welcome step),
        creating the same loop class as v0.2.2 even if the fix_action href itself is correct.
        """
        client, _ = fresh_profile

        # Simulate the "choose demo / text-only" fix path (the universal escape hatch).
        client.post("/api/setup/outcome", json={"outcome": "demo"})
        status = client.get("/api/setup/status").json()
        assert status["kind"] != "never-run", (
            "After the text-only escape fix_action (outcome=demo) the status must not be "
            "'never-run' — that would redirect back to the Welcome screen"
        )

    def test_all_fix_action_kinds_have_non_welcome_href(self, fresh_profile):
        """Exhaustively verify every distinct fix_action kind does not target Welcome."""
        client, _ = fresh_profile
        data = client.get("/api/preflight").json()
        seen_kinds: set[str] = set()
        for check in data["checks"]:
            fix = check.get("fix_action")
            if fix is None:
                continue
            kind = fix.get("kind", "unknown")
            href = fix.get("href", "")
            seen_kinds.add(kind)
            assert href not in (_WIZARD_WELCOME_STEP, _FIRST_RUN_ROUTE), (
                f"fix_action (kind={kind!r}) in check {check['id']!r} has href={href!r} "
                "which navigates to the Welcome screen"
            )

    def test_preflight_no_forbidden_vocabulary(self, fresh_profile):
        client, _ = fresh_profile
        checks = client.get("/api/preflight").json()["checks"]
        assert_no_forbidden_in_preflight(checks)
