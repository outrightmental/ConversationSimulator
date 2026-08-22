# SPDX-License-Identifier: Apache-2.0
"""Sessions must be playable for every installed pack scenario.

The session engine used to resolve scenarios only from the hardcoded catalog
in ``convsim_core/scenarios.py`` (6 entries), while the library seeds 20+
scenarios from the official packs — every non-catalog scenario failed session
creation with "Unknown scenario_id". ``resolve_scenario_info`` now falls back
to the installed pack's YAML (difficulty presets, events, ending conditions,
languages included). These tests pin that behaviour end-to-end through the
HTTP surface: create → start (opening + initial visible state) → turn.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"


@pytest.fixture()
def seeded_client(tmp_path):
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
        yield c


def _create(client: TestClient, scenario_id: str, language: str = "en") -> str:
    resp = client.post(
        "/api/sessions",
        json={
            "scenario_id": scenario_id,
            "difficulty": "standard",
            "language": language,
            "player_role_name": "Test Player",
            "save_transcript": True,
            # Explicit fake-runtime pin (issue #473).
            "runtime_id": "fake",
        },
    )
    assert resp.status_code == 201, f"{scenario_id}: {resp.text}"
    return resp.json()["session_id"]


def test_non_catalog_pack_scenario_full_session(seeded_client):
    """japanese_convenience_store is NOT in the static catalog — must play."""
    session_id = _create(seeded_client, "japanese_convenience_store", language="ja")

    start = seeded_client.post(f"/api/sessions/{session_id}/start")
    assert start.status_code == 200, start.text
    events = start.json()["events"]
    opening = next(e for e in events if e["event_type"] == "npc_opening")
    # Opening must come from the pack YAML, not the generic fallback line.
    assert "いらっしゃいませ" in opening["payload"]["content"]
    # Initial visible state includes the scenario's custom variables.
    visible = opening["payload"].get("visible_state") or {}
    assert "comprehension" in visible and "confidence" in visible

    turn = seeded_client.post(
        f"/api/sessions/{session_id}/turn",
        json={"content": "こんにちは！おにぎりはありますか？"},
    )
    assert turn.status_code == 200, turn.text


def test_every_seeded_scenario_can_create_a_session(seeded_client):
    """No library card may dead-end at session creation."""
    scenarios = seeded_client.get("/api/scenarios").json()
    assert len(scenarios) >= 15
    failures = []
    for s in scenarios:
        difficulty = s["difficulty"]["default"]
        language = s["supported_languages"][0]
        resp = seeded_client.post(
            "/api/sessions",
            json={
                "scenario_id": s["scenario_id"],
                "difficulty": difficulty,
                "language": language,
                "player_role_name": "Test Player",
                "save_transcript": True,
                # Explicit pin (issue #473).
                "runtime_id": "fake",
            },
        )
        if resp.status_code != 201:
            failures.append(f"{s['scenario_id']}: {resp.status_code} {resp.text[:120]}")
    assert not failures, "unplayable library scenarios:\n" + "\n".join(failures)


def test_pack_scenario_difficulty_presets_come_from_yaml(seeded_client):
    """A YAML 'warm' preset must be accepted for a non-catalog scenario."""
    resp = seeded_client.post(
        "/api/sessions",
        json={
            "scenario_id": "japanese_convenience_store",
            "difficulty": "warm",
            "language": "ja",
            "player_role_name": "Test Player",
            "save_transcript": True,
            # Explicit pin (issue #473).
            "runtime_id": "fake",
        },
    )
    assert resp.status_code == 201, resp.text
