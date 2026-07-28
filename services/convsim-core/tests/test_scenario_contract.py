# SPDX-License-Identifier: Apache-2.0
"""Frontend contract test for the scenario endpoints.

The web app's canonical ``ScenarioInfo`` type
(packages/shared/src/types/scenario.ts) is consumed WITHOUT guards in several
screens: ScenarioLibrary iterates ``supported_languages`` and
``difficulty.options`` with ``for..of``/``Object.keys`` and reads
``player_role.label``; ScenarioSetup indexes ``supported_languages[0]`` and
reads ``difficulty.default`` and ``state_meters_permitted``. A response
missing any of these fields does not degrade — it blank-screens the app
behind the "Something went wrong" boundary (observed in the v0.2.5 Steam
build as ``Y.supported_languages is not iterable``).

This test seeds the real official packs and asserts every scenario returned
by the list and detail endpoints carries the full canonical contract with
correct types, so backend model changes can never silently reintroduce the
mismatch.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.packs.seeder import seed_official_packs

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"

# Every key the frontend dereferences without a guard, with its expected type.
_CANONICAL_CONTRACT: dict[str, type | tuple[type, ...]] = {
    "scenario_id": str,
    "pack_id": str,
    "pack_name": str,
    "title": str,
    "summary": str,
    "supported_languages": list,
    "state_meters_permitted": bool,
    "voice_supported": bool,
    "safety_summary": str,
    "estimated_length_label": str,
    "recommended_model": list,
    "taught_dimensions": list,
    "tested_dimensions": list,
}


@pytest.fixture()
def seeded_client(tmp_path, monkeypatch):
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_OFFICIAL_PACKS),
    )
    app = create_app(config)
    with TestClient(app) as c:
        # App startup seeds official packs itself; run the seeder again only as
        # a safety net for app versions that defer it (idempotent warm start).
        seed_official_packs(config, app.state.db.connection())
        yield c


def _assert_canonical(s: dict) -> None:
    for key, typ in _CANONICAL_CONTRACT.items():
        assert key in s, f"scenario {s.get('scenario_id')!r} missing '{key}'"
        assert isinstance(s[key], typ), (
            f"scenario {s.get('scenario_id')!r} field '{key}' has type "
            f"{type(s[key]).__name__}, expected {typ}"
        )

    # supported_languages must be a NON-EMPTY list of strings — the setup page
    # indexes [0] and the library iterates it for the language filter.
    assert s["supported_languages"], (
        f"scenario {s.get('scenario_id')!r} has empty supported_languages"
    )
    assert all(isinstance(lang, str) for lang in s["supported_languages"])

    # difficulty must be an object with a string default and a dict options.
    difficulty = s.get("difficulty")
    assert isinstance(difficulty, dict), "difficulty must be an object"
    assert isinstance(difficulty.get("default"), str) and difficulty["default"]
    assert isinstance(difficulty.get("options"), dict)

    # player_role must be an object with a string label.
    player_role = s.get("player_role")
    assert isinstance(player_role, dict), "player_role must be an object"
    assert isinstance(player_role.get("label"), str)

    # duration must be an object with the two canonical keys present.
    duration = s.get("duration")
    assert isinstance(duration, dict), "duration must be an object"
    assert "max_turns" in duration
    assert "soft_time_limit_minutes" in duration


def test_scenario_list_meets_frontend_contract(seeded_client):
    resp = seeded_client.get("/api/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 5, "official packs should seed multiple scenarios"
    for s in scenarios:
        _assert_canonical(s)


def test_scenario_detail_meets_frontend_contract(seeded_client):
    listing = seeded_client.get("/api/scenarios").json()
    for s in listing:
        detail = seeded_client.get(f"/api/scenarios/{s['scenario_id']}")
        assert detail.status_code == 200
        _assert_canonical(detail.json())


def test_tutorial_scenario_canonical_fields(seeded_client):
    """The tutorial is the first scenario every new user opens — pin its shape."""
    resp = seeded_client.get("/api/scenarios/first_words_tutorial")
    assert resp.status_code == 200
    s = resp.json()
    _assert_canonical(s)
    assert s["difficulty"]["default"]
    assert s["duration"]["max_turns"] == 8
    assert s["taught_dimensions"], "tutorial declares taught_dimensions"
    assert s["opening_npc_says"], "tutorial must carry its scripted opening"


def test_language_cafe_languages_come_from_pack_manifest(seeded_client):
    """Language Café's manifest declares en/es/fr/ja — cards must surface them."""
    resp = seeded_client.get("/api/scenarios", params={"pack": "official.language_cafe"})
    assert resp.status_code == 200
    scenarios = resp.json()
    assert scenarios, "language cafe scenarios must be seeded"
    for s in scenarios:
        assert set(s["supported_languages"]) == {"en", "es", "fr", "ja"}
