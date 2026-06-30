# SPDX-License-Identifier: Apache-2.0
"""Redaction helpers for log-safe representations of sensitive values.

Use these helpers before logging any value that may be derived from user input,
conversation content, or filesystem paths that contain usernames.

Design rules:
- redact_transcript / redact_prompt always replace the full value with a
  placeholder — partial masking is not used because any fragment can re-identify.
- redact_path replaces the user's home-directory prefix so log files do not
  leak the OS username embedded in absolute paths.
- redact_audio_metadata keeps only a fixed allowlist of non-identifying fields.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_HOME_PREFIX: str = str(Path.home())

# Fields that carry no identifying information and are safe to log.
_SAFE_AUDIO_KEYS: frozenset[str] = frozenset(
    {"duration_seconds", "sample_rate", "channels", "codec", "format"}
)


def redact_transcript(text: str) -> str:
    """Return a safe placeholder in place of conversation transcript text."""
    if not text:
        return text
    return "[transcript redacted]"


def redact_prompt(text: str) -> str:
    """Return a safe placeholder in place of LLM prompt text."""
    if not text:
        return text
    return "[prompt redacted]"


def redact_path(path: str) -> str:
    """Replace the home-directory prefix with ~ to avoid leaking the OS username."""
    if _HOME_PREFIX and path.startswith(_HOME_PREFIX):
        return "~" + path[len(_HOME_PREFIX):]
    return path


def redact_audio_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *metadata* with only non-identifying fields kept."""
    return {k: v for k, v in metadata.items() if k in _SAFE_AUDIO_KEYS}
