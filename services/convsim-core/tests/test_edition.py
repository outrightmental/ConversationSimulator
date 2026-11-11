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
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.services.model_registry_service import load_and_persist_registry
from tests.helpers import make_pack_zip

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"
_REGISTRY_PATH = _REPO_ROOT / "model-registry" / "registry.yaml"

_STARTER_MODEL_ID = "qwen3-4b-instruct-2507-q4_k_m"


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


# ── Demo edition: a full-app profile's other model is not the demo's ──────────
#
# The demo shares the full app's data root (D-06). A player who used the full
# app before v0.4 has the earlier starter installed and selected; the v0.4
# registry sync keeps that model's registry row, and the demo now resolves the
# new starter. The demo must play only its own model's files: it must not start
# the engine on the full app's selection, and it must report its own model as
# missing, so the player is sent to the demo's one-click install.

_EARLIER_STARTER_ID = "qwen3-4b-instruct-q4_k_m"


def _unreachable_llama_url() -> str:
    """A loopback URL nothing listens on, so no llama_cpp health probe made by
    these tests reaches a real engine running on this machine."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _registry_entry(registry_id: str, role: str) -> dict:
    """A registry entry shaped like the bundled starter, under another id."""
    import copy

    data = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8"))
    starter = next(m for m in data["models"] if m["id"] == _STARTER_MODEL_ID)
    entry = copy.deepcopy(starter)
    entry["id"] = registry_id
    entry["name"] = f"{registry_id} (test)"
    entry["role"] = role
    return entry


def _install_ready(conn, models_dir: Path, registry_id: str) -> str:
    """A ready install record for *registry_id*, with its file on disk."""
    from convsim_core.services.model_manager_service import (
        create_install_record,
        mark_install_ready,
    )

    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / f"{registry_id}.gguf"
    path.write_bytes(b"GGUF")
    install_id = create_install_record(
        conn, registry_id=registry_id, filename=path.name, file_path=str(path)
    )
    mark_install_ready(conn, install_id, size_bytes=4, verified_sha256="0" * 64, file_path=str(path))
    return str(path)


def _settle_autostart(client: TestClient, app) -> None:
    """Wait for the startup autostart task, which runs on the client's loop."""
    import asyncio

    async def _wait() -> None:
        tasks = list(getattr(app.state, "_autostart_tasks", None) or ())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    client.portal.call(_wait)


@pytest.fixture()
def earlier_starter_root(tmp_path, monkeypatch):
    """A data root the full app left with the earlier starter installed and selected."""
    from convsim_core.runtime.sidecar import LlamaCppSidecar
    from convsim_core.services.model_manager_service import set_active_config
    from convsim_core.services.model_registry_service import upsert_registry_models

    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    monkeypatch.setenv("CONVSIM_LLAMA_CPP_BASE_URL", _unreachable_llama_url())
    # An engine executable is present, so a missing model is the only reason
    # an autostart can skip; the start itself is recorded, never run.
    monkeypatch.setattr(
        "convsim_core.runtime.sidecar.find_executable", lambda: "/fake/llama-server"
    )
    start = AsyncMock()
    monkeypatch.setattr(LlamaCppSidecar, "start", start)

    full = create_app(_config(tmp_path))
    with TestClient(full) as client:
        conn = full.state.db.connection()
        # The v0.3 registry row stays behind: registry sync never deletes rows.
        upsert_registry_models(conn, [_registry_entry(_EARLIER_STARTER_ID, "starter")])
        earlier = _install_ready(conn, tmp_path / "models" / "llm", _EARLIER_STARTER_ID)
        set_active_config(conn, runtime_id="llama_cpp", model_id=earlier)
        resp = client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})
        assert resp.status_code == 204
    start.reset_mock()
    return {"tmp_path": tmp_path, "earlier": earlier, "start": start}


