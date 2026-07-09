# SPDX-License-Identifier: Apache-2.0
"""Tests for the ProcessSupervisor and SidecarProcess contract.

Covers:
- assert_localhost enforcement
- ProcessSupervisor registration, deduplication, stop_all, health_summary
- SidecarProcess.tail_log default implementation
- LlamaCppSidecar localhost enforcement via assert_localhost
- Integration: missing binary, port conflict, crash, restart, graceful shutdown
  (full integration tests are in test_sidecar.py; this file focuses on the
   supervisor layer and the new contract behaviour)
"""
from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from convsim_core.runtime.supervisor import (
    ProcessSupervisor,
    SidecarProcess,
    assert_localhost,
)


# ---------------------------------------------------------------------------
# assert_localhost
# ---------------------------------------------------------------------------


def test_assert_localhost_accepts_ipv4_loopback():
    assert_localhost("127.0.0.1")  # must not raise


def test_assert_localhost_accepts_ipv6_loopback():
    assert_localhost("::1")  # must not raise


def test_assert_localhost_accepts_localhost_name():
    assert_localhost("localhost")  # must not raise


def test_assert_localhost_rejects_wildcard_ipv4():
    with pytest.raises(RuntimeError, match="not a loopback address"):
        assert_localhost("0.0.0.0")


def test_assert_localhost_rejects_wildcard_ipv6():
    with pytest.raises(RuntimeError, match="not a loopback address"):
        assert_localhost("::")


def test_assert_localhost_rejects_lan_ip():
    with pytest.raises(RuntimeError, match="not a loopback address"):
        assert_localhost("192.168.1.100")


def test_assert_localhost_message_includes_host():
    try:
        assert_localhost("10.0.0.1")
    except RuntimeError as exc:
        assert "10.0.0.1" in str(exc)


# ---------------------------------------------------------------------------
# Minimal concrete SidecarProcess for testing (not LlamaCppSidecar)
# ---------------------------------------------------------------------------


class _FakeSidecar(SidecarProcess):
    """Minimal concrete SidecarProcess for testing supervisor behaviour."""

    def __init__(self, sidecar_id: str = "fake_sidecar", stop_raises: bool = False) -> None:
        self._id = sidecar_id
        self._stop_raises = stop_raises
        self.stop_called = 0
        self._log_path = ""

    @property
    def sidecar_id(self) -> str:
        return self._id

    @property
    def display_name(self) -> str:
        return f"Fake ({self._id})"

    async def stop(self) -> None:
        self.stop_called += 1
        if self._stop_raises:
            raise RuntimeError("stop failed")

    def get_status(self) -> dict[str, Any]:
        return {
            "state": "stopped",
            "pid": None,
            "error": None,
            "log_path": self._log_path,
        }


# ---------------------------------------------------------------------------
# ProcessSupervisor.register
# ---------------------------------------------------------------------------


def test_register_single_sidecar():
    sup = ProcessSupervisor()
    sidecar = _FakeSidecar("a")
    sup.register(sidecar)
    assert sup.get("a") is sidecar


def test_register_duplicate_raises():
    sup = ProcessSupervisor()
    sup.register(_FakeSidecar("a"))
    with pytest.raises(ValueError, match="already registered"):
        sup.register(_FakeSidecar("a"))


def test_register_different_ids_allowed():
    sup = ProcessSupervisor()
    sup.register(_FakeSidecar("a"))
    sup.register(_FakeSidecar("b"))
    assert sup.get("a") is not None
    assert sup.get("b") is not None


def test_get_unknown_id_returns_none():
    sup = ProcessSupervisor()
    assert sup.get("nonexistent") is None


# ---------------------------------------------------------------------------
# ProcessSupervisor.stop_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_all_calls_stop_on_every_sidecar():
    sup = ProcessSupervisor()
    a = _FakeSidecar("a")
    b = _FakeSidecar("b")
    sup.register(a)
    sup.register(b)

    await sup.stop_all()

    assert a.stop_called == 1
    assert b.stop_called == 1


