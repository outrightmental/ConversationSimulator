# SPDX-License-Identifier: Apache-2.0
"""Packaged-build smoke tests: official pack seeding guarantee.

These tests run against the *real* packs/official directory in the repository
to verify the guarantee that an installed build never boots into an empty
library.  They simulate the startup sequence of a packaged app and assert:

  1. All five official packs seed successfully.
  2. Each pack's scenarios are browseable via GET /api/scenarios.
  3. GET /api/packs returns ≥ 4 packs (the minimum DoD requirement).
  4. The response shape matches what the web frontend expects
     ({packs: [...], total: N} with pack_id, name, scenario_count fields).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


# Resolve the repo's bundled packs/official directory the same way config.py
# does in dev mode (no _MEIPASS): walk up from this file to the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS_DIR = _REPO_ROOT / "packs" / "official"

# Official pack IDs expected in a packaged build.
_EXPECTED_PACK_IDS = {
    "official.job_interview_basic",
    "official.everyday_negotiation",
    "official.difficult_conversations",
    "official.language_cafe",
    "official.dating_confidence_boundaries",
}

MINIMUM_OFFICIAL_PACKS = 4


@pytest.fixture(scope="module")
def seeded_client(tmp_path_factory):
    """TestClient with all official packs seeded from the real bundled directory."""
    tmp_path = tmp_path_factory.mktemp("smoke")

    if not _OFFICIAL_PACKS_DIR.is_dir():
        pytest.skip(f"Official packs directory not found: {_OFFICIAL_PACKS_DIR}")

    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_OFFICIAL_PACKS_DIR),
        runtime_id="fake",
    )
    app = create_app(config)
    with TestClient(app) as client:
        yield client


class TestOfficialPackSeedingGuarantee:
    def test_pack_count_meets_minimum(self, seeded_client):
        """GET /api/packs returns at least the minimum required official pack count."""
        resp = seeded_client.get("/api/packs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= MINIMUM_OFFICIAL_PACKS, (
            f"Expected ≥{MINIMUM_OFFICIAL_PACKS} official packs, got {body['total']}"
        )

    def test_response_shape_matches_frontend_contract(self, seeded_client):
        """GET /api/packs response shape matches the web frontend's PacksResponse type."""
        resp = seeded_client.get("/api/packs")
        assert resp.status_code == 200
        body = resp.json()
        assert "packs" in body and "total" in body
        assert isinstance(body["packs"], list)
        assert body["total"] == len(body["packs"])
        for item in body["packs"]:
            assert "pack_id" in item, "Missing pack_id field"
            assert "name" in item, "Missing name field"
            assert "scenario_count" in item, "Missing scenario_count field"

    def test_all_expected_packs_present(self, seeded_client):
        """All five expected official pack IDs are installed."""
        resp = seeded_client.get("/api/packs")
        assert resp.status_code == 200
        installed_ids = {p["pack_id"] for p in resp.json()["packs"]}
        missing = _EXPECTED_PACK_IDS - installed_ids
        assert not missing, f"Expected official packs missing: {missing}"

    def test_each_pack_has_at_least_one_scenario(self, seeded_client):
        """Every seeded official pack exposes at least one scenario."""
        resp = seeded_client.get("/api/packs")
        assert resp.status_code == 200
        for pack in resp.json()["packs"]:
            assert pack["scenario_count"] >= 1, (
                f"Pack '{pack['pack_id']}' has no scenarios"
            )

    def test_scenarios_endpoint_is_non_empty(self, seeded_client):
        """GET /api/scenarios returns at least one scenario per official pack."""
        resp = seeded_client.get("/api/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        pack_ids_with_scenarios = {s["pack_id"] for s in scenarios}
        for expected_id in _EXPECTED_PACK_IDS:
            assert expected_id in pack_ids_with_scenarios, (
                f"No scenarios found for pack '{expected_id}'"
            )

    def test_reseed_is_idempotent(self, seeded_client):
        """POST /api/packs/reseed returns 0 when all packs are already current."""
        resp = seeded_client.post("/api/packs/reseed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] == 0