def test_demo_does_not_autostart_the_full_apps_earlier_starter(earlier_starter_root):
    from convsim_core.runtime.active import ensure_llama_sidecar_running, find_ready_model_path

    root = earlier_starter_root
    demo = create_app(_config(root["tmp_path"], edition="demo"))
    with TestClient(demo) as client:
        _settle_autostart(client, demo)
        assert root["start"].await_count == 0
        conn = demo.state.db.connection()
        config = demo.state.service_config
        assert edition.resolve_demo_model_id(conn, config) == _STARTER_MODEL_ID
        assert find_ready_model_path(conn, config) is None
        # An explicit path to that file does not load it either.
        started = client.portal.call(
            lambda: ensure_llama_sidecar_running(demo, model_path=root["earlier"])
        )
        assert started is None
        assert root["start"].await_count == 0
        # "Use model" says the model is missing, not that the engine failed.
        resp = client.post("/api/models/use", json={"runtime_id": "llama_cpp"})
        assert resp.status_code == 503
        assert "No AI model is installed yet" in resp.json()["error"]["message"]
        assert root["start"].await_count == 0


def test_full_edition_still_autostarts_the_earlier_starter(earlier_starter_root):
    """The full app keeps playing whatever its player selected."""
    from convsim_core.runtime.active import find_ready_model_path

    root = earlier_starter_root
    full = create_app(_config(root["tmp_path"]))
    with TestClient(full) as client:
        _settle_autostart(client, full)
        root["start"].assert_awaited_once()
        assert root["start"].await_args.kwargs["model_path"] == root["earlier"]
        conn = full.state.db.connection()
        assert find_ready_model_path(conn, full.state.service_config) == root["earlier"]
        assert find_ready_model_path(conn) == root["earlier"]


def test_demo_reports_its_model_missing_when_only_the_earlier_starter_is_installed(
    earlier_starter_root,
):
    root = earlier_starter_root
    demo = create_app(_config(root["tmp_path"], edition="demo"))
    with TestClient(demo) as client:
        status = client.get("/api/setup/status").json()
        assert status["kind"] == "incomplete"
        assert "llm-present" in status["missing"]
        # Home shows the demo's one-download prompt, not a ready model.
        assert client.get("/api/health").json()["runtime"]["llm_ready"] is False

    full = create_app(_config(root["tmp_path"]))
    with TestClient(full) as client:
        assert client.get("/api/setup/status").json()["kind"] == "ready"
        assert client.get("/api/health").json()["runtime"]["llm_ready"] is True


def test_demo_plays_its_own_install_when_another_model_is_selected(earlier_starter_root):
    """Once the demo model is installed it is the file the demo starts, even
    while the full app's selection names another model and a newer install of
    a third model exists."""
    from convsim_core.runtime.active import ensure_llama_sidecar_running, find_ready_model_path

    root = earlier_starter_root
    models_dir = root["tmp_path"] / "models" / "llm"
    demo = create_app(_config(root["tmp_path"], edition="demo"))
    with TestClient(demo) as client:
        conn = demo.state.db.connection()
        demo_path = _install_ready(conn, models_dir, _STARTER_MODEL_ID)
        _install_ready(conn, models_dir, "qwen3-8b-instruct-q4_k_m")  # the newest install
        assert find_ready_model_path(conn, demo.state.service_config) == demo_path
        started = client.portal.call(
            lambda: ensure_llama_sidecar_running(demo, model_path=root["earlier"])
        )
        assert started == demo_path
        assert root["start"].await_args.kwargs["model_path"] == demo_path

        assert client.get("/api/setup/status").json()["kind"] == "ready"
        assert client.get("/api/health").json()["runtime"]["llm_ready"] is True


# ── Demo edition: the full app's selection stays the full app's ───────────────
#
# The same shared data root (D-06), with the full app's selection naming a
# model the demo does not play: the earlier starter, the player's own GGUF or
# an Ollama tag. The demo's one-click install must leave that selection alone,
# every request the demo sends must be sampled for the demo model its engine
# runs, its records and checks must name that model, and it must boot the
# managed engine, never Ollama.

_OLLAMA_TAG = "llama3.1:8b"


def _select_earlier_starter(conn, models_dir: Path) -> str:
    """A pre-v0.4 full app: the earlier starter installed and selected."""
    from convsim_core.services.model_manager_service import set_active_config
    from convsim_core.services.model_registry_service import upsert_registry_models

    upsert_registry_models(conn, [_registry_entry(_EARLIER_STARTER_ID, "starter")])
    earlier = _install_ready(conn, models_dir, _EARLIER_STARTER_ID)
    set_active_config(conn, runtime_id="llama_cpp", model_id=earlier)
    return earlier


