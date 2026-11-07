# SPDX-License-Identifier: Apache-2.0
"""Tests for the llama-server sidecar process manager.

Unit tests cover command construction and state logic without spawning processes.
The integration test at the bottom spawns a real fake executable written to a
temp directory; it is marked asyncio and relies on a free port found at runtime.
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

from convsim_core.runtime.launch import LAUNCH_ENV_VARS, LaunchConfig, resolve_launch_config
from convsim_core.runtime.sidecar import (
    LlamaCppSidecar,
    SidecarState,
    _is_port_in_use,
    build_command,
    find_executable,
)
from convsim_core.services.model_manager_service import register_user_gguf
from convsim_core.storage.database import Database


# ---------------------------------------------------------------------------
# build_command — pure unit tests, no I/O
# ---------------------------------------------------------------------------


def test_build_command_minimal():
    cmd = build_command("/usr/bin/llama-server", "/models/foo.gguf")
    assert cmd[0] == "/usr/bin/llama-server"
    assert "--model" in cmd
    assert "/models/foo.gguf" in cmd
    assert "--host" in cmd
    assert "127.0.0.1" in cmd
    assert "--port" in cmd
    assert "7356" in cmd


def test_build_command_custom_host_port():
    cmd = build_command("/bin/llama-server", "model.gguf", host="127.0.0.1", port=9999)
    assert "127.0.0.1" in cmd
    assert "9999" in cmd


def test_build_command_context_length():
    cmd = build_command("/bin/llama-server", "m.gguf", context_length=8192)
    idx = cmd.index("--ctx-size")
    assert cmd[idx + 1] == "8192"


def test_build_command_threads():
    cmd = build_command("/bin/llama-server", "m.gguf", threads=4)
    idx = cmd.index("--threads")
    assert cmd[idx + 1] == "4"


def test_build_command_gpu_layers():
    cmd = build_command("/bin/llama-server", "m.gguf", gpu_layers=32)
    idx = cmd.index("--n-gpu-layers")
    assert cmd[idx + 1] == "32"


def test_build_command_all_options():
    cmd = build_command(
        "/bin/llama-server", "m.gguf",
        host="127.0.0.1", port=7356,
        context_length=4096, threads=8, gpu_layers=0,
    )
    assert "--ctx-size" in cmd
    assert "--threads" in cmd
    assert "--n-gpu-layers" in cmd
    assert "4096" in cmd
    assert "8" in cmd
    assert "0" in cmd


def test_build_command_omits_optional_flags_when_none():
    cmd = build_command("/bin/llama-server", "m.gguf")
    assert "--ctx-size" not in cmd
    assert "--threads" not in cmd
    assert "--n-gpu-layers" not in cmd


def test_build_command_port_is_string_not_int():
    cmd = build_command("/bin/llama-server", "m.gguf", port=7356)
    port_idx = cmd.index("--port")
    assert isinstance(cmd[port_idx + 1], str)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_initial_state_is_stopped(tmp_path):
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    assert sidecar.state == SidecarState.STOPPED


def test_get_status_initial_fields(tmp_path):
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    status = sidecar.get_status()
    assert status["state"] == "stopped"
    assert status["pid"] is None
    assert status["model_path"] is None
    assert status["error"] is None
    assert status["started_at"] is None
    assert "127.0.0.1" == status["host"]
    assert 7356 == status["port"]


# ---------------------------------------------------------------------------
# Port conflict detection
# ---------------------------------------------------------------------------


def test_is_port_in_use_free_port():
    # A port we just discovered to be free should report as not in use
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # Port is now closed; should be free
    assert not _is_port_in_use("127.0.0.1", port)


def test_is_port_in_use_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert _is_port_in_use("127.0.0.1", port)


@pytest.mark.asyncio
async def test_start_raises_on_port_conflict(tmp_path):
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    # Bind a real socket to occupy the port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        occupied_port = s.getsockname()[1]

        with pytest.raises(RuntimeError, match="already in use"):
            await sidecar.start(
                "fake.gguf",
                executable="/bin/true",
                port=occupied_port,
            )

    assert sidecar.state == SidecarState.PORT_CONFLICT
    assert sidecar.get_status()["error"] is not None


# ---------------------------------------------------------------------------
# Missing executable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_raises_when_executable_missing(tmp_path):
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    with pytest.raises(RuntimeError, match="Failed to start"):
        await sidecar.start(
            "fake.gguf",
            executable="/nonexistent/llama-server",
            port=_free_port(),
            startup_timeout=2.0,
        )
    assert sidecar.state == SidecarState.CRASHED


# ---------------------------------------------------------------------------
# Stop when already stopped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_raises_on_generic_oserror(tmp_path):
    """Any OSError from create_subprocess_exec must leave state=CRASHED, not STARTING.

    FileNotFoundError and PermissionError were already handled; other OSError
    subclasses (e.g. EMFILE — too many open files) were not caught, which left
    _state=STARTING with an open log handle and caused 500 instead of 503.
    """
    from unittest.mock import patch

    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    async def _raise_emfile(*_a, **_kw):
        raise OSError(24, "Too many open files")

    with patch("asyncio.create_subprocess_exec", _raise_emfile):
        with pytest.raises(RuntimeError, match="Failed to start"):
            await sidecar.start(
                "fake.gguf",
                executable="/bin/true",
                port=_free_port(),
            )

    assert sidecar.state == SidecarState.CRASHED
    assert sidecar._log_fh is None  # log handle must be closed, not leaked


@pytest.mark.asyncio
async def test_start_raises_on_log_open_oserror(tmp_path):
    """OSError from opening the log file must produce state=CRASHED and RuntimeError.

    open(log_path, "ab") can fail with PermissionError, EMFILE, or similar.
    Before the fix these propagated as raw OSError, bypassing the router's
    (RuntimeError, TimeoutError) handler and returning 500 instead of 503.
    """
    from unittest.mock import patch

    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    with patch("builtins.open", side_effect=OSError(13, "Permission denied")):
        with pytest.raises(RuntimeError, match="Failed to open log file"):
            await sidecar.start(
                "fake.gguf",
                executable="/bin/true",
                port=_free_port(),
            )

    assert sidecar.state == SidecarState.CRASHED
    assert sidecar._log_fh is None


@pytest.mark.asyncio
async def test_stop_when_not_running_is_noop(tmp_path):
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    await sidecar.stop()  # must not raise
    assert sidecar.state == SidecarState.STOPPED


# ---------------------------------------------------------------------------
# find_executable — smoke test (may return None in CI)
# ---------------------------------------------------------------------------


def test_find_executable_returns_none_or_str():
    result = find_executable()
    assert result is None or isinstance(result, str)


def test_find_executable_env_override_wins(monkeypatch):
    """CONVSIM_LLAMA_CPP_EXECUTABLE takes precedence over PATH and bundled dir."""
    monkeypatch.setenv("CONVSIM_LLAMA_CPP_EXECUTABLE", "/custom/llama-server")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", "/somewhere/runtimes")
    assert find_executable() == "/custom/llama-server"


def test_find_executable_uses_bundled_dir(monkeypatch, tmp_path):
    """When no override is set, an executable bundled binary is resolved."""
    monkeypatch.delenv("CONVSIM_LLAMA_CPP_EXECUTABLE", raising=False)
    binary_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    binary = tmp_path / binary_name
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path))
    assert find_executable() == str(binary)


def test_find_executable_bundled_dir_missing_binary_falls_through(monkeypatch, tmp_path):
    """A bundled dir without the binary must not short-circuit to a bad path."""
    monkeypatch.delenv("CONVSIM_LLAMA_CPP_EXECUTABLE", raising=False)
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path))  # empty dir
    from unittest.mock import patch
    with patch("convsim_core.runtime.sidecar.shutil.which", return_value=None):
        # Also patch Path.home so user-installed path doesn't accidentally exist.
        with patch("convsim_core.runtime.sidecar.Path.home", return_value=tmp_path / "home"):
            assert find_executable() is None


def test_find_executable_finds_user_installed_path(monkeypatch, tmp_path):
    """find_executable() resolves a binary installed to ~/.convsim/bin/ without PATH."""
    monkeypatch.delenv("CONVSIM_LLAMA_CPP_EXECUTABLE", raising=False)
    monkeypatch.delenv("CONVSIM_BUNDLED_RUNTIME_DIR", raising=False)

    binary_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    user_bin = tmp_path / ".convsim" / "bin"
    user_bin.mkdir(parents=True)
    binary = user_bin / binary_name
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    from unittest.mock import patch
    with patch("convsim_core.runtime.sidecar.Path.home", return_value=tmp_path):
        with patch("convsim_core.runtime.sidecar.shutil.which", return_value=None):
            result = find_executable()

    assert result == str(binary)


def test_find_executable_user_installed_does_not_shadow_bundled(monkeypatch, tmp_path):
    """The bundled dir (step 2) takes priority over user-installed (step 3)."""
    monkeypatch.delenv("CONVSIM_LLAMA_CPP_EXECUTABLE", raising=False)

    binary_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"

    # Bundled binary
    bundled_bin = tmp_path / "bundled"
    bundled_bin.mkdir()
    bundled = bundled_bin / binary_name
    bundled.write_text("bundled")
    bundled.chmod(0o755)
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(bundled_bin))

    # User-installed binary (should be shadowed)
    user_home = tmp_path / "home"
    user_bin = user_home / ".convsim" / "bin"
    user_bin.mkdir(parents=True)
    user_binary = user_bin / binary_name
    user_binary.write_text("user-installed")
    user_binary.chmod(0o755)

    from unittest.mock import patch
    with patch("convsim_core.runtime.sidecar.Path.home", return_value=user_home):
        result = find_executable()

    assert result == str(bundled)


# ---------------------------------------------------------------------------
# API endpoint tests via TestClient
# ---------------------------------------------------------------------------


def test_sidecar_status_endpoint_initial(client):
    resp = client.get("/api/sidecar/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "stopped"
    assert data["pid"] is None
    assert "log_path" in data


def test_sidecar_stop_when_not_running_returns_200(client):
    resp = client.post("/api/sidecar/stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "stopped"
    assert "No managed" in data["message"]


def test_sidecar_stop_when_crashed_returns_stopped(client):
    """POST /api/sidecar/stop must return state=stopped and clear error when sidecar crashed.

    Without the state fix, the endpoint returned state="crashed" — contradicting
    the "No managed llama-server is running" message.
    Without the error fix, GET /api/sidecar/status would still report the crash
    error message after stop, which is confusing when state=stopped.
    """
    client.app.state.sidecar._state = SidecarState.CRASHED
    client.app.state.sidecar._error = "llama-server exited unexpectedly with code 1."

    resp = client.post("/api/sidecar/stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "stopped"
    assert "No managed" in data["message"]

    status = client.get("/api/sidecar/status").json()
    assert status["state"] == "stopped"
    assert status["started_at"] is None
    assert status["error"] is None
    assert status["model_path"] is None


def test_sidecar_stop_when_port_conflict_returns_stopped(client):
    """POST /api/sidecar/stop must return state=stopped and clear error for PORT_CONFLICT."""
    client.app.state.sidecar._state = SidecarState.PORT_CONFLICT
    client.app.state.sidecar._error = "Port 7356 on 127.0.0.1 is already in use."
    client.app.state.sidecar._model_path = "/some/model.gguf"

    resp = client.post("/api/sidecar/stop")
    assert resp.status_code == 200
    assert resp.json()["state"] == "stopped"

    status = client.get("/api/sidecar/status").json()
    assert status["error"] is None
    assert status["model_path"] is None


def test_sidecar_start_missing_executable_returns_503(client):
    resp = client.post(
        "/api/sidecar/start",
        json={
            "model_path": "/nonexistent/model.gguf",
            "executable": "/nonexistent/llama-server",
            "startup_timeout": 2.0,
        },
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "SIDECAR_START_FAILED"


def test_sidecar_start_timeout_returns_503(client):
    """Startup timeout (TimeoutError, not RuntimeError) must map to 503, not 500."""
    async def _raise_timeout(*_args, **_kwargs):
        raise TimeoutError("llama-server did not become ready within 1s")

    client.app.state.sidecar.start = _raise_timeout

    resp = client.post(
        "/api/sidecar/start",
        json={"model_path": "/fake/model.gguf", "startup_timeout": 1.0},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SIDECAR_START_FAILED"


def test_sidecar_start_returns_409_when_already_running(client):
    """POST /api/sidecar/start must return 409 if the sidecar is RUNNING."""
    client.app.state.sidecar._state = SidecarState.RUNNING

    resp = client.post(
        "/api/sidecar/start",
        json={"model_path": "/path/to/model.gguf"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SIDECAR_ALREADY_RUNNING"


def test_gpu_variant_endpoint_non_windows_returns_cpu(client, monkeypatch):
    """On non-Windows platforms the GPU-variant probe is skipped and returns cpu."""
    # The endpoint reads platform via a local ``import sys as _sys``, which
    # aliases the real sys module, so patch sys.platform directly.
    monkeypatch.setattr(sys, "platform", "linux")

    resp = client.get("/api/sidecar/gpu-variant")
    assert resp.status_code == 200
    body = resp.json()
    assert body["variant"] == "cpu"


def test_gpu_variant_endpoint_windows_reports_probe_result(client, monkeypatch):
    """On Windows the endpoint surfaces detect_windows_gpu_variant()'s result."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "convsim_core.routers.sidecar.detect_windows_gpu_variant",
        lambda: "vulkan",
    )

    resp = client.get("/api/sidecar/gpu-variant")
    assert resp.status_code == 200
    assert resp.json()["variant"] == "vulkan"


