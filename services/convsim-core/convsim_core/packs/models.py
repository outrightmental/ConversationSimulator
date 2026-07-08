# SPDX-License-Identifier: Apache-2.0
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    """A single validation finding with enough detail for a human to act on."""

    severity: ValidationSeverity
    rule_id: str
    file: str
    pointer: str
    message: str
    suggested_fix: str


class PackManifest(BaseModel):
    """Parsed contents of a pack's manifest (manifest.yaml or pack.json)."""

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
    """Result of pack validation.

    ``errors`` block import; ``warnings`` allow local use but block official
    contribution.  ``valid`` is True when there are no errors (warnings are OK).
    ``manifest`` is populated whenever the manifest file could be parsed,
    regardless of other validation failures.
    """

    valid: bool
    pack_id: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    manifest: Optional[PackManifest] = None


class ImportResult(BaseModel):
    """Summary returned after a successful pack import."""

    pack_slug: str
    pack_name: str
    pack_version: str
    scenarios_indexed: int
    assets_indexed: int
