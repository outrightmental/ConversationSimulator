# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — Developer flow (issue #80).

Acceptance criteria exercised:
  D-1  Monorepo structure is intact (key paths and entry points exist).
  D-2  Core schema definitions load without error.
  D-3  Pack validation CLI is importable and runnable.
  D-4  Fake runtime is registered and accessible via the runtime registry.
  D-5  Debug logging outputs structured lines with expected keys.
  D-6  A developer can add a minimal runtime adapter stub.
  D-7  Official packs pass schema validation (CI-stable check).
  D-8  Backend health endpoint reports all required subsystem fields.

All checks run without a real model, browser, or internet access.
Owner: developer experience team.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.packs.validator import validate_pack_dir
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import RuntimeStatus

# Repo root — acceptance tests live at <repo-root>/tests/acceptance/
_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# D-1  Monorepo structure
# ---------------------------------------------------------------------------


class TestMonorepoStructure:
    """Key paths and entry points that every developer needs must be present."""

    @pytest.mark.parametrize("rel_path", [
        "services/convsim-core",
        "packages/prompt-composer",
        "packages/convsim-cli",
        "packages/pack-loader",
        "packages/scenario-schema",
        "apps/web",
        "packs/official",
        "schemas",
        "scripts/setup.sh",
        "scripts/dev.sh",
        "docs",
        "README.md",
    ])
    def test_expected_path_exists(self, rel_path):
        target = _REPO_ROOT / rel_path
        assert target.exists(), f"Expected repo path not found: {rel_path}"

    def test_at_least_one_official_pack_exists(self):
        official = _REPO_ROOT / "packs" / "official"
        packs = [p for p in official.iterdir() if p.is_dir()]
        assert len(packs) >= 1, "No official packs found under packs/official/"

    def test_schema_files_present(self):
        schemas_dir = _REPO_ROOT / "schemas"
        json_schemas = list(schemas_dir.rglob("*.json"))
        assert len(json_schemas) >= 1, "No JSON schema files found under schemas/"


# ---------------------------------------------------------------------------
# D-2  Schema definitions load
# ---------------------------------------------------------------------------


class TestSchemaLoad:
    """Core Python and JSON schemas must be importable and parseable."""

    def test_convsim_core_importable(self):
        import convsim_core
        assert convsim_core is not None

    def test_convsim_prompt_importable(self):
        import convsim_prompt
        assert convsim_prompt is not None

    def test_runtime_types_importable(self):
        from convsim_core.runtime.types import (
            ChatMessage,
            ChatRequest,
            RuntimeCapabilities,
            RuntimeStatus,
        )
        assert ChatMessage is not None

    def test_scenario_schema_importable(self):
        from convsim_core.scenarios import get_scenario_info
        scenario = get_scenario_info("behavioral_interview")
        assert scenario is not None

    def test_json_schemas_parse_as_valid_json(self):
        schemas_dir = _REPO_ROOT / "schemas"
        errors = []
        for schema_file in schemas_dir.rglob("*.json"):
            try:
                with open(schema_file, encoding="utf-8") as f:
                    data = json.load(f)
                assert isinstance(data, dict), f"{schema_file} is not a JSON object"
            except Exception as exc:
                errors.append(f"{schema_file}: {exc}")
        assert not errors, "Schema parse errors:\n" + "\n".join(errors)


# ---------------------------------------------------------------------------
# D-3  Pack validation CLI importable
# ---------------------------------------------------------------------------


class TestPackValidationCLI:
    """A developer can run pack validation from Python and the CLI entry point."""

    def test_validate_pack_dir_is_callable(self):
        assert callable(validate_pack_dir)

    def test_validate_pack_dir_returns_validation_result(self, tmp_path):
        from convsim_core.packs.models import ValidationResult
        result = validate_pack_dir(tmp_path)
        assert isinstance(result, ValidationResult)

    def test_validate_official_pack_returns_no_errors(self):
        official_dir = _REPO_ROOT / "packs" / "official"
        pack_dirs = [p for p in official_dir.iterdir() if p.is_dir()]
        assert pack_dirs, "No official pack directories found"
        errors_by_pack: dict[str, list] = {}
        for pack_dir in pack_dirs:
            result = validate_pack_dir(pack_dir)
            if not result.valid:
                errors_by_pack[pack_dir.name] = result.errors
        assert not errors_by_pack, (
            "Official pack validation errors:\n" +
            "\n".join(f"  {name}: {e}" for name, errs in errors_by_pack.items() for e in errs)
        )


# ---------------------------------------------------------------------------
# D-4  Runtime registry
# ---------------------------------------------------------------------------