@pytest.mark.asyncio
async def test_stop_all_with_no_sidecars_is_noop():
    sup = ProcessSupervisor()
    await sup.stop_all()  # must not raise


@pytest.mark.asyncio
async def test_stop_all_suppresses_individual_errors():
    """A failing stop() on one sidecar must not prevent others from stopping."""
    sup = ProcessSupervisor()
    bad = _FakeSidecar("bad", stop_raises=True)
    good = _FakeSidecar("good")
    sup.register(bad)
    sup.register(good)

    await sup.stop_all()  # must not raise even though bad.stop() raises

    assert good.stop_called == 1


@pytest.mark.asyncio
async def test_stop_all_is_concurrent(monkeypatch):
    """stop_all() runs all stops concurrently, not sequentially."""
    order: list[str] = []

    class _SlowSidecar(_FakeSidecar):
        async def stop(self) -> None:
            await asyncio.sleep(0.05)
            order.append(self._id)

    sup = ProcessSupervisor()
    sup.register(_SlowSidecar("a"))
    sup.register(_SlowSidecar("b"))

    import time
    t0 = time.monotonic()
    await sup.stop_all()
    elapsed = time.monotonic() - t0

    # Both run concurrently so total time is ~0.05s, not ~0.10s.
    assert elapsed < 0.09, f"stop_all took {elapsed:.3f}s — expected concurrent execution"
    assert set(order) == {"a", "b"}


# ---------------------------------------------------------------------------
# ProcessSupervisor.health_summary
# ---------------------------------------------------------------------------


def test_health_summary_empty_when_no_sidecars():
    sup = ProcessSupervisor()
    assert sup.health_summary() == []


def test_health_summary_includes_sidecar_id_and_display_name():
    sup = ProcessSupervisor()
    sup.register(_FakeSidecar("llm"))
    summary = sup.health_summary()
    assert len(summary) == 1
    assert summary[0]["sidecar_id"] == "llm"
    assert "display_name" in summary[0]


def test_health_summary_merges_get_status_keys():
    sup = ProcessSupervisor()
    sup.register(_FakeSidecar("llm"))
    summary = sup.health_summary()
    entry = summary[0]
    assert entry["state"] == "stopped"
    assert entry["pid"] is None
    assert entry["error"] is None
    assert "log_path" in entry


def test_health_summary_multiple_sidecars():
    sup = ProcessSupervisor()
    sup.register(_FakeSidecar("a"))
    sup.register(_FakeSidecar("b"))
    ids = {e["sidecar_id"] for e in sup.health_summary()}
    assert ids == {"a", "b"}


# ---------------------------------------------------------------------------
# SidecarProcess.tail_log default implementation
# ---------------------------------------------------------------------------


def test_tail_log_returns_empty_when_log_missing(tmp_path):
    sidecar = _FakeSidecar()
    sidecar._log_path = str(tmp_path / "no-such.log")
    assert sidecar.tail_log() == []


def test_tail_log_returns_last_n_lines(tmp_path):
    log = tmp_path / "runtime.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)))
    sidecar = _FakeSidecar()
    sidecar._log_path = str(log)
    result = sidecar.tail_log(lines=10)
    assert len(result) == 10
    assert result[-1] == "line 99"


def test_tail_log_zero_lines_returns_all(tmp_path):
    log = tmp_path / "runtime.log"
    log.write_text("a\nb\nc")
    sidecar = _FakeSidecar()
    sidecar._log_path = str(log)
    assert sidecar.tail_log(lines=0) == ["a", "b", "c"]


def test_tail_log_fewer_lines_than_requested(tmp_path):
    log = tmp_path / "runtime.log"
    log.write_text("only\ntwo")
    sidecar = _FakeSidecar()
    sidecar._log_path = str(log)
    result = sidecar.tail_log(lines=50)
    assert result == ["only", "two"]


