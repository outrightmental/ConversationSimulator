# SPDX-License-Identifier: Apache-2.0
"""The model registry's sampling defaults reach the request (issue #580).

``model-registry/registry.yaml`` declares ``runtime.llama_cpp.temperature_default``
and ``top_p_default`` per model. Turns, their repair and retry calls, and the
debrief are sent with them when the llama.cpp model serving the request has a
registry entry that declares them, and with today's 0.8 temperature and the
adapter's 0.95 top_p otherwise.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatChunk, ChatFinal, ChatRequest, SamplingDefaults
from convsim_core.scenarios import get_scenario_data
from convsim_core.services.model_manager_service import (
    create_install_record,
    register_user_gguf,
    set_active_config,
)
from convsim_core.services.model_registry_service import (
    active_model_sampling,
    load_and_persist_registry,
    registry_sampling_defaults,
    upsert_registry_models,
)
from convsim_core.services.turn_pipeline import process_turn
from convsim_core.storage.migrations import run_migrations

_REGISTRY_PATH = Path(__file__).parent.parent.parent.parent / "model-registry" / "registry.yaml"

_MODEL_PATH = "/data/models/llm/fake-model-q4.gguf"
#: Values no default uses, so a request carrying them got them from the entry.
_TEMPERATURE = 0.6
_TOP_P = 0.85
#: What a request is sent with when the registry declares nothing: the
#: ChatRequest temperature, and no top_p, so the adapter's own 0.95 applies.
_FALLBACK_TEMPERATURE = 0.8


def _entry(registry_id: str = "fake-model-q4", llama_cpp: dict | None = None) -> dict:
    """A fake registry entry; ``llama_cpp`` is its runtime block, if any."""
    entry: dict = {
        "id": registry_id,
        "name": "Fake Model Q4",
        "family": "fake",
        "role": "standard",
        "format": "gguf",
        "license": "MIT",
        "size_gb": 1.0,
        "hardware": {"min_vram_gb": 2, "recommended_vram_gb": 4},
        "download": {
            "provider": "huggingface",
            "url": "https://example.invalid/fake-model-q4.gguf",
            "sha256": "0" * 64,
        },
    }
    if llama_cpp is not None:
        entry["runtime"] = {"llama_cpp": llama_cpp}
    return entry


_DECLARING = {"context_length": 4096, "temperature_default": _TEMPERATURE, "top_p_default": _TOP_P}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn


def _install(conn: sqlite3.Connection, entry: dict, path: str = _MODEL_PATH) -> None:
    """Put ``entry`` in the registry, record its file as installed and select it,
    the way first-run setup leaves a registry model."""
    upsert_registry_models(conn, [entry])
    create_install_record(conn, registry_id=entry["id"], filename=Path(path).name, file_path=path)
    set_active_config(conn, "llama_cpp", path)


class _RecordingLlamaRuntime(FakeChatRuntime):
    """The fake engine under the llama.cpp id, keeping every request it is sent."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ChatRequest] = []

    @property
    def id(self) -> str:
        return "llama_cpp"

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatChunk, None]:
        self.requests.append(request)
        return super().chat_stream(request)


class _GarbageFirstLlamaRuntime(_RecordingLlamaRuntime):
    """Answers the turn with non-JSON, so the parser makes a repair call."""

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatChunk, None]:
        self.requests.append(request)
        if len(self.requests) == 1:
            return self._garbage()
        return FakeChatRuntime.chat_stream(self, request)

    async def _garbage(self) -> AsyncGenerator[ChatChunk, None]:
        yield ChatFinal(text="not json at all", model_id="fake", input_tokens=1, output_tokens=1)


def _unit_session(conn: sqlite3.Connection) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, "
        "turn_count, setup_json) "
        "VALUES ('sess-sampling', 'behavioral_interview', 'PlayerTurnListening', '{}', '[]', 0, '{}')"
    )
    conn.commit()
    return conn.execute("SELECT * FROM turn_sessions WHERE session_id = 'sess-sampling'").fetchone()


async def _play_turn(conn: sqlite3.Connection, runtime: FakeChatRuntime) -> None:
    await process_turn(
        session_row=_unit_session(conn),
        player_text="I led the migration and cut the error rate in half.",
        scenario_data=get_scenario_data("behavioral_interview", "standard"),
        max_turns=10,
        runtime=runtime,
        conn=conn,
    )


