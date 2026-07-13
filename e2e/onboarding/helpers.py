# SPDX-License-Identifier: Apache-2.0
"""Shared assertion helpers for the onboarding e2e suite (issue #387).

These invariants are enforced in every path (P1–P8):

  1. Forbidden vocabulary — internal technical terms must not appear in any
     message a first-run user can read.
  2. Network allowlist — no request during onboarding escapes to an external
     host; only localhost and the fixture server are permitted.

Import and call both from the shared assertion block at the end of each
journey test so a future path automatically inherits them.
"""
from __future__ import annotations

# Words that must never appear in any user-visible onboarding message.
# These are internal implementation details that are confusing or alarming
# when surfaced in the first-run UI.
#
# "GGUF" is allowed only inside the Advanced disclosure section; the
# check here is at the API message level so it applies to preflight check
# messages and install error text, not to UI labels we do not control.
_FORBIDDEN: frozenset[str] = frozenset({
    "binary",
    "sidecar",
    "llama",
    "preflight",
    "checksum",
    "llama-server",
})

# Hosts that onboarding requests are permitted to reach.  Any URL not
# starting with one of these prefixes is a privacy/security violation.
_ALLOWED_PREFIXES: tuple[str, ...] = (
    "http://127.0.0.1",
    "http://localhost",
    "http://[::1]",
)


def assert_no_forbidden_vocabulary(text: str, context: str = "") -> None:
    """Assert that a user-visible string contains no forbidden vocabulary."""
    lower = text.lower()
    found = {word for word in _FORBIDDEN if word in lower}
    if found:
        where = f" in {context}" if context else ""
        raise AssertionError(
            f"Forbidden vocabulary found{where}: {found!r}. "
            "These internal terms must not appear in first-run user messages. "
            f"Offending text: {text!r}"
        )


def assert_no_forbidden_in_preflight(checks: list[dict]) -> None:
    """Assert no needs-human preflight failure message contains forbidden words."""
    for check in checks:
        if check.get("severity") == "needs-human" and check.get("status") == "fail":
            assert_no_forbidden_vocabulary(
                check.get("message", ""),
                context=f"preflight check {check.get('id')!r} fail message",
            )


def assert_no_forbidden_in_install_error(stages: list[dict]) -> None:
    """Assert no failed install-pipeline stage error contains forbidden words."""
    for stage in stages:
        if stage.get("state") == "failed" and stage.get("error"):
            assert_no_forbidden_vocabulary(
                stage["error"],
                context=f"install stage {stage.get('id')!r} error",
            )


def assert_url_is_allowlisted(url: str) -> None:
    """Assert that a URL is on the network allowlist (localhost only)."""
    if not any(url.startswith(p) for p in _ALLOWED_PREFIXES):
        raise AssertionError(
            f"Network request to non-allowlisted host: {url!r}. "
            "Onboarding flows must only contact localhost. "
            "This enforces the offline-safe and privacy guarantees."
        )


def is_allowlisted_host(host: str) -> bool:
    """True if ``host`` is loopback — the only network onboarding may contact.

    Used by the autouse ``network_allowlist_guard`` fixture to enforce the
    privacy promise mechanically: any socket connection to a non-loopback host
    during onboarding fails the test.
    """
    import ipaddress

    if host in ("localhost", ""):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Any hostname that is not a bare IP is off the allowlist — onboarding
        # must never resolve an external name.
        return False
    if ip.is_loopback:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(mapped and mapped.is_loopback)


def assert_fix_action_not_welcome(fix_action: dict | None, check_id: str) -> None:
    """P7 invariant: a fix_action must never navigate back to the Welcome step.

    This is the v0.2.2 regression class: a fix_action with kind='wizard-step'
    and href='welcome' caused an infinite redirect loop for first-run users.
    """
    if fix_action is None:
        return
    kind = fix_action.get("kind", "")
    href = fix_action.get("href", "")
    assert not (kind == "wizard-step" and href == "welcome"), (
        f"Preflight check {check_id!r} has a fix_action that navigates to the "
        f"'welcome' wizard step (kind={kind!r}, href={href!r}). "
        "This recreates the v0.2.2 loop bug where clicking the fix action "
        "brought the user back to the Welcome screen instead of resolving the issue."
    )
    assert href != "/first-run", (
        f"Preflight check {check_id!r} fix_action.href is '/first-run' "
        f"(kind={kind!r}). This would reload the Welcome screen."
    )
