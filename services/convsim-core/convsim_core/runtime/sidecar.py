# SPDX-License-Identifier: Apache-2.0
"""Managed llama-server sidecar process lifecycle.

Handles launching, health-polling, log capture, and graceful shutdown of a
local llama-server process. External llama.cpp users can skip this entirely;
the LlamaCppRuntime HTTP adapter works against any reachable llama-server.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import IO

from convsim_core.runtime.supervisor import SidecarProcess, assert_localhost


class SidecarState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"
    PORT_CONFLICT = "port_conflict"


_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7356
_STARTUP_TIMEOUT = 120.0
_HEALTH_POLL_INTERVAL = 0.5
_TERMINATE_TIMEOUT = 5.0


def build_command(
    executable: str,
    model_path: str,
    *,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    context_length: int | None = None,
    threads: int | None = None,
    gpu_layers: int | None = None,
) -> list[str]:
    """Build the llama-server argument list from the given parameters.

    Kept as a module-level function so command construction can be unit-tested
    without touching the process or file system.
    """
    cmd: list[str] = [
        executable,
        "--model", model_path,
        "--host", host,
        "--port", str(port),
    ]
    if context_length is not None:
        cmd.extend(["--ctx-size", str(context_length)])
    if threads is not None:
        cmd.extend(["--threads", str(threads)])
    if gpu_layers is not None:
        cmd.extend(["--n-gpu-layers", str(gpu_layers)])
    return cmd


_EXECUTABLE_ENV_VAR = "CONVSIM_LLAMA_CPP_EXECUTABLE"
_BUNDLED_RUNTIME_DIR_ENV_VAR = "CONVSIM_BUNDLED_RUNTIME_DIR"
_BUNDLED_BINARY_NAME = "llama-server"


def find_executable() -> str | None:
    """Resolve the llama-server binary using the Steam bundling convention.

    Resolution order (first hit wins), matching docs/sidecar-bundling.md:

    1. Explicit override — the ``CONVSIM_LLAMA_CPP_EXECUTABLE`` environment
       variable. Used by developer builds and tests to point at any binary.
       The value is returned verbatim (existence is validated when the process
       is spawned) so an explicit override always wins.
    2. Bundled path — ``<CONVSIM_BUNDLED_RUNTIME_DIR>/llama-server`` (Steam
       depot builds). The ``.exe`` suffix is appended on Windows. Only used
       when the file exists and is executable.
    3. User-installed path — ``~/.convsim/bin/llama-server[.exe]``, the
       default destination used by ``download_binary()``. Resolves immediately
       after an in-app install without requiring a PATH change or app restart.
    4. PATH lookup — ``shutil.which("llama-server")`` (developer builds).

    Returns None when no candidate resolves.
    """
    override = os.environ.get(_EXECUTABLE_ENV_VAR)
    if override:
        return override

    bundled_dir = os.environ.get(_BUNDLED_RUNTIME_DIR_ENV_VAR)
    if bundled_dir:
        suffix = ".exe" if sys.platform == "win32" else ""
        candidate = Path(bundled_dir) / f"{_BUNDLED_BINARY_NAME}{suffix}"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    suffix = ".exe" if sys.platform == "win32" else ""
    user_installed = Path.home() / ".convsim" / "bin" / f"{_BUNDLED_BINARY_NAME}{suffix}"
    if user_installed.is_file() and os.access(user_installed, os.X_OK):
        return str(user_installed)

    return shutil.which("llama-server") or shutil.which("llama_server")


def _is_port_in_use(host: str, port: int) -> bool:
    """Return True if something is already listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


async def _wait_for_ready(
    process: asyncio.subprocess.Process,
    health_url: str,
    timeout: float,
    log_path: Path,
) -> None:
    """Poll health_url until 200 OK, or raise on process crash or timeout."""
    import httpx

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_error: Exception | None = None
    last_status: int | None = None

    while loop.time() < deadline:
        if process.returncode is not None:
            raise RuntimeError(
                f"llama-server exited early (code {process.returncode}). "
                f"Check log: {log_path}"
            )

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(health_url)
                if resp.status_code == 200:
                    return
                # 503 = model still loading; keep polling
                last_status = resp.status_code
                last_error = None
        except httpx.TransportError as exc:
            last_error = exc
            last_status = None

        await asyncio.sleep(_HEALTH_POLL_INTERVAL)

    if last_error is not None:
        detail = f"Last error: {last_error}"
    elif last_status is not None:
        detail = f"Last HTTP status: {last_status} (server may still be loading the model)"
    else:
        detail = "no response received"
    raise TimeoutError(
        f"llama-server did not become ready within {timeout}s. "
        f"{detail}. Check log: {log_path}"
    )