def test_sidecar_start_returns_409_when_starting(client):
    """POST /api/sidecar/start must return 409 if the sidecar is still STARTING.

    Without this guard, a second concurrent request would slip through the RUNNING
    check, spawn a second process, and overwrite the open log file handle.
    """
    client.app.state.sidecar._state = SidecarState.STARTING

    resp = client.post(
        "/api/sidecar/start",
        json={"model_path": "/path/to/model.gguf"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SIDECAR_ALREADY_RUNNING"


def test_sidecar_start_forwards_custom_host_and_port(client):
    """POST /api/sidecar/start must forward host and port to sidecar.start().

    The port-conflict error message tells users to "configure a different port",
    so the API must actually accept host/port fields and forward them.
    Only localhost addresses are accepted; non-localhost is rejected by start().
    """
    from unittest.mock import AsyncMock, patch

    captured = {}

    async def _mock_start(model_path, *, host, port, **kwargs):
        captured["host"] = host
        captured["port"] = port

    with patch.object(client.app.state.sidecar, "start", _mock_start):
        with patch.object(
            client.app.state.sidecar, "get_status",
            return_value={
                "state": "running", "pid": 42, "model_path": "/m.gguf",
                "log_path": "/tmp/runtime.log", "host": "127.0.0.1", "port": 9001,
                "error": None, "started_at": "2026-01-01T00:00:00+00:00",
            },
        ):
            resp = client.post(
                "/api/sidecar/start",
                json={"model_path": "/m.gguf", "host": "127.0.0.1", "port": 9001},
            )

    assert resp.status_code == 200
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9001


# ---------------------------------------------------------------------------
# Integration test — real fake executable
# ---------------------------------------------------------------------------


_FAKE_LLAMA_SERVER = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Minimal fake llama-server for sidecar integration testing.

    Handles:
      GET  /health                    → 200 {"status":"ok"}
      GET  /v1/models                 → 200 {"data":[{"id":"fake-model"}]}
      GET  /props                     → 200 slot count and per-slot context, derived
                                        from --ctx-size and the LLAMA_ARG_* variables
                                        the way llama-server derives them; the engine
                                        defaults (issue #489) when they are absent
      GET  /__launch                  → 200 {"argv": [...], "env": {LLAMA_ARG_*}}
                                        (test-only: what the engine was launched with)
      POST /v1/chat/completions       → SSE stream with one token then [DONE]

    HONOUR_LAUNCH_ENV=False models an engine build that predates the
    LLAMA_ARG_* variables: it starts all the same and keeps its defaults.
    \"\"\"
    import http.server
    import json
    import os
    import sys

    HONOUR_LAUNCH_ENV = __HONOUR_LAUNCH_ENV__

    # Engine defaults, as the log in issue #489 showed them.
    port = 7356
    ctx_size = 40960  # the model's trained length when no --ctx-size is given
    model_path = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if i + 1 >= len(args):
            break
        if arg == "--port":
            port = int(args[i + 1])
        elif arg == "--ctx-size":
            ctx_size = int(args[i + 1])
        elif arg == "--model":
            model_path = args[i + 1]

    def _env_int(name, default):
        raw = os.environ.get(name) if HONOUR_LAUNCH_ENV else None
        return int(raw) if raw else default

    n_parallel = _env_int("LLAMA_ARG_N_PARALLEL", 4)
    launch_env = {k: v for k, v in os.environ.items() if k.startswith("LLAMA_ARG_")}

    _PROPS = json.dumps({
        "total_slots": n_parallel,
        "default_generation_settings": {"n_ctx": ctx_size // n_parallel},
        "model_path": model_path,
    }).encode()
    _LAUNCH = json.dumps({"argv": args, "env": launch_env}).encode()

    _SSE_CHUNK = json.dumps({
        "choices": [{"delta": {"content": "hello"}, "finish_reason": None}],
        "usage": None,
    })
    _SSE_FINAL = json.dumps({
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    })
    _SSE_BODY = (
        f"data: {_SSE_CHUNK}\\n\\n"
        f"data: {_SSE_FINAL}\\n\\n"
        "data: [DONE]\\n\\n"
    ).encode()

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self._json(b'{"status":"ok"}')
            elif self.path == "/v1/models":
                self._json(b'{"data":[{"id":"fake-model"}]}')
            elif self.path == "/props":
                self._json(_PROPS)
            elif self.path == "/__launch":
                self._json(_LAUNCH)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            # Consume request body so the connection can proceed
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            if self.path == "/v1/chat/completions":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(_SSE_BODY)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(_SSE_BODY)
                self.wfile.flush()
            else:
                self.send_response(404)
                self.end_headers()

        def _json(self, body: bytes):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a, **_kw):
            pass

    with http.server.HTTPServer(("127.0.0.1", port), _H) as srv:
        srv.serve_forever()
""")


def _free_port() -> int:
    """Return a currently free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_fake_server(tmp_path: Path, *, honour_launch_env: bool = True) -> str:
    """Write the fake llama-server script and return its path.

    ``honour_launch_env=False`` writes a build that ignores the ``LLAMA_ARG_*``
    variables, standing in for an engine that predates them.
    """
    exe = tmp_path / "fake-llama-server"
    exe.write_text(
        _FAKE_LLAMA_SERVER.replace("__HONOUR_LAUNCH_ENV__", "True" if honour_launch_env else "False")
    )
    exe.chmod(0o755)
    return str(exe)


@pytest.mark.asyncio
async def test_wait_for_ready_retries_on_read_error(tmp_path):
    """_wait_for_ready must retry on ReadError, not raise an unhandled exception.

    ConnectError and TimeoutException were already caught. ReadError (connection
    reset mid-response) and RemoteProtocolError were not, which would have
    propagated through start() as a non-RuntimeError/TimeoutError type, bypassing
    the router's exception handler and producing a 500 instead of 503.
    Catching httpx.TransportError covers all transport-layer failures.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from convsim_core.runtime.sidecar import _wait_for_ready

    fake_process = MagicMock()
    fake_process.returncode = None

    call_count = 0

    async def _raise_read_error(*_a, **_kw):
        nonlocal call_count
        call_count += 1
        raise httpx.ReadError("connection reset by peer")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = _raise_read_error

    # timeout=1.5s, poll_interval=0.5s → at least 2 calls before deadline
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TimeoutError):
            await _wait_for_ready(
                fake_process,
                "http://127.0.0.1:9999/health",
                timeout=1.5,
                log_path=tmp_path / "runtime.log",
            )

    # Must have retried at least twice — if ReadError propagated immediately there
    # would be exactly 1 call and the assertion above would be a RuntimeError, not
    # a TimeoutError.
    assert call_count >= 2


@pytest.mark.asyncio
async def test_start_and_stop_with_fake_executable(tmp_path):
    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start(
        "fake-model.gguf",
        executable=exe,
        port=port,
        startup_timeout=15.0,
    )

    assert sidecar.state == SidecarState.RUNNING
    status = sidecar.get_status()
    assert status["pid"] is not None
    assert status["model_path"] == "fake-model.gguf"
    assert status["port"] == port
    assert status["error"] is None
    log_path = Path(status["log_path"])
    assert log_path.exists()

    await sidecar.stop()

    assert sidecar.state == SidecarState.STOPPED
    status = sidecar.get_status()
    assert status["pid"] is None
    assert status["model_path"] is None
    assert status["error"] is None
    assert status["started_at"] is None


@pytest.mark.asyncio
async def test_stop_clears_model_path_after_crash(tmp_path):
    """stop() must clear model_path regardless of whether the sidecar crashed.

    The state property transitions _state to CRASHED but does not touch
    _model_path. stop() must clear it so that GET /api/sidecar/status returns
    model_path=null after the sidecar is stopped, not the stale path.
    Also verifies that _process is set to None (resource cleanup).
    """
    import signal

    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("crash-model.gguf", executable=exe, port=port, startup_timeout=15.0)
    assert sidecar.state == SidecarState.RUNNING

    # Kill externally to trigger spontaneous crash, then read .state so the
    # property updates _state = CRASHED (the early-return path in stop()).
    os.kill(sidecar.get_status()["pid"], signal.SIGKILL)
    await asyncio.sleep(0.3)
    assert sidecar.state == SidecarState.CRASHED

    await sidecar.stop()

    assert sidecar.state == SidecarState.STOPPED
    status = sidecar.get_status()
    assert status["model_path"] is None
    assert status["error"] is None
    assert status["started_at"] is None
    assert sidecar._process is None


@pytest.mark.asyncio
async def test_start_crash_detected_on_immediate_exit(tmp_path):
    crasher = tmp_path / "crash-server"
    crasher.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n")
    crasher.chmod(0o755)

    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    with pytest.raises(Exception):
        await sidecar.start(
            "m.gguf",
            executable=str(crasher),
            port=port,
            startup_timeout=5.0,
        )

    assert sidecar.state == SidecarState.CRASHED
    assert sidecar.get_status()["error"] is not None


@pytest.mark.asyncio
async def test_kill_on_start_produces_non_empty_runtime_log(tmp_path):
    """runtime.log must be non-empty after a kill-on-start failure.

    The sidecar writes a timestamped header to runtime.log before launching
    the subprocess, so the file must have content even when the process exits
    immediately without producing any output.
    """
    crasher = tmp_path / "crash-server"
    # Write one line to stdout before exiting so the log captures subprocess output too.
    crasher.write_text(
        "#!/usr/bin/env python3\nimport sys\nprint('fatal: cannot initialise')\nsys.exit(1)\n"
    )
    crasher.chmod(0o755)

    log_dir = tmp_path / "logs"
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(log_dir))

    with pytest.raises(Exception):
        await sidecar.start(
            "m.gguf",
            executable=str(crasher),
            port=port,
            startup_timeout=5.0,
        )

    runtime_log = log_dir / "runtime.log"
    assert runtime_log.exists(), "runtime.log was not created"
    assert runtime_log.stat().st_size > 0, "runtime.log is empty after kill-on-start"
    content = runtime_log.read_text(errors="replace")
    # Header written before spawn must be present.
    assert "llama-server start" in content


@pytest.mark.asyncio
async def test_start_twice_when_already_running_is_noop(tmp_path):
    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("fake.gguf", executable=exe, port=port, startup_timeout=15.0)
    assert sidecar.state == SidecarState.RUNNING
    pid_before = sidecar.get_status()["pid"]

    # Second call should be a no-op (same process)
    await sidecar.start("other.gguf", executable=exe, port=port, startup_timeout=15.0)
    assert sidecar.get_status()["pid"] == pid_before

    await sidecar.stop()


@pytest.mark.asyncio
async def test_restart_after_spontaneous_crash(tmp_path):
    """start() must restart a crashed sidecar, not silently no-op.

    Regression test: start() was checking self._state (raw field) instead of
    self.state (property). A spontaneously crashed process leaves _state as
    RUNNING until the property is called, so start() would return early without
    restarting.
    """
    import signal

    exe = _write_fake_server(tmp_path)
    port1 = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("fake.gguf", executable=exe, port=port1, startup_timeout=15.0)
    assert sidecar.state == SidecarState.RUNNING
    pid = sidecar.get_status()["pid"]

    # Kill the child externally, bypassing stop()
    os.kill(pid, signal.SIGKILL)
    await asyncio.sleep(0.3)

    # Calling start() directly (without first reading .state) must detect the
    # crash via the property and proceed to restart, not silently return.
    port2 = _free_port()
    await sidecar.start("fake.gguf", executable=exe, port=port2, startup_timeout=15.0)

    assert sidecar.state == SidecarState.RUNNING
    assert sidecar.get_status()["pid"] != pid

    await sidecar.stop()


@pytest.mark.asyncio
async def test_log_file_closed_after_spontaneous_crash(tmp_path):
    """state property must close _log_fh when it detects a crash.

    Regression test: the log file handle was leaked when a process exited
    spontaneously because _close_log() was only called in the startup-failure
    path, not in the state property's crash-detection branch.
    """
    import signal

    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("fake.gguf", executable=exe, port=port, startup_timeout=15.0)
    log_fh = sidecar._log_fh
    assert log_fh is not None

    os.kill(sidecar.get_status()["pid"], signal.SIGKILL)
    await asyncio.sleep(0.3)

    # Accessing .state triggers crash detection; the log handle must be closed.
    assert sidecar.state == SidecarState.CRASHED
    assert sidecar._log_fh is None
    assert log_fh.closed


# ---------------------------------------------------------------------------
# No executable in PATH (executable=None, find_executable returns None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_raises_when_no_executable_in_path(tmp_path):
    """start() with executable=None and nothing in PATH must raise RuntimeError.

    This exercises the find_executable() → None → RuntimeError("not found in PATH")
    path, which is distinct from the explicit-bad-path path (FileNotFoundError from
    create_subprocess_exec). State must remain STOPPED since no state changes happen
    before this early-return error.
    """
    from unittest.mock import patch

    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    with patch("convsim_core.runtime.sidecar.find_executable", return_value=None):
        with pytest.raises(RuntimeError, match="executable not found in PATH"):
            await sidecar.start("fake.gguf", port=_free_port())

    # No state change — sidecar was never touched
    assert sidecar.state == SidecarState.STOPPED
    assert sidecar._log_fh is None


# ---------------------------------------------------------------------------
# Timeout message includes HTTP status when server returns non-200 responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_ready_timeout_message_includes_http_status(tmp_path):
    """Timeout message must report last HTTP status, not 'Last error: None'.

    When llama-server starts but keeps returning HTTP 503 (model still loading)
    and the startup timeout elapses, the old code produced:
        'Last error: None. Check log: ...'
    which is not actionable. The fixed code must include the HTTP status code
    so users know the server was reachable but still loading.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from convsim_core.runtime.sidecar import _wait_for_ready

    fake_process = MagicMock()
    fake_process.returncode = None

    mock_resp = MagicMock()
    mock_resp.status_code = 503

    async def _return_503(*_a, **_kw):
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = _return_503

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TimeoutError) as exc_info:
            await _wait_for_ready(
                fake_process,
                "http://127.0.0.1:9999/health",
                timeout=1.2,
                log_path=tmp_path / "runtime.log",
            )

    assert "503" in str(exc_info.value), (
        "Timeout message should include the last HTTP status (503), not 'Last error: None'"
    )


# ---------------------------------------------------------------------------
# End-to-end integration: sidecar + runtime adapter + streaming chat
#
# These tests use the enhanced _FAKE_LLAMA_SERVER (which now handles
# GET /health, GET /v1/models, and POST /v1/chat/completions) to verify the
# full pipeline without a real model or GPU.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_chat_via_fake_server(tmp_path):
    """LlamaCppRuntime.chat_stream() works end-to-end with the fake llama-server.

    This is the CI-safe mock-server integration test: a real subprocess runs
    the fake HTTP server, the sidecar manages its lifecycle, and the runtime
    adapter communicates with it over localhost — no model weights needed.
    """
    from convsim_core.runtime.llama_cpp import LlamaCppConfig, LlamaCppRuntime
    from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest, ChatToken

    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("fake-model.gguf", executable=exe, port=port, startup_timeout=15.0)
    assert sidecar.state == SidecarState.RUNNING

    try:
        runtime = LlamaCppRuntime(
            LlamaCppConfig(base_url=f"http://127.0.0.1:{port}", model_id="fake-model")
        )

        request = ChatRequest(messages=[ChatMessage(role="user", content="hello")])
        tokens: list[str] = []
        final: ChatFinal | None = None

        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatToken):
                tokens.append(chunk.text)
            elif isinstance(chunk, ChatFinal):
                final = chunk

        assert final is not None, "chat_stream() must yield a ChatFinal"
        assert final.text == "hello", f"Unexpected text: {final.text!r}"
        assert len(tokens) >= 1

        # Capability flags must be set correctly for the llama_cpp adapter
        caps = runtime.capabilities
        assert caps.streaming is True, "streaming must be True"
        assert caps.json_schema is True, "json_schema must be True (enabled by default)"
        assert caps.grammar is False
        assert caps.tool_calling is False

    finally:
        await sidecar.stop()


@pytest.mark.asyncio
async def test_list_models_via_fake_server(tmp_path):
    """LlamaCppRuntime.list_models() returns the models served by the fake server."""
    from convsim_core.runtime.llama_cpp import LlamaCppConfig, LlamaCppRuntime

    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("fake-model.gguf", executable=exe, port=port, startup_timeout=15.0)
    assert sidecar.state == SidecarState.RUNNING

    try:
        runtime = LlamaCppRuntime(
            LlamaCppConfig(base_url=f"http://127.0.0.1:{port}")
        )
        models = await runtime.list_models()
        assert len(models) == 1
        assert models[0].id == "fake-model"
    finally:
        await sidecar.stop()


@pytest.mark.asyncio
async def test_structured_output_via_fake_server(tmp_path):
    """Structured-output (json_schema) path works when json_schema is sent to fake server.

    The fake server echoes a token "hello"; the runtime must attempt to parse
    it as JSON and fall back gracefully (structured=None) without crashing.
    """
    from convsim_core.runtime.llama_cpp import LlamaCppConfig, LlamaCppRuntime
    from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest

    exe = _write_fake_server(tmp_path)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start("fake-model.gguf", executable=exe, port=port, startup_timeout=15.0)

    try:
        runtime = LlamaCppRuntime(
            LlamaCppConfig(base_url=f"http://127.0.0.1:{port}")
        )
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="go")],
            json_schema=schema,
        )
        final: ChatFinal | None = None
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                final = chunk

        assert final is not None
        # "hello" is not valid JSON → structured must be None (graceful fallback)
        assert final.structured is None

    finally:
        await sidecar.stop()


