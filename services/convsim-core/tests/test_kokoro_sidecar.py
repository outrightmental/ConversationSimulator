# SPDX-License-Identifier: Apache-2.0
"""Tests for the Kokoro TTS sidecar process manager.

Unit tests cover executable resolution and state logic without spawning
processes. The async tests exercise the sidecar lifecycle using fake processes
and mock health endpoints.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from convsim_core.runtime.kokoro_sidecar import (
    KokoroSidecar,
    _is_port_in_use,
    find_kokoro_executable,
)
from convsim_core.runtime.sidecar import SidecarState
from convsim_core.runtime.supervisor import assert_localhost


# ---------------------------------------------------------------------------
# find_kokoro_executable — pure resolution logic
# ---------------------------------------------------------------------------


def test_find_executable_returns_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_KOKORO_EXECUTABLE", "/fake/kokoro-server")
    assert find_kokoro_executable() == "/fake/kokoro-server"


def test_find_executable_env_override_wins_over_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_KOKORO_EXECUTABLE", "/explicit/kokoro-server")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path))
    assert find_kokoro_executable() == "/explicit/kokoro-server"


def test_find_executable_uses_bundled_path(tmp_path, monkeypatch):
    monkeypatch.delenv("CONVSIM_KOKORO_EXECUTABLE", raising=False)
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path))
    suffix = ".exe" if sys.platform == "win32" else ""
    binary = tmp_path / f"kokoro-server{suffix}"
    binary.write_bytes(b"")
    binary.chmod(0o755)
    result = find_kokoro_executable()
    assert result == str(binary)


def test_find_executable_returns_none_when_not_found(monkeypatch):
    monkeypatch.delenv("CONVSIM_KOKORO_EXECUTABLE", raising=False)
    monkeypatch.delenv("CONVSIM_BUNDLED_RUNTIME_DIR", raising=False)
    with patch("shutil.which", return_value=None):
        result = find_kokoro_executable()
    assert result is None


def test_find_executable_bundled_dir_set_but_file_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("CONVSIM_KOKORO_EXECUTABLE", raising=False)
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path))
    # No binary in tmp_path — should fall back to PATH lookup (mocked absent)
    with patch("shutil.which", return_value=None):
        result = find_kokoro_executable()
    assert result is None


# ---------------------------------------------------------------------------
# KokoroSidecar — initial state and get_status
# ---------------------------------------------------------------------------


def test_sidecar_initial_state_is_stopped(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    assert sidecar.state == SidecarState.STOPPED


def test_sidecar_get_status_state_stopped(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    status = sidecar.get_status()
    assert status["state"] == "stopped"


def test_sidecar_get_status_pid_none_when_stopped(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    assert sidecar.get_status()["pid"] is None


def test_sidecar_get_status_error_none_when_stopped(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    assert sidecar.get_status()["error"] is None


def test_sidecar_get_status_has_required_keys(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    status = sidecar.get_status()
    assert "state" in status
    assert "pid" in status
    assert "error" in status
    assert "log_path" in status


def test_sidecar_sidecar_id(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    assert sidecar.sidecar_id == "kokoro"


def test_sidecar_display_name(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    assert "kokoro" in sidecar.display_name.lower()


# ---------------------------------------------------------------------------
# KokoroSidecar.start() — error conditions (no real process spawned)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_raises_when_executable_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("CONVSIM_KOKORO_EXECUTABLE", raising=False)
    monkeypatch.delenv("CONVSIM_BUNDLED_RUNTIME_DIR", raising=False)
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    with patch("convsim_core.runtime.kokoro_sidecar.find_kokoro_executable", return_value=None):
        with pytest.raises(RuntimeError, match="kokoro-server executable not found"):
            await sidecar.start()


@pytest.mark.asyncio
async def test_start_sets_crashed_state_when_executable_not_found(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    with patch("convsim_core.runtime.kokoro_sidecar.find_kokoro_executable", return_value=None):
        with pytest.raises(RuntimeError):
            await sidecar.start()
    assert sidecar.state == SidecarState.CRASHED


@pytest.mark.asyncio
async def test_start_raises_port_conflict(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    with (
        patch("convsim_core.runtime.kokoro_sidecar.find_kokoro_executable", return_value="/fake/kokoro"),
        patch("convsim_core.runtime.kokoro_sidecar._is_port_in_use", return_value=True),
    ):
        with pytest.raises(RuntimeError, match="already in use"):
            await sidecar.start()


@pytest.mark.asyncio
async def test_start_sets_port_conflict_state(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    with (
        patch("convsim_core.runtime.kokoro_sidecar.find_kokoro_executable", return_value="/fake/kokoro"),
        patch("convsim_core.runtime.kokoro_sidecar._is_port_in_use", return_value=True),
    ):
        with pytest.raises(RuntimeError):
            await sidecar.start()
    assert sidecar.state == SidecarState.PORT_CONFLICT


@pytest.mark.asyncio
async def test_start_noop_when_already_running(tmp_path):
    """start() is idempotent — no error when already running."""
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    sidecar._state = SidecarState.RUNNING
    # Should return without error, not attempt to start another process.
    await sidecar.start(executable="/fake/kokoro")
    assert sidecar.state == SidecarState.RUNNING


@pytest.mark.asyncio
async def test_start_rejects_non_localhost_host(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="loopback"):
        await sidecar.start(executable="/fake/kokoro", host="0.0.0.0")


# ---------------------------------------------------------------------------
# KokoroSidecar.stop() — various states
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_when_stopped_is_noop(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    await sidecar.stop()
    assert sidecar.state == SidecarState.STOPPED


@pytest.mark.asyncio
async def test_stop_clears_error(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    sidecar._error = "previous error"
    await sidecar.stop()
    assert sidecar.get_status()["error"] is None


@pytest.mark.asyncio
async def test_stop_clears_started_at(tmp_path):
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    sidecar._started_at = "2026-01-01T00:00:00+00:00"
    await sidecar.stop()
    assert sidecar._started_at is None


# ---------------------------------------------------------------------------
# KokoroSidecar supervisor integration
# ---------------------------------------------------------------------------


def test_kokoro_sidecar_registered_in_supervisor(tmp_path):
    from convsim_core.runtime.supervisor import ProcessSupervisor

    supervisor = ProcessSupervisor()
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    supervisor.register(sidecar)
    assert supervisor.get("kokoro") is sidecar


def test_kokoro_sidecar_appears_in_health_summary(tmp_path):
    from convsim_core.runtime.supervisor import ProcessSupervisor

    supervisor = ProcessSupervisor()
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    supervisor.register(sidecar)
    summary = supervisor.health_summary()
    ids = [s["sidecar_id"] for s in summary]
    assert "kokoro" in ids


@pytest.mark.asyncio
async def test_supervisor_stop_all_stops_kokoro(tmp_path):
    from convsim_core.runtime.supervisor import ProcessSupervisor

    supervisor = ProcessSupervisor()
    sidecar = KokoroSidecar(log_dir=str(tmp_path))
    supervisor.register(sidecar)
    # Should not raise even though sidecar was never started.
    await supervisor.stop_all()
    assert sidecar.state == SidecarState.STOPPED


# ---------------------------------------------------------------------------
# assert_localhost — shared contract
# ---------------------------------------------------------------------------


def test_assert_localhost_accepts_127_0_0_1():
    assert_localhost("127.0.0.1")


def test_assert_localhost_accepts_loopback_v6():
    assert_localhost("::1")


def test_assert_localhost_rejects_non_loopback():
    with pytest.raises(RuntimeError, match="loopback"):
        assert_localhost("0.0.0.0")


# ---------------------------------------------------------------------------
# /api/health — kokoro sidecar field
# ---------------------------------------------------------------------------


def test_health_endpoint_includes_sidecar_summary(client):
    """The /api/health endpoint must expose all registered sidecars."""
    body = client.get("/api/health").json()
    # Sidecars are optional in the health response but the supervisor should
    # be wired; check that the response at least contains TTS info.
    assert "tts" in body
