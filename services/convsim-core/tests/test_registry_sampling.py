# SPDX-License-Identifier: Apache-2.0
"""The model registry's sampling defaults reach the request (issue #580).

``model-registry/registry.yaml`` declares ``runtime.llama_cpp.temperature_default``
and ``top_p_default`` per model. Turns, their repair and retry calls, and the
debrief are sent with them when the llama.cpp model serving the request has a
registry entry that declares them, and with today's 0.8 temperature and the
adapter's 0.95 top_p otherwise. The model is the one the engine launch path
picks and maps to its registry entry, so it does not matter whether a
selection was saved.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.runtime.active import find_ready_model_path
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.launch import DEFAULT_CONTEXT_LENGTH, resolve_launch_config
from convsim_core.runtime.types import ChatChunk, ChatFinal, ChatRequest, SamplingDefaults
from convsim_core.scenarios import get_scenario_data
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_active_config,
    mark_install_ready,
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

#: Values no default uses, so a request carrying them got them from the entry.
_TEMPERATURE = 0.6
_TOP_P = 0.85
_DECLARED = SamplingDefaults(temperature=_TEMPERATURE, top_p=_TOP_P)
#: The fake entry's context length, which the launch path sizes the engine at
#: when it finds the entry; DEFAULT_CONTEXT_LENGTH when it does not.
_CONTEXT_LENGTH = 4096
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
            "url": f"https://example.invalid/{registry_id}.gguf",
            "sha256": "0" * 64,
        },
    }
    if llama_cpp is not None:
        entry["runtime"] = {"llama_cpp": llama_cpp}
    return entry


_DECLARING = {
    "context_length": _CONTEXT_LENGTH,
    "temperature_default": _TEMPERATURE,
    "top_p_default": _TOP_P,
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn


def _model_file(tmp_path: Path, name: str = "fake-model-q4.gguf") -> str:
    """A model file on disk: the launch path only starts the engine on one."""
    path = tmp_path / "models" / "llm" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GGUF")
    return str(path)


@pytest.fixture()
def model_file(tmp_path) -> str:
    return _model_file(tmp_path)


def _install(
    conn: sqlite3.Connection,
    entry: dict,
    path: str,
    *,
    select: bool = True,
    ready: bool = True,
) -> None:
    """Put ``entry`` in the registry and record ``path`` as its install.

    By default this is how first-run setup leaves a registry model: the
    install finished and the file saved as the selection. ``select=False``
    saves nothing, as for a core started with ``CONVSIM_RUNTIME_ID=llama_cpp``
    alone; ``ready=False`` leaves the install unfinished.
    """
    upsert_registry_models(conn, [entry])
    install_id = create_install_record(
        conn, registry_id=entry["id"], filename=Path(path).name, file_path=path
    )
    if ready:
        mark_install_ready(conn, install_id, size_bytes=4, verified_sha256="0" * 64, file_path=path)
    if select:
        set_active_config(conn, "llama_cpp", path)


def _engine_and_turn(conn: sqlite3.Connection) -> tuple[int, SamplingDefaults]:
    """The context the engine launch path would start the engine with, and the
    sampling a llama.cpp turn is sent with. When the launch path finds the fake
    entry, its context is the entry's; when it does not, it is the default."""
    launch = resolve_launch_config(find_ready_model_path(conn), conn)
    return launch.context_length, active_model_sampling(conn, "llama_cpp")


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


# ── Reading a registry entry ─────────────────────────────────────────────────


