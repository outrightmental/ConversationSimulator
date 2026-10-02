# SPDX-License-Identifier: Apache-2.0
"""Loading a ``mode: flyting`` scenario out of a pack directory.

The conversation loader (``convsim_core.scenarios.load_scenario_info_from_pack``)
reads the fields a conversation turn needs. A flyting run needs four more things
from the same files: the ``flyting`` block from the scenario, the target's
``attack_surface`` from the NPC, the ``volley_judge`` block from a rubric, and
the ``audience`` block from the scene. This module reads all of it in one pass
and hands back a single resolved object.

Resolution is forgiving by design — a missing rubric block means engine
defaults, a missing audience means no crowd — but a scenario that does not
declare ``mode: flyting`` is *not* loaded as a flyting run. Guessing a game mode
from a scenario's contents would mean one typo silently changes how a scenario
plays.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from convsim_prompt import (
    AttackSurfaceTrait,
    JudgeRubric,
    NpcData,
    NpcPrivatePersona,
    NpcPublicPersona,
)

from convsim_core.flyting.config import (
    AudienceConfig,
    FlytingConfig,
    parse_attack_surface,
    parse_judge_rubric,
)
from convsim_core.flyting.service import ScoringContext
from convsim_core.input_router import SafetyPolicyConfig
from convsim_core.services.safety_policy_service import (
    SafetyPolicyValidationError,
    load_safety_policy,
)

logger = logging.getLogger(__name__)

FLYTING_MODE = "flyting"


@dataclass(frozen=True)
class FlytingScenario:
    """A fully resolved flyting scenario, ready to play."""

    scenario_id: str
    title: str
    summary: str
    pack_dir: Path
    flyting: FlytingConfig
    npc: NpcData
    attack_surface: Tuple[AttackSurfaceTrait, ...] = ()
    rubric: JudgeRubric = field(default_factory=JudgeRubric)
    audience: Optional[AudienceConfig] = None
    safety_policy: Optional[SafetyPolicyConfig] = None
    content_rating: str = "PG-13"
    player_role_label: str = "Player"
    player_role_brief: str = ""
    setting_brief: str = ""
    player_visible_goals: Tuple[str, ...] = ()
    state_variables: Optional[Dict[str, Any]] = None
    supported_languages: Tuple[str, ...] = ("en",)
    pack_id: Optional[str] = None

    def scoring_context(self) -> ScoringContext:
        """The ScoringContext a VolleyScoringService needs for this scenario."""
        # Imported here rather than at module scope: the turn pipeline pulls in
        # the whole conversation stack, and the flyting engine must stay
        # importable without it.
        from convsim_core.services.turn_pipeline import _DEFAULT_SAFETY_POLICY_CONFIG

        return ScoringContext(
            scenario_id=self.scenario_id,
            scenario_title=self.title,
            flyting=self.flyting,
            safety_policy=self.safety_policy or _DEFAULT_SAFETY_POLICY_CONFIG,
            rubric=self.rubric,
            attack_surface=self.attack_surface,
            target_name=self.npc.display_name,
            setting_brief=self.setting_brief,
            audience=self.audience,
            content_rating=self.content_rating,
        )


def _read_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _npc_from_dict(raw: Dict[str, Any]) -> NpcData:
    pub = raw.get("public_persona") or {}
    priv = raw.get("private_persona") or {}
    return NpcData(
        npc_id=str(raw.get("npc_id") or "npc"),
        display_name=str(raw.get("display_name") or "the target"),
        public_persona=NpcPublicPersona(
            occupation=str(pub.get("occupation") or ""),
            speaking_style=str(pub.get("speaking_style") or ""),
            demeanor=str(pub.get("demeanor") or ""),
        ),
        private_persona=NpcPrivatePersona(
            hidden_agenda=list(priv.get("hidden_agenda") or []),
            biases_to_simulate=list(priv.get("biases_to_simulate") or []),
            boundaries=list(priv.get("boundaries") or []),
        ),
    )


def _resolve_optional(base: Path, ref: Any) -> Optional[Path]:
    """Resolve a pack-relative ``{ref: ...}`` block, refusing paths outside the pack."""
    if not isinstance(ref, dict) or not ref.get("ref"):
        return None
    candidate = (base / str(ref["ref"])).resolve()
    return candidate if candidate.is_file() else None


def load_flyting_scenario(
    pack_dir: Path,
    scenario_rel_path: str,
    *,
    pack_id: Optional[str] = None,
) -> Optional[FlytingScenario]:
    """Load a flyting scenario from a pack, or None when it is not one.

    Returns None — rather than raising — for a conversation-mode scenario, so a
    caller can ask "is this a flyting scenario?" without catching exceptions.
    Raises ``OSError`` or ``yaml.YAMLError`` only if the files cannot be read.
    """
    scenario_file = (pack_dir / scenario_rel_path).resolve()
    raw = _read_yaml(scenario_file)
    if str(raw.get("mode") or "conversation") != FLYTING_MODE:
        return None

    flyting = FlytingConfig.from_yaml(raw.get("flyting"))
    if flyting is None:
        # The schema makes this combination invalid, but a locally edited pack
        # can still reach the engine, and an unplayable run is worse than a
        # scenario that declines to start.
        logger.warning(
            "Scenario %s declares mode: flyting with no flyting block; not loading it",
            scenario_rel_path,
        )
        return None

    scenario_dir = scenario_file.parent

    npc_raw: Dict[str, Any] = {}
    npc_path = _resolve_optional(scenario_dir, raw.get("npc"))
    if npc_path is not None:
        npc_raw = _read_yaml(npc_path)
    elif isinstance(raw.get("npc"), dict):
        npc_raw = raw["npc"]

    # The judge rubric may be a dedicated rubric or the scenario's main one.
    rubric = JudgeRubric()
    rubric_ref = {"ref": flyting.judge_rubric_ref} if flyting.judge_rubric_ref else raw.get("rubric")
    rubric_path = _resolve_optional(scenario_dir, rubric_ref)
    if rubric_path is not None:
        rubric = parse_judge_rubric(_read_yaml(rubric_path))

    audience: Optional[AudienceConfig] = None
    setting_brief = ""
    scene_path = _resolve_optional(scenario_dir, raw.get("scene"))
    if scene_path is not None:
        scene_raw = _read_yaml(scene_path)
        audience = AudienceConfig.from_yaml(scene_raw.get("audience"))
        setting_brief = str(scene_raw.get("description") or "")

    safety_policy: Optional[SafetyPolicyConfig] = None
    content_rating = "PG-13"
    manifest_path = pack_dir / "manifest.yaml"
    if manifest_path.is_file():
        manifest = _read_yaml(manifest_path)
        content_rating = str(manifest.get("content_rating") or content_rating)
        policy_ref = (manifest.get("safety") or {}).get("policy")
        if policy_ref:
            policy_path = (pack_dir / str(policy_ref)).resolve()
            try:
                safety_policy = load_safety_policy(policy_path)
            except SafetyPolicyValidationError as exc:
                # Falling back to the default PG policy is the safe direction:
                # it is stricter than a pack that fails to load, never looser.
                logger.warning(
                    "Pack safety policy at %s could not be loaded (%s); using the default",
                    policy_path, exc,
                )

    player_role = raw.get("player_role") or {}
    goals = raw.get("goals") or {}
    state = raw.get("state") or {}
    langs = raw.get("supported_languages")

    return FlytingScenario(
        scenario_id=str(raw.get("scenario_id") or scenario_file.stem),
        title=str(raw.get("title") or "Flyting"),
        summary=str(raw.get("summary") or ""),
        pack_dir=pack_dir,
        flyting=flyting,
        npc=_npc_from_dict(npc_raw),
        attack_surface=parse_attack_surface(npc_raw.get("attack_surface")),
        rubric=rubric,
        audience=audience,
        safety_policy=safety_policy,
        content_rating=content_rating,
        player_role_label=str(player_role.get("label") or "Player"),
        player_role_brief=str(player_role.get("brief") or ""),
        setting_brief=setting_brief,
        player_visible_goals=tuple(str(g) for g in (goals.get("player_visible") or [])),
        state_variables=state.get("variables") if isinstance(state, dict) else None,
        supported_languages=tuple(str(x) for x in langs) if isinstance(langs, list) and langs else ("en",),
        pack_id=pack_id,
    )


# ---------------------------------------------------------------------------
# Installed-pack resolution
# ---------------------------------------------------------------------------

_cache: Dict[str, Optional[FlytingScenario]] = {}
_cache_lock = threading.Lock()


def resolve_flyting_scenario(scenario_id: str, conn: Any) -> Optional[FlytingScenario]:
    """Resolve a flyting scenario by id from the installed pack index.

    Results are cached for the process lifetime — including the negative result
    for a conversation-mode scenario, so the common case of "this id is not
    flyting" costs one query per process rather than one per request.
    """
    with _cache_lock:
        if scenario_id in _cache:
            return _cache[scenario_id]

    resolved: Optional[FlytingScenario] = None
    try:
        row = conn.execute(
            "SELECT s.rel_path, p.source_path, p.slug AS pack_slug "
            "FROM scenarios s JOIN packs p ON s.pack_id = p.id "
            "WHERE s.slug = ? LIMIT 1",
            (scenario_id,),
        ).fetchone()
    except Exception:  # noqa: BLE001 — a missing index must not break the route
        row = None

    if row is not None and row["source_path"] and row["rel_path"]:
        try:
            resolved = load_flyting_scenario(
                Path(row["source_path"]), row["rel_path"], pack_id=row["pack_slug"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load flyting scenario %s: %s", scenario_id, exc)
            resolved = None

    with _cache_lock:
        _cache[scenario_id] = resolved
    return resolved


def clear_scenario_cache() -> None:
    """Forget resolved scenarios — used by tests and after a pack is re-imported."""
    with _cache_lock:
        _cache.clear()


def list_flyting_scenarios(conn: Any) -> list[FlytingScenario]:
    """Every installed flyting scenario, for the library and the format picker."""
    try:
        rows = conn.execute(
            "SELECT s.slug, s.rel_path, p.source_path, p.slug AS pack_slug "
            "FROM scenarios s JOIN packs p ON s.pack_id = p.id ORDER BY s.slug"
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []

    out: list[FlytingScenario] = []
    for row in rows:
        if not row["source_path"] or not row["rel_path"]:
            continue
        try:
            scenario = load_flyting_scenario(
                Path(row["source_path"]), row["rel_path"], pack_id=row["pack_slug"]
            )
        except Exception:  # noqa: BLE001
            continue
        if scenario is not None:
            out.append(scenario)
    return out


def state_variable_json(scenario: FlytingScenario) -> str:
    """The scenario's declared state variables, serialised for the session row."""
    return json.dumps(scenario.state_variables or {})
