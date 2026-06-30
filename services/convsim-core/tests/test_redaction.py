# SPDX-License-Identifier: Apache-2.0
"""Unit tests for redaction helpers.

These tests are acceptance-criteria gates: they fail if any helper starts
leaking sensitive content or if the safe-field allowlist changes unexpectedly.
"""
from pathlib import Path

import pytest

from convsim_core.redaction import (
    redact_audio_metadata,
    redact_path,
    redact_prompt,
    redact_transcript,
)


# ---------------------------------------------------------------------------
# redact_transcript
# ---------------------------------------------------------------------------


def test_redact_transcript_replaces_content():
    result = redact_transcript("Hello, I am the patient and I feel unwell.")
    assert "redacted" in result.lower()
    assert "patient" not in result
    assert "unwell" not in result


def test_redact_transcript_empty_passthrough():
    assert redact_transcript("") == ""


def test_redact_transcript_returns_string():
    assert isinstance(redact_transcript("some text"), str)


# ---------------------------------------------------------------------------
# redact_prompt
# ---------------------------------------------------------------------------


def test_redact_prompt_replaces_content():
    result = redact_prompt("You are an NPC named Alice. Respond as Alice.")
    assert "redacted" in result.lower()
    assert "Alice" not in result


def test_redact_prompt_empty_passthrough():
    assert redact_prompt("") == ""


def test_redact_prompt_returns_string():
    assert isinstance(redact_prompt("some prompt"), str)


# ---------------------------------------------------------------------------
# redact_path
# ---------------------------------------------------------------------------


def test_redact_path_strips_home_prefix():
    home = str(Path.home())
    path = str(Path.home() / ".convsim" / "logs" / "app.log")
    result = redact_path(path)
    assert home not in result
    assert result.startswith("~")


def test_redact_path_preserves_suffix():
    path = str(Path.home() / ".convsim" / "logs" / "app.log")
    result = redact_path(path)
    assert result.endswith("app.log")


def test_redact_path_unrelated_path_unchanged():
    path = "/tmp/some/path/that/has/no/home"
    home = str(Path.home())
    if not path.startswith(home):
        assert redact_path(path) == path


def test_redact_path_returns_string():
    assert isinstance(redact_path("/some/path"), str)


def test_redact_path_empty_string():
    assert redact_path("") == ""


def test_redact_path_does_not_match_sibling_with_shared_prefix():
    # Regression: startswith(_HOME_PREFIX) used to match paths whose name
    # merely begins with the home username (e.g. home=/home/nick would
    # wrongly match /home/nickname/foo).
    home = str(Path.home())
    sibling = home + "extra"  # same prefix, but NOT a child of home
    assert redact_path(sibling) == sibling


def test_redact_path_matches_home_directory_itself():
    home = str(Path.home())
    assert redact_path(home) == "~"


# ---------------------------------------------------------------------------
# redact_audio_metadata
# ---------------------------------------------------------------------------


def test_redact_audio_metadata_keeps_safe_fields():
    metadata = {
        "duration_seconds": 12.5,
        "sample_rate": 16000,
        "channels": 1,
        "codec": "opus",
        "format": "ogg",
    }
    result = redact_audio_metadata(metadata)
    assert result == metadata


def test_redact_audio_metadata_removes_raw_audio():
    metadata = {
        "duration_seconds": 5.0,
        "raw_audio_bytes": b"\x00\x01\x02",
        "sample_rate": 44100,
    }
    result = redact_audio_metadata(metadata)
    assert "raw_audio_bytes" not in result
    assert result["duration_seconds"] == 5.0
    assert result["sample_rate"] == 44100


def test_redact_audio_metadata_removes_speaker_id():
    metadata = {"speaker_id": "user-abc-123", "duration_seconds": 3.0}
    result = redact_audio_metadata(metadata)
    assert "speaker_id" not in result


def test_redact_audio_metadata_removes_transcript():
    metadata = {"transcript": "Hello world", "duration_seconds": 2.0}
    result = redact_audio_metadata(metadata)
    assert "transcript" not in result
    assert result["duration_seconds"] == 2.0


def test_redact_audio_metadata_empty():
    assert redact_audio_metadata({}) == {}


def test_redact_audio_metadata_returns_new_dict():
    metadata = {"duration_seconds": 1.0, "secret": "x"}
    result = redact_audio_metadata(metadata)
    assert "secret" not in result
    # Original is unchanged
    assert "secret" in metadata
