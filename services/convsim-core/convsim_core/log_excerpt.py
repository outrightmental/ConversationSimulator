# SPDX-License-Identifier: Apache-2.0
"""Assemble a compact, redacted excerpt of the most relevant local logs.

Powers the "Copy diagnostics" action on the UI's error surfaces
(``GET /api/diag/log-excerpt``). The excerpt is designed to be pasted into a
GitHub issue by the user: small enough for a clipboard, redacted like the
crash bundle, and focused on the most recent failure rather than the whole
log history.

Selection rules per file (most relevant first):

  app.log     — the last WARNING/ERROR/CRITICAL entries (structured JSON
                lines); falls back to a plain tail when no error-level entry
                exists so the excerpt is never silently empty.
  runtime.log — everything after the LAST ``--- llama-server start`` marker
                (the most recent engine launch attempt — exactly the chunk
                needed to triage "Model loaded but could not start"); falls
                back to a plain tail when no marker is present.
  kokoro.log  — plain tail, only when the file exists.

Privacy: the excerpt is assembled locally and returned to the local UI only.
It is never transmitted automatically — the user explicitly copies it. All
text passes through :func:`redact_paths_in_text` so home-directory prefixes
(which embed the OS username) appear as ``~``, matching the crash-bundle
redaction promise.
"""
from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from convsim_core import __version__
from convsim_core.redaction import redact_paths_in_text

# Marker written by LlamaCppSidecar.start() before each launch attempt.
_RUNTIME_START_MARKER = "--- llama-server start"

_ERROR_LEVELS: frozenset[str] = frozenset({"WARNING", "ERROR", "CRITICAL"})

# Per-section line budgets. Tails matter most, so sections keep their newest
# lines when over budget.
_APP_LOG_MAX_LINES = 60
_RUNTIME_LOG_MAX_LINES = 80
_SIDECAR_LOG_MAX_LINES = 30
# llama-server can emit very long single lines (tensor dumps); clamp so one
# line cannot blow the clipboard budget.
_MAX_LINE_CHARS = 400
# Hard cap for the assembled excerpt body.
_MAX_EXCERPT_BYTES = 16_000

# Read at most this many bytes from the end of each log file. runtime.log in
# particular receives raw llama-server stdout through the sidecar's file
# handle, which the rotating logging handler cannot cap, so the file can grow
# very large during long sessions. The most recent launch attempt lives at
# the end, so a bounded tail read is both safe and sufficient.
_MAX_READ_BYTES = 512 * 1024

_TRUNCATION_NOTE = "[… earlier lines truncated …]"


@dataclass
class LogExcerpt:
    """The assembled excerpt text plus the log files that contributed."""

    text: str
    sources: list[str] = field(default_factory=list)


def _clamp_line(line: str) -> str:
    if len(line) <= _MAX_LINE_CHARS:
        return line
    return line[:_MAX_LINE_CHARS] + " […]"


