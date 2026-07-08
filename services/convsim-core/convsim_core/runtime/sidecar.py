# SPDX-License-Identifier: Apache-2.0
"""Managed llama-server sidecar process lifecycle.

Handles launching, health-polling, log capture, and graceful shutdown of a
local llama-server process. External llama.cpp users can skip this entirely;
the LlamaCppRuntime HTTP adapter works against any reachable llama-server.
"""
from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import IO


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


def find_executable() -> str | None:
    """Return the path to llama-server if found in PATH, else None."""
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
        except httpx.TransportError as exc:
            last_error = exc

        await asyncio.sleep(_HEALTH_POLL_INTERVAL)

    raise TimeoutError(
        f"llama-server did not become ready within {timeout}s. "
        f"Last error: {last_error}. Check log: {log_path}"
    )


class LlamaCppSidecar:
    """Owns the lifecycle of a single managed llama-server child process.

    One instance lives on ``app.state.sidecar`` for the duration of the
    server process. External llama.cpp users never call start(); the
    LlamaCppRuntime HTTP adapter connects directly to their server.
    """

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
            self._state = SidecarState.STOPPED
            self._started_at = None
            return
        await self._terminate_process()
        self._close_log()
        self._state = SidecarState.STOPPED
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
