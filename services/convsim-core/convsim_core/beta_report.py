# SPDX-License-Identifier: Apache-2.0
"""Beta report bundle creation.

Extends the crash bundle with a preflight snapshot and optional last-session
metadata (never transcript content).  Like crash bundles, beta report bundles
are written locally and never transmitted automatically — the tester must
review and attach them manually.

Bundle contents:
  versions.json          — app, Python, and OS version strings
  config.json            — sanitised settings (home paths replaced by ~)
  preflight.json         — runtime/stt/tts health snapshot (no user data)
  recent_errors.txt      — redacted tail of app.log
  session_metadata.json  — (opt-in) last session: scenario, turn count, state;
                            never includes transcript content or player input
  README.txt             — privacy notice
"""
from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from convsim_core import __version__
from convsim_core.crash_report import _safe_settings, _tail_log, _MAX_LOG_TAIL_LINES
from convsim_core.models import AppSettings

_HOME_PREFIX: str = str(Path.home())

_BUNDLE_README = """\
BETA REPORT BUNDLE — ConversationSimulator
==========================================

This file was created locally on your device.
It has NOT been transmitted anywhere automatically.

Please review the contents below before attaching it to a GitHub issue.
Open the ZIP in a text editor or archive viewer to confirm it contains
only the system and diagnostic information described here.

Contents
--------
  versions.json          — App, Python, and OS version strings
  system.txt             — OS name, release, architecture, Python implementation
  config.json            — Settings with home-directory paths replaced by ~
  preflight.json         — Runtime, STT, and TTS health snapshot (no user data)
  recent_errors.txt      — Last lines of app.log (no conversation content)
  session_metadata.json  — Last session stats (only if you opted in; no transcript
                           content, no player input, no NPC responses)
  crash-bundle.zip       — Most recent crash bundle, if one exists (already
                           redacted the same way as this bundle)
  README.txt             — This file

Privacy notes
-------------
  - No conversation transcripts, prompts, audio, or player input are included.
  - The optional session_metadata.json contains only: scenario identifier,
    session state (e.g. "Completed"), turn count, and timestamps.  No text.
  - Filesystem paths have the username portion replaced with ~.
  - Sharing this bundle is entirely at your discretion.

Attach to:
  https://github.com/outrightmental/ConversationSimulator/issues/new?template=beta-report.yml
"""

# Fields extracted from the last session row that are safe to include.
# Deliberately omits: setup_json (contains player name), state_vars_json,
# fired_events_json (may contain event keys derived from scenario content).
_SAFE_SESSION_FIELDS: tuple[str, ...] = (
    "session_id",
    "scenario_id",
    "flow_state",
    "ending_type",
    "turn_count",
    "created_at",
    "ended_at",
)


def _redact_home_in_text(text: str) -> str:
    """Replace the home-directory prefix with ``~`` anywhere it appears.

    Unlike :func:`convsim_core.redaction.redact_path`, which only redacts a
    string that *is* an absolute path, this also catches paths embedded inside
    larger strings — e.g. an STT health ``message`` such as
    ``"STT model not found at '/home/alice/.convsim/...'"``.  The prefix is only
    replaced when followed by a path separator so unrelated strings that merely
    share the prefix (e.g. ``/home/alice-backup``) are left intact.
    """
    if not _HOME_PREFIX:
        return text
    return text.replace(_HOME_PREFIX + os.sep, "~" + os.sep)


def _redact_paths(value: Any) -> Any:
    """Recursively redact home-directory prefixes in any string values.

    The preflight snapshot embeds health fields such as ``stt.model_path`` and
    error ``message`` strings that contain absolute paths — these leak the OS
    username unless redacted.  Non-path strings are returned unchanged, so this
    is safe to apply blanket across the whole snapshot.
    """
    if isinstance(value, str):
        return _redact_home_in_text(value)
    if isinstance(value, dict):
        return {k: _redact_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_paths(v) for v in value]
    return value