def _select_own_gguf(conn, models_dir: Path) -> str:
    """The full app's player registered their own GGUF and selected it."""
    from convsim_core.services.model_manager_service import register_user_gguf, set_active_config

    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / "my-own-model.gguf"
    path.write_bytes(b"GGUF")
    register_user_gguf(conn, path=str(path))
    set_active_config(conn, runtime_id="llama_cpp", model_id=str(path))
    return str(path)


def _select_ollama(conn, models_dir: Path) -> str:
    """The full app's player chose a model they run in Ollama."""
    from convsim_core.services.model_manager_service import set_active_config

    set_active_config(conn, runtime_id="ollama", model_id=_OLLAMA_TAG)
    return _OLLAMA_TAG


def _install_demo_model_file(conn, models_dir: Path) -> str:
    return _install_ready(conn, models_dir, _STARTER_MODEL_ID)


@pytest.fixture()
def shared_root(tmp_path, monkeypatch):
    """Factory: the data root the full app leaves once its *selects* ran.

    No engine is started or reached: the llama.cpp and Ollama URLs point at a
    loopback port nothing listens on, an engine executable is "present" so a
    missing model is the only reason an autostart can skip, and the engine
    start is recorded, never run. With no *selects* the root is left fresh.
    """
    from types import SimpleNamespace

    from convsim_core.runtime.sidecar import LlamaCppSidecar

    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    monkeypatch.setenv("CONVSIM_LLAMA_CPP_BASE_URL", _unreachable_llama_url())
    monkeypatch.setenv("CONVSIM_OLLAMA_BASE_URL", _unreachable_llama_url())
    monkeypatch.setattr(
        "convsim_core.runtime.sidecar.find_executable", lambda: "/fake/llama-server"
    )
    start = AsyncMock()
    monkeypatch.setattr(LlamaCppSidecar, "start", start)
    models_dir = tmp_path / "models" / "llm"

    def _make(*selects) -> SimpleNamespace:
        saved = None
        if selects:
            full = create_app(_config(tmp_path))
            with TestClient(full) as client:
                conn = full.state.db.connection()
                saved = [select(conn, models_dir) for select in selects][0]
                resp = client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})
                assert resp.status_code == 204
        start.reset_mock()
        return SimpleNamespace(tmp_path=tmp_path, models_dir=models_dir, start=start, saved=saved)

    return _make


def _install_demo_model(client: TestClient, app, models_dir: Path) -> str:
    """Run the one-click install pipeline for the demo model; return its file.

    The file is already on disk, so the pipeline takes its repair path (no
    download), and the engine reports running, so the warmup start and its
    probe are skipped: nothing is started or reached. What these tests check
    is the pipeline's last step: whether it saves its model as the selection.
    """
    import asyncio
    from unittest.mock import MagicMock

    from convsim_core.routers import setup_install
    from convsim_core.runtime.sidecar import SidecarState
    from convsim_core.services.setup_install_service import create_job, get_job

    conn = app.state.db.connection()
    path = _install_demo_model_file(conn, models_dir)
    job_id = create_job(conn, registry_id=_STARTER_MODEL_ID, model_label="Downloading the model")
    sidecar = MagicMock()
    sidecar.state = SidecarState.RUNNING

    async def _run() -> None:
        with patch.object(setup_install, "find_executable", return_value="/fake/llama-server"), \
             patch.object(setup_install, "seed_official_packs", return_value=0):
            await setup_install._run_pipeline(
                job_id=job_id,
                registry_id=_STARTER_MODEL_ID,
                model_label="Downloading the model",
                conn=conn,
                config=app.state.service_config,
                sidecar=sidecar,
                model_cancel_events={},
                cancel_event=asyncio.Event(),
                app=app,
            )

    client.portal.call(_run)
    assert get_job(conn, job_id)["status"] == "complete"
    return path


