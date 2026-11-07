# SPDX-License-Identifier: Apache-2.0
"""This machine's recent turn speeds (issue #519).

Routes:
  GET /api/performance/rolling — medians over the recent recorded NPC turns for
                                 the active model and engine configuration

Everything here is read from the ``turn_timing`` events the turn pipeline
persists locally. No measurement leaves the machine; nothing is estimated.
The wait estimate (#539), the speed check (#535) and the per-reply details
(#549) read this instead of guessing.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from convsim_core.services.model_manager_service import get_active_config
from convsim_core.services.turn_timing import RollingSpeeds, rolling_speeds

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("/rolling", response_model=RollingSpeeds)
async def get_rolling_speeds(
    request: Request,
    runtime_id: Optional[str] = Query(default=None, max_length=64),
    model_id: Optional[str] = Query(default=None, max_length=256),
) -> RollingSpeeds:
    """Recent medians for one model and engine configuration.

    With no query parameters the active selection is used: the persisted
    runtime and model the player chose, falling back to the runtime the app is
    serving. Returns ``samples: 0`` and null figures when nothing matching has
    been recorded yet.
    """
    conn = request.app.state.db.connection()
    if runtime_id is None and model_id is None:
        active = get_active_config(conn)
        runtime_id = active.get("runtime_id") or getattr(request.app.state.runtime, "id", None)
        model_id = active.get("model_id")
    return rolling_speeds(conn, runtime_id=runtime_id, model_id=model_id)
