# SPDX-License-Identifier: Apache-2.0
"""Steam Workshop item index endpoints.

The full Workshop sync flow (validate → import → quarantine) is driven by the
desktop shell handing subscribed-item paths to ``POST /api/workshop/sync``.
The sync implementation has not been ported from the legacy Node API yet; the
read endpoints below exist so the library and workshop UI can render their
(empty) Workshop sections without console-noise 404s in every session.

When sync lands, these endpoints read from the same tables it writes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/workshop", tags=["workshop"])


class WorkshopItemEntry(BaseModel):
    item_id: str
    pack_id: str
    author_name: str
    install_path: str
    workshop_updated_at: int
    synced_at: int


class WorkshopQuarantineEntry(BaseModel):
    item_id: str
    install_path: str
    reason: str
    quarantined_at: int


class WorkshopItemsResponse(BaseModel):
    items: list[WorkshopItemEntry] = []


class WorkshopQuarantineResponse(BaseModel):
    items: list[WorkshopQuarantineEntry] = []


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


@router.get("/items", response_model=WorkshopItemsResponse)
async def list_workshop_items(request: Request) -> WorkshopItemsResponse:
    """List successfully synced Workshop items. Empty until sync has run."""
    conn = request.app.state.db.connection()
    if not _table_exists(conn, "workshop_items"):
        return WorkshopItemsResponse(items=[])
    rows = conn.execute(
        "SELECT item_id, pack_id, author_name, install_path, "
        "workshop_updated_at, synced_at FROM workshop_items ORDER BY synced_at DESC"
    ).fetchall()
    return WorkshopItemsResponse(
        items=[WorkshopItemEntry(**dict(r)) for r in rows]
    )


@router.get("/quarantine", response_model=WorkshopQuarantineResponse)
async def list_workshop_quarantine(request: Request) -> WorkshopQuarantineResponse:
    """List Workshop items quarantined by validation. Empty until sync has run."""
    conn = request.app.state.db.connection()
    if not _table_exists(conn, "workshop_quarantine"):
        return WorkshopQuarantineResponse(items=[])
    rows = conn.execute(
        "SELECT item_id, install_path, reason, quarantined_at "
        "FROM workshop_quarantine ORDER BY quarantined_at DESC"
    ).fetchall()
    return WorkshopQuarantineResponse(
        items=[WorkshopQuarantineEntry(**dict(r)) for r in rows]
    )
