# SPDX-License-Identifier: Apache-2.0
"""Tests for the model registry schema, service layer, SQLite persistence, and API."""

from pathlib import Path

import jsonschema
import pytest
import yaml

from convsim_core.schema_paths import get_schema
from convsim_core.services.model_registry_service import (
    RegistryValidationError,
    load_and_persist_registry,
    list_registry_models,
    load_registry_yaml,
    validate_registry,
)
from convsim_core.storage.database import Database

# Canonical registry file relative to this test file.
# tests/ → convsim-core/ → services/ → repo root → model-registry/registry.yaml
_REGISTRY_PATH = Path(__file__).parent.parent.parent.parent / "model-registry" / "registry.yaml"


@pytest.fixture(scope="module")
def registry_schema() -> dict:
    return get_schema("model-registry.schema.json")


@pytest.fixture
def valid_registry_entry() -> dict:
    return {
        "id": "test-model-q4-k-m",
        "name": "Test Model Q4_K_M",
        "family": "test",
        "role": "starter",
        "format": "gguf",
        "license": "MIT",
        "license_url": "https://opensource.org/licenses/MIT",
        "size_gb": 2.5,
        "hardware": {"min_vram_gb": 4, "recommended_vram_gb": 6},
        "download": {
            "provider": "huggingface",
            "url": "PENDING",
            "sha256": "PENDING",
        },
        "runtime": {
            "llama_cpp": {
                "context_length": 8192,
                "temperature_default": 0.75,
                "top_p_default": 0.9,
            }
        },
    }


@pytest.fixture
def valid_user_supplied_entry() -> dict:
    return {
        "id": "user-supplied-gguf",
        "name": "User-Supplied GGUF",
        "family": "unknown",
        "role": "user-supplied",
        "format": "gguf",
        "license": "unknown-user-supplied",
        "size_gb": None,
        "hardware": {"min_vram_gb": None, "recommended_vram_gb": None},
        "download": {
            "provider": "user-filesystem",
            "path_hint": "~/.convsim/models/",
        },
    }


def make_registry(models: list) -> dict:
    return {"schema_version": "0.1", "models": models}


# ── Schema validation: valid entries ─────────────────────────────────────────


def test_valid_registry_entry_passes(registry_schema, valid_registry_entry):
    jsonschema.validate(
        instance=make_registry([valid_registry_entry]), schema=registry_schema
    )


def test_valid_sha256_hex_passes(registry_schema, valid_registry_entry):
    valid_registry_entry["download"]["sha256"] = "a" * 64
    jsonschema.validate(
        instance=make_registry([valid_registry_entry]), schema=registry_schema
    )


def test_pending_sentinel_passes(registry_schema, valid_registry_entry):
    valid_registry_entry["download"]["sha256"] = "PENDING"
    jsonschema.validate(
        instance=make_registry([valid_registry_entry]), schema=registry_schema
    )


def test_user_supplied_entry_passes(registry_schema, valid_user_supplied_entry):
    jsonschema.validate(
        instance=make_registry([valid_user_supplied_entry]), schema=registry_schema
    )


def test_user_supplied_without_path_hint_passes(registry_schema, valid_user_supplied_entry):
    del valid_user_supplied_entry["download"]["path_hint"]
    jsonschema.validate(
        instance=make_registry([valid_user_supplied_entry]), schema=registry_schema
    )


def test_registry_with_multiple_models_passes(
    registry_schema, valid_registry_entry, valid_user_supplied_entry
):
    # Change user-supplied id to avoid conflict in a hypothetical single list
    valid_user_supplied_entry["id"] = "user-supplied-gguf-2"
    jsonschema.validate(
        instance=make_registry([valid_registry_entry, valid_user_supplied_entry]),
        schema=registry_schema,
    )


# ── Schema validation: invalid entries ───────────────────────────────────────


