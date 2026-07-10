# SPDX-License-Identifier: Apache-2.0
"""Privacy-facing API for NPC relationship memory (issue #314 spike).

Routes:
  GET    /api/relationship-memory              — list all recaps
  DELETE /api/relationship-memory/{npc_id}/{pack_id} — delete one recap
  DELETE /api/relationship-memory              — delete all recaps

All data is stored locally and never sent to any remote service.
These endpoints back the Settings data-controls panel so players can
inspect and erase every NPC memory entry individually.
"""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from convsim_core.storage.repositories.relationship_repo import (
    delete_all_relationship_recaps,
    delete_relationship_recap,
    list_relationship_recaps,
)

router = APIRouter(prefix="/api/relationship-memory", tags=["relationship-memory"])


class RelationshipRecapSummary(BaseModel):
    npc_id: str
    pack_id: str
    session_count: int
    updated_at: str
    key_observations: List[str]
    player_style_tags: List[str]
    last_outcome: Optional[str]
    last_session_at: Optional[str]


class RelationshipMemoryListResponse(BaseModel):
    recaps: List[RelationshipRecapSummary]
    total: int


class DeleteAllResponse(BaseModel):
    deleted: int


@router.get("", response_model=RelationshipMemoryListResponse)
async def list_recaps(request: Request) -> RelationshipMemoryListResponse:
    """Return all NPC relationship recaps for the Settings data-controls panel."""
    conn = request.app.state.db.connection()
    rows = list_relationship_recaps(conn)
    recaps = [RelationshipRecapSummary(**row) for row in rows]
    return RelationshipMemoryListResponse(recaps=recaps, total=len(recaps))


@router.delete("/{npc_id}/{pack_id}", status_code=204)
async def delete_recap(npc_id: str, pack_id: str, request: Request) -> None:
    """Delete the relationship recap for one NPC / pack combination.

    Path segments are URL-decoded before the DB lookup, so slashes embedded
    in npc_id or pack_id must be percent-encoded by the client (%2F).
    """
    npc_id = unquote(npc_id)
    pack_id = unquote(pack_id)
    conn = request.app.state.db.connection()
    found = delete_relationship_recap(conn, npc_id, pack_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"No relationship recap found for npc_id={npc_id!r} pack_id={pack_id!r}",
        )


@router.delete("", response_model=DeleteAllResponse)
async def delete_all_recaps(request: Request) -> DeleteAllResponse:
    """Delete every NPC relationship recap.

    Called by the 'Clear all relationship memories' action in Settings.
    """
    conn = request.app.state.db.connection()
    deleted = delete_all_relationship_recaps(conn)
    return DeleteAllResponse(deleted=deleted)