@pytest.mark.asyncio
async def test_start_disables_model_reasoning_via_env(tmp_path, monkeypatch):
    """The spawned llama-server must run with LLAMA_ARG_REASONING=off.

    Reasoning-family models (Qwen3, R1 distils) otherwise burn the turn token
    budget on chain-of-thought: the structured turn JSON gets truncated, every
    turn degrades to the fallback utterance, and latency multiplies. The env
    var (unlike the CLI flag) is ignored by older llama-server binaries, so
    user-installed engines keep starting.
    """
    from convsim_core.runtime.sidecar import LlamaCppSidecar

    captured: dict = {}

    async def _fake_exec(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        raise OSError("stop after capture")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path))
    with pytest.raises(RuntimeError):
        await sidecar.start("/tmp/model.gguf", executable="/tmp/llama-server")

    assert captured["env"] is not None
    assert captured["env"].get("LLAMA_ARG_REASONING") == "off"


@pytest.mark.asyncio
async def test_start_respects_existing_reasoning_env(tmp_path, monkeypatch):
    """An explicit user override of LLAMA_ARG_REASONING wins over the default."""
    from convsim_core.runtime.sidecar import LlamaCppSidecar

    captured: dict = {}

    async def _fake_exec(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        raise OSError("stop after capture")

    monkeypatch.setenv("LLAMA_ARG_REASONING", "on")
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path))
    with pytest.raises(RuntimeError):
        await sidecar.start("/tmp/model.gguf", executable="/tmp/llama-server")

    assert captured["env"].get("LLAMA_ARG_REASONING") == "on"