def test_missing_license_fails(registry_schema, valid_registry_entry):
    del valid_registry_entry["license"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_empty_license_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["license"] = ""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_missing_sha256_fails(registry_schema, valid_registry_entry):
    del valid_registry_entry["download"]["sha256"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_placeholder_sha256_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["download"]["sha256"] = "<placeholder>"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_invalid_sha256_length_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["download"]["sha256"] = "abc123"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_missing_size_gb_for_registry_model_fails(registry_schema, valid_registry_entry):
    del valid_registry_entry["size_gb"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_null_size_gb_for_registry_model_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["size_gb"] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_invalid_role_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["role"] = "ultra-mega-tier"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_invalid_format_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["format"] = "safetensors"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_missing_hardware_fails(registry_schema, valid_registry_entry):
    del valid_registry_entry["hardware"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_missing_download_fails(registry_schema, valid_registry_entry):
    del valid_registry_entry["download"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_user_supplied_with_wrong_license_fails(registry_schema, valid_user_supplied_entry):
    # user-supplied models MUST declare license as "unknown-user-supplied"
    valid_user_supplied_entry["license"] = "Apache-2.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_user_supplied_entry]), schema=registry_schema
        )


def test_user_supplied_with_registry_download_fails(registry_schema, valid_user_supplied_entry):
    valid_user_supplied_entry["download"] = {
        "provider": "huggingface",
        "url": "PENDING",
        "sha256": "PENDING",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_user_supplied_entry]), schema=registry_schema
        )


def test_registry_model_with_user_filesystem_provider_fails(
    registry_schema, valid_registry_entry
):
    valid_registry_entry["download"] = {"provider": "user-filesystem"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_null_min_vram_gb_for_registry_model_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["hardware"]["min_vram_gb"] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_missing_min_vram_gb_for_registry_model_fails(registry_schema, valid_registry_entry):
    valid_registry_entry["hardware"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=make_registry([valid_registry_entry]), schema=registry_schema
        )


def test_unknown_schema_version_fails(registry_schema, valid_registry_entry):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"schema_version": "9.9", "models": [valid_registry_entry]},
            schema=registry_schema,
        )


def test_empty_models_list_fails(registry_schema):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"schema_version": "0.1", "models": []}, schema=registry_schema
        )


# ── Bundled registry.yaml integration test ───────────────────────────────────


def test_actual_registry_file_validates(registry_schema):
    """The canonical model-registry/registry.yaml must pass schema validation."""
    assert _REGISTRY_PATH.exists(), f"Registry file not found: {_REGISTRY_PATH}"
    data = load_registry_yaml(_REGISTRY_PATH)
    validate_registry(data, registry_schema)


def test_actual_registry_has_all_required_tiers(registry_schema):
    """The registry must include at least one model per required tier."""
    data = load_registry_yaml(_REGISTRY_PATH)
    roles = {m["role"] for m in data["models"]}
    assert "starter" in roles
    assert "standard" in roles
    assert "high-quality" in roles
    assert "user-supplied" in roles


def test_actual_registry_no_model_weights():
    """No binary model weights are included in the repository."""
    registry_dir = _REGISTRY_PATH.parent
    for path in registry_dir.rglob("*"):
        if path.is_file():
            suffix = path.suffix.lower()
            assert suffix not in {".gguf", ".bin", ".safetensors", ".pt", ".ckpt"}, (
                f"Model weight file found in repository: {path}"
            )


# ── SQLite persistence tests ─────────────────────────────────────────────────


def test_registry_loads_into_sqlite(tmp_path):
    db = Database.open(str(tmp_path / "db"))
    try:
        count = load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        assert count > 0
        rows = list_registry_models(db.connection())
        ids = [r["id"] for r in rows]
        assert "user-supplied-gguf" in ids
    finally:
        db.close()


def test_registry_upsert_is_idempotent(tmp_path):
    db = Database.open(str(tmp_path / "db"))
    try:
        count1 = load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        count2 = load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        total = db.connection().execute(
            "SELECT COUNT(*) FROM model_registry"
        ).fetchone()[0]
        assert count1 == count2
        assert total == count1
    finally:
        db.close()


def test_registry_models_have_license_spdx_in_db(tmp_path):
    """All registry-managed models (not user-supplied) must store a license_spdx."""
    db = Database.open(str(tmp_path / "db"))
    try:
        load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        rows = db.connection().execute(
            "SELECT id, license_spdx FROM model_registry WHERE source_type = 'registry'"
        ).fetchall()
        assert rows, "No registry-managed models found in DB"
        for row in rows:
            assert row["license_spdx"], (
                f"Missing license_spdx for registry model id={row['id']}"
            )
    finally:
        db.close()


def test_registry_models_have_sha256_in_db(tmp_path):
    """All registry-managed models must store a sha256 value (even PENDING)."""
    db = Database.open(str(tmp_path / "db"))
    try:
        load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        rows = db.connection().execute(
            "SELECT id, sha256 FROM model_registry WHERE source_type = 'registry'"
        ).fetchall()
        assert rows, "No registry-managed models found in DB"
        for row in rows:
            assert row["sha256"], f"Missing sha256 for registry model id={row['id']}"
    finally:
        db.close()


