# SPDX-License-Identifier: Apache-2.0
"""Preflight self-test pipeline.

Runs all readiness checks concurrently and returns structured results with
per-check remediation actions. Completes in < 5 s. Designed to run both on
first launch (via FirstRunWizard) and on demand from the Support screen.
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


# ── Response schemas ──────────────────────────────────────────────────────────


class FixAction(BaseModel):
    """A single actionable remedy for a failing or warning check."""

    kind: str   # "navigate" | "open-url" | "wizard-step" | "install-engine"
    href: str
    label: str


class CheckResult(BaseModel):
    id: str
    name: str
    status: str         # "pass" | "warn" | "fail"
    message: str
    fix_action: Optional[FixAction] = None


class PreflightResponse(BaseModel):
    overall: str        # "pass" | "warn" | "fail"
    checks: list[CheckResult]
    ran_at: str         # ISO 8601


# ── Individual checks ─────────────────────────────────────────────────────────


def _check_runtime_handshake() -> CheckResult:
    """Check 1: Core service is reachable and reports its version."""
    return CheckResult(
        id="runtime-handshake",
        name="Runtime handshake",
        status="pass",
        message=f"convsim-core {__version__} is running.",
    )


def _check_data_dir(data_dir: str) -> CheckResult:
    """Check 2: Data directory exists and is writable."""
    path = Path(data_dir)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult(
            id="data-dir-writable",
            name="Data directory",
            status="pass",
            message=f"Data directory is writable at {data_dir}.",
        )
    except OSError as exc:
        return CheckResult(
            id="data-dir-writable",
            name="Data directory",
            status="fail",
            message=f"Cannot write to data directory: {exc}",
            fix_action=FixAction(kind="navigate", href="/settings", label="Open Settings"),
        )


def _check_disk_space(models_dir: str, required_gb: float) -> CheckResult:
    """Check 3: Sufficient free disk space for the active or starter model."""
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
            message=f"{free_gb:.1f} GB free — {required_gb:.1f} GB required.",
        )
    if free_gb >= required_gb:
        return CheckResult(
            id="disk-space",
            name="Disk space",
            status="warn",
            message=(
                f"Disk space is tight: {free_gb:.1f} GB free, "
                f"{needed_gb:.1f} GB recommended for the selected model."
            ),
        )
    return CheckResult(
        id="disk-space",
        name="Disk space",
        status="fail",
        message=(
            f"Insufficient disk space: {free_gb:.1f} GB free, "
            f"{required_gb:.1f} GB required for the selected model."
        ),
        fix_action=FixAction(kind="navigate", href="/settings", label="Open Settings"),
    )


def _check_llama_cpp_binary() -> CheckResult:
    """Check 4: llama-server binary is present and executable."""
    binary = find_executable()
    if binary is not None:
        return CheckResult(
            id="llama-cpp-binary",
            name="Inference engine",
            status="pass",
            message=f"llama-server found at {binary}.",
        )
    return CheckResult(
        id="llama-cpp-binary",
        name="Inference engine",
        status="fail",
        message=(
            "llama-server binary not found. "
            "The inference engine is missing from this installation."
        ),
        fix_action=FixAction(
            kind="install-engine",
            href="/settings/install-engine",
            label="Install engine",
        ),
    )


def _check_llm_present(conn, active_model_id: Optional[str]) -> CheckResult:
    """Check 5: At least one LLM model file is installed and ready."""
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM installed_models "
        "WHERE install_status IN ('ready', 'complete')"
    ).fetchone()
    count = row["cnt"] if row else 0

    if count > 0:
        return CheckResult(
            id="llm-present",
            name="Language model",
            status="pass",
            message=f"{count} model{'s' if count != 1 else ''} installed and ready.",
        )

    # An active_model_id without an install record means Ollama or a user-supplied path.
    if active_model_id:
        return CheckResult(
            id="llm-present",
            name="Language model",
            status="pass",
            message=f"Active model configured: {active_model_id}.",
        )

    return CheckResult(
        id="llm-present",
        name="Language model",
        status="fail",
        message=(
            "No language model installed. "
            "Install a starter model to enable AI responses."
        ),
        fix_action=FixAction(
            kind="wizard-step",
            href="choose",
            label="Open Model Manager",
        ),
    )


def _check_packs_seeded(conn) -> CheckResult:
    """Check 6: At least four scenario packs are present."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM packs").fetchone()
    count = row["cnt"] if row else 0

    if count >= _MIN_PACKS:
        return CheckResult(
            id="packs-seeded",
            name="Scenario packs",
            status="pass",
            message=f"{count} scenario pack{'s' if count != 1 else ''} available.",
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
            fix_action=FixAction(kind="navigate", href="/library", label="Browse Scenarios"),
        )
    return CheckResult(
        id="packs-seeded",
        name="Scenario packs",
        status="fail",
        message="No scenario packs found. The app needs at least one pack to play.",
        fix_action=FixAction(kind="navigate", href="/library", label="Browse Scenarios"),
    )


async def _check_voice_ready(stt_worker, tts_worker, vad_worker) -> CheckResult:
    """Check 7: Optional voice feature readiness — warns, never fails."""

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
        )
    return CheckResult(
        id="voice-ready",
        name="Voice features",
        status="warn",
        message=(
            f"Some voice features are unavailable: {'; '.join(issues)}. "
            "Text-only mode is always available."
        ),
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