# ---------------------------------------------------------------------------
# Launch configuration (issue #523): one slot, explicit context, small batches
# ---------------------------------------------------------------------------


@pytest.fixture()
def clean_launch_env(monkeypatch):
    """Keep LLAMA_ARG_* from the developer's shell out of these tests."""
    for name in LAUNCH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _seed_registry_model(conn, *, registry_id: str, context_length: int, file_path: str) -> None:
    """A registry row plus the installed-model row that points at ``file_path``."""
    conn.execute(
        "INSERT INTO model_registry (id, name, provider, context_length) VALUES (?, ?, ?, ?)",
        (registry_id, "Registry Model", "test", context_length),
    )
    conn.execute(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status) "
        "VALUES (?, ?, ?, 'ready')",
        (registry_id, Path(file_path).name, file_path),
    )
    conn.commit()


async def _capture_launch(tmp_path, monkeypatch, **start_kwargs) -> dict:
    """Run start() up to the spawn and return the argv and env it would use."""
    captured: dict = {}

    async def _fake_exec(*args, **kwargs):
        captured["argv"] = list(args)
        captured["env"] = kwargs.get("env")
        raise OSError("stop after capture")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
    with pytest.raises(RuntimeError):
        await sidecar.start("/tmp/model.gguf", executable="/tmp/llama-server", **start_kwargs)
    return captured