class TestRegistrySamplingDefaults:
    def test_an_entry_gives_what_it_declares(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        assert registry_sampling_defaults(conn, "fake-model-q4") == _DECLARED

    def test_an_entry_may_declare_one_and_not_the_other(self):
        conn = _db()
        upsert_registry_models(
            conn, [_entry(llama_cpp={"context_length": 4096, "temperature_default": _TEMPERATURE})]
        )
        assert registry_sampling_defaults(conn, "fake-model-q4") == SamplingDefaults(
            temperature=_TEMPERATURE
        )

    def test_an_entry_without_a_runtime_block_declares_nothing(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=None)])
        assert registry_sampling_defaults(conn, "fake-model-q4") == SamplingDefaults()

    def test_no_entry_declares_nothing(self):
        conn = _db()
        assert registry_sampling_defaults(conn, None) == SamplingDefaults()
        assert registry_sampling_defaults(conn, "") == SamplingDefaults()
        assert registry_sampling_defaults(conn, "no-such-model") == SamplingDefaults()

    def test_a_hand_edited_value_outside_the_schema_is_ignored(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        with conn:
            conn.execute(
                "UPDATE model_registry SET capabilities_json = ? WHERE id = 'fake-model-q4'",
                (json.dumps({"llama_cpp": {"temperature_default": 7, "top_p_default": True}}),),
            )
        assert registry_sampling_defaults(conn, "fake-model-q4") == SamplingDefaults()

    def test_a_corrupt_runtime_block_never_raises(self):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        with conn:
            conn.execute(
                "UPDATE model_registry SET capabilities_json = '{not json' WHERE id = 'fake-model-q4'"
            )
        assert registry_sampling_defaults(conn, "fake-model-q4") == SamplingDefaults()

    def test_the_bundled_starter_entry_yields_what_registry_yaml_declares(self):
        data = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8"))
        starter = next(m for m in data["models"] if m["role"] == "starter")
        declared = starter["runtime"]["llama_cpp"]
        conn = _db()
        load_and_persist_registry(conn, _REGISTRY_PATH)
        assert registry_sampling_defaults(conn, starter["id"]) == SamplingDefaults(
            temperature=declared["temperature_default"], top_p=declared["top_p_default"]
        )


# ── Which model: the one the engine launch path picks ────────────────────────


class TestActiveModelSampling:
    """Each case checks the turn's sampling against the engine's launch
    context, so a turn and the launch always find the same registry entry."""

    def test_the_saved_selection_gives_its_entry(self, model_file):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file)
        assert _engine_and_turn(conn) == (_CONTEXT_LENGTH, _DECLARED)

    @pytest.mark.parametrize(
        "saved",
        [None, ("llama_cpp", None), ("ollama", "llama3.2:3b")],
        ids=["nothing-saved", "runtime-saved-without-a-model", "ollama-tag-saved"],
    )
    def test_without_a_saved_model_file_the_newest_ready_install_gives_its_entry(
        self, model_file, saved
    ):
        # A core started with CONVSIM_RUNTIME_ID=llama_cpp and nothing saved
        # (scripts/nightly-model-smoke.py starts one that way), Settings saving
        # llama.cpp with no model, or a saved Ollama tag, which is no file the
        # engine can load: in each the app starts the engine on the newest
        # ready install.
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file, select=False)
        if saved is not None:
            set_active_config(conn, *saved)
        else:
            assert get_active_config(conn) == {"runtime_id": None, "model_id": None}
        assert _engine_and_turn(conn) == (_CONTEXT_LENGTH, _DECLARED)

    def test_the_saved_selection_wins_over_a_newer_install(self, tmp_path):
        conn = _db()
        selected = _model_file(tmp_path, "fake-model-q4.gguf")
        _install(conn, _entry(llama_cpp=_DECLARING), selected)
        newer = _model_file(tmp_path, "other-model-q4.gguf")
        _install(
            conn,
            _entry("other-model-q4", {"context_length": 2048, "temperature_default": 0.3}),
            newer,
            select=False,
        )
        assert _engine_and_turn(conn) == (_CONTEXT_LENGTH, _DECLARED)

    def test_a_selection_spelled_unlike_its_install_record_still_maps(self, model_file):
        # The launch path compares paths after normalisation, and so does the
        # turn: a "." or ".." segment in the saved path does not lose the entry.
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file)
        folder, name = os.path.split(model_file)
        set_active_config(
            conn, "llama_cpp", os.path.join(folder, "..", os.path.basename(folder), ".", name)
        )
        assert _engine_and_turn(conn) == (_CONTEXT_LENGTH, _DECLARED)

    @pytest.mark.parametrize("select", [True, False], ids=["saved", "newest-install"])
    def test_a_player_supplied_gguf_has_no_entry(self, tmp_path, model_file, select):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file, select=False)
        mine = _model_file(tmp_path, "mine.gguf")
        register_user_gguf(conn, path=mine)
        if select:
            set_active_config(conn, "llama_cpp", mine)
        assert _engine_and_turn(conn) == (DEFAULT_CONTEXT_LENGTH, SamplingDefaults())

    def test_an_unfinished_install_is_not_what_the_engine_starts(self, model_file):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file, select=False, ready=False)
        assert _engine_and_turn(conn) == (DEFAULT_CONTEXT_LENGTH, SamplingDefaults())

    def test_with_no_model_file_on_record_nothing_is_declared(self):
        # An engine the app did not start, on a data directory with no install
        # record (the nightly smoke's): neither the launch path nor the turn
        # knows its model. A saved registry id is not a file the engine can be
        # started on, so it does not name one either.
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        assert _engine_and_turn(conn) == (DEFAULT_CONTEXT_LENGTH, SamplingDefaults())
        set_active_config(conn, "llama_cpp", "fake-model-q4")
        assert _engine_and_turn(conn) == (DEFAULT_CONTEXT_LENGTH, SamplingDefaults())

    @pytest.mark.parametrize("runtime_id", ["ollama", "fake", "scripted", None])
    def test_only_the_llama_cpp_runtime_reads_the_llama_cpp_block(self, model_file, runtime_id):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file)
        assert active_model_sampling(conn, runtime_id) == SamplingDefaults()


