# SPDX-License-Identifier: Apache-2.0
"""Scenario library endpoints: list with filters/FTS, and full scenario detail."""
from typing import Annotated, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from convsim_core.errors import ConvsimError
from convsim_core.packs.models import ScenarioCard, ScenarioDetail
from convsim_core.storage.repositories.scenario_repo import get_scenario_by_id, list_scenarios

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioCard])
async def get_scenarios(
    request: Request,
    q: Annotated[Optional[str], Query(description="Full-text search over title, summary, tags, and pack README")] = None,
    pack: Annotated[Optional[str], Query(description="Filter by pack slug")] = None,
    tag: Annotated[Optional[str], Query(description="Filter by tag")] = None,
    language: Annotated[Optional[str], Query(description="Filter by supported language code")] = None,
    content_rating: Annotated[Optional[str], Query(description="Filter by content rating (G, PG, PG-13)")] = None,
    difficulty: Annotated[Optional[str], Query(description="Filter by default difficulty (warm, standard, hard, adversarial)")] = None,
    voice_support: Annotated[Optional[bool], Query(description="Filter to scenarios with voice support")] = None,
) -> list[ScenarioCard]:
    """List installed scenarios with optional filters and full-text search."""
    conn = request.app.state.db.connection()
    return list_scenarios(
        conn,
        q=q,
        pack=pack,
        tag=tag,
        language=language,
        content_rating=content_rating,
        difficulty=difficulty,
        voice_support=voice_support,
    )


@router.get("/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario(
    scenario_id: str,
    request: Request,
    include_hidden: Annotated[bool, Query(description="Include hidden agenda (only honoured in dev mode)")] = False,
) -> ScenarioDetail:
    """Return full scenario metadata. Hidden agenda is excluded unless dev mode is active."""
    conn = request.app.state.db.connection()
    config = request.app.state.service_config
    dev_mode: bool = getattr(config, "dev_debug", False)
    reveal_hidden = include_hidden and dev_mode

    detail = get_scenario_by_id(conn, scenario_id, include_hidden=reveal_hidden)
    if detail is None:
        raise ConvsimError("NOT_FOUND", f"Scenario '{scenario_id}' not found.", status_code=404)
    return detail