@pytest.mark.parametrize(
    "select",
    [_select_earlier_starter, _select_own_gguf, _select_ollama],
    ids=["earlier-starter", "own-gguf", "ollama"],
)
def test_demo_install_leaves_the_full_apps_selection_alone(shared_root, select):
    from convsim_core.runtime.active import find_ready_model_path
    from convsim_core.services.model_manager_service import get_active_config

    root = shared_root(select)
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        conn = demo.state.db.connection()
        before = get_active_config(conn)
        assert before["model_id"] == root.saved
        demo_path = _install_demo_model(client, demo, root.models_dir)
        assert get_active_config(conn) == before
        # The demo finds its own install without the selection naming it.
        assert find_ready_model_path(conn, demo.state.service_config) == demo_path
        assert client.get("/api/setup/status").json()["kind"] == "ready"
        assert client.get("/api/health").json()["runtime"]["llm_ready"] is True

    # The full app, opened next, plays what its player selected.
    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        _settle_autostart(client, full)
        assert get_active_config(full.state.db.connection()) == before
        assert full.state.runtime.id == before["runtime_id"]
        if before["runtime_id"] == "llama_cpp":
            assert root.start.await_args.kwargs["model_path"] == root.saved


def test_demo_install_saves_its_model_when_nothing_is_selected(shared_root):
    """On a root with no selection the demo saves its model, so a full app
    installed later finds it and offers no download (D-06)."""
    from convsim_core.services.model_manager_service import get_active_config

    root = shared_root()
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        conn = demo.state.db.connection()
        assert get_active_config(conn) == {"runtime_id": None, "model_id": None}
        demo_path = _install_demo_model(client, demo, root.models_dir)
        assert get_active_config(conn) == {"runtime_id": "llama_cpp", "model_id": demo_path}
        resp = client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})
        assert resp.status_code == 204

    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        _settle_autostart(client, full)
        assert full.state.runtime.id == "llama_cpp"
        assert root.start.await_args.kwargs["model_path"] == demo_path
        assert client.get("/api/setup/status").json()["kind"] == "ready"


def test_full_edition_install_still_saves_its_model_over_another_selection(shared_root):
    from convsim_core.services.model_manager_service import get_active_config

    root = shared_root(_select_own_gguf)
    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        installed = _install_demo_model(client, full, root.models_dir)
        assert get_active_config(full.state.db.connection()) == {
            "runtime_id": "llama_cpp",
            "model_id": installed,
        }


@pytest.mark.parametrize(
    ("runtime_id", "model_id", "demo_saves"),
    [
        (None, None, True),
        ("fake", None, True),
        ("scripted", None, True),
        ("llama_cpp", "<demo>", True),
        ("llama_cpp", None, False),
        ("llama_cpp", "<other>", False),
        ("ollama", _OLLAMA_TAG, False),
    ],
    ids=[
        "nothing", "fake", "scripted", "the-demo-model", "llama-cpp-newest-install",
        "another-file", "ollama",
    ],
)
def test_which_selections_the_demo_install_replaces(tmp_path, runtime_id, model_id, demo_saves):
    from convsim_core.routers.setup_install import _install_saves_selection
    from convsim_core.services.model_manager_service import set_active_config
    from convsim_core.storage.database import Database

    db = Database.open(str(tmp_path / "db"))
    try:
        conn = db.connection()
        load_and_persist_registry(conn, _REGISTRY_PATH)
        paths = {
            "<demo>": _install_demo_model_file(conn, tmp_path / "models"),
            "<other>": _install_ready(conn, tmp_path / "models", "qwen3-8b-instruct-q4_k_m"),
        }
        if runtime_id is not None:
            set_active_config(conn, runtime_id=runtime_id, model_id=paths.get(model_id, model_id))
        assert _install_saves_selection(conn, _config(tmp_path, edition="demo")) is demo_saves
        assert _install_saves_selection(conn, _config(tmp_path)) is True
    finally:
        db.close()


class _RecordingLlamaRuntime(FakeChatRuntime):
    """The fake engine under the llama.cpp id, keeping every request it is sent."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list = []

    @property
    def id(self) -> str:
        return "llama_cpp"

    def chat_stream(self, request):
        self.requests.append(request)
        return super().chat_stream(request)


def _unpinned_session_body(scenario_id: str = "behavioral_interview") -> dict:
    body = _session_body(scenario_id)
    body.pop("runtime_id")
    return body


def _play_turn_and_debrief(client: TestClient) -> dict:
    """Play one unpinned turn and the debrief; return the turn's timing record."""
    created = client.post("/api/sessions", json=_unpinned_session_body())
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]
    assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
    turn = client.post(f"/api/sessions/{session_id}/turn", json={"content": "I shipped it on time."})
    assert turn.status_code == 200, turn.text
    npc = next(e for e in turn.json()["events"] if e["event_type"] == "npc_turn")
    assert client.post(f"/api/sessions/{session_id}/end").status_code == 200
    debrief = client.post(f"/api/sessions/{session_id}/debrief")
    assert debrief.status_code == 200, debrief.text
    return npc["payload"]["timing"]


