# SPDX-License-Identifier: Apache-2.0
"""Local crash-report bundle creation.

Bundles are ZIP files written to the dedicated crash-bundles directory
(falling back to <log_dir>/crash-reports/) and are NEVER transmitted
automatically.  The user must review and share them manually.

Bundle contents (no conversation data is included):
  versions.json     — app, Python, and OS version strings
  config.json       — user settings with home-directory paths replaced by ~
  recent_errors.txt — tail of app.log (structured JSON lines)
  system.txt        — OS, architecture, and Python implementation info
  README.txt        — plain-text notice explaining the bundle
"""
from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from convsim_core import __version__
from convsim_core.models import AppSettings
from convsim_core.redaction import redact_path

_MAX_LOG_TAIL_LINES = 500
_SENSITIVE_SETTINGS_FIELDS: frozenset[str] = frozenset({"data_dir", "log_dir"})

_BUNDLE_README = """\
CRASH BUNDLE — ConversationSimulator
=====================================

This file was created locally on your device.
It has NOT been transmitted anywhere automatically.

Please review the contents below before sharing, then attach this ZIP
manually to a GitHub issue:
  https://github.com/outrightmental/ConversationSimulator/issues

Contents
--------
  versions.json     — App, Python, and OS version strings
  config.json       — Settings with home-directory paths replaced by ~
  recent_errors.txt — Last lines of app.log (no conversation content)
  system.txt        — OS and architecture summary
  README.txt        — This file

Privacy notes
-------------
  - No conversation transcripts, prompts, or audio are included.
  - Filesystem paths have the username portion replaced with ~.
  - Sharing this bundle is entirely at your discretion.
"""


def _safe_settings(settings: AppSettings) -> dict:
    d = settings.model_dump()
    for field in _SENSITIVE_SETTINGS_FIELDS:
        if field in d:
            d[field] = redact_path(str(d[field]))
    return d


_ERROR_LEVELS: frozenset[str] = frozenset({"WARNING", "ERROR", "CRITICAL"})


def _tail_log(log_path: Path, n: int) -> str:
    """Return the last *n* WARNING/ERROR/CRITICAL entries from *log_path*.

    Lines that cannot be parsed as JSON are included verbatim so that
    nothing is silently dropped when the log format is unexpected.
    """
    if not log_path.exists():
        return ""
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    error_lines: list[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
            if entry.get("level") in _ERROR_LEVELS:
                error_lines.append(line)
        except (json.JSONDecodeError, AttributeError):
            error_lines.append(line)
    return "\n".join(error_lines[-n:])


def create_crash_bundle(
    log_dir: str, settings: AppSettings, bundle_dir: str | None = None
) -> Path:
    """Create a local crash-report ZIP bundle.

    The bundle is written to ``bundle_dir`` when provided (the dedicated
    platform crash-bundles directory that the Settings UI exposes and that is
    marked ``.nosteamcloudpath``); it falls back to ``<log_dir>/crash-reports/``
    when omitted.  ``log_dir`` is always used to read ``app.log`` for the recent
    errors excerpt.

    The bundle never contains raw conversation text, prompts, or audio.
    Home-directory prefixes in paths are replaced with ``~``.

    Returns the absolute :class:`~pathlib.Path` to the created ``.zip`` file.
    """
    dest = Path(bundle_dir) if bundle_dir is not None else Path(log_dir) / "crash-reports"
    dest.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = dest / f"crash-{ts}.zip"

    versions = {
        "app": __version__,
        "python": sys.version,
        "platform": platform.platform(),
    }

    system_info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python_implementation": platform.python_implementation(),
    }

    recent_errors = _tail_log(Path(log_dir) / "app.log", _MAX_LOG_TAIL_LINES)

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("versions.json", json.dumps(versions, indent=2))
        zf.writestr("config.json", json.dumps(_safe_settings(settings), indent=2))
        zf.writestr("recent_errors.txt", recent_errors)
        zf.writestr("system.txt", json.dumps(system_info, indent=2))
        zf.writestr("README.txt", _BUNDLE_README)

    return bundle_path
