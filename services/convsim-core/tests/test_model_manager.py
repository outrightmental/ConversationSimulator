# SPDX-License-Identifier: Apache-2.0
"""Tests for the model manager API: install guard, use-model, benchmark, and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import convsim_core.runtime  # noqa: F401 — register built-in adapters
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.runtime.types import (
    ChatFinal,
    ChatToken,
    RuntimeHealth,
    RuntimeStatus,
)
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_active_config,
    get_installed_models,
    get_latest_benchmark,
    save_benchmark_result,
    set_active_config,
)
from convsim_core.services.model_registry_service import load_and_persist_registry
from convsim_core.storage.database import Database

_REGISTRY_PATH = Path(__file__).parent.parent.parent.parent / "model-registry" / "registry.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(tmp_path):
    database = Database.open(str(tmp_path / "db"))
    yield database
    database.close()


# ── GET /api/models (integration) ─────────────────────────────────────────────


def test_get_models_empty_state_has_all_sections(client):
    body = client.get("/api/models").json()
    assert body["registry"] == []
    assert body["installed"] == []
    assert body["ollama_models"] == []
    assert body["active"] == {"runtime_id": None, "model_id": None}
    assert body["total"] == 0
    assert "runtime_health" in body


def test_get_models_runtime_health_present(client):
    body = client.get("/api/models").json()
    health = body["runtime_health"]
    assert health["runtime_id"] == "fake"
    assert health["status"] == "ready"


def test_get_models_after_registry_load(client):
    load_and_persist_registry(client.app.state.db.connection(), _REGISTRY_PATH)
    body = client.get("/api/models").json()
    assert body["total"] > 0
    assert len(body["registry"]) == body["total"]


# ── model_manager_service: install records ────────────────────────────────────


def _insert_registry_model(conn, model_id: str) -> None:
    """Helper: insert a minimal model_registry row to satisfy the FK constraint."""
    conn.execute(
        """INSERT OR IGNORE INTO model_registry (id, name, provider)
           VALUES (?, ?, 'test')""",
        (model_id, model_id),
    )
    conn.commit()


def test_create_install_record_returns_id(db):
    # Use None registry_id to bypass the FK constraint in a pure service test
    install_id = create_install_record(db.connection(), None, "my-model.gguf", "")
    assert isinstance(install_id, int)
    assert install_id > 0


def test_installed_models_initially_empty(db):
    assert get_installed_models(db.connection()) == []


def test_create_install_record_shows_pending_status(db):
    _insert_registry_model(db.connection(), "my-model")
    create_install_record(db.connection(), "my-model", "my-model.gguf", "/tmp/my-model.gguf")
    rows = get_installed_models(db.connection())
    assert len(rows) == 1
    assert rows[0]["install_status"] == "pending"
    assert rows[0]["registry_id"] == "my-model"
    assert rows[0]["filename"] == "my-model.gguf"


def test_get_installed_models_ordered_by_newest_first(db):
    _insert_registry_model(db.connection(), "model-a")
    _insert_registry_model(db.connection(), "model-b")
    create_install_record(db.connection(), "model-a", "a.gguf", "")
    create_install_record(db.connection(), "model-b", "b.gguf", "")
    rows = get_installed_models(db.connection())
    assert len(rows) == 2
    # The last inserted record (model-b) should appear first due to ORDER BY DESC
    assert rows[0]["registry_id"] == "model-b"


# ── model_manager_service: active config ─────────────────────────────────────


def test_active_config_initially_empty(db):
    cfg = get_active_config(db.connection())
    assert cfg == {"runtime_id": None, "model_id": None}


def test_set_and_get_active_config_with_model(db):
    set_active_config(db.connection(), runtime_id="ollama", model_id="llama3.2:latest")
    cfg = get_active_config(db.connection())
    assert cfg["runtime_id"] == "ollama"
    assert cfg["model_id"] == "llama3.2:latest"


def test_set_active_config_clears_model_id_when_none(db):
    set_active_config(db.connection(), runtime_id="ollama", model_id="llama3.2:latest")
    set_active_config(db.connection(), runtime_id="fake", model_id=None)
    cfg = get_active_config(db.connection())
    assert cfg["runtime_id"] == "fake"
    assert cfg["model_id"] is None


def test_set_active_config_is_idempotent(db):
    set_active_config(db.connection(), runtime_id="ollama", model_id="llama3.2")
    set_active_config(db.connection(), runtime_id="llama_cpp", model_id="my-model")
    cfg = get_active_config(db.connection())
    assert cfg["runtime_id"] == "llama_cpp"
    assert cfg["model_id"] == "my-model"


# ── model_manager_service: benchmark persistence ──────────────────────────────


def test_save_benchmark_result_and_retrieve(db):
    save_benchmark_result(
        db.connection(),
        model_id="fake-small",
        runtime_id="fake",
        tokens_per_sec=123.45,
        context_length=4096,
        warnings=[],
        prompt_used="Say hello",
        output_tokens=10,
    )
    result = get_latest_benchmark(db.connection(), "fake-small", "fake")
    assert result is not None
    assert result["model_id"] == "fake-small"
    assert result["runtime_id"] == "fake"
    assert result["tokens_per_sec"] == pytest.approx(123.45)
    assert result["context_length"] == 4096
    assert result["warnings"] == []
    assert result["output_tokens"] == 10


def test_benchmark_warnings_round_trip(db):
    warnings = ["token count was 0", "fast runtime"]
    save_benchmark_result(
        db.connection(),
        model_id="fake-small",
        runtime_id="fake",
        tokens_per_sec=50.0,
        warnings=warnings,
    )
    result = get_latest_benchmark(db.connection(), "fake-small", "fake")
    assert result["warnings"] == warnings


def test_get_latest_benchmark_returns_most_recent(db):
    save_benchmark_result(
        db.connection(), model_id="m", runtime_id="r", tokens_per_sec=10.0
    )
    save_benchmark_result(
        db.connection(), model_id="m", runtime_id="r", tokens_per_sec=20.0
    )
    result = get_latest_benchmark(db.connection(), "m", "r")
    assert result["tokens_per_sec"] == pytest.approx(20.0)


def test_get_latest_benchmark_none_when_missing(db):
    assert get_latest_benchmark(db.connection(), "does-not-exist", "fake") is None


# ── POST /api/models/install ─────────────────────────────────────────────────


def _load_registry(client):
    load_and_persist_registry(client.app.state.db.connection(), _REGISTRY_PATH)


def test_install_rejects_unknown_model(client):
    resp = client.post("/api/models/install", json={"registry_id": "does-not-exist"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_install_rejects_user_supplied_model(client):
    _load_registry(client)
    resp = client.post("/api/models/install", json={"registry_id": "user-supplied-gguf"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSTALL_NOT_APPLICABLE"


def test_install_rejects_model_with_pending_sha256(client):
    """The explicit-download guard must reject models that have PENDING checksums."""
    conn = client.app.state.db.connection()
    conn.execute(
        """INSERT INTO model_registry (id, name, provider, license_spdx, sha256, source_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("pending-sha-model", "Pending SHA Model", "test", "MIT", "PENDING", "registry"),
    )
    conn.commit()
    resp = client.post("/api/models/install", json={"registry_id": "pending-sha-model"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MISSING_CHECKSUM"


def test_install_rejects_model_without_license(client):
    """A registry entry with no license must be rejected."""
    _load_registry(client)
    conn = client.app.state.db.connection()
    # Insert a test model with a real sha256 but no license
    conn.execute(
        """
        INSERT INTO model_registry
            (id, name, provider, license_spdx, sha256, source_type)
        VALUES (?, ?, ?, NULL, ?, ?)
        """,
        ("test-no-license", "Test No License", "test", "a" * 64, "registry"),
    )
    conn.commit()
    resp = client.post("/api/models/install", json={"registry_id": "test-no-license"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MISSING_LICENSE"


def test_install_accepted_when_license_and_sha256_present(client):
    """A model with valid license and real sha256 must be accepted."""
    _load_registry(client)
    conn = client.app.state.db.connection()
    conn.execute(
        """
        INSERT INTO model_registry
            (id, name, provider, license_spdx, sha256, source_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "test-valid-model",
            "Test Valid Model",
            "test",
            "MIT",
            "a" * 64,
            "registry",
        ),
    )
    conn.commit()
    resp = client.post("/api/models/install", json={"registry_id": "test-valid-model"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["registry_id"] == "test-valid-model"
    assert isinstance(body["install_id"], int)


def test_install_creates_record_in_installed_models(client):
    _load_registry(client)
    conn = client.app.state.db.connection()
    conn.execute(
        """INSERT INTO model_registry (id, name, provider, license_spdx, sha256, source_type)
           VALUES ('valid-m', 'V', 'p', 'MIT', ?, 'registry')""",
        ("b" * 64,),
    )
    conn.commit()
    client.post("/api/models/install", json={"registry_id": "valid-m"})
    rows = get_installed_models(conn)
    assert any(r["registry_id"] == "valid-m" and r["install_status"] == "pending" for r in rows)


# ── POST /api/models/use ─────────────────────────────────────────────────────


def test_use_model_rejects_unknown_runtime(client):
    resp = client.post("/api/models/use", json={"runtime_id": "nonexistent_runtime"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNKNOWN_RUNTIME"


def test_use_model_fake_runtime_succeeds(client):
    resp = client.post("/api/models/use", json={"runtime_id": "fake"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["runtime_id"] == "fake"
    assert body["status"] == "ready"
    assert "Fake" in body["runtime_name"]


def test_use_model_persists_active_config(client):
    client.post("/api/models/use", json={"runtime_id": "fake", "model_id": "fake-small"})
    cfg = get_active_config(client.app.state.db.connection())
    assert cfg["runtime_id"] == "fake"
    assert cfg["model_id"] == "fake-small"


def test_use_model_active_config_appears_in_models_response(client):
    client.post("/api/models/use", json={"runtime_id": "fake", "model_id": "fake-large"})
    body = client.get("/api/models").json()
    assert body["active"]["runtime_id"] == "fake"
    assert body["active"]["model_id"] == "fake-large"


def test_use_model_active_config_appears_in_health_response(client):
    client.post("/api/models/use", json={"runtime_id": "fake", "model_id": "fake-small"})
    health = client.get("/api/health").json()
    assert health["active_model"]["runtime_id"] == "fake"
    assert health["active_model"]["model_id"] == "fake-small"


def _make_unavailable_runtime():
    """Return a fake ChatRuntime whose health always reports UNAVAILABLE."""
    rt = MagicMock()
    rt.id = "ollama"
    rt.display_name = "Ollama (local)"
    rt.health = AsyncMock(
        return_value=RuntimeHealth(
            runtime_id="ollama",
            runtime_name="Ollama (local)",
            status=RuntimeStatus.UNAVAILABLE,
            message="Ollama is not reachable",
            checked_at="2026-01-01T00:00:00+00:00",
        )
    )
    return rt


def test_use_model_ollama_runtime_returns_error_when_unavailable(client, monkeypatch):
    """use_model must return 503 when the requested runtime is unreachable."""
    import convsim_core.routers.models as models_module

    monkeypatch.setattr(models_module, "build_runtime", lambda _id: _make_unavailable_runtime())
    resp = client.post("/api/models/use", json={"runtime_id": "ollama"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"


def test_use_model_llama_cpp_returns_error_when_unavailable(client, monkeypatch):
    """use_model must return 503 for llama_cpp when the server is not running."""
    import convsim_core.routers.models as models_module

    rt = MagicMock()
    rt.id = "llama_cpp"
    rt.display_name = "llama.cpp (local)"
    rt.health = AsyncMock(
        return_value=RuntimeHealth(
            runtime_id="llama_cpp",
            runtime_name="llama.cpp (local)",
            status=RuntimeStatus.UNAVAILABLE,
            message="Cannot connect to llama-server",
            checked_at="2026-01-01T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(models_module, "build_runtime", lambda _id: rt)
    resp = client.post("/api/models/use", json={"runtime_id": "llama_cpp"})
    assert resp.status_code == 503
    assert "llama" in resp.json()["error"]["message"].lower()


# ── POST /api/models/benchmark ───────────────────────────────────────────────


def test_benchmark_returns_200_with_fake_runtime(client):
    resp = client.post("/api/models/benchmark", json={})
    assert resp.status_code == 200


def test_benchmark_response_shape(client):
    body = client.post("/api/models/benchmark", json={}).json()
    assert "model_id" in body
    assert "runtime_id" in body
    assert "tokens_per_sec" in body
    assert isinstance(body["tokens_per_sec"], (int, float))
    assert isinstance(body["warnings"], list)
    assert isinstance(body["output_tokens"], int)
    assert body["output_tokens"] > 0
    assert "benchmarked_at" in body


def test_benchmark_persists_result(client):
    body = client.post("/api/models/benchmark", json={}).json()
    model_id = body["model_id"]
    runtime_id = body["runtime_id"]
    saved = get_latest_benchmark(
        client.app.state.db.connection(), model_id, runtime_id
    )
    assert saved is not None
    assert saved["tokens_per_sec"] == pytest.approx(body["tokens_per_sec"])


def test_benchmark_uses_active_model_id(client):
    client.post("/api/models/use", json={"runtime_id": "fake", "model_id": "fake-large"})
    body = client.post("/api/models/benchmark", json={}).json()
    assert body["model_id"] == "fake-large"


def test_benchmark_context_length_from_fake_runtime(client):
    # fake-small has context_length=4096 in the fake runtime
    resp = client.post("/api/models/benchmark", json={"model_id": "fake-small"})
    body = resp.json()
    assert body["context_length"] == 4096


def test_benchmark_runtime_unavailable_returns_503(client, monkeypatch):
    import convsim_core.routers.models as models_module

    unavailable_health = RuntimeHealth(
        runtime_id="fake",
        runtime_name="Fake",
        status=RuntimeStatus.UNAVAILABLE,
        message="Runtime is down",
        checked_at="2026-01-01T00:00:00+00:00",
    )
    original_runtime = client.app.state.runtime
    patched = MagicMock(wraps=original_runtime)
    patched.health = AsyncMock(return_value=unavailable_health)
    client.app.state.runtime = patched
    resp = client.post("/api/models/benchmark", json={})
    client.app.state.runtime = original_runtime
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"
