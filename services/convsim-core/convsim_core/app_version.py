# SPDX-License-Identifier: Apache-2.0
"""The app version that diagnostics report.

``convsim_core.__version__`` is the Python package's own version. It is not
bumped per release, so every build — a Steam release or a dev checkout —
reported ``app: 0.1.0`` in the copy-diagnostics excerpt and the crash / beta
report bundles (issue #490). A bug report needs the release the player is
actually running, so those surfaces use :func:`app_version`, resolved in
this order:

1. ``CONVSIM_APP_VERSION`` — set by the desktop shell when it launches the
   core, from the app version ``release.yml`` stamps from the release tag.
   Every packaged build takes this path. A bare version (``0.2.9``) is shown
   in tag form (``v0.2.9``) so it matches the release a maintainer looks up.
2. ``dev-<short commit hash>`` — convsim-core running from a source checkout
   (``./scripts/dev.sh``), where no release tag applies.
3. ``__version__`` — neither is available.
"""
from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from pathlib import Path

from convsim_core import __version__

APP_VERSION_ENV = "CONVSIM_APP_VERSION"

# Longest value accepted from the environment; anything longer is not a
# version string and would bloat a header meant to fit in a clipboard.
_MAX_VERSION_LENGTH = 64

_SHORT_SHA_RE = re.compile(r"^[0-9a-f]{4,40}$")


def app_version() -> str:
    """Return the version string to report in diagnostics. Never raises."""
    from_env = _version_from_env(os.environ.get(APP_VERSION_ENV))
    if from_env is not None:
        return from_env
    sha = _source_checkout_commit()
    if sha is not None:
        return f"dev-{sha}"
    return __version__


def _version_from_env(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = " ".join(raw.split())
    if not cleaned or len(cleaned) > _MAX_VERSION_LENGTH:
        return None
    if cleaned[0].isdigit():
        return f"v{cleaned}"
    return cleaned


@functools.lru_cache(maxsize=1)
def _source_checkout_commit() -> str | None:
    """Short commit hash of the checkout this package runs from, if any.

    Skipped in a frozen (PyInstaller) build: there is no checkout to ask, and
    the shell always sets ``CONVSIM_APP_VERSION`` there. Cached because the
    answer cannot change while the process runs.
    """
    if getattr(sys, "frozen", False):
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    if result.returncode != 0 or not _SHORT_SHA_RE.match(sha):
        return None
    return sha
