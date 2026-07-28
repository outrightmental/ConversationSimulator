# SPDX-License-Identifier: Apache-2.0
"""Startup must seed the model registry from the bundled catalogue.

A fresh profile previously had an EMPTY model_registry table — nothing in the
app ever called ``load_and_persist_registry`` — so the Welcome screen had no
starter model to offer and "Set me up" dead-ended with MODEL_NOT_FOUND before
any download began. These tests pin the seeded startup state a new user's
first session depends on.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def fresh_client(tmp_path):
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        model_registry_path=str(_REPO_ROOT / "model-registry" / "registry.yaml"),
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


def test_fresh_profile_has_seeded_model_registry(fresh_client):
    resp = fresh_client.get("/api/models")
    assert resp.status_code == 200
    registry = resp.json()["registry"]
    assert registry, "fresh profile must offer models from the bundled registry"
    roles = {m["role"] for m in registry}
    assert "starter" in roles, "the Set-me-up flow requires a starter-role model"


def test_setup_install_accepts_the_starter_model(fresh_client):
    registry = fresh_client.get("/api/models").json()["registry"]
    starter = next(m for m in registry if m["role"] == "starter")
    resp = fresh_client.post("/api/setup/install", json={"registry_id": starter["id"]})
    # 200 — the pipeline job is created (the engine stage may later skip or
    # download; what must never happen on a fresh install is MODEL_NOT_FOUND).
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["registry_id"] == starter["id"]
    assert job["status"] in ("pending", "running")
    # Cancel immediately: this test asserts admission, not the download.
    fresh_client.delete(f"/api/setup/install/{job['id']}")


def test_missing_registry_file_does_not_break_startup(tmp_path):
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        model_registry_path=str(tmp_path / "nope" / "registry.yaml"),
    )
    app = create_app(config)
    with TestClient(app) as c:
        resp = c.get("/api/models")
        assert resp.status_code == 200
        assert resp.json()["registry"] == []