class LlamaCppSidecar(SidecarProcess):
    """Owns the lifecycle of a single managed llama-server child process.

    Implements SidecarProcess so the ProcessSupervisor can stop it at exit
    alongside any future sidecars (whisper.cpp, kokoro, …).

    One instance lives on ``app.state.sidecar`` for the duration of the
    server process. External llama.cpp users never call start(); the
    LlamaCppRuntime HTTP adapter connects directly to their server.
    """

    @property
    def sidecar_id(self) -> str:
        return "llama_cpp"

    @property
    def display_name(self) -> str:
        return "llama.cpp (llama-server)"

    def __init__(self, log_dir: str) -> None:
        self._log_dir = Path(log_dir)
        self._log_path = self._log_dir / "runtime.log"
        self._log_fh: IO[bytes] | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._state = SidecarState.STOPPED
        self._error: str | None = None
        self._model_path: str | None = None
        self._host: str = _DEFAULT_HOST
        self._port: int = _DEFAULT_PORT
        self._started_at: str | None = None

    async def start(
        self,
        model_path: str,
        *,
        executable: str | None = None,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        context_length: int | None = None,
        threads: int | None = None,
        gpu_layers: int | None = None,
        startup_timeout: float = _STARTUP_TIMEOUT,
    ) -> None:
        """Launch llama-server and block until the /health endpoint is ready.

        Raises RuntimeError on port conflict, missing executable, or startup
        failure. Raises TimeoutError if startup_timeout elapses before /health
        returns 200.
        """
        if self.state in (SidecarState.RUNNING, SidecarState.STARTING):
            return

        assert_localhost(host)

        exe = executable or find_executable()
        if exe is None:
            raise RuntimeError(
                "llama-server executable not found in PATH. "
                "Install llama.cpp or set the 'executable' field in the request."
            )

        if _is_port_in_use(host, port):
            self._state = SidecarState.PORT_CONFLICT
            self._error = (
                f"Port {port} on {host} is already in use. "
                "Stop the existing process or configure a different port."
            )
            raise RuntimeError(self._error)

        cmd = build_command(
            exe, model_path,
            host=host, port=port,
            context_length=context_length,
            threads=threads,
            gpu_layers=gpu_layers,
        )

        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._log_dir / "runtime.log"
        try:
            log_fh: IO[bytes] = open(self._log_path, "ab")  # noqa: WPS515
        except OSError as exc:
            self._state = SidecarState.CRASHED
            self._error = f"Failed to open log file {self._log_path}: {exc}"
            raise RuntimeError(self._error) from exc
        self._log_fh = log_fh

        self._state = SidecarState.STARTING
        self._error = None
        self._model_path = model_path
        self._host = host
        self._port = port
        self._started_at = datetime.now(timezone.utc).isoformat()

        header = (
            f"\n--- llama-server start {self._started_at} ---\n"
            f"cmd: {' '.join(cmd)}\n"
        ).encode()
        log_fh.write(header)
        log_fh.flush()

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            self._state = SidecarState.CRASHED
            self._error = f"Failed to start llama-server: {exc}"
            self._close_log()
            raise RuntimeError(self._error) from exc

        health_url = f"http://{host}:{port}/health"
        try:
            await _wait_for_ready(self._process, health_url, startup_timeout, self._log_path)
        except Exception as exc:
            self._state = SidecarState.CRASHED
            self._error = str(exc)
            await self._terminate_process()
            self._close_log()
            raise

        self._state = SidecarState.RUNNING

    async def stop(self) -> None:
        """Terminate the managed process and release resources."""
        if self._state not in (SidecarState.RUNNING, SidecarState.STARTING):
            self._process = None
            self._state = SidecarState.STOPPED
            self._error = None
            self._model_path = None
            self._started_at = None
            return
        await self._terminate_process()
        self._close_log()
        self._state = SidecarState.STOPPED
        self._error = None
        self._model_path = None
        self._started_at = None

    @property
    def state(self) -> SidecarState:
        """Current sidecar state; detects crash by polling process returncode."""
        if (
            self._state == SidecarState.RUNNING
            and self._process is not None
            and self._process.returncode is not None
        ):
            self._state = SidecarState.CRASHED
            self._error = (
                f"llama-server exited unexpectedly with code {self._process.returncode}. "
                f"Check log: {self._log_path}"
            )
            self._close_log()
        return self._state

    def get_status(self) -> dict:
        """Return a serialisable snapshot of the current sidecar state."""
        current_state = self.state
        return {
            "state": current_state.value,
            "pid": (
                self._process.pid
                if self._process is not None and current_state == SidecarState.RUNNING
                else None
            ),
            "model_path": self._model_path,
            "error": self._error,
            "log_path": str(self._log_path),
            "host": self._host,
            "port": self._port,
            "started_at": self._started_at,
        }

    async def _terminate_process(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=_TERMINATE_TIMEOUT)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        except ProcessLookupError:
            pass
        self._process = None

    def _close_log(self) -> None:
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            except OSError:
                pass
            self._log_fh = None
