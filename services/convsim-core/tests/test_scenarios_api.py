# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the scenario library API."""
import pytest
from fastapi.testclient import TestClient

from tests.helpers import make_pack_zip, make_pack_dir


# ── helpers ───────────────────────────────────────────────────────────────────


def _import_pack(client: TestClient, tmp_path, manifest: dict | None = None) -> None:
    zip_bytes = make_pack_zip(tmp_path, manifest=manifest)
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201, resp.text


# ── no-pack state ─────────────────────────────────────────────────────────────


def test_list_scenarios_empty_when_no_packs(client):
    resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_scenario_404_when_no_packs(client):
    resp = client.get("/api/scenarios/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ── basic listing ─────────────────────────────────────────────────────────────


def test_list_scenarios_returns_cards_after_import(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 1
    card = scenarios[0]
    assert "scenario_id" in card
    assert "pack_id" in card
    assert "pack_name" in card
    assert "title" in card


def test_scenario_card_has_expected_fields(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios")
    cards = resp.json()
    assert len(cards) >= 1
    card = cards[0]
    required = {
        "scenario_id", "pack_id", "pack_name", "title", "summary",
        "tags", "content_rating", "difficulty_default", "max_turns",
        "estimated_length_minutes", "voice_support", "model_recommendation",
    }
    assert required.issubset(card.keys())


def test_scenario_card_includes_pack_metadata(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios")
    card = resp.json()[0]
    assert card["pack_id"] == "test.sample_pack"
    assert card["pack_name"] == "Sample Pack"
    assert card["content_rating"] == "G"
    assert "test" in card["tags"]


# ── scenario detail ───────────────────────────────────────────────────────────


def test_get_scenario_detail_returns_full_metadata(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios")
    scenario_id = resp.json()[0]["scenario_id"]

    detail_resp = client.get(f"/api/scenarios/{scenario_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    assert detail["scenario_id"] == scenario_id
    assert "title" in detail
    assert "player_role" in detail
    assert "opening_npc_says" in detail
    assert "player_visible_goals" in detail
    assert isinstance(detail["player_visible_goals"], list)


def test_get_scenario_detail_intro(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios/intro")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["title"] == "Introduction Scenario"
    assert detail["max_turns"] == 10
    assert detail["estimated_length_minutes"] == 8
    assert detail["difficulty_default"] == "easy"
    assert detail["player_role"]["label"] == "Participant"
    assert detail["opening_npc_says"] == "Hello! Welcome to the session."
    assert "Build rapport with the host" in detail["player_visible_goals"]


# ── hidden agenda security ────────────────────────────────────────────────────


def test_hidden_goals_not_returned_by_default(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios/intro")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail.get("hidden_goals") is None


def test_hidden_goals_not_returned_even_when_requested_without_dev_mode(client, tmp_path):
    """include_hidden=1 must be ignored when dev_debug is False (the default)."""
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios/intro?include_hidden=true")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail.get("hidden_goals") is None


# ── filters ───────────────────────────────────────────────────────────────────


def test_filter_by_pack(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?pack=test.sample_pack")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 1
    for s in scenarios:
        assert s["pack_id"] == "test.sample_pack"


def test_filter_by_nonexistent_pack_returns_empty(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?pack=no_such_pack")
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_by_tag(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?tag=test")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_filter_by_nonexistent_tag_returns_empty(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?tag=nonexistent_tag_xyz")
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_by_language(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?language=en")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_filter_by_language_not_supported_returns_empty(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?language=jp")
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_by_content_rating(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?content_rating=G")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_filter_by_content_rating_no_match(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?content_rating=PG-13")
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_by_difficulty(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?difficulty=easy")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 1
    for s in scenarios:
        assert s["difficulty_default"] == "easy"


def test_filter_by_voice_support_false(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?voice_support=false")
    assert resp.status_code == 200
    for s in resp.json():
        assert s["voice_support"] is False


def test_filter_by_voice_support_true_returns_empty_for_test_pack(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?voice_support=true")
    assert resp.status_code == 200
    assert resp.json() == []


# ── FTS search ────────────────────────────────────────────────────────────────


def test_fts_search_by_title_word(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?q=Introduction")
    assert resp.status_code == 200
    results = resp.json()
    assert any(s["scenario_id"] == "intro" for s in results)


def test_fts_search_by_summary_word(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?q=introductory")
    assert resp.status_code == 200
    results = resp.json()
    assert any(s["scenario_id"] == "intro" for s in results)


def test_fts_search_by_pack_name(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?q=Sample")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1


def test_fts_search_by_pack_description(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?q=minimal")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1


def test_fts_search_no_match_returns_empty(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?q=zzznomatchxxx")
    assert resp.status_code == 200
    assert resp.json() == []


def test_fts_search_works_without_network(client, tmp_path):
    """FTS is local SQLite — it must not make any network calls (structural test)."""
    _import_pack(client, tmp_path)
    resp = client.get("/api/scenarios?q=pressure")
    assert resp.status_code == 200


# ── validation rule_ids ───────────────────────────────────────────────────────


def test_validate_valid_pack_returns_rule_ids_empty(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path)
    resp = client.post(
        "/api/packs/validate",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["rule_ids"] == []


def test_validate_invalid_pack_returns_rule_ids(client, tmp_path):
    zip_bytes = make_pack_zip(tmp_path, extra_files={"bad.sh": b"#!/bin/sh\necho hi"})
    resp = client.post(
        "/api/packs/validate",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "FORBIDDEN_EXTENSION" in body["rule_ids"]


# ── manifest.yaml format ──────────────────────────────────────────────────────


def test_import_manifest_yaml_pack(client, tmp_path):
    """Packs with manifest.yaml (YAML format) instead of pack.json must import successfully."""
    pack_dir = tmp_path / "yaml_pack"
    pack_dir.mkdir()

    manifest_content = (
        "schema_version: '0.1'\n"
        "pack_id: test.yaml_pack\n"
        "name: YAML Pack\n"
        "version: 1.0.0\n"
        "description: Pack using manifest.yaml format\n"
        "author: Test Suite\n"
        "license: CC BY 4.0\n"
        "content_rating: G\n"
        "tags:\n"
        "  - yaml\n"
        "  - test\n"
        "supported_languages:\n"
        "  - en\n"
        "entry_scenarios:\n"
        "  - scenarios/yaml_intro.yaml\n"
        "safety:\n"
        "  policy: safety/default.yaml\n"
    )
    (pack_dir / "manifest.yaml").write_text(manifest_content, encoding="utf-8")

    scenarios_dir = pack_dir / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "yaml_intro.yaml").write_text(
        "schema_version: '0.1'\n"
        "scenario_id: yaml_intro\n"
        "title: YAML Intro\n"
        "summary: A scenario loaded from a manifest.yaml pack.\n"
        "npc:\n  ref: ../npcs/host.yaml\n"
        "rubric:\n  ref: ../rubrics/default.yaml\n"
        "duration:\n  max_turns: 5\n  soft_time_limit_minutes: 4\n"
        "opening:\n  npc_says: Hello from YAML pack.\n"
        "goals:\n  player_visible:\n    - Test YAML import\n",
        encoding="utf-8",
    )

    safety_dir = pack_dir / "safety"
    safety_dir.mkdir()
    (safety_dir / "default.yaml").write_text(
        "schema_version: '0.1'\n"
        "policy_id: default\n"
        "content_categories:\n"
        "  nsfw_sexual: block\n"
        "  real_person_impersonation: block\n"
        "  instructional_criminal: block\n"
        "  crisis_content: redirect\n"
        "redirect_message: \"I can't help with that.\"\n"
        "content_rating_cap: G\n",
        encoding="utf-8",
    )

    import io as _io
    import zipfile as _zipfile

    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for f in sorted(pack_dir.rglob("*")):
            if f.is_file():
                arcname = "yaml_pack/" + str(f.relative_to(pack_dir)).replace("\\", "/")
                zf.write(f, arcname)
    zip_bytes = buf.getvalue()

    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("yaml_pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["pack_slug"] == "test.yaml_pack"
    assert body["scenarios_indexed"] >= 1

    # Verify it shows up in scenarios list
    scenarios_resp = client.get("/api/scenarios?pack=test.yaml_pack")
    assert scenarios_resp.status_code == 200
    assert len(scenarios_resp.json()) >= 1


# ── packs list includes new fields ────────────────────────────────────────────


def test_pack_list_includes_content_rating(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/packs")
    assert resp.status_code == 200
    packs = resp.json()
    assert len(packs) == 1
    assert packs[0]["content_rating"] == "G"


def test_pack_list_includes_supported_languages(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/packs")
    packs = resp.json()
    assert packs[0]["supported_languages"] == ["en"]


def test_pack_list_includes_validation_status(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/packs")
    packs = resp.json()
    assert "validation_status" in packs[0]
    assert packs[0]["validation_status"] == "unknown"


def test_pack_list_includes_tags(client, tmp_path):
    _import_pack(client, tmp_path)
    resp = client.get("/api/packs")
    packs = resp.json()
    assert "test" in packs[0]["tags"]
