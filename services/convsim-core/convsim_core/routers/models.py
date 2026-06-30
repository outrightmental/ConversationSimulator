# SPDX-License-Identifier: Apache-2.0
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.services.model_registry_service import list_registry_models

router = APIRouter()


class ModelRegistryEntry(BaseModel):
    id: str
    name: str
    provider: str
    family: Optional[str] = None
    role: Optional[str] = None
    format: Optional[str] = None
    license_spdx: Optional[str] = None
    license_url: Optional[str] = None
    source_type: Optional[str] = None
    download_url: Optional[str] = None
    sha256: Optional[str] = None
    size_gb: Optional[float] = None
    min_vram_gb: Optional[float] = None
    recommended_vram_gb: Optional[float] = None
    context_length: Optional[int] = None
    registered_at: str


class ModelsResponse(BaseModel):
    models: list[ModelRegistryEntry]
    total: int


@router.get("/api/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    """Return all entries in the local model registry."""
    db = request.app.state.db
    rows: list[dict[str, Any]] = list_registry_models(db.connection())
    entries = [ModelRegistryEntry(**row) for row in rows]
    return ModelsResponse(models=entries, total=len(entries))