@pytest.mark.asyncio
async def test_start_applies_launch_config_to_command_line_and_env(
    tmp_path, monkeypatch, clean_launch_env
):
    """The context size goes on the command line; slots, batch and cache go in
    the environment, where an engine build lacking the flag ignores them
    instead of refusing to start. No slot id is sent anywhere."""
    captured = await _capture_launch(tmp_path, monkeypatch, launch=LaunchConfig(context_length=6144))

    argv = captured["argv"]
    assert argv[argv.index("--ctx-size") + 1] == "6144"
    for flag in ("--parallel", "-np", "--batch-size", "-b", "--cache-ram", "--id-slot"):
        assert flag not in argv

    env = captured["env"]
    assert env["LLAMA_ARG_N_PARALLEL"] == "1"
    assert env["LLAMA_ARG_BATCH"] == "256"
    assert env["LLAMA_ARG_CACHE_RAM"] == "1024"
    assert env["LLAMA_ARG_REASONING"] == "off"
    assert "LLAMA_ARG_CTX_SIZE" not in env


@pytest.mark.asyncio
async def test_start_without_launch_config_uses_the_defaults(tmp_path, monkeypatch, clean_launch_env):
    """A start that resolved nothing still never runs on the engine's own defaults."""
    captured = await _capture_launch(tmp_path, monkeypatch)

    argv = captured["argv"]
    assert argv[argv.index("--ctx-size") + 1] == "8192"
    assert captured["env"]["LLAMA_ARG_N_PARALLEL"] == "1"
    assert captured["env"]["LLAMA_ARG_BATCH"] == "256"
    assert captured["env"]["LLAMA_ARG_CACHE_RAM"] == "1024"


