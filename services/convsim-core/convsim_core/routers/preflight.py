# SPDX-License-Identifier: Apache-2.0
"""Preflight self-test pipeline.

Runs all readiness checks concurrently and returns structured results with
per-check remediation actions. Completes in < 5 s. Designed to run both on
first launch (via FirstRunWizard) and on demand from the Support screen.

Check severity classes
----------------------
auto-fixable   — the app resolves this silently as a stage in the setup
                 pipeline; never rendered as an error during onboarding.
needs-human    — requires a user decision (disk space, permissions, offline);
                 shown as a remediation card and always offers a text-only
                 escape hatch.
informational  — voice readiness, non-default paths; never shown during
                 first-run, visible in Settings → System health only.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core import __version__
from convsim_core.runtime.sidecar import find_executable
from convsim_core.services.model_manager_service import get_active_config

logger = logging.getLogger(__name__)
router = APIRouter()

_MIN_FREE_GB_BUFFER = 1.1   # 10 % headroom above model size
_MIN_PACKS = 4

# Exhaustive triage map — every check id must appear here exactly once.
# Enforced by test_preflight_triage_is_exhaustive.
CHECK_TRIAGE: dict[str, tuple[str, bool]] = {
    #             id                  severity          autofix
    "runtime-handshake":    ("informational",  False),
    "data-dir-writable":    ("needs-human",    False),
    "disk-space":           ("needs-human",    False),
    "llama-cpp-binary":     ("auto-fixable",   True),
    "llm-present":          ("auto-fixable",   True),
    "packs-seeded":         ("auto-fixable",   True),
    "voice-ready":          ("informational",  False),
}


# ── Response schemas ──────────────────────────────────────────────────────────


class FixAction(BaseModel):
    """A single actionable remedy for a failing or warning check."""

    kind: str   # "navigate" | "open-url" | "wizard-step" | "install-engine"
    href: str
    label: str


class CheckResult(BaseModel):
    id: str
    name: str
    status: str             # "pass" | "warn" | "fail"
    message: str
    severity: str           # "auto-fixable" | "needs-human" | "informational"
    autofix: bool           # True if the setup pipeline can resolve this silently
    fix_action: Optional[FixAction] = None
    detail: Optional[dict] = None   # check-specific structured data (e.g. {free_gb, required_gb})


class PreflightResponse(BaseModel):
    overall: str        # "pass" | "warn" | "fail"
    checks: list[CheckResult]
    ran_at: str         # ISO 8601


# ── Individual checks ─────────────────────────────────────────────────────────


def _check_runtime_handshake() -> CheckResult:
    """Check 1: Core service is reachable and reports its version."""
    severity, autofix = CHECK_TRIAGE["runtime-handshake"]
    return CheckResult(
        id="runtime-handshake",
        name="Runtime handshake",
        status="pass",
        message=f"convsim-core {__version__} is running.",
        severity=severity,
        autofix=autofix,
    )


def _check_data_dir(data_dir: str) -> CheckResult:
    """Check 2: Data directory exists and is writable."""
    severity, autofix = CHECK_TRIAGE["data-dir-writable"]
    path = Path(data_dir)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult(
            id="data-dir-writable",
            name="Data folder",
            status="pass",
            message="The data folder is writable.",
            severity=severity,
            autofix=autofix,
        )
    except OSError as exc:
        return CheckResult(
            id="data-dir-writable",
            name="Data folder",
            status="fail",
            message="The app can't write to its data folder. You may need to check your disk permissions.",
            severity=severity,
            autofix=autofix,
            fix_action=FixAction(kind="navigate", href="/settings", label="Open Settings"),
            detail={"path": data_dir, "error": str(exc)},
        )


def _check_disk_space(models_dir: str, required_gb: float) -> CheckResult:
    """Check 3: Sufficient free disk space for the active or starter model."""
    severity, autofix = CHECK_TRIAGE["disk-space"]
    try:
        usage = shutil.disk_usage(models_dir)
    except OSError:
        parent = Path(models_dir).parent
        try:
            usage = shutil.disk_usage(str(parent))
        except OSError:
            usage = shutil.disk_usage(str(Path.home()))

    free_gb = usage.free / (1024 ** 3)
    needed_gb = required_gb * _MIN_FREE_GB_BUFFER

    if free_gb >= needed_gb:
        return CheckResult(
            id="disk-space",
            name="Disk space",
            status="pass",
            message=f"{free_gb:.1f} GB free — {required_gb:.1f} GB needed.",
            severity=severity,
            autofix=autofix,
            detail={"free_gb": round(free_gb, 2), "required_gb": round(required_gb, 2)},
        )
    if free_gb >= required_gb:
        return CheckResult(
            id="disk-space",
            name="Disk space",
            status="warn",
            message=(
                f"Space is tight: {free_gb:.1f} GB free, "
                f"{needed_gb:.1f} GB recommended for the AI model."
            ),
            severity=severity,
            autofix=autofix,
            detail={"free_gb": round(free_gb, 2), "required_gb": round(required_gb, 2)},
        )
    return CheckResult(
        id="disk-space",
        name="Not enough disk space",
        status="fail",
        message=(
            f"The AI model needs {required_gb:.1f} GB "
            f"and this disk has {free_gb:.1f} GB free."
        ),
        severity=severity,
        autofix=autofix,
        fix_action=FixAction(kind="navigate", href="/settings", label="Choose another location"),
        detail={"free_gb": round(free_gb, 2), "required_gb": round(required_gb, 2)},
    )


def _check_llama_cpp_binary() -> CheckResult:
    """Check 4: AI engine executable is present. Auto-fixable by the setup pipeline."""
    severity, autofix = CHECK_TRIAGE["llama-cpp-binary"]
    binary = find_executable()
    if binary is not None:
        return CheckResult(
            id="llama-cpp-binary",
            name="AI engine",
            status="pass",
            message="The AI engine is ready.",
            severity=severity,
            autofix=autofix,
        )
    return CheckResult(
        id="llama-cpp-binary",
        name="AI engine",
        status="fail",
        message="The AI engine is not installed. It will be set up automatically.",
        severity=severity,
        autofix=autofix,
        fix_action=FixAction(
            kind="install-engine",
            href="/settings/install-engine",
            label="Install engine",
        ),
    )


def _check_llm_present(conn, active_model_id: Optional[str]) -> CheckResult:
    """Check 5: At least one AI model is installed. Auto-fixable by the setup pipeline."""
    severity, autofix = CHECK_TRIAGE["llm-present"]
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM installed_models "
        "WHERE install_status IN ('ready', 'complete')"
    ).fetchone()
    count = row["cnt"] if row else 0

    if count > 0:
        return CheckResult(
            id="llm-present",
            name="AI model",
            status="pass",
            message=f"{count} AI model{'s' if count != 1 else ''} installed and ready.",
            severity=severity,
            autofix=autofix,
        )

    # An active_model_id without an install record means Ollama or a user-supplied path.
    if active_model_id:
        return CheckResult(
            id="llm-present",
            name="AI model",
            status="pass",
            message="Active AI model configured.",
            severity=severity,
            autofix=autofix,
        )

    return CheckResult(
        id="llm-present",
        name="AI model",
        status="fail",
        message="No AI model is installed. It will be downloaded automatically during setup.",
        severity=severity,
        autofix=autofix,
        fix_action=FixAction(
            kind="wizard-step",
            href="choose",
            label="Open Model Manager",
        ),
    )


def _check_packs_seeded(conn) -> CheckResult:
    """Check 6: At least four scenario packs are present. Auto-fixable by the setup pipeline."""
    severity, autofix = CHECK_TRIAGE["packs-seeded"]
    row = conn.execute("SELECT COUNT(*) AS cnt FROM packs").fetchone()
    count = row["cnt"] if row else 0

    if count >= _MIN_PACKS:
        return CheckResult(
            id="packs-seeded",
            name="Scenario packs",
            status="pass",
            message=f"{count} scenario pack{'s' if count != 1 else ''} available.",
            severity=severity,
            autofix=autofix,
        )
    if count > 0:
        return CheckResult(
            id="packs-seeded",
            name="Scenario packs",
            status="warn",
            message=(
                f"Only {count} scenario pack{'s' if count != 1 else ''} found "
                f"({_MIN_PACKS}+ recommended)."
            ),
            severity=severity,
            autofix=autofix,
            fix_action=FixAction(kind="navigate", href="/library", label="Browse Scenarios"),
        )
    return CheckResult(
        id="packs-seeded",
        name="Scenario packs",
        status="fail",
        message="No scenario packs are installed. They will be added automatically during setup.",
        severity=severity,
        autofix=autofix,
        fix_action=FixAction(kind="navigate", href="/library", label="Browse Scenarios"),
    )


async def _check_voice_ready(stt_worker, tts_worker, vad_worker) -> CheckResult:
    """Check 7: Optional voice feature readiness — informational, never blocks onboarding."""
    severity, autofix = CHECK_TRIAGE["voice-ready"]

    async def _safe(worker):
        try:
            return await asyncio.wait_for(worker.health(), timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            return exc

    stt_h, tts_h, vad_h = await asyncio.gather(
        _safe(stt_worker),
        _safe(tts_worker),
        _safe(vad_worker),
    )

    ready: list[str] = []
    issues: list[str] = []
    for label, health in [("STT", stt_h), ("TTS", tts_h), ("VAD", vad_h)]:
        if isinstance(health, Exception):
            issues.append(f"{label}: error")
        elif getattr(health, "status", None) == "ready":
            ready.append(label)
        elif getattr(health, "status", None) == "unavailable":
            issues.append(f"{label}: not installed")
        elif health is not None:
            issues.append(f"{label}: {getattr(health, 'status', 'unknown')}")

    if not issues:
        return CheckResult(
            id="voice-ready",
            name="Voice features",
            status="pass",
            message=f"Voice features ready: {', '.join(ready)}.",
            severity=severity,
            autofix=autofix,
        )
    return CheckResult(
        id="voice-ready",
        name="Voice features",
        status="warn",
        message=(
            f"Some voice features are unavailable: {'; '.join(issues)}. "
            "Text-only mode is always available."
        ),
        severity=severity,
        autofix=autofix,
        fix_action=FixAction(kind="navigate", href="/settings", label="Voice Settings"),
    )


def _required_model_gb(conn, active_model_id: Optional[str]) -> float:
    """Return the size_gb needed for the active model, or the starter model default."""
    if active_model_id:
        row = conn.execute(
            "SELECT size_gb FROM model_registry WHERE id = ?", (active_model_id,)
        ).fetchone()
        if row and row["size_gb"]:
            return float(row["size_gb"])

    row = conn.execute(
        "SELECT size_gb FROM model_registry WHERE role = 'starter' LIMIT 1"
    ).fetchone()
    if row and row["size_gb"]:
        return float(row["size_gb"])

    return 5.0  # Conservative default if registry is empty


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.get("/api/preflight", response_model=PreflightResponse)
async def run_preflight(request: Request) -> PreflightResponse:
    """Run all readiness checks and return structured results with fix actions.

    Completes in < 5 s. Results are cached on app state so the crash-bundle
    endpoint can include them automatically without a second round-trip.
    """
    config = request.app.state.service_config
    db = request.app.state.db
    conn = db.connection()

    active_cfg = get_active_config(conn)
    active_model_id: Optional[str] = active_cfg.get("model_id")
    required_gb = _required_model_gb(conn, active_model_id)

    # Synchronous checks (fast I/O or DB) + async voice check in parallel
    voice_check, *_ = await asyncio.gather(
        _check_voice_ready(
            request.app.state.stt_worker,
            request.app.state.tts_worker,
            request.app.state.vad_worker,
        ),
    )

    checks: list[CheckResult] = [
        _check_runtime_handshake(),
        _check_data_dir(config.data_dir),
        _check_disk_space(config.models_dir, required_gb),
        _check_llama_cpp_binary(),
        _check_llm_present(conn, active_model_id),
        _check_packs_seeded(conn),
        voice_check,
    ]

    if any(c.status == "fail" for c in checks):
        overall = "fail"
    elif any(c.status == "warn" for c in checks):
        overall = "warn"
    else:
        overall = "pass"

    result = PreflightResponse(
        overall=overall,
        checks=checks,
        ran_at=datetime.now(timezone.utc).isoformat(),
    )

    # Cache for crash-bundle inclusion (see routers/diag.py)
    request.app.state.last_preflight = result.model_dump(mode="json")

    logger.info("Preflight completed: overall=%s", overall)
    return result
