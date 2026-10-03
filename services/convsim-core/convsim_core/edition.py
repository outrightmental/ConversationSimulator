# SPDX-License-Identifier: Apache-2.0
"""Product edition: the full app versus the Steam Next Fest demo.

The demo edition (issue #495) is a deliberately narrowed slice of the same
build: one curated model download and exactly five curated conversations,
with the rest of the product surface hidden. The edition is selected with
``CONVSIM_EDITION=demo`` (see :class:`convsim_core.config.ServiceConfig`);
the default is the full app, so nothing here changes behaviour unless a demo
build opts in.

This module is the single source of truth for *what* the demo exposes. The
web UI reads the same facts from ``GET /api/health`` (``edition`` and
``demo``) instead of duplicating the list, so the five conversations are
curated in exactly one place.

Curation rule for the five: the flagship scenario of each of the five
player-facing official packs — the one scenario per pack whose difficulty
ladder carries authored labels and descriptions. They span the product's
range (interview, negotiation, difficult conversation, dating confidence,
language practice) without exposing its full option set. The scripted
tutorial pack (``tutorial.first_words``) and the sample pack are internal /
developer content and are never part of the demo. See
``docs/steam-next-fest-demo.md`` for the full decision record.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable, Optional, TypeVar

from fastapi import Request

from convsim_core.errors import ConvsimError

logger = logging.getLogger(__name__)

FULL_EDITION = "full"
DEMO_EDITION = "demo"
EDITIONS: tuple[str, ...] = (FULL_EDITION, DEMO_EDITION)

# Stable error code returned when a demo build refuses an action that only the
# full edition offers. The web client maps it to an upsell, never a crash.
EDITION_RESTRICTED = "EDITION_RESTRICTED"


@dataclass(frozen=True)
class DemoScenario:
    """One curated demo conversation, keyed the way the scenario index is."""

    pack_id: str
    scenario_id: str


# Display order is the order players see on the demo Home screen: the most
# universally relatable conversation first, the language-practice showcase last.
DEMO_SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario("official.job_interview_basic", "behavioral_interview"),
    DemoScenario("official.everyday_negotiation", "used_car_negotiation"),
    DemoScenario("official.difficult_conversations", "ask_for_raise"),
    DemoScenario("official.dating_confidence_boundaries", "the_ask"),
    DemoScenario("official.language_cafe", "spanish_coffee"),
)

DEMO_SCENARIO_IDS: tuple[str, ...] = tuple(s.scenario_id for s in DEMO_SCENARIOS)
DEMO_PACK_IDS: tuple[str, ...] = tuple(dict.fromkeys(s.pack_id for s in DEMO_SCENARIOS))

_DEMO_KEYS: frozenset[tuple[str, str]] = frozenset(
    (s.pack_id, s.scenario_id) for s in DEMO_SCENARIOS
)
_DEMO_ORDER: dict[str, int] = {s.scenario_id: i for i, s in enumerate(DEMO_SCENARIOS)}


def is_demo(config: Any) -> bool:
    """True when the service runs as the demo edition."""
    return getattr(config, "edition", FULL_EDITION) == DEMO_EDITION


def edition_of(config: Any) -> str:
    """The edition name the service is running as (``full`` or ``demo``)."""
    return DEMO_EDITION if is_demo(config) else FULL_EDITION


def demo_scenario_allowed(pack_id: Optional[str], scenario_id: Optional[str]) -> bool:
    """Whether a (pack, scenario) pair is one of the five demo conversations.

    Keyed on both ids: scenario slugs are file stems and two packs could in
    principle ship the same stem, so the pack id is part of the key.
    """
    if not pack_id or not scenario_id:
        return False
    return (pack_id, scenario_id) in _DEMO_KEYS


def demo_pack_id_for(scenario_id: Optional[str]) -> Optional[str]:
    """The official pack a demo conversation is played from, or None."""
    for s in DEMO_SCENARIOS:
        if s.scenario_id == scenario_id:
            return s.pack_id
    return None


def demo_scenario_id_allowed(scenario_id: Optional[str]) -> bool:
    """Whether a scenario id (without pack context) is a demo conversation.

    Used where only the scenario id is known (session creation resolves the
    scenario by id). The five demo ids are unique across all official packs.
    """
    return scenario_id in _DEMO_ORDER


_T = TypeVar("_T")


def filter_demo_scenarios(
    items: Iterable[_T],
    *,
    pack_id: Any,
    scenario_id: Any,
) -> list[_T]:
    """Keep only the demo conversations, in the curated display order.

    ``pack_id`` and ``scenario_id`` are accessors ``(item) -> str`` so the
    same filter serves ORM-ish models and raw rows alike.
    """
    kept = [it for it in items if demo_scenario_allowed(pack_id(it), scenario_id(it))]
    kept.sort(key=lambda it: _DEMO_ORDER.get(scenario_id(it), len(_DEMO_ORDER)))
    return kept


def resolve_demo_model_id(conn: sqlite3.Connection, config: Any) -> Optional[str]:
    """The registry id of the one model the demo edition installs.

    ``CONVSIM_DEMO_MODEL_ID`` pins it explicitly — that is how a demo build
    ships on the registry's smaller ``role: lightweight`` tier
    (``qwen3-1.7b-instruct-q8_0``) instead; a demo build carries the pin from
    release.yml's ``demo_model_id`` input. Otherwise the registry's
    ``role: starter`` entry is used, which is deliberately still the default:
    the lightweight tier has not been played through the five demo
    conversations, and an incoherent NPC is a worse demo than a longer
    download (see ``docs/steam-next-fest-demo.md``). A pin that names nothing
    in the registry, or an entry with no download URL, falls back to the
    starter with a logged error rather than dead-ending first-run setup on a
    model that cannot be installed. Returns ``None`` when neither resolves,
    which the models endpoint reports as an empty registry rather than
    guessing.
    """
    pinned = (getattr(config, "demo_model_id", None) or "").strip()
    if pinned:
        try:
            hit = conn.execute(
                "SELECT id, download_url FROM model_registry WHERE id = ? LIMIT 1",
                (pinned,),
            ).fetchone()
        except sqlite3.Error:
            hit = None
        if hit is not None and hit["download_url"]:
            return pinned
        if hit is not None:
            # In the registry, but not downloadable: `user-supplied-gguf` stands
            # for a file the player brings, so it carries no URL and no
            # checksum. The demo offers no second model, so every install would
            # fail at the download stage with nothing to fall back to. The build
            # gates (build.rs, release.yml) refuse this too, but they only cover
            # a packaged build and a CI dispatch — this is the one place every
            # way of setting the variable passes through.
            logger.error(
                "CONVSIM_DEMO_MODEL_ID=%r has no download URL in the model registry "
                "(it is the user-supplied placeholder, not a downloadable tier); "
                "falling back to the registry's starter model",
                pinned,
            )
        else:
            # A pin that names nothing in the registry (a typo, or an entry not
            # yet seeded) would advertise a model the wizard can never install —
            # a first-run dead end. Fall back to the starter and say so loudly.
            logger.error(
                "CONVSIM_DEMO_MODEL_ID=%r is not in the model registry; "
                "falling back to the registry's starter model",
                pinned,
            )
    try:
        row = conn.execute(
            "SELECT id FROM model_registry WHERE role = 'starter' ORDER BY id LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    return row["id"] if row is not None else None


def demo_model_paths(conn: sqlite3.Connection, config: Any) -> set[str]:
    """Filesystem paths under which the demo model has been (or is being) installed.

    The runtime selection and sidecar routes take a model *path*; in the demo
    only the curated model's own install paths are acceptable.
    """
    demo_id = resolve_demo_model_id(conn, config)
    if demo_id is None:
        return set()
    try:
        rows = conn.execute(
            "SELECT file_path FROM installed_models WHERE registry_id = ?", (demo_id,)
        ).fetchall()
    except sqlite3.Error:
        return set()
    return {str(r["file_path"]) for r in rows if r["file_path"]}


def require_demo_model_path(conn: sqlite3.Connection, config: Any, model_path: Optional[str]) -> None:
    """Refuse a model path that is not the demo model's own install (demo only)."""
    if not is_demo(config):
        return
    if model_path and model_path in demo_model_paths(conn, config):
        return
    raise ConvsimError(
        EDITION_RESTRICTED,
        "Only the demo's own AI model can be used in the demo edition. The full "
        "version of Conversation Simulator adds the standard and high-quality "
        "tiers, Ollama, and your own GGUF files.",
        status_code=403,
    )


