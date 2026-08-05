# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
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
    content_rating: Optional[str] = None
    supported_languages: list[str] = []
    tags: list[str] = []
    source_path: Optional[str] = None
    installed_at: str
    validation_status: str = "unknown"
    last_validated_at: Optional[str] = None


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
    rule_ids: list[str] = []
    manifest: Optional[PackManifest] = None


class ImportResult(BaseModel):
    """Summary returned after a successful pack import."""

    pack_slug: str
    pack_name: str
    pack_version: str
    scenarios_indexed: int
    assets_indexed: int


class PlayerRoleInfo(BaseModel):
    """Player role details for a scenario."""

    label: str
    brief: Optional[str] = None


class DifficultyConfigInfo(BaseModel):
    """Difficulty block in the shape the frontend's ScenarioInfo expects."""

    default: str = "standard"
    options: dict = {}


class DurationInfo(BaseModel):
    """Duration block in the shape the frontend's ScenarioInfo expects."""

    max_turns: Optional[int] = None
    soft_time_limit_minutes: Optional[int] = None


class ScenarioCard(BaseModel):
    """Summary of a scenario suitable for a library card view.

    The field set is a superset of the frontend's canonical ``ScenarioInfo``
    contract (packages/shared/src/types/scenario.ts). The frontend iterates
    ``supported_languages``, ``difficulty.options``, and reads
    ``player_role.label`` unconditionally — omitting any of them blank-screens
    the scenario library (the v0.2.5 "supported_languages is not iterable"
    startup-adjacent crash), so every canonical field is always present here
    with a safe default. Legacy flat fields (``difficulty_default``,
    ``voice_support``, ``model_recommendation``) are kept for compatibility
    with existing consumers of this API.
    """

    scenario_id: str
    pack_id: str
    pack_name: str
    title: str
    summary: str = ""
    tags: list[str] = []
    content_rating: Optional[str] = None

    # ── Canonical ScenarioInfo contract fields ────────────────────────────────
    player_role: PlayerRoleInfo = PlayerRoleInfo(label="")
    difficulty: DifficultyConfigInfo = DifficultyConfigInfo()
    supported_languages: list[str] = ["en"]
    duration: DurationInfo = DurationInfo()
    state_meters_permitted: bool = False
    voice_supported: bool = False
    safety_summary: str = ""
    estimated_length_label: str = ""
    recommended_model: list[str] = []
    ladder_position: Optional[str] = None
    taught_dimensions: list[str] = []
    tested_dimensions: list[str] = []

    # ── Legacy flat fields (kept for API compatibility) ───────────────────────
    difficulty_default: Optional[str] = None
    max_turns: Optional[int] = None
    estimated_length_minutes: Optional[int] = None
    voice_support: bool = False
    model_recommendation: Optional[str] = None


class ScenarioDetail(ScenarioCard):
    """Full scenario metadata without hidden agenda.

    Extends the card (which already carries the full canonical ScenarioInfo
    contract) with detail-only fields used by the setup and conversation
    screens.
    """

    difficulty_options: dict = {}
    opening_npc_says: Optional[str] = None
    player_visible_goals: list[str] = []
    hidden_goals: Optional[list[str]] = None


@dataclass
class ScenarioInsertData:
    """Metadata for inserting a scenario record and its FTS entry."""

    slug: str
    name: str
    title: Optional[str] = None
    summary: Optional[str] = None
    content_rating: Optional[str] = None
    difficulty_default: Optional[str] = None
    max_turns: Optional[int] = None
    soft_time_limit_minutes: Optional[int] = None
    tags_json: Optional[str] = None
    voice_support: bool = False
    model_recommendation: Optional[str] = None
    rel_path: Optional[str] = None
    pack_name: str = ""
    pack_description: Optional[str] = None
    pack_tags: list[str] = field(default_factory=list)