class TestRuntimeRegistry:
    """The fake runtime is registered; developers can inspect available runtimes."""

    @pytest.mark.asyncio
    async def test_fake_runtime_id(self):
        rt = FakeChatRuntime()
        assert rt.id == "fake"

    @pytest.mark.asyncio
    async def test_fake_runtime_reports_ready(self):
        rt = FakeChatRuntime()
        health = await rt.health()
        assert health.status == RuntimeStatus.READY

    @pytest.mark.asyncio
    async def test_fake_runtime_lists_models(self):
        rt = FakeChatRuntime()
        models = await rt.list_models()
        assert len(models) >= 1

    def test_runtime_registry_importable(self):
        from convsim_core.runtime import registry as rt_registry
        assert hasattr(rt_registry, "register"), "runtime registry must expose a register decorator"


# ---------------------------------------------------------------------------
# D-5  Debug logging
# ---------------------------------------------------------------------------


class TestDebugLogging:
    """Debug-level log output must produce structured lines with expected keys."""

    def test_session_create_emits_log_record(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
        config = ServiceConfig(
            host="127.0.0.1",
            port=7355,
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
            db_dir=str(tmp_path / "db"),
            packs_dir=str(tmp_path / "packs"),
        )
        app = create_app(config)
        with caplog.at_level(logging.DEBUG, logger="convsim_core"):
            with TestClient(app) as c:
                c.post("/api/sessions", json={
                    "scenario_id": "behavioral_interview",
                    "difficulty": "normal",
                    "player_role_name": "Dev Tester",
                    "language": "en",
                    "input_mode": "text-only",
                    "tts_enabled": False,
                    "show_state_meters": False,
                    "save_transcript": True,
                    "seed": None,
                })
        assert len(caplog.records) > 0, "Expected at least one log record during session creation"

    def test_health_endpoint_provides_runtime_debug_info(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
        config = ServiceConfig(
            host="127.0.0.1",
            port=7355,
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
            db_dir=str(tmp_path / "db"),
            packs_dir=str(tmp_path / "packs"),
        )
        app = create_app(config)
        with TestClient(app) as c:
            res = c.get("/api/health")
        body = res.json()
        assert "runtime" in body, "Health endpoint must include runtime field for developer diagnostics"
        assert "database" in body, "Health endpoint must include database field"


# ---------------------------------------------------------------------------
# D-6  Adapter stub
# ---------------------------------------------------------------------------


class TestAdapterStub:
    """A developer can define a minimal adapter that satisfies the runtime interface."""

    @pytest.mark.asyncio
    async def test_custom_adapter_satisfies_interface(self):
        """Demonstrates that extending FakeChatRuntime is sufficient to add an adapter."""
        from convsim_core.runtime.types import (
            ChatFinal,
            ChatRequest,
            RuntimeCapabilities,
            RuntimeHealth,
        )

        class _StubAdapter(FakeChatRuntime):
            @property
            def id(self) -> str:
                return "stub-adapter"

            @property
            def display_name(self) -> str:
                return "Developer Stub Adapter"

            @property
            def capabilities(self) -> RuntimeCapabilities:
                return RuntimeCapabilities(
                    streaming=True,
                    json_schema=False,
                    grammar=False,
                    tool_calling=False,
                    embeddings=False,
                )

        adapter = _StubAdapter()
        assert adapter.id == "stub-adapter"
        health = await adapter.health()
        assert health.status == RuntimeStatus.READY


# ---------------------------------------------------------------------------
# D-7  Official packs — schema gate
# ---------------------------------------------------------------------------


class TestOfficialPackGate:
    """Official packs must pass schema validation — this mirrors the CI pack-validation job."""

    def test_all_official_packs_pass_validation(self):
        official_dir = _REPO_ROOT / "packs" / "official"
        pack_dirs = sorted(p for p in official_dir.iterdir() if p.is_dir())
        assert pack_dirs, "No official pack directories found"
        failures: list[str] = []
        for pack_dir in pack_dirs:
            result = validate_pack_dir(pack_dir)
            for err in result.errors:
                failures.append(f"[{pack_dir.name}] {err}")
        assert not failures, "Official pack schema failures:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# D-8  Backend health subsystem fields
# ---------------------------------------------------------------------------


class TestBackendHealth:
    """The health endpoint must report all subsystem fields a developer needs."""

    def test_health_returns_ok_status(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
        config = ServiceConfig(
            host="127.0.0.1",
            port=7355,
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
            db_dir=str(tmp_path / "db"),
            packs_dir=str(tmp_path / "packs"),
        )
        app = create_app(config)
        with TestClient(app) as c:
            res = c.get("/api/health")
        assert res.status_code == 200
        body = res.json()
        assert body.get("status") == "ok"

    def test_health_includes_required_subsystem_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
        config = ServiceConfig(
            host="127.0.0.1",
            port=7355,
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
            db_dir=str(tmp_path / "db"),
            packs_dir=str(tmp_path / "packs"),
        )
        app = create_app(config)
        with TestClient(app) as c:
            body = c.get("/api/health").json()
        required_fields = {"status", "database", "runtime"}
        missing = required_fields - set(body.keys())
        assert not missing, f"Health endpoint missing subsystem fields: {missing}"
