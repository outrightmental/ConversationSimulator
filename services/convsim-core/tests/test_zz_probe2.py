import shutil, json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.flyting.loader import clear_scenario_cache

_FLYTING_PACK = Path(__file__).resolve().parents[3] / "packs" / "official" / "flyting-school"


@pytest.fixture()
def fclient(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper"))
    clear_scenario_cache()
    root = tmp_path / "official"; root.mkdir()
    shutil.copytree(_FLYTING_PACK, root / "flyting-school")
    config = ServiceConfig(
        host="127.0.0.1", port=7399,
        data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"), packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"), cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"), models_dir=str(tmp_path / "models"),
        official_packs_dir=str(root), runtime_id="fake",
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c
    clear_scenario_cache()


def test_probe_bout(fclient):
    r = fclient.post("/api/flyting/sessions", json={
        "scenario_id": "dockside_parley", "play_format": "bout", "runtime_id": "fake"})
    sid = r.json()["session_id"]
    detail = fclient.get(f"/api/flyting/sessions/{sid}").json()
    print("OPENING:", detail["opening"][:80])
    lines = [
        "Your charter is wet paper and your crew knows it, captain.",
        "You call that a ship; the harbour calls it ballast.",
        "Your thrift is famous: you salvage even your own excuses.",
    ]
    npc_lines = []
    for t in lines:
        d = fclient.post(f"/api/flyting/sessions/{sid}/volley", json={"content": t}).json()
        pv, nv = d["player_volley"], d["npc_volley"]
        npc_lines.append(d["npc_line"])
        print(f"  P={pv['score']:4d} N={nv['score'] if nv else None} mom={d['exchange']} round={d['run']['round_number']} "
              f"pt={d['run']['player_total']} nt={d['run']['npc_total']} F={pv['composition']['freshness']}")
    # parrot the opponent
    d = fclient.post(f"/api/flyting/sessions/{sid}/volley", json={"content": npc_lines[-1]}).json()
    pv = d["player_volley"]
    print("  PARROT score=", pv["score"], "F=", pv["composition"]["freshness"],
          "nearest=", pv["freshness"]["nearest_source"])
    assert pv["freshness"]["nearest_source"] == "session", pv["freshness"]
