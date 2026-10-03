# SPDX-License-Identifier: Apache-2.0
"""Demo edition (Steam Next Fest demo, issue #495).

The demo is the same build narrowed to one curated model and five curated
conversations, selected with ``CONVSIM_EDITION=demo``. These tests pin three
things: the curated list points at real official-pack content, the full app is
byte-for-byte unaffected apart from the new ``edition`` health field, and every
API surface the demo hides in the UI is also refused server-side.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from convsim_core import edition
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services.model_registry_service import load_and_persist_registry
from tests.helpers import make_pack_zip

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"
_REGISTRY_PATH = _REPO_ROOT / "model-registry" / "registry.yaml"

_STARTER_MODEL_ID = "qwen3-4b-instruct-q4_k_m"


def _config(tmp_path: Path, **overrides) -> ServiceConfig:
    base = dict(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"),
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
        models_dir=str(tmp_path / "models" / "llm"),
        local_dev_packs_dir=str(tmp_path),
        official_packs_dir=str(_OFFICIAL_PACKS),
        model_registry_path=str(_REGISTRY_PATH),
    )
    base.update(overrides)
    return ServiceConfig(**base)


@pytest.fixture()
def demo_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    app = create_app(_config(tmp_path, edition="demo"))
    with TestClient(app) as c:
        yield c, app


@pytest.fixture()
def full_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    app = create_app(_config(tmp_path))
    with TestClient(app) as c:
        yield c, app


def _official_pack_index() -> dict[str, Path]:
    """pack_id → pack directory, read from the real bundled manifests."""
    index: dict[str, Path] = {}
    for manifest in sorted(_OFFICIAL_PACKS.glob("*/manifest.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        index[data["pack_id"]] = manifest.parent
    return index


# ── Curation: the five point at real, shippable content ───────────────────────


def test_demo_curates_exactly_five_conversations():
    assert len(edition.DEMO_SCENARIOS) == 5
    assert len(set(edition.DEMO_SCENARIO_IDS)) == 5, "scenario ids must be unique"


def test_demo_scenarios_exist_in_official_packs():
    index = _official_pack_index()
    for s in edition.DEMO_SCENARIOS:
        assert s.pack_id in index, f"{s.pack_id} is not a bundled official pack"
        scenario_file = index[s.pack_id] / "scenarios" / f"{s.scenario_id}.yaml"
        assert scenario_file.is_file(), f"{scenario_file} missing"
        data = yaml.safe_load(scenario_file.read_text(encoding="utf-8"))
        # Scenario slugs are file stems; the YAML id must agree so the card the
        # demo Home renders and the session it starts are the same scenario.
        assert data["scenario_id"] == s.scenario_id


def test_demo_scenarios_are_one_per_player_facing_pack():
    """One flagship per pack, and never the tutorial or sample packs."""
    assert len(set(edition.DEMO_PACK_IDS)) == 5
    for pack_id in edition.DEMO_PACK_IDS:
        assert pack_id.startswith("official."), pack_id
    assert "tutorial.first_words" not in edition.DEMO_PACK_IDS


def test_demo_scenarios_are_the_flagship_of_each_pack():
    """The curation rule: the one scenario per pack with an authored difficulty ladder."""
    index = _official_pack_index()
    for s in edition.DEMO_SCENARIOS:
        data = yaml.safe_load(
            (index[s.pack_id] / "scenarios" / f"{s.scenario_id}.yaml").read_text(encoding="utf-8")
        )
        options = data["difficulty"]["options"]
        assert all("label" in opt and "description" in opt for opt in options.values()), (
            f"{s.scenario_id}: every difficulty option must carry a label and description"
        )


def test_demo_content_ratings_are_pg13_or_milder():
    """A Next Fest demo must not need an age gate the base app does not have."""
    index = _official_pack_index()
    for pack_id in edition.DEMO_PACK_IDS:
        data = yaml.safe_load((index[pack_id] / "manifest.yaml").read_text(encoding="utf-8"))
        assert data["content_rating"] in ("G", "PG", "PG-13"), pack_id


# ── Config ────────────────────────────────────────────────────────────────────


def test_edition_defaults_to_full(tmp_path):
    assert _config(tmp_path).edition == "full"
    assert not edition.is_demo(_config(tmp_path))


def test_edition_env_var_selects_demo(monkeypatch):
    monkeypatch.setenv("CONVSIM_EDITION", "demo")
    assert ServiceConfig().edition == "demo"


def test_edition_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("CONVSIM_EDITION", "trial")
    with pytest.raises(Exception):
        ServiceConfig()


def test_filter_demo_scenarios_keeps_curated_order():
    shuffled = [
        {"pack_id": "official.language_cafe", "scenario_id": "spanish_coffee"},
        {"pack_id": "official.job_interview_basic", "scenario_id": "hostile_executive_interview"},
        {"pack_id": "official.job_interview_basic", "scenario_id": "behavioral_interview"},
        {"pack_id": "other.pack", "scenario_id": "behavioral_interview"},  # same stem, wrong pack
    ]
    kept = edition.filter_demo_scenarios(
        shuffled, pack_id=lambda r: r["pack_id"], scenario_id=lambda r: r["scenario_id"]
    )
    assert [r["scenario_id"] for r in kept] == ["behavioral_interview", "spanish_coffee"]
    assert kept[0]["pack_id"] == "official.job_interview_basic"


# ── Full edition: unchanged apart from the new health field ───────────────────


def test_full_edition_health_reports_full(full_client):
    client, _ = full_client
    body = client.get("/api/health").json()
    assert body["edition"] == "full"
    assert body["demo"] is None


def test_full_edition_serves_whole_library(full_client):
    client, _ = full_client
    scenarios = client.get("/api/scenarios").json()
    ids = {s["scenario_id"] for s in scenarios}
    assert set(edition.DEMO_SCENARIO_IDS) <= ids
    assert "hostile_executive_interview" in ids
    assert len(scenarios) > 5


def test_full_edition_workbench_reachable(full_client):
    client, _ = full_client
    assert client.get("/api/workbench/packs").status_code == 200


# ── Demo edition: health ──────────────────────────────────────────────────────


def test_demo_health_reports_edition_and_curated_content(demo_client):
    client, _ = demo_client
    body = client.get("/api/health").json()
    assert body["edition"] == "demo"
    assert body["demo"]["scenario_ids"] == list(edition.DEMO_SCENARIO_IDS)
    assert body["demo"]["pack_ids"] == list(edition.DEMO_PACK_IDS)
    assert body["demo"]["model_id"] == _STARTER_MODEL_ID


def test_demo_model_id_can_be_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    app = create_app(_config(tmp_path, edition="demo", demo_model_id="qwen3-8b-instruct-q4_k_m"))
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["demo"]["model_id"] == "qwen3-8b-instruct-q4_k_m"
        registry = client.get("/api/models").json()["registry"]
        assert [m["id"] for m in registry] == ["qwen3-8b-instruct-q4_k_m"]


# ── Demo edition: scenarios and packs ─────────────────────────────────────────


def test_demo_scenario_list_is_exactly_the_five_in_order(demo_client):
    client, _ = demo_client
    scenarios = client.get("/api/scenarios").json()
    assert [s["scenario_id"] for s in scenarios] == list(edition.DEMO_SCENARIO_IDS)
    assert [s["pack_id"] for s in scenarios] == [s.pack_id for s in edition.DEMO_SCENARIOS]


def test_demo_scenario_list_filters_apply_within_the_five(demo_client):
    client, _ = demo_client
    scenarios = client.get("/api/scenarios", params={"language": "es"}).json()
    assert [s["scenario_id"] for s in scenarios] == ["spanish_coffee"]


def test_demo_cards_lead_with_their_target_language(demo_client):
    """The Language Café flagship exists to show a non-English conversation.

    The setup page defaults to ``supported_languages[0]`` and the demo card is
    labelled with it, so that card must lead with Spanish (its own scenario
    list, not the pack manifest's English-first one) and every other card
    with English — otherwise "Coffee at Café Sol" would start in English and
    carry no language label at all.
    """
    client, _ = demo_client
    first_language = {
        s["scenario_id"]: s["supported_languages"][0] for s in client.get("/api/scenarios").json()
    }
    assert first_language["spanish_coffee"] == "es"
    assert {sid: lang for sid, lang in first_language.items() if sid != "spanish_coffee"} == {
        sid: "en" for sid in edition.DEMO_SCENARIO_IDS if sid != "spanish_coffee"
    }


def test_demo_hidden_scenario_detail_is_404(demo_client):
    client, _ = demo_client
    resp = client.get("/api/scenarios/hostile_executive_interview")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_demo_curated_scenario_detail_is_served(demo_client):
    client, _ = demo_client
    resp = client.get("/api/scenarios/behavioral_interview")
    assert resp.status_code == 200
    assert resp.json()["pack_id"] == "official.job_interview_basic"


def test_demo_packs_list_only_curated_packs_and_counts(demo_client):
    client, _ = demo_client
    body = client.get("/api/packs").json()
    assert body["total"] == 5
    assert {p["pack_id"] for p in body["packs"]} == set(edition.DEMO_PACK_IDS)
    assert all(p["scenario_count"] == 1 for p in body["packs"])


# ── Demo edition: sessions ────────────────────────────────────────────────────


def _session_body(scenario_id: str, language: str = "en") -> dict:
    return {
        "scenario_id": scenario_id,
        "difficulty": "standard",
        "language": language,
        "player_role_name": "Demo Player",
        "save_transcript": True,
        "runtime_id": "fake",
    }


def test_demo_refuses_session_for_hidden_scenario(demo_client):
    client, _ = demo_client
    # hostile_executive_interview is also in the built-in catalogue, so this
    # proves the guard runs before catalogue resolution.
    resp = client.post("/api/sessions", json=_session_body("hostile_executive_interview"))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == edition.EDITION_RESTRICTED


def test_demo_every_curated_scenario_is_playable(demo_client):
    client, _ = demo_client
    for s in client.get("/api/scenarios").json():
        resp = client.post(
            "/api/sessions",
            json=_session_body(s["scenario_id"], s["supported_languages"][0]),
        )
        assert resp.status_code == 201, f"{s['scenario_id']}: {resp.text}"
        start = client.post(f"/api/sessions/{resp.json()['session_id']}/start")
        assert start.status_code == 200, f"{s['scenario_id']}: {start.text}"


# ── Demo edition: models and install ──────────────────────────────────────────


def test_demo_models_registry_is_the_single_curated_model(demo_client):
    client, _ = demo_client
    body = client.get("/api/models").json()
    assert [m["id"] for m in body["registry"]] == [_STARTER_MODEL_ID]
    assert body["registry"][0]["role"] == "starter"
    assert body["total"] == 1
    assert body["ollama_models"] == []


def test_demo_setup_install_refuses_other_models(demo_client):
    client, _ = demo_client
    resp = client.post("/api/setup/install", json={"registry_id": "qwen3-8b-instruct-q4_k_m"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_setup_install_accepts_the_curated_model(demo_client):
    client, _ = demo_client
    with patch("convsim_core.routers.setup_install._run_pipeline", new_callable=AsyncMock):
        resp = client.post("/api/setup/install", json={"registry_id": _STARTER_MODEL_ID})
    assert resp.status_code == 200, resp.text
    assert resp.json()["registry_id"] == _STARTER_MODEL_ID


def test_demo_direct_install_refuses_other_models(demo_client):
    client, _ = demo_client
    resp = client.post("/api/models/install", json={"registry_id": "qwen3-14b-instruct-q4_k_m"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


# ── Demo edition: full-app-only surfaces ──────────────────────────────────────


def test_demo_refuses_pack_import(demo_client, tmp_path):
    client, _ = demo_client
    zip_bytes = make_pack_zip(tmp_path)
    resp = client.post(
        "/api/packs/import/zip",
        files={"file": ("pack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_refuses_workbench(demo_client):
    client, _ = demo_client
    resp = client.get("/api/workbench/packs")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_refuses_voice_setup(demo_client):
    """The demo ships no voice, so the guided flow (issue #487) is refused here.

    The UI collapses /voice-setup to Home in the demo, but the gate that matters
    is this one: without it a hand-crafted POST could start a ~150 MB download
    the demo never offers.
    """
    client, _ = demo_client
    for method, path in (
        ("get", "/api/voice/setup/plan"),
        ("post", "/api/voice/setup/install"),
        ("get", "/api/voice/setup/install/1"),
        ("delete", "/api/voice/setup/install/1"),
        ("post", "/api/voice/setup/engine/kokoro-server/start"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 403, (method, path)
        assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED, (method, path)


def test_full_edition_voice_setup_reachable(full_client):
    client, _ = full_client
    assert client.get("/api/voice/setup/plan").status_code == 200


def test_demo_privacy_controls_still_available(demo_client):
    """Privacy controls (gate F-06) are never trimmed, whatever the edition."""
    client, _ = demo_client
    assert client.get("/api/privacy/folders").status_code == 200
    assert client.post("/api/privacy/clear").status_code == 200


def test_registry_starter_role_backs_the_demo_model(demo_client):
    """The demo model is the registry's starter tier unless pinned."""
    _, app = demo_client
    conn = app.state.db.connection()
    load_and_persist_registry(conn, _REGISTRY_PATH)
    assert edition.resolve_demo_model_id(conn, app.state.service_config) == _STARTER_MODEL_ID


# ── Demo edition: the curated pack YAML is what plays, not the built-in catalogue ──


def _pack_opening(pack_id: str, scenario_id: str) -> str:
    index = _official_pack_index()
    data = yaml.safe_load(
        (index[pack_id] / "scenarios" / f"{scenario_id}.yaml").read_text(encoding="utf-8")
    )
    return data["opening"]["npc_says"]


def test_demo_plays_the_pack_version_of_every_curated_conversation(demo_client):
    """behavioral_interview, used_car_negotiation and spanish_coffee also exist in the
    hardcoded catalogue with different openings; the demo card advertises the pack
    YAML, so the session must open with the pack YAML too."""
    client, _ = demo_client
    for s in edition.DEMO_SCENARIOS:
        lang = "es" if s.scenario_id == "spanish_coffee" else "en"
        created = client.post("/api/sessions", json=_session_body(s.scenario_id, lang))
        assert created.status_code == 201, created.text
        start = client.post(f"/api/sessions/{created.json()['session_id']}/start")
        assert start.status_code == 200, start.text
        opening = next(e for e in start.json()["events"] if e["event_type"] == "npc_opening")
        assert opening["payload"]["content"] == _pack_opening(s.pack_id, s.scenario_id), s.scenario_id


def test_demo_every_offered_difficulty_starts_a_session(demo_client):
    """Gate D-04: every card starts at every difficulty its card offers.

    The setup page renders exactly the card's ``difficulty.options`` and posts
    the chosen one; when the session resolved the built-in catalogue entry
    instead of the pack YAML, ``spanish_coffee`` offered four rungs but the
    built-in ladder had three, and "adversarial" answered 400.
    """
    client, _ = demo_client
    cards = {s["scenario_id"]: s for s in client.get("/api/scenarios").json()}
    for s in edition.DEMO_SCENARIOS:
        lang = cards[s.scenario_id]["supported_languages"][0]
        options = list(cards[s.scenario_id]["difficulty"]["options"])
        assert options, s.scenario_id
        for level in options:
            body = {**_session_body(s.scenario_id, lang), "difficulty": level}
            created = client.post("/api/sessions", json=body)
            assert created.status_code == 201, f"{s.scenario_id}@{level}: {created.text}"


def test_full_edition_resolution_order_is_unchanged(full_client):
    """The full app keeps catalogue-first resolution for catalogue ids."""
    from convsim_core.scenarios import SCENARIOS

    client, _ = full_client
    created = client.post("/api/sessions", json=_session_body("behavioral_interview"))
    assert created.status_code == 201, created.text
    start = client.post(f"/api/sessions/{created.json()['session_id']}/start")
    opening = next(e for e in start.json()["events"] if e["event_type"] == "npc_opening")
    assert opening["payload"]["content"] == SCENARIOS["behavioral_interview"].opening_npc_says


def test_demo_ignores_a_foreign_pack_that_reuses_a_curated_slug(tmp_path, monkeypatch):
    """The data directory is shared with the full app, which can hold a user pack
    whose scenario slug collides with a demo id. The demo must play (and list)
    the official pack's version, never the foreign one."""
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    foreign_scenario = (
        "schema_version: '0.1'\n"
        "scenario_id: the_ask\n"
        "title: Impostor Ask\n"
        "summary: A foreign pack reusing a demo slug.\n"
        "player_role:\n  label: Impostor\n  brief: You should never be playable in the demo.\n"
        "npc:\n  ref: ../npcs/host.yaml\n"
        "rubric:\n  ref: ../rubrics/intro_rubric.yaml\n"
        "duration:\n  max_turns: 5\n"
        "opening:\n  npc_says: IMPOSTOR OPENING\n"
        "goals:\n  player_visible:\n    - Nothing\n"
    )
    # Install the foreign pack through the FULL app (the demo refuses import).
    full_app = create_app(_config(tmp_path))
    with TestClient(full_app) as full:
        zip_bytes = make_pack_zip(
            tmp_path,
            manifest={"pack_id": "user.collision"},
            extra_files={"scenarios/the_ask.yaml": foreign_scenario},
        )
        resp = full.post(
            "/api/packs/import/zip",
            files={"file": ("pack.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 201, resp.text

    demo_app = create_app(_config(tmp_path, edition="demo"))
    with TestClient(demo_app) as demo:
        cards = [s for s in demo.get("/api/scenarios").json() if s["scenario_id"] == "the_ask"]
        assert [c["pack_id"] for c in cards] == ["official.dating_confidence_boundaries"]
        created = demo.post("/api/sessions", json=_session_body("the_ask"))
        assert created.status_code == 201, created.text
        start = demo.post(f"/api/sessions/{created.json()['session_id']}/start")
        opening = next(e for e in start.json()["events"] if e["event_type"] == "npc_opening")
        assert opening["payload"]["content"] == _pack_opening(
            "official.dating_confidence_boundaries", "the_ask"
        )
        assert "IMPOSTOR" not in opening["payload"]["content"]


# ── Demo edition: every model route, not just the two install routes ──────────


def test_demo_refuses_register_gguf(demo_client, tmp_path):
    client, _ = demo_client
    gguf = tmp_path / "anything.gguf"
    gguf.write_bytes(b"GGUF")
    resp = client.post("/api/models/register-gguf", json={"path": str(gguf)})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_refuses_switching_to_ollama(demo_client):
    client, _ = demo_client
    resp = client.post("/api/models/use", json={"runtime_id": "ollama", "model_id": "llama3:latest"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_refuses_foreign_model_path_on_use_and_sidecar(demo_client, tmp_path):
    client, _ = demo_client
    foreign = tmp_path / "foreign.gguf"
    foreign.write_bytes(b"GGUF")
    resp = client.post("/api/models/use", json={"runtime_id": "llama_cpp", "model_id": str(foreign)})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED
    resp = client.post("/api/sidecar/start", json={"model_path": str(foreign)})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_model_own_install_path_is_accepted_by_the_path_guard(demo_client, tmp_path):
    """The guard is about *which* model, not about whether the engine can start."""
    from convsim_core.services.model_manager_service import create_install_record

    client, app = demo_client
    conn = app.state.db.connection()
    models_dir = tmp_path / "models" / "llm"
    models_dir.mkdir(parents=True, exist_ok=True)
    create_install_record(
        conn,
        registry_id=_STARTER_MODEL_ID,
        filename=f"{_STARTER_MODEL_ID}.gguf",
        file_path=str(models_dir / f"{_STARTER_MODEL_ID}.gguf"),
    )
    paths = edition.demo_model_paths(conn, app.state.service_config)
    assert paths and all(p.endswith(f"{_STARTER_MODEL_ID}.gguf") for p in paths)
    # A foreign path is still refused once the curated install exists.
    resp = client.post("/api/sidecar/start", json={"model_path": str(tmp_path / "other.gguf")})
    assert resp.status_code == 403


def test_demo_refuses_pack_export(demo_client):
    client, _ = demo_client
    for slug in ("official.job_interview_basic", "tutorial.first_words"):
        resp = client.get(f"/api/packs/{slug}/export")
        assert resp.status_code == 403, slug
        assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_refuses_folder_import(demo_client, tmp_path):
    from tests.helpers import make_pack_dir

    client, _ = demo_client
    pack_dir = make_pack_dir(tmp_path / "folder-src")
    resp = client.post("/api/packs/import/folder", json={"path": str(pack_dir)})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == edition.EDITION_RESTRICTED


def test_demo_skips_the_ollama_probe_and_full_edition_runs_it(demo_client, full_client):
    probe = AsyncMock(return_value=[])
    with patch("convsim_core.routers.models._detect_ollama_models", probe):
        demo_client[0].get("/api/models")
        assert probe.await_count == 0
        full_client[0].get("/api/models")
        assert probe.await_count == 1


def test_demo_pin_that_is_not_in_the_registry_falls_back_to_the_starter(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    app = create_app(_config(tmp_path, edition="demo", demo_model_id="does-not-exist"))
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["demo"]["model_id"] == _STARTER_MODEL_ID
        registry = client.get("/api/models").json()["registry"]
        assert [m["id"] for m in registry] == [_STARTER_MODEL_ID]
        with patch("convsim_core.routers.setup_install._run_pipeline", new_callable=AsyncMock):
            resp = client.post("/api/setup/install", json={"registry_id": _STARTER_MODEL_ID})
        assert resp.status_code == 200, resp.text