@pytest.mark.asyncio
async def test_start_explicit_context_length_wins_over_launch_config(
    tmp_path, monkeypatch, clean_launch_env
):
    captured = await _capture_launch(
        tmp_path, monkeypatch, context_length=2048, launch=LaunchConfig(context_length=6144)
    )
    argv = captured["argv"]
    assert argv[argv.index("--ctx-size") + 1] == "2048"


@pytest.mark.asyncio
async def test_start_respects_operator_launch_env_overrides(tmp_path, monkeypatch, clean_launch_env):
    """A LLAMA_ARG_* already in the app's environment wins — the same rule as
    LLAMA_ARG_REASONING — and a pinned LLAMA_ARG_CTX_SIZE keeps --ctx-size off
    the command line so the flag cannot silently beat the variable."""
    monkeypatch.setenv("LLAMA_ARG_N_PARALLEL", "2")
    monkeypatch.setenv("LLAMA_ARG_CTX_SIZE", "4096")

    captured = await _capture_launch(tmp_path, monkeypatch, launch=LaunchConfig(context_length=6144))

    assert captured["env"]["LLAMA_ARG_N_PARALLEL"] == "2"
    assert captured["env"]["LLAMA_ARG_CTX_SIZE"] == "4096"
    assert "--ctx-size" not in captured["argv"]
    assert captured["env"]["LLAMA_ARG_BATCH"] == "256"  # not overridden → still applied