def latest_crash_bundle(bundle_dir: str | Path) -> Path | None:
    """Return the most recent ``crash-*.zip`` in *bundle_dir*, or None.

    Crash bundles (see :mod:`convsim_core.crash_report`) are written to the same
    directory as beta reports and named ``crash-<UTC timestamp>.zip``, so the
    lexicographically greatest name is also the newest.  Beta-report ZIPs use a
    ``beta-report-`` prefix and are therefore never matched.
    """
    directory = Path(bundle_dir)
    if not directory.is_dir():
        return None
    candidates = sorted(p for p in directory.glob("crash-*.zip") if p.is_file())
    return candidates[-1] if candidates else None


def _last_session_metadata(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return metadata for the most recent session, or None if no sessions exist.

    Only safe, non-identifying fields are included (see ``_SAFE_SESSION_FIELDS``).
    Transcript content, player input, and NPC responses are never included.
    """
    try:
        cursor = conn.execute(
            "SELECT session_id, scenario_id, flow_state, ending_type, "
            "turn_count, created_at, ended_at "
            "FROM turn_sessions ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return dict(zip(_SAFE_SESSION_FIELDS, row, strict=False))


def create_beta_report_bundle(
    log_dir: str,
    settings: AppSettings,
    preflight: dict[str, Any],
    bundle_dir: str | None = None,
    db_conn: sqlite3.Connection | None = None,
    include_session_metadata: bool = False,
    crash_bundle_path: Path | None = None,
) -> Path:
    """Create a local beta-report ZIP bundle.

    Parameters
    ----------
    log_dir:
        Directory containing ``app.log``.
    settings:
        Current application settings (paths are sanitised before inclusion).
    preflight:
        A health/runtime snapshot dict.  Home-directory prefixes in any string
        values are redacted to ``~`` before writing, so it is safe to pass the
        raw health payload; callers remain responsible for ensuring it contains
        no transcripts or user input.
    bundle_dir:
        Directory to write the bundle into.  Falls back to
        ``<log_dir>/beta-reports/`` when *None*.
    db_conn:
        Open SQLite connection used to read the last session metadata when
        ``include_session_metadata`` is True.  Ignored otherwise.
    include_session_metadata:
        When True, include a ``session_metadata.json`` file with non-identifying
        fields from the last session (no transcript content or player input).
    crash_bundle_path:
        When provided and the file exists, the crash bundle is embedded as
        ``crash-bundle.zip``.  Crash bundles are already redacted, so this adds
        no new sensitive data.  Use :func:`latest_crash_bundle` to locate it.

    Returns the absolute :class:`~pathlib.Path` to the created ``.zip`` file.
    """
    dest = (
        Path(bundle_dir) if bundle_dir is not None else Path(log_dir) / "beta-reports"
    )
    dest.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = dest / f"beta-report-{ts}.zip"

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
        zf.writestr("preflight.json", json.dumps(_redact_paths(preflight), indent=2))
        zf.writestr("recent_errors.txt", recent_errors)
        zf.writestr("system.txt", json.dumps(system_info, indent=2))

        if include_session_metadata and db_conn is not None:
            meta = _last_session_metadata(db_conn)
            zf.writestr(
                "session_metadata.json",
                json.dumps(meta, indent=2) if meta is not None else "null",
            )

        if crash_bundle_path is not None and crash_bundle_path.is_file():
            zf.write(crash_bundle_path, arcname="crash-bundle.zip")

        zf.writestr("README.txt", _BUNDLE_README)

    return bundle_path


def beta_report_manifest(
    include_session_metadata: bool, include_crash_bundle: bool = False
) -> list[str]:
    """Return the list of files that will be included in the bundle.

    Used by the UI consent screen so the tester sees exactly what the bundle
    will contain before it is written to disk.  ``include_crash_bundle`` should
    reflect whether a crash bundle actually exists (see
    :func:`latest_crash_bundle`) so the preview matches the real contents.
    """
    files = [
        "versions.json — app, Python, and OS versions",
        "system.txt — OS name, release, architecture",
        "config.json — settings (home directory replaced with ~)",
        "preflight.json — runtime / STT / TTS health snapshot",
        "recent_errors.txt — last log lines at WARNING or above (no conversation content)",
    ]
    if include_session_metadata:
        files.append(
            "session_metadata.json — last session: scenario ID, state, turn count,"
            " timestamps (no transcript content or player input)"
        )
    if include_crash_bundle:
        files.append(
            "crash-bundle.zip — most recent crash bundle (already redacted)"
        )
    files.append("README.txt — privacy notice")
    return files