# ---------------------------------------------------------------------------
# LlamaCppSidecar implements SidecarProcess
# ---------------------------------------------------------------------------


def test_llama_cpp_sidecar_is_sidecar_process(tmp_path):
    from convsim_core.runtime.sidecar import LlamaCppSidecar
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    assert isinstance(sidecar, SidecarProcess)


def test_llama_cpp_sidecar_id(tmp_path):
    from convsim_core.runtime.sidecar import LlamaCppSidecar
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    assert sidecar.sidecar_id == "llama_cpp"


def test_llama_cpp_display_name(tmp_path):
    from convsim_core.runtime.sidecar import LlamaCppSidecar
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    assert "llama" in sidecar.display_name.lower()


@pytest.mark.asyncio
async def test_llama_cpp_start_rejects_non_localhost_host(tmp_path):
    """start() must raise RuntimeError for any non-loopback host."""
    from convsim_core.runtime.sidecar import LlamaCppSidecar
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    with pytest.raises(RuntimeError, match="not a loopback address"):
        await sidecar.start("fake.gguf", host="0.0.0.0", port=_free_port())


@pytest.mark.asyncio
async def test_llama_cpp_start_rejects_lan_ip(tmp_path):
    from convsim_core.runtime.sidecar import LlamaCppSidecar
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    with pytest.raises(RuntimeError, match="not a loopback address"):
        await sidecar.start("fake.gguf", host="192.168.1.1", port=_free_port())


@pytest.mark.asyncio
async def test_llama_cpp_non_localhost_does_not_change_state(tmp_path):
    """State must remain STOPPED when start() is rejected before port check."""
    from convsim_core.runtime.sidecar import LlamaCppSidecar, SidecarState
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    try:
        await sidecar.start("fake.gguf", host="0.0.0.0", port=_free_port())
    except RuntimeError:
        pass
    assert sidecar.state == SidecarState.STOPPED


# ---------------------------------------------------------------------------
# Supervisor integration: app.state wiring
# ---------------------------------------------------------------------------


def test_app_state_has_supervisor(client):
    """create_app must register a ProcessSupervisor on app.state.supervisor."""
    assert hasattr(client.app.state, "supervisor")
    assert isinstance(client.app.state.supervisor, ProcessSupervisor)


def test_app_state_supervisor_has_llama_cpp_sidecar(client):
    """The llama_cpp sidecar must be registered with the supervisor at startup."""
    sup: ProcessSupervisor = client.app.state.supervisor
    sidecar = sup.get("llama_cpp")
    assert sidecar is not None
    assert sidecar is client.app.state.sidecar


def test_health_endpoint_includes_sidecar_diagnostics(client):
    """GET /api/health must include the sidecar_diagnostics field."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "sidecar_diagnostics" in body
    diag = body["sidecar_diagnostics"]
    assert "all_ready" in diag
    assert "user_message" in diag
    assert "sidecars" in diag


def test_health_sidecar_diagnostics_has_llama_cpp_entry(client):
    """The sidecar_diagnostics sidecars list must contain the llama_cpp entry."""
    body = client.get("/api/health").json()
    sidecars = body["sidecar_diagnostics"]["sidecars"]
    ids = [s["sidecar_id"] for s in sidecars]
    assert "llama_cpp" in ids


def test_health_sidecar_not_ready_when_stopped(client):
    """all_ready must be False when the llama_cpp sidecar is stopped."""
    body = client.get("/api/health").json()
    diag = body["sidecar_diagnostics"]
    assert diag["all_ready"] is False


def test_health_sidecar_user_message_for_stopped(client):
    """user_message must be an actionable non-empty string when sidecar is stopped."""
    body = client.get("/api/health").json()
    diag = body["sidecar_diagnostics"]
    assert isinstance(diag["user_message"], str)
    assert len(diag["user_message"]) > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
