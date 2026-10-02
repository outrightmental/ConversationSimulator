# SPDX-License-Identifier: Apache-2.0
"""Shut convsim-core down when the process that launched it goes away.

Why this exists
---------------
The desktop shell (Tauri) spawns convsim-core as a child process and kills that
child when the app quits. Killing it is not enough to stop the engine:

* the packaged binary is a PyInstaller **one-file** bundle, whose bootloader
  process unpacks itself and runs the real Python server as a child of its own.
  The shell only holds a handle on the bootloader, so terminating that handle
  leaves the server — the process that actually owns port 7355 — running;
* the server in turn supervises sidecars (``llama-server``, Kokoro TTS), and a
  hard kill never runs the FastAPI lifespan teardown that stops them.

On Windows that left ``convsim-core.exe`` in the task list after the app
window closed, and Steam kept reporting Conversation Simulator as running
(issue #485). The same orphaning happens on macOS and Linux, because ``SIGKILL``
cannot be forwarded by the bootloader to its child either.

How it works
------------
The shell spawns us with a **pipe on stdin** and holds the write end open for
its entire life. The kernel closes that handle when the shell exits for *any*
reason — clean quit, crash, or being killed outright — so a read on stdin
returning EOF is a reliable "your launcher is gone" signal on every platform,
with no process-tree surgery, PID polling (PIDs get recycled) or platform FFI.

On EOF we ask uvicorn for a *graceful* shutdown, which runs the lifespan
teardown and therefore stops every supervised sidecar on the way out.

The watch is opt-in through ``CONVSIM_SHUTDOWN_ON_STDIN_EOF`` because stdin is
not a launcher heartbeat in every deployment: run from a terminal it is a TTY,
and under ``./scripts/dev.sh`` or a service manager it is often ``/dev/null``,
which reports EOF immediately and would shut the engine down the moment it
booted. Only a launcher that really does hold the pipe open sets the variable.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import IO, Callable, Mapping, Optional

logger = logging.getLogger(__name__)

#: Set to a truthy value by a launcher that spawns convsim-core with a pipe on
#: stdin and keeps the write end open for its own lifetime.
ENV_VAR = "CONVSIM_SHUTDOWN_ON_STDIN_EOF"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

_THREAD_NAME = "parent-exit-watch"


def is_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the launcher asked us to shut down on stdin EOF."""
    source = os.environ if env is None else env
    return source.get(ENV_VAR, "").strip().lower() in _TRUTHY


def _wait_for_eof(stream: IO[bytes] | IO[str]) -> None:
    """Block until *stream* reports end-of-file (or becomes unreadable).

    Nothing is ever written to the pipe, so this parks the thread for the whole
    session. A one-byte read is used rather than ``read()`` so that a launcher
    which does send something is not mistaken for one that has exited.
    """
    while True:
        try:
            chunk = stream.read(1)
        except (OSError, ValueError):
            # Closed or unreadable from under us — treat as the launcher going
            # away rather than hanging on to a pipe we can no longer observe.
            return
        if not chunk:
            return


def watch_parent_exit(
    on_parent_exit: Callable[[], None],
    *,
    stream: Optional[IO[bytes] | IO[str]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[threading.Thread]:
    """Call *on_parent_exit* once the launcher's end of stdin closes.

    Returns the watch thread, or ``None`` when the watch is not enabled (see
    :data:`ENV_VAR`) or no readable stdin exists — a frozen GUI build can have
    ``sys.stdin is None``.

    The thread is a daemon: it must never hold up interpreter shutdown, and the
    pending one-byte read cannot be cancelled.
    """
    if not is_enabled(env):
        return None

    if stream is None:
        stdin = sys.stdin
        if stdin is None:
            logger.warning(
                "%s is set but this process has no stdin; parent-exit watch disabled",
                ENV_VAR,
            )
            return None
        # Read the raw byte stream where one exists: it is unaffected by the
        # text layer's decoding and newline translation, neither of which can
        # do anything useful with a pipe that only ever delivers EOF.
        stream = getattr(stdin, "buffer", stdin)

    def _run() -> None:
        _wait_for_eof(stream)
        # ASCII only: this lands on the inherited stdout as well as the
        # UTF-8 app.log, and that stream takes the console codepage on
        # Windows — one that cannot encode an em dash (cp932, cp437) would
        # turn the line docs/troubleshooting.md tells players to look for
        # into a logging-error traceback.
        logger.info("Launcher closed our stdin pipe; shutting down.")
        try:
            on_parent_exit()
        except Exception:  # noqa: BLE001 — a failed callback must not kill the thread silently
            logger.exception("Parent-exit shutdown callback failed")

    thread = threading.Thread(target=_run, name=_THREAD_NAME, daemon=True)
    thread.start()
    return thread
