# SPDX-License-Identifier: Apache-2.0
from typing import Optional

from pydantic import BaseModel


class PackManifest(BaseModel):
    """Parsed contents of a pack's pack.json manifest file."""

    schema_version: str
    pack_id: str
    name: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    content_rating: Optional[str] = None
    tags: list[str] = []
    supported_languages: list[str] = []
    entry_scenarios: list[str] = []
    requirements: Optional[dict] = None
    assets: Optional[dict] = None
    safety: Optional[dict] = None


class PackSummary(BaseModel):
    """Database record for an installed pack."""

    id: int
    slug: str
    name: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    source_path: Optional[str] = None
    installed_at: str


class ValidationResult(BaseModel):
    """Result of pack validation without installation."""

    valid: bool
    pack_id: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    errors: list[str] = []


class ImportResult(BaseModel):
    """Summary returned after a successful pack import."""

    pack_slug: str
    pack_name: str
    pack_version: str
    scenarios_indexed: int
    assets_indexed: int