def test_user_supplied_model_stored_correctly(tmp_path):
    """The user-supplied entry is correctly flagged in the DB."""
    db = Database.open(str(tmp_path / "db"))
    try:
        load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        row = db.connection().execute(
            "SELECT * FROM model_registry WHERE id = 'user-supplied-gguf'"
        ).fetchone()
        assert row is not None
        assert row["source_type"] == "user-supplied"
        assert row["license_spdx"] == "unknown-user-supplied"
        assert row["sha256"] is None
    finally:
        db.close()


def test_list_registry_models_returns_sorted_results(tmp_path):
    """list_registry_models should return models sorted by tier (starter first)."""
    db = Database.open(str(tmp_path / "db"))
    try:
        load_and_persist_registry(db.connection(), _REGISTRY_PATH)
        models = list_registry_models(db.connection())
        roles = [m["role"] for m in models]
        # starter(s) should appear before standard, which should appear before high-quality
        tier_order = {"starter": 0, "standard": 1, "high-quality": 2, "user-supplied": 3}
        sorted_roles = sorted(roles, key=lambda r: tier_order.get(r, 99))
        assert roles == sorted_roles
    finally:
        db.close()


def test_invalid_registry_raises_registry_validation_error(tmp_path):
    """A registry YAML that fails schema validation raises RegistryValidationError."""
    bad_path = tmp_path / "bad_registry.yaml"
    bad_data = {
        "schema_version": "0.1",
        "models": [
            {
                "id": "bad-model",
                "name": "Bad Model",
                "family": "test",
                "role": "standard",
                "format": "gguf",
                # intentionally missing: license, size_gb, hardware, download
            }
        ],
    }
    bad_path.write_text(yaml.dump(bad_data), encoding="utf-8")

    db = Database.open(str(tmp_path / "db"))
    try:
        with pytest.raises(RegistryValidationError):
            load_and_persist_registry(db.connection(), bad_path)
    finally:
        db.close()


def test_malformed_yaml_raises_registry_validation_error(tmp_path):
    """A registry file with a YAML syntax error raises RegistryValidationError."""
    bad_path = tmp_path / "malformed.yaml"
    bad_path.write_text("key: [unclosed bracket\n", encoding="utf-8")

    db = Database.open(str(tmp_path / "db"))
    try:
        with pytest.raises(RegistryValidationError, match="not valid YAML"):
            load_and_persist_registry(db.connection(), bad_path)
    finally:
        db.close()


# ── GET /api/models endpoint tests ───────────────────────────────────────────


def test_get_models_returns_200(client):
    resp = client.get("/api/models")
    assert resp.status_code == 200


def test_get_models_empty_database_returns_empty_list(client):
    body = client.get("/api/models").json()
    assert body["models"] == []
    assert body["total"] == 0


def test_get_models_after_registry_load_returns_sorted_entries(client):
    load_and_persist_registry(client.app.state.db.connection(), _REGISTRY_PATH)
    body = client.get("/api/models").json()
    models = body["models"]
    assert body["total"] == len(models)
    assert body["total"] > 0
    roles = [m["role"] for m in models]
    tier_order = {"starter": 0, "standard": 1, "high-quality": 2, "user-supplied": 3}
    assert roles == sorted(roles, key=lambda r: tier_order.get(r, 99))


def test_get_models_entry_shape(client):
    load_and_persist_registry(client.app.state.db.connection(), _REGISTRY_PATH)
    body = client.get("/api/models").json()
    entry = next(m for m in body["models"] if m["role"] == "starter")
    assert entry["license_spdx"] == "Apache-2.0"
    assert entry["source_type"] == "registry"
    assert entry["sha256"] == "PENDING"
    assert isinstance(entry["size_gb"], float)
    assert isinstance(entry["min_vram_gb"], float)


def test_get_models_user_supplied_entry(client):
    load_and_persist_registry(client.app.state.db.connection(), _REGISTRY_PATH)
    body = client.get("/api/models").json()
    entry = next(m for m in body["models"] if m["id"] == "user-supplied-gguf")
    assert entry["source_type"] == "user-supplied"
    assert entry["license_spdx"] == "unknown-user-supplied"
    assert entry["sha256"] is None
    assert entry["size_gb"] is None
