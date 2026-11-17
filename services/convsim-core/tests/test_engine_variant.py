# SPDX-License-Identifier: Apache-2.0
"""The graphics card by default, the processor when it fails (issue #531).

Three layers:

* the probe parser and the device classification, from fixtures (one of them
  a real capture from a Windows laptop with an RTX 4080 and Intel graphics);
* the choice and the fingerprint, as pure functions;
* the ladder, against fake engine builds that really run as processes
  (``tests/fake_engine.py``): every rung must end on the processor build within
  the startup timeout, with one stored record that stops a retry loop.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator

import httpx
import pytest

from convsim_core.runtime.engine_variant import (
    DEVICE_DISCRETE,
    DEVICE_INTEGRATED,
    DEVICE_SOFTWARE,
    DEVICE_UNKNOWN,
    ENGINE_VARIANT_SETTING_KEY,
    RUNG_CRASH,
    RUNG_FIRST_GENERATION,
    RUNG_LOAD,
    RUNG_PROBE,
    RUNG_WRONG_OUTPUT,
    EngineBuild,
    EngineBuilds,
    GpuFailure,
    GraphicsAdapter,
    ProbeResult,
    canary_passes,
    choose_variant,
    classify_device,
    gpu_fingerprint,
    load_gpu_failure,
    parse_list_devices,
    record_crash_and_fall_back,
    save_gpu_failure,
    start_engine,
)
from convsim_core.runtime.launch import LaunchConfig
from convsim_core.runtime.sidecar import LlamaCppSidecar, wait_for_port_release
from convsim_core.storage.database import Database
from tests.fake_engine import (
    DISCRETE_AND_INTEGRATED,
    INTEGRATED_ONLY,
    NO_DEVICES,
    builds_for,
    free_port,
    run_python_scripts,  # noqa: F401 — fixture
    write_fake_build,
)

FIXTURES = Path(__file__).parent / "fixtures"
ADAPTERS = [GraphicsAdapter("NVIDIA GeForce RTX 4080 Laptop GPU", "32.0.16.1742")]
STARTUP_TIMEOUT = 20.0


# ── The probe output ──────────────────────────────────────────────────────────


def test_parses_the_real_windows_capture():
    devices = parse_list_devices(
        (FIXTURES / "llama_server_b9415_list_devices_windows_rtx4080_laptop.txt").read_text()
    )
    assert [(d.backend_id, d.name, d.total_mib, d.free_mib, d.kind) for d in devices] == [
        ("Vulkan0", "NVIDIA GeForce RTX 4080 Laptop GPU", 11995, 11227, DEVICE_DISCRETE),
        ("Vulkan1", "Intel(R) RaptorLake-S Mobile Graphics Controller", 32629, 48107, DEVICE_INTEGRATED),
    ]


def test_steam_deck_is_integrated():
    devices = parse_list_devices((FIXTURES / "synthetic_llama_server_list_devices_steam_deck.txt").read_text())
    assert [d.kind for d in devices] == [DEVICE_INTEGRATED]


def test_verbose_output_and_a_name_with_parentheses():
    devices = parse_list_devices(
        (FIXTURES / "synthetic_llama_server_list_devices_linux_radeon_rx.txt").read_text()
    )
    assert devices[0].name == "AMD Radeon RX 7800 XT (RADV NAVI32)"
    assert [d.kind for d in devices] == [DEVICE_DISCRETE, DEVICE_INTEGRATED]


def test_no_devices():
    assert parse_list_devices((FIXTURES / "synthetic_llama_server_list_devices_none.txt").read_text()) == []
    assert parse_list_devices("") == []


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("NVIDIA GeForce RTX 3060", DEVICE_DISCRETE),
        ("NVIDIA RTX A2000 12GB", DEVICE_DISCRETE),
        ("AMD Radeon RX 6700 XT", DEVICE_DISCRETE),
        ("AMD Radeon Pro W6800", DEVICE_DISCRETE),
        ("Intel(R) Arc(TM) A770 Graphics", DEVICE_DISCRETE),
        ("Intel(R) Arc(tm) B580 Graphics (BMG G21)", DEVICE_DISCRETE),
        ("Intel(R) UHD Graphics 770", DEVICE_INTEGRATED),
        ("Intel(R) Iris(R) Xe Graphics", DEVICE_INTEGRATED),
        ("Intel(R) Arc(TM) Graphics", DEVICE_INTEGRATED),
        ("Intel(R) Arc(TM) 140V GPU (16GB)", DEVICE_INTEGRATED),
        ("AMD Radeon(TM) Graphics", DEVICE_INTEGRATED),
        ("AMD Radeon 780M Graphics", DEVICE_INTEGRATED),
        ("AMD Radeon 890M (RADV STRIX1)", DEVICE_INTEGRATED),
        ("AMD Custom GPU 0932 (RADV VANGOGH)", DEVICE_INTEGRATED),
        ("NVIDIA Tegra Orin (nvgpu)", DEVICE_INTEGRATED),
        ("llvmpipe (LLVM 15.0.7, 256 bits)", DEVICE_SOFTWARE),
        ("Microsoft Basic Render Driver", DEVICE_SOFTWARE),
        ("Some Future GPU 9000", DEVICE_UNKNOWN),
    ],
)
def test_classify_device(name, kind):
    assert classify_device(name) == kind


def test_more_free_than_total_means_shared_memory():
    assert classify_device("Mystery Graphics", 4096, 9000) == DEVICE_INTEGRATED


# ── Choosing ──────────────────────────────────────────────────────────────────

BOTH = EngineBuilds(EngineBuild("cpu", "/r/llama-server", "bundled"), EngineBuild("vulkan", "/r/vulkan/llama-server", "bundled"))


def _probe(text: str) -> ProbeResult:
    return ProbeResult(ok=True, devices=tuple(parse_list_devices(text)))


def test_auto_picks_the_discrete_card():
    decision = choose_variant("auto", BOTH, _probe(DISCRETE_AND_INTEGRATED))
    assert decision.variant == "vulkan"
    assert decision.device is not None and decision.device.name.startswith("NVIDIA")


@pytest.mark.parametrize("listing", [INTEGRATED_ONLY, NO_DEVICES])
def test_auto_keeps_the_processor_without_a_discrete_card(listing):
    decision = choose_variant("auto", BOTH, _probe(listing))
    assert decision.variant == "cpu"
    assert decision.failure_rung is None  # not a failure: there is nothing to use


def test_an_allow_listed_integrated_chip_counts_as_a_card():
    decision = choose_variant("auto", BOTH, _probe(INTEGRATED_ONLY), allow_list=(r"custom gpu 0405",))
    assert decision.variant == "vulkan"


def test_the_player_may_ask_for_integrated_graphics():
    assert choose_variant("vulkan", BOTH, _probe(INTEGRATED_ONLY)).variant == "vulkan"


def test_asking_for_the_card_when_none_is_listed_is_a_probe_failure():
    decision = choose_variant("vulkan", BOTH, _probe(NO_DEVICES))
    assert (decision.variant, decision.failure_rung) == ("cpu", RUNG_PROBE)


def test_a_failed_probe_is_the_probe_rung():
    decision = choose_variant("auto", BOTH, ProbeResult(ok=False, error="exited with code 3"))
    assert (decision.variant, decision.failure_rung) == ("cpu", RUNG_PROBE)


def test_processor_choice_and_remembered_failure_never_probe():
    assert choose_variant("cpu", BOTH, None).variant == "cpu"
    decision = choose_variant("auto", BOTH, None, remembered_failure=True)
    assert (decision.variant, decision.failure_rung) == ("cpu", None)


def test_without_a_vulkan_build_the_default_build_runs():
    macos = EngineBuilds(EngineBuild("metal", "/r/llama-server", "bundled"), None)
    assert choose_variant("vulkan", macos, None).variant == "metal"


def test_canary_check():
    assert canary_passes(" 9, 10")
    assert canary_passes("9")
    assert canary_passes("\n 9,")
    assert not canary_passes("GGGGGGGG")
    assert not canary_passes("")
    assert not canary_passes(" 10, 11")


# ── The fingerprint ───────────────────────────────────────────────────────────


def test_fingerprint_changes_with_the_driver_and_nothing_else():
    build = EngineBuild("vulkan", "/r/vulkan/llama-server", "bundled")
    base = gpu_fingerprint(build, ADAPTERS)
    assert gpu_fingerprint(build, list(ADAPTERS)) == base
    assert gpu_fingerprint(build, [GraphicsAdapter(ADAPTERS[0].name, "32.0.16.9999")]) != base
    assert gpu_fingerprint(EngineBuild("vulkan", "/other/llama-server", "user"), ADAPTERS) != base


# ── The ladder, against fake engine processes ────────────────────────────────


@pytest.fixture
def engine_env(tmp_path, run_python_scripts):  # noqa: F811 — fixture
    db = Database.open(str(tmp_path / "db"))
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    app = SimpleNamespace(state=SimpleNamespace(db=db, sidecar=sidecar))
    cpu = write_fake_build(tmp_path / "runtimes")
    vulkan = write_fake_build(tmp_path / "runtimes" / "vulkan", list_output=DISCRETE_AND_INTEGRATED)
    env = SimpleNamespace(
        app=app, db=db, conn=db.connection(), sidecar=sidecar, cpu=cpu, vulkan=vulkan,
        port=free_port(), tmp_path=tmp_path,
    )
    yield env
    db.close()


async def _start(env, *, adapters=ADAPTERS, gpu_layers=None) -> tuple[str, float]:
    # A test that starts twice reuses the port of the engine it just stopped.
    await wait_for_port_release("127.0.0.1", env.port)
    started = time.monotonic()
    async with env.sidecar.start_lock:
        variant = await start_engine(
            env.app, env.sidecar,
            model_path=str(env.tmp_path / "model.gguf"),
            launch=LaunchConfig(),
            conn=env.conn,
            startup_timeout=STARTUP_TIMEOUT,
            gpu_layers=gpu_layers,
            port=env.port,
            builds=builds_for(env.cpu, env.vulkan),
            adapters=adapters,
        )
    return variant, time.monotonic() - started


@pytest.mark.asyncio
async def test_auto_starts_the_vulkan_build_on_a_discrete_card(engine_env):
    try:
        variant, _ = await _start(engine_env)
        assert variant == "vulkan"
        assert engine_env.sidecar.variant == "vulkan"
        assert engine_env.sidecar.get_status()["variant"] == "vulkan"
        assert engine_env.vulkan.serves() and not engine_env.cpu.serves()
        assert load_gpu_failure(engine_env.conn) is None
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("listing", [INTEGRATED_ONLY, NO_DEVICES])
async def test_auto_starts_the_processor_without_a_discrete_card(engine_env, listing):
    engine_env.vulkan.configure(list_output=listing)
    try:
        variant, _ = await _start(engine_env)
        assert variant == "cpu"
        assert engine_env.vulkan.probes() == 1
        assert not engine_env.vulkan.serves()
        assert load_gpu_failure(engine_env.conn) is None  # nothing failed, no notice
    finally:
        await engine_env.sidecar.stop()


_RUNGS = {
    "probe crashes": (dict(list_rc=3221225477), RUNG_PROBE),
    "probe exits non-zero": (dict(list_rc=1), RUNG_PROBE),
    "model load fails": (dict(load="fail"), RUNG_LOAD),
    "first generation fails": (dict(completion=None), RUNG_FIRST_GENERATION),
    "wrong output": (dict(completion="GGGGGGGG"), RUNG_WRONG_OUTPUT),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("behaviour, rung", list(_RUNGS.values()), ids=list(_RUNGS))
async def test_each_rung_ends_on_the_processor_and_is_remembered(engine_env, behaviour, rung):
    engine_env.vulkan.configure(**behaviour)
    try:
        variant, elapsed = await _start(engine_env)
        assert variant == "cpu"
        assert engine_env.sidecar.variant == "cpu"
        assert elapsed < STARTUP_TIMEOUT
        failure = load_gpu_failure(engine_env.conn)
        assert failure is not None and failure.rung == rung
        assert failure.notice_seen is False  # one notice, pending
        await engine_env.sidecar.stop()

        # The next start does not try the card again: no probe, no Vulkan start.
        probes, serves = engine_env.vulkan.probes(), len(engine_env.vulkan.serves())
        variant, _ = await _start(engine_env)
        assert variant == "cpu"
        assert engine_env.vulkan.probes() == probes
        assert len(engine_env.vulkan.serves()) == serves
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
async def test_a_hung_probe_ends_on_the_processor(engine_env, monkeypatch):
    monkeypatch.setattr("convsim_core.runtime.engine_variant.PROBE_TIMEOUT", 1.0)
    engine_env.vulkan.configure(list_hang=True)
    try:
        variant, elapsed = await _start(engine_env)
        assert variant == "cpu"
        assert elapsed < STARTUP_TIMEOUT
        assert load_gpu_failure(engine_env.conn).rung == RUNG_PROBE
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
async def test_a_new_driver_clears_the_stored_failure(engine_env):
    build = builds_for(engine_env.cpu, engine_env.vulkan).vulkan
    save_gpu_failure(engine_env.conn, GpuFailure(fingerprint=gpu_fingerprint(build, ADAPTERS), rung=RUNG_LOAD, detail="x"))
    try:
        variant, _ = await _start(engine_env)
        assert variant == "cpu"  # same card, same driver: remembered
        await engine_env.sidecar.stop()

        updated = [GraphicsAdapter(ADAPTERS[0].name, "32.0.16.9999")]
        variant, _ = await _start(engine_env, adapters=updated)
        assert variant == "vulkan"
        assert load_gpu_failure(engine_env.conn) is None
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("setting, expected", [("cpu", "cpu"), ("vulkan", "vulkan")])
async def test_the_players_choice_is_honoured(engine_env, setting, expected):
    engine_env.conn.execute(
        "INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (ENGINE_VARIANT_SETTING_KEY, setting),
    )
    engine_env.conn.commit()
    engine_env.vulkan.configure(list_output=INTEGRATED_ONLY)  # Auto would keep the processor
    try:
        variant, _ = await _start(engine_env)
        assert variant == expected
        if setting == "cpu":
            assert engine_env.vulkan.probes() == 0
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
async def test_no_layer_count_unless_the_player_set_one(engine_env):
    try:
        await _start(engine_env)
        assert "--n-gpu-layers" not in engine_env.vulkan.serves()[-1]
        await engine_env.sidecar.stop()

        await _start(engine_env, gpu_layers=20)
        argv = engine_env.vulkan.serves()[-1]
        assert argv[argv.index("--n-gpu-layers") + 1] == "20"
        # The explicit context size the fit needs is always there (#523).
        assert argv[argv.index("--ctx-size") + 1] == str(LaunchConfig().context_length)
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
async def test_a_crash_during_a_conversation_falls_back_and_is_remembered(engine_env, monkeypatch):
    """The Vulkan engine dies mid-conversation: record it, start the processor
    on the same port, and report that the turn may be retried."""
    monkeypatch.setenv("CONVSIM_LLAMA_CPP_EXECUTABLE", str(engine_env.cpu.script))
    monkeypatch.setenv("CONVSIM_LLAMA_CPP_VULKAN_EXECUTABLE", str(engine_env.vulkan.script))
    model = engine_env.tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    engine_env.vulkan.configure(chat="crash")
    try:
        async with engine_env.sidecar.start_lock:
            variant = await start_engine(
                engine_env.app, engine_env.sidecar,
                model_path=str(model), launch=LaunchConfig(), conn=engine_env.conn,
                startup_timeout=STARTUP_TIMEOUT, port=engine_env.port,
            )
        assert variant == "vulkan"
        with pytest.raises(httpx.TransportError):
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"http://127.0.0.1:{engine_env.port}/v1/chat/completions", json={})

        assert await record_crash_and_fall_back(engine_env.app) is True
        assert engine_env.sidecar.variant == "cpu"
        assert engine_env.sidecar.port == engine_env.port
        assert load_gpu_failure(engine_env.conn).rung == RUNG_CRASH
        async with httpx.AsyncClient(timeout=10.0) as client:
            assert (await client.get(f"http://127.0.0.1:{engine_env.port}/health")).status_code == 200
    finally:
        await engine_env.sidecar.stop()


@pytest.mark.asyncio
async def test_a_processor_engine_that_stops_is_not_a_graphics_card_failure(engine_env):
    engine_env.vulkan.configure(list_output=NO_DEVICES)
    try:
        await _start(engine_env)
        assert engine_env.sidecar.variant == "cpu"
        assert await record_crash_and_fall_back(engine_env.app) is False
        assert load_gpu_failure(engine_env.conn) is None
    finally:
        await engine_env.sidecar.stop()


# ── The Settings API ──────────────────────────────────────────────────────────


def test_engine_status_reports_the_setting_and_no_failure(client):
    body = client.get("/api/runtime/engine").json()
    assert body["setting"] == "auto"
    assert body["running"] is None
    assert body["gpu_failure"] is None
    assert body["notice_pending"] is False


def _store_failure(client, rung=RUNG_LOAD):
    conn = client.app.state.db.connection()
    save_gpu_failure(conn, GpuFailure(fingerprint="f" * 16, rung=rung, detail="ErrorDeviceLost", device="GPU"))


def test_the_notice_is_shown_once(client):
    _store_failure(client)
    body = client.get("/api/runtime/engine").json()
    assert body["notice_pending"] is True
    assert body["gpu_failure"]["rung"] == RUNG_LOAD
    assert client.post("/api/runtime/engine/notice-seen").json()["notice_pending"] is False
    body = client.get("/api/runtime/engine").json()
    assert body["notice_pending"] is False
    assert body["gpu_failure"] is not None  # still remembered, just not announced again


def test_try_the_graphics_card_again_forgets_the_failure(client):
    _store_failure(client)
    body = client.post("/api/runtime/engine/retry-graphics-card").json()
    assert body["gpu_failure"] is None
    assert load_gpu_failure(client.app.state.db.connection()) is None


def test_choosing_an_engine_is_a_fresh_attempt(client):
    _store_failure(client)
    resp = client.put("/api/runtime/settings", json={"engine_variant": "vulkan"})
    assert resp.status_code == 200
    assert resp.json()["settings"]["engine_variant"] == "vulkan"
    assert resp.json()["requires_restart"] is True
    assert load_gpu_failure(client.app.state.db.connection()) is None


def test_an_unknown_engine_variant_is_rejected(client):
    resp = client.put("/api/runtime/settings", json={"engine_variant": "cuda"})
    assert resp.status_code == 422


def test_engine_variant_defaults_to_auto(client):
    body = client.get("/api/runtime/settings").json()
    assert body["settings"]["engine_variant"] is None
    assert body["recommended"]["engine_variant"] == "auto"


# ── A turn in flight when the engine dies ─────────────────────────────────────

_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Test Player",
    "save_transcript": True,
    "runtime_id": "fake",
}


def _crash_once_runtime():
    from convsim_core.runtime.fake import FakeChatRuntime

    class _CrashOnce(FakeChatRuntime):
        calls = 0

        @property
        def id(self) -> str:
            return "llama_cpp"

        def chat_stream(self, request) -> AsyncGenerator:
            type(self).calls += 1
            if type(self).calls == 1:
                return self._dropped()
            return super().chat_stream(request)

        async def _dropped(self):
            raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")
            yield  # pragma: no cover

    return _CrashOnce()


def _turn_rows(client, session_id):
    conn = client.app.state.db.connection()
    return conn.execute(
        "SELECT role FROM turn_session_turns WHERE session_id = ? ORDER BY turn_number",
        (session_id,),
    ).fetchall()


def test_a_turn_in_flight_is_retried_on_the_processor_and_commits_once(client, monkeypatch):
    from convsim_core.routers import sessions

    runtime = _crash_once_runtime()
    recoveries: list[object] = []

    async def _recover(app):
        recoveries.append(app)
        return True

    monkeypatch.setattr(sessions, "_resolve_runtime", lambda request, setup: runtime)
    monkeypatch.setattr(sessions, "record_crash_and_fall_back", _recover)

    session_id = client.post("/api/sessions", json=_SETUP).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    resp = client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello."})

    assert resp.status_code == 200, resp.text
    assert len(recoveries) == 1
    assert type(runtime).calls >= 2
    roles = [r["role"] for r in _turn_rows(client, session_id)]
    assert roles.count("player") == 1


def test_without_a_fallback_the_turn_fails_and_is_not_recorded(client, monkeypatch):
    from convsim_core.routers import sessions

    runtime = _crash_once_runtime()

    async def _no_fallback(app):
        return False

    monkeypatch.setattr(sessions, "_resolve_runtime", lambda request, setup: runtime)
    monkeypatch.setattr(sessions, "record_crash_and_fall_back", _no_fallback)

    session_id = client.post("/api/sessions", json=_SETUP).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    resp = client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello."})

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"
    assert [r["role"] for r in _turn_rows(client, session_id)].count("player") == 0


@pytest.mark.asyncio
async def test_released_words_block_a_retry():
    from convsim_core.routers.sessions import _ReleaseWatchingStreamer

    class _Inner:
        output_tokens = 0

        async def progress(self, stage, prompt=None):
            pass

        async def token(self, text):
            pass

        async def final(self, content):
            pass

    watched = _ReleaseWatchingStreamer(_Inner())
    await watched.progress("waiting")
    watched.output_tokens += 1
    assert watched.released is False and watched.output_tokens == 1
    await watched.token("Hello.")
    assert watched.released is True