def _declared_sampling(registry_id: str) -> tuple[float, float]:
    data = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8"))
    block = next(m for m in data["models"] if m["id"] == registry_id)["runtime"]["llama_cpp"]
    return block["temperature_default"], block["top_p_default"]


def test_demo_samples_and_records_its_own_model_not_the_full_apps_selection(shared_root):
    """The full app selected the player's own GGUF, which has no registry
    sampling. The demo's engine runs the demo model, so every turn and the
    debrief are sent with the demo model's registry values, and the turn's
    timing record names the demo model."""
    from convsim_core.runtime.types import SamplingDefaults
    from convsim_core.services.model_registry_service import active_model_sampling

    temperature, top_p = _declared_sampling(_STARTER_MODEL_ID)
    root = shared_root(_select_own_gguf)
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        conn = demo.state.db.connection()
        _install_demo_model_file(conn, root.models_dir)
        assert active_model_sampling(conn, "llama_cpp", demo.state.service_config) == (
            SamplingDefaults(temperature=temperature, top_p=top_p)
        )
        # Without the config the full edition's rule applies: the selection.
        assert active_model_sampling(conn, "llama_cpp") == SamplingDefaults()

        runtime = _RecordingLlamaRuntime()
        demo.state.runtime = runtime
        timing = _play_turn_and_debrief(client)
    assert len(runtime.requests) >= 2, "a turn and the debrief"
    assert {(r.temperature, r.top_p) for r in runtime.requests} == {(temperature, top_p)}
    assert timing["context"]["registry_model_id"] == _STARTER_MODEL_ID


def test_full_edition_samples_and_records_its_selection(shared_root):
    """The full app keeps sampling and recording the model its player selected."""
    root = shared_root(_select_own_gguf)
    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        _install_demo_model_file(full.state.db.connection(), root.models_dir)
        runtime = _RecordingLlamaRuntime()
        full.state.runtime = runtime
        timing = _play_turn_and_debrief(client)
    assert len(runtime.requests) >= 2
    assert all(r.top_p is None for r in runtime.requests)
    assert timing["context"]["registry_model_id"] == "my-own-model.gguf"


def _llm_present(client: TestClient) -> dict:
    checks = client.get("/api/preflight").json()["checks"]
    return next(c for c in checks if c["id"] == "llm-present")


@pytest.mark.parametrize(
    "select",
    [_select_earlier_starter, _select_own_gguf, _select_ollama],
    ids=["earlier-starter", "own-gguf", "ollama"],
)
def test_demo_preflight_counts_only_the_demo_models_install(shared_root, select):
    """Support's AI-model check agrees with Home and the setup status: the full
    app's other installs and its selection are not the demo's model."""
    root = shared_root(select)
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        assert "llm-present" in client.get("/api/setup/status").json()["missing"]
        assert _llm_present(client)["status"] == "fail"
        _install_demo_model_file(demo.state.db.connection(), root.models_dir)
        check = _llm_present(client)
        assert check["status"] == "pass"
        assert check["message"] == "1 AI model installed and ready."

    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        assert _llm_present(client)["status"] == "pass"