# ── The turn pipeline ────────────────────────────────────────────────────────


class TestTurnRequests:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("select", [True, False], ids=["saved", "nothing-saved"])
    async def test_the_turn_is_sent_with_the_registry_values(self, model_file, select):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file, select=select)
        runtime = _RecordingLlamaRuntime()
        await _play_turn(conn, runtime)
        assert len(runtime.requests) == 1
        assert runtime.requests[0].temperature == _TEMPERATURE
        assert runtime.requests[0].top_p == _TOP_P

    @pytest.mark.asyncio
    async def test_a_repair_call_samples_like_the_turn(self, model_file):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file)
        runtime = _GarbageFirstLlamaRuntime()
        await _play_turn(conn, runtime)
        assert len(runtime.requests) >= 2, "the garbage reply should have been repaired"
        assert all(r.temperature == _TEMPERATURE for r in runtime.requests)
        assert all(r.top_p == _TOP_P for r in runtime.requests)

    @pytest.mark.asyncio
    async def test_an_entry_that_declares_nothing_keeps_todays_values(self, model_file):
        conn = _db()
        _install(conn, _entry(llama_cpp={"context_length": 4096}), model_file)
        runtime = _GarbageFirstLlamaRuntime()
        await _play_turn(conn, runtime)
        assert len(runtime.requests) >= 2
        assert all(r.temperature == _FALLBACK_TEMPERATURE for r in runtime.requests)
        assert all(r.top_p is None for r in runtime.requests)

    @pytest.mark.asyncio
    async def test_a_player_supplied_gguf_keeps_todays_values(self, model_file):
        conn = _db()
        upsert_registry_models(conn, [_entry(llama_cpp=_DECLARING)])
        register_user_gguf(conn, path=model_file)
        set_active_config(conn, "llama_cpp", model_file)
        runtime = _RecordingLlamaRuntime()
        await _play_turn(conn, runtime)
        assert runtime.requests[0].temperature == _FALLBACK_TEMPERATURE
        assert runtime.requests[0].top_p is None

    @pytest.mark.asyncio
    async def test_a_runtime_other_than_llama_cpp_keeps_todays_values(self, model_file):
        conn = _db()
        _install(conn, _entry(llama_cpp=_DECLARING), model_file)

        class _RecordingFake(_RecordingLlamaRuntime):
            """A test double that is not the llama.cpp runtime."""

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


def _play_to_debrief(
    tmp_config, model_file: str, llama_cpp: dict | None, *, select: bool = True
) -> list[ChatRequest]:
    """Install a fake registry model, play one turn and the debrief on it, and
    return every request the engine was sent. With ``select=False`` nothing is
    saved and the live runtime alone is llama.cpp, as in a core started with
    ``CONVSIM_RUNTIME_ID=llama_cpp``."""
    app = create_app(tmp_config)
    runtime = _RecordingLlamaRuntime()
    with TestClient(app) as client:
        conn = app.state.db.connection()
        _install(conn, _entry(llama_cpp=llama_cpp), model_file, select=select)
        if not select:
            assert get_active_config(conn) == {"runtime_id": None, "model_id": None}
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
    @pytest.mark.parametrize("select", [True, False], ids=["saved", "nothing-saved"])
    def test_turn_and_debrief_are_sent_with_the_registry_values(self, tmp_config, model_file, select):
        requests = _play_to_debrief(tmp_config, model_file, _DECLARING, select=select)
        # One turn, then the debrief (the only request with its schema).
        assert len(requests) == 2
        assert "replay_suggestions" in requests[1].json_schema["properties"]
        assert [(r.temperature, r.top_p) for r in requests] == [(_TEMPERATURE, _TOP_P)] * 2

    def test_without_registry_values_both_keep_todays_defaults(self, tmp_config, model_file):
        requests = _play_to_debrief(tmp_config, model_file, None)
        assert len(requests) == 2
        assert [(r.temperature, r.top_p) for r in requests] == [(_FALLBACK_TEMPERATURE, None)] * 2
