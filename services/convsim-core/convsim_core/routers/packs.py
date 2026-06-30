# SPDX-License-Identifier: Apache-2.0
"""Pack management endpoints: list, import (zip/folder), validate, and export."""
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from convsim_core.errors import ConvsimError
from convsim_core.packs.exporter import export_to_zip
from convsim_core.packs.importer import safe_extract_zip, import_from_folder, import_from_zip
from convsim_core.packs.models import ImportResult, PackSummary, ValidationResult
from convsim_core.packs.validator import validate_pack_dir
from convsim_core.storage.repositories.pack_repo import list_packs

router = APIRouter(prefix="/api/packs", tags=["packs"])


class _FolderImportBody(BaseModel):
    path: str


@router.get("", response_model=list[PackSummary])
async def get_packs(request: Request) -> list[PackSummary]:
    """List all installed packs."""
    return list_packs(request.app.state.db.connection())


@router.post("/import/zip", response_model=ImportResult, status_code=201)
async def import_pack_from_zip(
    request: Request,
    file: Annotated[UploadFile, File(description="Pack zip archive")],
) -> ImportResult:
    """Import a pack from an uploaded zip file."""
    config = request.app.state.service_config
    db = request.app.state.db

    zip_bytes = await file.read()
    packs_dir = Path(config.packs_dir)
    packs_dir.mkdir(parents=True, exist_ok=True)

    return import_from_zip(zip_bytes, packs_dir, db.connection())


@router.post("/import/folder", response_model=ImportResult, status_code=201)
async def import_pack_from_folder(
    body: _FolderImportBody,
    request: Request,
) -> ImportResult:
    """Import a pack from a local folder path (files are copied; source is not modified)."""
    config = request.app.state.service_config
    db = request.app.state.db

    packs_dir = Path(config.packs_dir)
    packs_dir.mkdir(parents=True, exist_ok=True)

    return import_from_folder(Path(body.path), packs_dir, db.connection())


@router.post("/validate", response_model=ValidationResult)
async def validate_pack(
    file: Annotated[UploadFile, File(description="Pack zip archive to validate")],
) -> ValidationResult:
    """Validate a zip pack without installing it. Returns a list of validation errors."""
    zip_bytes = await file.read()

    if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
        return ValidationResult(valid=False, errors=["Not a valid zip archive"])

    with tempfile.TemporaryDirectory(prefix="convsim_validate_") as tmp_root:
        extract_dir = Path(tmp_root) / "extracted"
        extract_dir.mkdir()

        try:
            safe_extract_zip(zip_bytes, extract_dir)
        except ConvsimError as exc:
            return ValidationResult(valid=False, errors=[exc.message])

        top_level = list(extract_dir.iterdir())
        pack_source = (
            top_level[0]
            if len(top_level) == 1 and top_level[0].is_dir()
            else extract_dir
        )

        manifest, errors = validate_pack_dir(pack_source)

    return ValidationResult(
        valid=len(errors) == 0,
        pack_id=manifest.pack_id if manifest else None,
        name=manifest.name if manifest else None,
        version=manifest.version if manifest else None,
        errors=errors,
    )


@router.get("/{pack_slug}/export")
async def export_pack(pack_slug: str, request: Request) -> Response:
    """Download an installed pack as a zip archive."""
    db = request.app.state.db
    zip_bytes, filename = export_to_zip(pack_slug, db.connection())
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