def test_demo_boots_the_managed_engine_when_the_full_app_selected_ollama(shared_root):
    """A full-app profile on Ollama: the demo boots llama.cpp and starts it on
    the demo model, while the full app keeps booting Ollama."""
    from convsim_core.runtime.active import resolve_startup_runtime_id

    root = shared_root(_select_ollama, _install_demo_model_file)
    demo_path = str(root.models_dir / f"{_STARTER_MODEL_ID}.gguf")
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        _settle_autostart(client, demo)
        assert demo.state.runtime.id == "llama_cpp"
        root.start.assert_awaited_once()
        assert root.start.await_args.kwargs["model_path"] == demo_path
        conn = demo.state.db.connection()
        assert resolve_startup_runtime_id(conn, "fake", demo.state.service_config) == "llama_cpp"
        assert client.get("/api/setup/status").json()["kind"] == "ready"
        created = client.post("/api/sessions", json=_unpinned_session_body())
        assert created.status_code == 201, created.text

    root.start.reset_mock()
    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        _settle_autostart(client, full)
        assert full.state.runtime.id == "ollama"
        assert root.start.await_count == 0
        assert resolve_startup_runtime_id(full.state.db.connection(), "fake") == "ollama"


def test_demo_with_nothing_selected_keeps_the_config_default_runtime(shared_root):
    """A fresh demo profile boots the config default, so the no-model
    backstop (issue #473) still refuses an unpinned session."""
    from convsim_core.runtime.active import resolve_startup_runtime_id

    root = shared_root()
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        assert demo.state.runtime.id == "fake"
        conn = demo.state.db.connection()
        config = demo.state.service_config
        assert resolve_startup_runtime_id(conn, "fake", config) == "fake"
        # A model runtime other than the managed engine is not the demo's.
        assert resolve_startup_runtime_id(conn, "ollama", config) == "llama_cpp"
        assert client.post("/api/sessions", json=_unpinned_session_body()).status_code == 409


def test_demo_refuses_a_session_on_a_live_runtime_other_than_llama_cpp(shared_root):
    from convsim_core.runtime.active import activate_runtime

    root = shared_root(_select_ollama)
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        client.portal.call(activate_runtime, demo, "ollama")
        resp = client.post("/api/sessions", json=_unpinned_session_body())
        assert resp.status_code == 403, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == edition.EDITION_RESTRICTED
        assert "set to use Ollama (local)" in detail["message"]
        # A session pinned to a model-free runtime does not use the live one.
        pinned = client.post("/api/sessions", json=_session_body("behavioral_interview"))
        assert pinned.status_code == 201, pinned.text

    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        assert full.state.runtime.id == "ollama"
        created = client.post("/api/sessions", json=_unpinned_session_body())
        assert created.status_code == 201, created.text


@pytest.mark.parametrize(
    "select",
    [_select_earlier_starter, _select_own_gguf, _select_ollama],
    ids=["earlier-starter", "own-gguf", "ollama"],
)
def test_demo_without_its_model_refuses_a_session_like_a_fresh_profile(shared_root, select):
    """On a root the full app set up with another model, the demo boots its
    managed engine, but its model is not installed: an unpinned session is
    refused with the finish-setup 409 (#473), not started to fail with a 503
    on its first turn. The full app on the same root still plays its own."""
    root = shared_root(select)
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        _settle_autostart(client, demo)
        assert demo.state.runtime.id == "llama_cpp"
        resp = client.post("/api/sessions", json=_unpinned_session_body())
        assert resp.status_code == 409, resp.text
        assert "demo's AI model is not installed" in resp.json()["detail"]
        # Once the demo's model is installed the same request is accepted.
        _install_demo_model_file(demo.state.db.connection(), root.models_dir)
        created = client.post("/api/sessions", json=_unpinned_session_body())
        assert created.status_code == 201, created.text


def test_demo_rolling_speeds_follow_the_demo_model_not_the_full_apps_selection(shared_root):
    """The reply-start estimate reads /api/performance/rolling with no
    parameters. In the demo it counts the turns the demo model played, which
    are recorded under it, not the full app's selection."""
    root = shared_root(_select_own_gguf)
    demo = create_app(_config(root.tmp_path, edition="demo"))
    with TestClient(demo) as client:
        _install_demo_model_file(demo.state.db.connection(), root.models_dir)
        demo.state.runtime = _RecordingLlamaRuntime()
        assert client.get("/api/performance/rolling").json()["samples"] == 0
        _play_turn_and_debrief(client)
        assert client.get("/api/performance/rolling").json()["samples"] == 1

    full = create_app(_config(root.tmp_path))
    with TestClient(full) as client:
        # The full app's selection (the player's own GGUF) has no turns yet.
        assert client.get("/api/performance/rolling").json()["samples"] == 0
