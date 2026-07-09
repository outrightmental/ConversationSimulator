# SPDX-License-Identifier: Apache-2.0
"""Common sidecar contract and process supervisor for local runtime sidecars.

Every managed subprocess (llama.cpp, whisper.cpp, kokoro, silero-vad) must
implement SidecarProcess so the application can stop them through a consistent
interface, gather health snapshots in one place, and guarantee localhost-only
binding in packaged (Steam) builds.

The ProcessSupervisor is the single authority over all sidecar lifetimes. It
is created once in app.py and stored on app.state.supervisor.

See docs/sidecar-bundling.md for how Steam packages and developer builds each
locate the correct sidecar executable.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

_LOCALHOST_ADDRS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
_LOG_TAIL_DEFAULT = 50

logger = logging.getLogger(__name__)


def assert_localhost(host: str) -> None:
    """Raise RuntimeError if *host* is not a loopback address.

    All managed sidecars must bind only to a loopback interface so they remain
    unreachable from the local network. Concrete sidecar start() methods must
    call this before spawning any child process.

    Allowed values: ``"127.0.0.1"``, ``"::1"``, ``"localhost"``.

    See docs/network-security.md for the localhost-only policy and
    docs/sidecar-bundling.md for deployment context.
    """
    if host not in _LOCALHOST_ADDRS:
        raise RuntimeError(
            f"Sidecar host {host!r} is not a loopback address. "
            "Managed sidecars must bind to 127.0.0.1 or ::1 to stay "
            "unreachable from the local network. "
            "See docs/network-security.md for the localhost-only policy."
        )


class SidecarProcess(ABC):
    """Contract that every managed sidecar subprocess must satisfy.

    Concrete implementations (LlamaCppSidecar, future WhisperCppSidecar, …)
    inherit from this base. The rest of the application depends only on this
    interface; it never imports concrete sidecar classes directly.

    Design note: start() is excluded from the abstract interface deliberately.
    Each sidecar type needs a different set of typed launch arguments (model
    path, port, grammar file, sample rate, …). Concrete classes expose their
    own typed start() method and must call assert_localhost(host) before
    spawning any child process.
    """

    @property
    @abstractmethod
    def sidecar_id(self) -> str:
        """Stable machine-readable identifier, e.g. ``"llama_cpp"``."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable label shown in the runtime health panel."""

    @abstractmethod
    async def stop(self) -> None:
        """Terminate the managed process and release file handles.

        Must be idempotent: safe to call when already stopped or crashed.
        Must clear all mutable state (pid, model_path, error) so that a
        subsequent get_status() call returns a clean stopped snapshot.
        """

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return a serialisable snapshot of the current sidecar state.

        Required keys
        -------------
        state : str
            Current lifecycle state: ``"stopped"``, ``"starting"``,
            ``"running"``, ``"crashed"``, or ``"port_conflict"``.
        pid : int | None
            OS process id when running, else None.
        error : str | None
            Last error message, else None.
        log_path : str
            Absolute path to the sidecar log file. The file may not exist yet
            if the sidecar has never been started.

        Concrete sidecars may include additional keys such as model_path, host,
        port, and started_at.
        """

    def tail_log(self, lines: int = _LOG_TAIL_DEFAULT) -> list[str]:
        """Return the last *lines* lines from the sidecar log file.

        Returns an empty list when the log file does not exist or cannot be
        read (e.g. the sidecar has never been started or the log directory has
        not been created yet).
        """
        log_path = Path(self.get_status().get("log_path", ""))
        if not log_path.is_file():
            return []
        try:
            text = log_path.read_text(errors="replace")
        except OSError:
            return []
        all_lines = text.splitlines()
        return all_lines[-lines:] if lines > 0 else all_lines


class ProcessSupervisor:
    """Manages the lifetimes of all locally-bound sidecar processes.

    One instance lives on ``app.state.supervisor`` for the duration of the
    server process. All managed sidecars are registered with the supervisor so
    that they are stopped in one place when the application exits.

    Usage::

        supervisor = ProcessSupervisor()
        supervisor.register(llama_sidecar)    # LlamaCppSidecar
        supervisor.register(whisper_sidecar)  # future WhisperCppSidecar
        …

        # At application shutdown:
        await supervisor.stop_all()

    The supervisor does not own the start() call for each sidecar — each
    concrete sidecar type has its own typed start() method that the router
    calls directly. The supervisor's responsibilities are:

    1. Guarantee that stop() is called on every sidecar at application exit.
    2. Provide a central health_summary() view for the /api/health endpoint.
    3. Document that all sidecars must be localhost-bound (see assert_localhost).
    """

    def __init__(self) -> None:
        self._sidecars: dict[str, SidecarProcess] = {}

    def register(self, sidecar: SidecarProcess) -> None:
        """Add *sidecar* to the supervisor registry.

        Raises ValueError if a sidecar with the same sidecar_id is already
        registered. Duplicate registrations are always a programming error.
        """
        if sidecar.sidecar_id in self._sidecars:
            raise ValueError(
                f"A sidecar with id {sidecar.sidecar_id!r} is already registered. "
                "Duplicate registrations are not allowed."
            )
        self._sidecars[sidecar.sidecar_id] = sidecar

    def get(self, sidecar_id: str) -> SidecarProcess | None:
        """Return the registered SidecarProcess with *sidecar_id*, or None."""
        return self._sidecars.get(sidecar_id)

    async def stop_all(self) -> None:
        """Stop every registered sidecar concurrently.

        Errors from individual sidecars are suppressed so that a crash in one
        sidecar does not prevent the others from shutting down cleanly.
        All errors are logged at WARNING level so they appear in the server log.
        """
        if not self._sidecars:
            return
        results = await asyncio.gather(
            *(s.stop() for s in self._sidecars.values()),
            return_exceptions=True,
        )
        for sidecar, result in zip(self._sidecars.values(), results):
            if isinstance(result, Exception):
                logger.warning(
                    "Error stopping sidecar %r during shutdown: %s",
                    sidecar.sidecar_id,
                    result,
                )

    def health_summary(self) -> list[dict[str, Any]]:
        """Return a status snapshot for every registered sidecar.

        Each entry contains ``sidecar_id``, ``display_name``, and all keys
        returned by the sidecar's get_status(). Callers must not depend on
        the order of entries.
        """
        out: list[dict[str, Any]] = []
        for sidecar in self._sidecars.values():
            out.append(
                {
                    "sidecar_id": sidecar.sidecar_id,
                    "display_name": sidecar.display_name,
                    **sidecar.get_status(),
                }
            )
        return out
