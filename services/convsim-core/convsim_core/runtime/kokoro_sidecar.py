# SPDX-License-Identifier: Apache-2.0
"""Managed Kokoro TTS server sidecar process lifecycle.

Handles launching, health-polling, log capture, and graceful shutdown of a
local Kokoro TTS server process. Users who run Kokoro externally (e.g. via
Docker) skip this entirely; the KokoroTtsWorker HTTP adapter connects directly
to any reachable server bound on the configured port.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from convsim_core.runtime.supervisor import SidecarProcess, assert_localhost
from convsim_core.runtime.sidecar import SidecarState

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7358
_STARTUP_TIMEOUT = 120.0
_HEALTH_POLL_INTERVAL = 0.5
_TERMINATE_TIMEOUT = 5.0

_EXECUTABLE_ENV_VAR = "CONVSIM_KOKORO_EXECUTABLE"
_BUNDLED_RUNTIME_DIR_ENV_VAR = "CONVSIM_BUNDLED_RUNTIME_DIR"
_BUNDLED_BINARY_NAME = "kokoro-server"


def find_kokoro_executable() -> str | None:
    """Resolve the Kokoro TTS server binary using the Steam bundling convention.

    Resolution order (first hit wins):

    1. ``CONVSIM_KOKORO_EXECUTABLE`` env var — explicit override.
    2. ``<CONVSIM_BUNDLED_RUNTIME_DIR>/kokoro-server`` — Steam depot build.
       ``.exe`` suffix appended on Windows. Only used when the file exists
       and is executable.
    3. PATH lookup — ``kokoro-server`` then ``kokoro_server`` (developer builds).

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

    return shutil.which("kokoro-server") or shutil.which("kokoro_server")


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


async def _wait_for_kokoro_ready(
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
                f"Kokoro server exited early (code {process.returncode}). "
                f"Check log: {log_path}"
            )

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(health_url)
                if resp.status_code == 200:
                    return
                last_status = resp.status_code
                last_error = None
        except httpx.TransportError as exc:
            last_error = exc
            last_status = None

        await asyncio.sleep(_HEALTH_POLL_INTERVAL)

    if last_error is not None:
        detail = f"Last error: {last_error}"
    elif last_status is not None:
        detail = f"Last HTTP status: {last_status}"
    else:
        detail = "no response received"
    raise TimeoutError(
        f"Kokoro TTS server did not become ready within {timeout}s. "
        f"{detail}. Check log: {log_path}"
    )


class KokoroSidecar(SidecarProcess):
    """Owns the lifecycle of a single managed Kokoro TTS server child process.

    Implements SidecarProcess so the ProcessSupervisor can stop it at exit
    alongside other sidecars (llama.cpp, whisper.cpp, …).

    One instance lives on ``app.state.kokoro_sidecar`` for the duration of
    the server process.  Users who run Kokoro externally (e.g. Docker) never
    call start(); the KokoroTtsWorker HTTP adapter connects to their server.
    """

    @property
    def sidecar_id(self) -> str:
        return "kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro TTS server"

    def __init__(self, log_dir: str) -> None:
        self._log_dir = Path(log_dir)
        self._log_path = self._log_dir / "kokoro.log"
        self._log_fh: IO[bytes] | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._state = SidecarState.STOPPED
        self._error: str | None = None
        self._host: str = _DEFAULT_HOST
        self._port: int = _DEFAULT_PORT
        self._started_at: str | None = None

    async def start(
        self,
        *,
        executable: str | None = None,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        startup_timeout: float = _STARTUP_TIMEOUT,
        extra_args: list[str] | None = None,
    ) -> None:
        """Launch the Kokoro TTS server and block until /health returns 200.

        Raises RuntimeError on port conflict, missing executable, or startup
        failure. Raises TimeoutError if startup_timeout elapses.
        """
        if self._state in (SidecarState.RUNNING, SidecarState.STARTING):
            return

        assert_localhost(host)

        exe = executable or find_kokoro_executable()
        if exe is None:
            self._state = SidecarState.CRASHED
            self._error = (
                "kokoro-server executable not found. "
                "Install Kokoro TTS or set CONVSIM_KOKORO_EXECUTABLE."
            )
            raise RuntimeError(self._error)

        if _is_port_in_use(host, port):
            self._state = SidecarState.PORT_CONFLICT
            self._error = (
                f"Port {port} on {host} is already in use. "
                "Stop the existing process or configure a different port."
            )
            raise RuntimeError(self._error)

        cmd = [exe, "--host", host, "--port", str(port)]
        if extra_args:
            cmd.extend(extra_args)

        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._log_dir / "kokoro.log"
        try:
            log_fh: IO[bytes] = open(self._log_path, "ab")  # noqa: WPS515
        except OSError as exc:
            self._state = SidecarState.CRASHED
            self._error = f"Failed to open log file {self._log_path}: {exc}"
            raise RuntimeError(self._error) from exc
        self._log_fh = log_fh

        self._state = SidecarState.STARTING
        self._error = None
        self._host = host
        self._port = port
        self._started_at = datetime.now(timezone.utc).isoformat()

        header = (
            f"\n--- kokoro-server start {self._started_at} ---\n"
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
            self._error = f"Failed to start Kokoro server: {exc}"
            self._close_log()
            raise RuntimeError(self._error) from exc

        health_url = f"http://{host}:{port}/health"
        try:
            await _wait_for_kokoro_ready(self._process, health_url, startup_timeout, self._log_path)
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
            self._started_at = None
            return
        await self._terminate_process()
        self._close_log()
        self._state = SidecarState.STOPPED
        self._error = None
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
                f"Kokoro TTS server exited unexpectedly with code {self._process.returncode}. "
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
