# SPDX-License-Identifier: Apache-2.0
"""Tests for the llama-server sidecar process manager.

Unit tests cover command construction and state logic without spawning processes.
The integration test at the bottom spawns a real fake executable written to a
temp directory; it is marked asyncio and relies on a free port found at runtime.
"""
from __future__ import annotations

import os
import socket
import sys
import textwrap
from pathlib import Path

import pytest

from convsim_core.runtime.sidecar import (
    LlamaCppSidecar,
    SidecarState,
    _is_port_in_use,
    build_command,
    find_executable,
)


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
    cmd = build_command("/bin/llama-server", "model.gguf", host="0.0.0.0", port=9999)
    assert "0.0.0.0" in cmd
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


# ---------------------------------------------------------------------------
# Integration test — real fake executable
# ---------------------------------------------------------------------------


_FAKE_LLAMA_SERVER = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Minimal fake llama-server for sidecar integration testing.\"\"\"
    import http.server
    import sys

    port = 7356
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            break

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()
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


def _write_fake_server(tmp_path: Path) -> str:
    """Write the fake llama-server script and return its path."""
    exe = tmp_path / "fake-llama-server"
    exe.write_text(_FAKE_LLAMA_SERVER)
    exe.chmod(0o755)
    return str(exe)


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
    assert sidecar.get_status()["pid"] is None


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