def _read_lines(path: Path) -> list[str] | None:
    """Return the tail of the file as lines, or None when it is unreadable.

    Reads at most the last ``_MAX_READ_BYTES`` so an unbounded runtime.log
    (raw sidecar stdout is not rotated) can never stall the endpoint or blow
    memory. When the read is truncated the first, possibly partial, line is
    dropped.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            truncated = size > _MAX_READ_BYTES
            if truncated:
                fh.seek(size - _MAX_READ_BYTES)
            data = fh.read()
        lines = data.decode("utf-8", errors="replace").splitlines()
        if truncated and lines:
            lines = lines[1:]
        return lines
    except OSError:
        return None


def _tail(lines: list[str], max_lines: int) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    return [_TRUNCATION_NOTE, *lines[-max_lines:]]


def _app_log_excerpt(path: Path) -> list[str] | None:
    """Last error-level entries from the structured app log.

    Unparsable lines are kept verbatim so nothing is silently dropped when the
    log format is unexpected (same policy as the crash bundle). When no
    error-level entry exists, fall back to a short plain tail — an excerpt
    that says "no errors" would hide the INFO lines leading up to a failure.
    """
    lines = _read_lines(path)
    if lines is None:
        return None
    relevant: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("level") in _ERROR_LEVELS:
                relevant.append(line)
        except (json.JSONDecodeError, AttributeError):
            relevant.append(line)
    if not relevant:
        relevant = [ln for ln in lines if ln.strip()]
    return _tail(relevant, _APP_LOG_MAX_LINES)


def _runtime_log_excerpt(path: Path) -> list[str] | None:
    """The chunk covering the most recent engine launch attempt.

    Finds the last ``--- llama-server start`` marker and returns everything
    from there to the end of the file. When the chunk is over budget the
    marker and command lines are kept (they identify the model and flags) and
    the middle is elided, because the crash reason is at the very end.
    """
    lines = _read_lines(path)
    if lines is None:
        return None

    marker_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith(_RUNTIME_START_MARKER):
            marker_idx = i
            break

    if marker_idx is None:
        return _tail(lines, _RUNTIME_LOG_MAX_LINES)

    chunk = lines[marker_idx:]
    if len(chunk) <= _RUNTIME_LOG_MAX_LINES:
        return chunk

    # Keep the marker + cmd header, elide the middle, keep the newest lines.
    head = chunk[:2]
    tail_budget = _RUNTIME_LOG_MAX_LINES - len(head)
    omitted = len(chunk) - len(head) - tail_budget
    return [*head, f"[… {omitted} lines omitted …]", *chunk[-tail_budget:]]


def _plain_tail_excerpt(path: Path, max_lines: int) -> list[str] | None:
    lines = _read_lines(path)
    if lines is None:
        return None
    return _tail([ln for ln in lines if ln.strip()], max_lines)


def _sanitize_context(context: str | None) -> str | None:
    """Single-line, length-capped context tag safe to embed in the header."""
    if context is None:
        return None
    cleaned = " ".join(context.split())
    if not cleaned:
        return None
    return cleaned[:200]


def build_log_excerpt(log_dir: str, *, context: str | None = None) -> LogExcerpt:
    """Assemble the redacted log excerpt for the given log directory.

    Never raises on missing or unreadable files — an error surface must be
    able to call this while the system is unhealthy. Returns a header-only
    excerpt when no log file exists.
    """
    log_root = Path(log_dir)

    header = [
        "ConversationSimulator log excerpt",
        f"app: {__version__}",
        f"platform: {platform.platform()}",
        f"time: {datetime.now(timezone.utc).isoformat()}",
    ]
    ctx = _sanitize_context(context)
    if ctx is not None:
        header.append(f"context: {ctx}")

    sections: list[tuple[str, str, list[str]]] = []

    app_lines = _app_log_excerpt(log_root / "app.log")
    if app_lines is not None:
        sections.append(("app.log", "recent error-level entries", app_lines))

    runtime_lines = _runtime_log_excerpt(log_root / "runtime.log")
    if runtime_lines is not None:
        sections.append(("runtime.log", "since last engine start", runtime_lines))

    kokoro_lines = _plain_tail_excerpt(log_root / "kokoro.log", _SIDECAR_LOG_MAX_LINES)
    if kokoro_lines is not None:
        sections.append(("kokoro.log", "tail", kokoro_lines))

    body_parts: list[str] = []
    sources: list[str] = []
    for name, label, lines in sections:
        sources.append(name)
        # Redact BEFORE clamping: a clamp cut through the middle of an
        # absolute path could otherwise leave a partial home prefix (and a
        # partial OS username) that the redaction pass no longer matches.
        section_lines = [_clamp_line(redact_paths_in_text(ln)) for ln in lines]
        body_parts.append(f"── {name} ({label}) ──")
        body_parts.append("\n".join(section_lines) if section_lines else "(empty)")

    if not sections:
        body_parts.append("No log files found in the logs folder.")

    body = "\n".join(body_parts)

    # Hard cap: keep the header and the newest part of the body. The tail is
    # where crash reasons live, so truncate from the front.
    if len(body.encode("utf-8", errors="replace")) > _MAX_EXCERPT_BYTES:
        encoded = body.encode("utf-8", errors="replace")
        kept = encoded[-_MAX_EXCERPT_BYTES:].decode("utf-8", errors="replace")
        # Cut at a line boundary so the excerpt does not open mid-line.
        newline_idx = kept.find("\n")
        if newline_idx != -1:
            kept = kept[newline_idx + 1 :]
        body = f"{_TRUNCATION_NOTE}\n{kept}"

    text = "\n".join(header) + "\n\n" + body
    return LogExcerpt(text=text, sources=sources)