# ── SamplingDefaults ─────────────────────────────────────────────────────────


def test_request_fields_hold_only_what_was_declared():
    assert SamplingDefaults().request_fields() == {}
    assert SamplingDefaults(temperature=0.6).request_fields() == {"temperature": 0.6}
    assert SamplingDefaults(top_p=0.85).request_fields() == {"top_p": 0.85}
    assert SamplingDefaults(temperature=0.6, top_p=0.85).request_fields() == {
        "temperature": 0.6,
        "top_p": 0.85,
    }


def test_a_request_with_no_registry_sampling_keeps_todays_defaults():
    request = ChatRequest(messages=[], **SamplingDefaults().request_fields())
    assert request.temperature == _FALLBACK_TEMPERATURE
    assert request.top_p is None


# ── Reading the registry ─────────────────────────────────────────────────────


class TestRegistrySamplingDefaults:
    def test_an_installed_model_file_maps_to_its_entry(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        assert registry_sampling_defaults(conn, _MODEL_PATH) == SamplingDefaults(
            temperature=_TEMPERATURE, top_p=_TOP_P
        )

    def test_a_registry_id_names_its_own_entry(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        assert registry_sampling_defaults(conn, "fake-model-q4") == SamplingDefaults(
            temperature=_TEMPERATURE, top_p=_TOP_P
        )

    def test_an_entry_may_declare_one_and_not_the_other(self):
        conn = _db()
        _install(conn, _entry(llama_cpp={"context_length": 4096, "temperature_default": _TEMPERATURE}))
        assert registry_sampling_defaults(conn, _MODEL_PATH) == SamplingDefaults(temperature=_TEMPERATURE)

    def test_an_entry_without_a_runtime_block_declares_nothing(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=None))
        assert registry_sampling_defaults(conn, _MODEL_PATH) == SamplingDefaults()

    def test_a_player_supplied_gguf_has_no_entry(self):
        conn = _db()
        register_user_gguf(conn, path="/home/player/models/mine.gguf")
        assert registry_sampling_defaults(conn, "/home/player/models/mine.gguf") == SamplingDefaults()

    def test_an_unknown_or_missing_model_declares_nothing(self):
        conn = _db()
        assert registry_sampling_defaults(conn, None) == SamplingDefaults()
        assert registry_sampling_defaults(conn, "") == SamplingDefaults()
        assert registry_sampling_defaults(conn, "/nowhere/else.gguf") == SamplingDefaults()
        assert registry_sampling_defaults(conn, "llama3.2:3b") == SamplingDefaults()

    def test_a_hand_edited_value_outside_the_schema_is_ignored(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        with conn:
            conn.execute(
                "UPDATE model_registry SET capabilities_json = ? WHERE id = 'fake-model-q4'",
                (json.dumps({"llama_cpp": {"temperature_default": 7, "top_p_default": True}}),),
            )
        assert registry_sampling_defaults(conn, _MODEL_PATH) == SamplingDefaults()

    def test_a_corrupt_runtime_block_never_raises(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        with conn:
            conn.execute(
                "UPDATE model_registry SET capabilities_json = '{not json' WHERE id = 'fake-model-q4'"
            )
        assert registry_sampling_defaults(conn, _MODEL_PATH) == SamplingDefaults()

    def test_the_bundled_starter_entry_yields_what_registry_yaml_declares(self):
        data = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8"))
        starter = next(m for m in data["models"] if m["role"] == "starter")
        declared = starter["runtime"]["llama_cpp"]
        conn = _db()
        load_and_persist_registry(conn, _REGISTRY_PATH)
        assert registry_sampling_defaults(conn, starter["id"]) == SamplingDefaults(
            temperature=declared["temperature_default"], top_p=declared["top_p_default"]
        )


class TestActiveModelSampling:
    def test_the_active_llama_cpp_model_gives_its_entry(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        assert active_model_sampling(conn, "llama_cpp") == SamplingDefaults(
            temperature=_TEMPERATURE, top_p=_TOP_P
        )

    @pytest.mark.parametrize("runtime_id", ["ollama", "fake", "scripted", None])
    def test_only_the_llama_cpp_runtime_reads_the_llama_cpp_block(self, runtime_id):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        assert active_model_sampling(conn, runtime_id) == SamplingDefaults()

    def test_a_selection_on_another_runtime_does_not_count(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        set_active_config(conn, "ollama", "fake-model-q4")
        assert active_model_sampling(conn, "llama_cpp") == SamplingDefaults()

    def test_no_selection_declares_nothing(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        assert active_model_sampling(conn, "llama_cpp") == SamplingDefaults()


# ── The turn pipeline ────────────────────────────────────────────────────────


class TestTurnRequests:
    @pytest.mark.asyncio
    async def test_the_turn_is_sent_with_the_registry_values(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        runtime = _RecordingLlamaRuntime()
        await _play_turn(conn, runtime)
        assert len(runtime.requests) == 1
        assert runtime.requests[0].temperature == _TEMPERATURE
        assert runtime.requests[0].top_p == _TOP_P

    @pytest.mark.asyncio
    async def test_a_repair_call_samples_like_the_turn(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))
        runtime = _GarbageFirstLlamaRuntime()
        await _play_turn(conn, runtime)
        assert len(runtime.requests) >= 2, "the garbage reply should have been repaired"
        assert all(r.temperature == _TEMPERATURE for r in runtime.requests)
        assert all(r.top_p == _TOP_P for r in runtime.requests)

    @pytest.mark.asyncio
    async def test_an_entry_that_declares_nothing_keeps_todays_values(self):
        conn = _db()
        _install(conn, _entry(llama_cpp={"context_length": 4096}))
        runtime = _GarbageFirstLlamaRuntime()
        await _play_turn(conn, runtime)
        assert len(runtime.requests) >= 2
        assert all(r.temperature == _FALLBACK_TEMPERATURE for r in runtime.requests)
        assert all(r.top_p is None for r in runtime.requests)

    @pytest.mark.asyncio
    async def test_a_player_supplied_gguf_keeps_todays_values(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        register_user_gguf(conn, path=_MODEL_PATH)
        set_active_config(conn, "llama_cpp", _MODEL_PATH)
        runtime = _RecordingLlamaRuntime()
        await _play_turn(conn, runtime)
        assert runtime.requests[0].temperature == _FALLBACK_TEMPERATURE
        assert runtime.requests[0].top_p is None

    @pytest.mark.asyncio
    async def test_a_runtime_other_than_the_selection_keeps_todays_values(self):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING))

        class _RecordingFake(_RecordingLlamaRuntime):
            """A test double that is not the selected runtime."""

            @property
            def id(self) -> str:
                return "fake"

        runtime = _RecordingFake()
        await _play_turn(conn, runtime)
        assert runtime.requests[0].temperature == _FALLBACK_TEMPERATURE
        assert runtime.requests[0].top_p is None


# ── Through the session API: turn and debrief ────────────────────────────────

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Candidate",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
}


def _play_to_debrief(tmp_config, llama_cpp: dict | None) -> list[ChatRequest]:
    """Select a fake registry model, play one turn and the debrief on it, and
    return every request the engine was sent."""
    app = create_app(tmp_config)
    runtime = _RecordingLlamaRuntime()
    with TestClient(app) as client:
        _install(app.state.db.connection(), _entry(llama_cpp=llama_cpp))
        app.state.runtime = runtime
        res = client.post("/api/sessions", json=_SETUP)
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]
        assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
        res = client.post(f"/api/sessions/{session_id}/turn", json={"content": "I shipped it on time."})
        assert res.status_code == 200, res.text
        assert client.post(f"/api/sessions/{session_id}/end").status_code == 200
        res = client.post(f"/api/sessions/{session_id}/debrief")
        assert res.status_code == 200, res.text
        assert res.json()["used_fallback"] is False
    return runtime.requests


class TestThroughTheSessionApi:
    def test_turn_and_debrief_are_sent_with_the_registry_values(self, tmp_config):
        requests = _play_to_debrief(tmp_config, _DECLARING)
        # One turn, then the debrief (the only request with its schema).
        assert len(requests) == 2
        assert "replay_suggestions" in requests[1].json_schema["properties"]
        assert [(r.temperature, r.top_p) for r in requests] == [(_TEMPERATURE, _TOP_P)] * 2

    def test_without_registry_values_both_keep_todays_defaults(self, tmp_config):
        requests = _play_to_debrief(tmp_config, None)
        assert len(requests) == 2
        assert [(r.temperature, r.top_p) for r in requests] == [(_FALLBACK_TEMPERATURE, None)] * 2