def demo_model_allowed(conn: sqlite3.Connection, config: Any, registry_id: str) -> bool:
    """Whether ``registry_id`` is the model a demo build may install."""
    demo_id = resolve_demo_model_id(conn, config)
    return demo_id is not None and registry_id == demo_id


def edition_info(conn: sqlite3.Connection, config: Any) -> dict[str, Any]:
    """Edition facts for ``GET /api/health``.

    Always carries ``edition``; carries ``demo`` only for the demo edition so
    the full app's health payload is unchanged apart from the new key.
    """
    if not is_demo(config):
        return {"edition": FULL_EDITION, "demo": None}
    return {
        "edition": DEMO_EDITION,
        "demo": {
            "model_id": resolve_demo_model_id(conn, config),
            "scenario_ids": list(DEMO_SCENARIO_IDS),
            "pack_ids": list(DEMO_PACK_IDS),
        },
    }


def require_full_edition(request: Request) -> None:
    """FastAPI dependency: refuse a full-app-only route in the demo edition.

    Attached at router-inclusion time (see ``convsim_core.app``) so the guarded
    routers themselves stay edition-agnostic. A no-op in the full edition.
    """
    if is_demo(request.app.state.service_config):
        raise ConvsimError(
            EDITION_RESTRICTED,
            "This feature is not available in the demo edition. The full version "
            "of Conversation Simulator includes the Creator Workbench, pack import, "
            "and the complete scenario library.",
            status_code=403,
        )