@pytest.mark.asyncio
async def test_runtime_log_header_records_the_launch(tmp_path, monkeypatch, clean_launch_env):
    """The runtime.log header — what #489 was diagnosed from — shows how the
    engine was launched, variables included."""
    await _capture_launch(tmp_path, monkeypatch, launch=LaunchConfig(context_length=6144))

    text = (tmp_path / "logs" / "runtime.log").read_text()
    assert "cmd: " in text
    assert "--ctx-size 6144" in text
    assert "env: " in text
    for item in ("LLAMA_ARG_N_PARALLEL=1", "LLAMA_ARG_BATCH=256", "LLAMA_ARG_CACHE_RAM=1024"):
        assert item in text


async def _props_and_launch(port: int) -> tuple[dict, dict]:
    """What the fake engine ended up with, and what it was launched with."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        props = (await client.get(f"http://127.0.0.1:{port}/props")).json()
        seen = (await client.get(f"http://127.0.0.1:{port}/__launch")).json()
    return props, seen


@pytest.mark.asyncio
async def test_fake_engine_reports_one_slot_with_the_registry_context(tmp_path, clean_launch_env):
    """End to end against the fake engine: resolve the launch configuration for
    a registry model, start, and read back what the engine ended up with."""
    db = Database.open(str(tmp_path / "db"))
    try:
        conn = db.connection()
        model = tmp_path / "registry-model.gguf"
        model.write_bytes(b"gguf")
        _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))
        launch = resolve_launch_config(str(model), conn)
        assert launch.context_length == 6144

        exe = _write_fake_server(tmp_path)
        port = _free_port()
        sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
        await sidecar.start(
            str(model), executable=exe, port=port, startup_timeout=15.0, launch=launch
        )
        try:
            assert sidecar.state == SidecarState.RUNNING
            props, seen = await _props_and_launch(port)
        finally:
            await sidecar.stop()
    finally:
        db.close()

    assert props["total_slots"] == 1
    assert props["default_generation_settings"]["n_ctx"] == 6144
    assert props["model_path"] == str(model)
    assert seen["env"]["LLAMA_ARG_N_PARALLEL"] == "1"
    assert seen["env"]["LLAMA_ARG_BATCH"] == "256"
    assert seen["env"]["LLAMA_ARG_CACHE_RAM"] == "1024"
    assert seen["argv"][seen["argv"].index("--ctx-size") + 1] == "6144"


@pytest.mark.asyncio
async def test_fake_engine_gives_a_player_supplied_model_8192_and_one_slot(
    tmp_path, clean_launch_env
):
    """A GGUF the player registered has no registry row: 8192 tokens, one slot."""
    db = Database.open(str(tmp_path / "db"))
    try:
        conn = db.connection()
        model = tmp_path / "my-own.gguf"
        model.write_bytes(b"gguf")
        register_user_gguf(conn, path=str(model))
        launch = resolve_launch_config(str(model), conn)

        exe = _write_fake_server(tmp_path)
        port = _free_port()
        sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))
        await sidecar.start(
            str(model), executable=exe, port=port, startup_timeout=15.0, launch=launch
        )
        try:
            props, _seen = await _props_and_launch(port)
        finally:
            await sidecar.stop()
    finally:
        db.close()

    assert props["total_slots"] == 1
    assert props["default_generation_settings"]["n_ctx"] == 8192


@pytest.mark.asyncio
async def test_engine_that_ignores_the_launch_variables_still_starts(tmp_path, clean_launch_env):
    """An engine build that does not recognise LLAMA_ARG_* must start all the
    same — the reason these settings are variables and not flags."""
    exe = _write_fake_server(tmp_path, honour_launch_env=False)
    port = _free_port()
    sidecar = LlamaCppSidecar(log_dir=str(tmp_path / "logs"))

    await sidecar.start(
        "fake-model.gguf", executable=exe, port=port, startup_timeout=15.0,
        launch=LaunchConfig(context_length=8192),
    )
    try:
        assert sidecar.state == SidecarState.RUNNING
        props, seen = await _props_and_launch(port)
    finally:
        await sidecar.stop()

    # The variables reached the process but were ignored: the engine kept its
    # own slot count, while --ctx-size (a flag every build has) still applied.
    assert seen["env"]["LLAMA_ARG_N_PARALLEL"] == "1"
    assert props["total_slots"] == 4
    assert props["default_generation_settings"]["n_ctx"] == 8192 // 4


_RUNNING_STATUS = {
    "state": "running", "pid": 42, "model_path": "/m.gguf",
    "log_path": "/tmp/runtime.log", "host": "127.0.0.1", "port": 7356,
    "error": None, "started_at": "2026-01-01T00:00:00+00:00",
}


def test_sidecar_start_endpoint_passes_the_registry_launch_config(client, tmp_path):
    """POST /api/sidecar/start — the third start site — resolves the same launch
    configuration as the autostart and the install pipeline for the same model."""
    from unittest.mock import patch

    conn = client.app.state.db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))

    captured: dict = {}

    async def _mock_start(model_path, **kwargs):
        captured["model_path"] = model_path
        captured.update(kwargs)

    with patch.object(client.app.state.sidecar, "start", _mock_start), \
         patch.object(client.app.state.sidecar, "get_status", return_value=_RUNNING_STATUS):
        resp = client.post("/api/sidecar/start", json={"model_path": str(model)})

    assert resp.status_code == 200, resp.text
    assert captured["model_path"] == str(model)
    assert captured["launch"] == resolve_launch_config(str(model), conn)
    assert captured["launch"] == LaunchConfig(context_length=6144)
    # Nothing explicit in the body: the launch configuration decides the context.
    assert captured["context_length"] is None


def test_sidecar_start_endpoint_explicit_context_length_is_still_forwarded(client, tmp_path):
    """An explicit context_length in the request body keeps winning; the rest of
    the launch configuration (one slot, small batches) still applies."""
    from unittest.mock import patch

    model = tmp_path / "not-installed.gguf"
    model.write_bytes(b"gguf")
    captured: dict = {}

    async def _mock_start(model_path, **kwargs):
        captured.update(kwargs)

    with patch.object(client.app.state.sidecar, "start", _mock_start), \
         patch.object(client.app.state.sidecar, "get_status", return_value=_RUNNING_STATUS):
        resp = client.post(
            "/api/sidecar/start", json={"model_path": str(model), "context_length": 2048}
        )

    assert resp.status_code == 200, resp.text
    assert captured["context_length"] == 2048
    assert captured["launch"] == LaunchConfig()  # no registry row → the 8192 default
