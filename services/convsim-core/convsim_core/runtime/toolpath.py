# SPDX-License-Identifier: Apache-2.0
"""Resolve a command-line program the way the player's shell would.

``shutil.which`` searches ``PATH``, and the backend's ``PATH`` is not the
player's. On macOS the desktop shell is launched by launchd, which hands every
GUI app ``/usr/bin:/bin:/usr/sbin:/sbin`` and nothing else — notably not
Homebrew's bin directory, which is where ``brew install`` puts everything. The
Tauri wrapper passes its environment through to ``convsim-core`` unchanged
(``apps/desktop/src-tauri/src/lib.rs`` sets only ``CONVSIM_*`` variables), so a
Finder- or Steam-launched build cannot see a single brew-installed program,
however normal it looks from a terminal.

That is load-bearing for voice setup (issue #487), whose macOS route *is*
Homebrew:

  * ``brew install whisper.cpp`` lands ``whisper-cli`` in ``/opt/homebrew/bin``,
    so a PATH-only lookup leaves the row amber and "Check again" can never turn
    it green — the dead end the guided flow exists to remove, reproduced by the
    very command the flow hands out;
  * ``brew install ffmpeg`` lands there too, and ``WhisperCppWorker.health``
    reports UNAVAILABLE without ffmpeg, so the screen would tell a player to
    install what they already have — and ``transcribe`` really would fail,
    because it spawns ffmpeg out of the same ``PATH``;
  * the ``brew`` and ``docker`` prerequisite notes would claim a program "was
    not found on this machine" about a machine that plainly has it.

So every lookup of a program a *player* may have installed goes through
``find_tool``: ``PATH`` first, then the well-known package-manager prefixes for
this platform. Windows needs no supplement — its machine ``PATH`` lives in the
environment of every process, GUI ones included.

Resolved paths are returned rather than bare names so that callers which
*spawn* the program are not left trusting the ``PATH`` the lookup just worked
around.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Bin directories a GUI-launched process does not inherit, searched only after
# PATH so an explicit PATH entry always wins.
_SUPPLEMENTARY_BIN_DIRS: dict[str, tuple[str, ...]] = {
    # Homebrew lives under /opt/homebrew on Apple Silicon and /usr/local on
    # Intel; MacPorts under /opt/local.
    "darwin": ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"),
    # A desktop session normally exports /usr/local/bin already, but a
    # containerised Steam runtime may not, and Homebrew-on-Linux never is.
    "linux": ("/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin"),
}


def supplementary_bin_dirs(platform: str | None = None) -> tuple[str, ...]:
    """Directories searched after ``PATH`` on *platform* (this one by default)."""
    key = platform if platform is not None else sys.platform
    if key.startswith("linux"):
        key = "linux"
    return _SUPPLEMENTARY_BIN_DIRS.get(key, ())


def find_tool(name: str) -> str | None:
    """Return the resolved path of *name*, or None when it cannot be found.

    A drop-in replacement for ``shutil.which`` for any program the player — as
    opposed to the app's own bundler — installed.
    """
    found = shutil.which(name)
    if found:
        return found

    for directory in supplementary_bin_dirs():
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


__all__ = ["find_tool", "supplementary_bin_dirs"]
