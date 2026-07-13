# SPDX-License-Identifier: Apache-2.0
"""Setup status and onboarding outcome endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.services.model_manager_service import get_active_config
from convsim_core import __version__

router = APIRouter()


class OnboardingOutcome(BaseModel):
    outcome: str
    recorded_at: str


class SetupStatusResponse(BaseModel):
    kind: str  # "never-run" | "ready" | "incomplete"
    missing: list[str] = []
    onboarding_outcome: Optional[OnboardingOutcome] = None
    pending_install_id: Optional[int] = None


class RecordOutcomeRequest(BaseModel):
    outcome: str  # "completed-with-model" | "demo" | "skipped"


@router.post("/api/setup/outcome", status_code=204)
async def record_outcome(body: RecordOutcomeRequest, request: Request) -> None:
    """Record the user's onboarding decision in the database."""
    conn = request.app.state.db.connection()
    conn.execute(
        "INSERT INTO onboarding_outcomes (outcome, app_version) VALUES (?, ?)",
        (body.outcome, __version__),
    )
    conn.commit()


@router.get("/api/setup/status", response_model=SetupStatusResponse)
async def get_setup_status(request: Request) -> SetupStatusResponse:
    """Return the current setup status derived from DB state.

    - never-run: no onboarding outcome has been recorded
    - ready: outcome recorded + engine/model/packs all present
    - incomplete: outcome recorded but something is missing
    """
    conn = request.app.state.db.connection()

    # Check for recorded outcome (most recent)
    outcome_row = conn.execute(
        "SELECT outcome, recorded_at FROM onboarding_outcomes ORDER BY id DESC LIMIT 1"
    ).fetchone()

    # Check for pending install (mid-install resume)
    pending_row = conn.execute(
        "SELECT id FROM installed_models WHERE install_status IN ('pending', 'downloading') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    pending_install_id: Optional[int] = pending_row["id"] if pending_row else None

    if outcome_row is None:
        # User has never finished or skipped onboarding
        return SetupStatusResponse(
            kind="never-run",
            pending_install_id=pending_install_id,
        )

    onboarding_outcome = OnboardingOutcome(
        outcome=outcome_row["outcome"],
        recorded_at=outcome_row["recorded_at"],
    )

    # Derive readiness from actual system state
    missing: list[str] = []

    active_cfg = get_active_config(conn)
    active_model_id: Optional[str] = active_cfg.get("model_id")

    # Check LLM presence
    installed_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM installed_models "
        "WHERE install_status IN ('ready', 'complete')"
    ).fetchone()
    installed_count = installed_row["cnt"] if installed_row else 0

    if installed_count == 0 and not active_model_id:
        missing.append("llm-present")

    # Check packs
    packs_row = conn.execute("SELECT COUNT(*) AS cnt FROM packs").fetchone()
    pack_count = packs_row["cnt"] if packs_row else 0
    if pack_count < 1:
        missing.append("packs-seeded")

    kind = "ready" if not missing else "incomplete"

    return SetupStatusResponse(
        kind=kind,
        missing=missing,
        onboarding_outcome=onboarding_outcome,
        pending_install_id=pending_install_id,
    )
