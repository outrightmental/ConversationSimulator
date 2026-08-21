# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.log_excerpt — the copy-diagnostics excerpt builder."""
import json
from pathlib import Path

from convsim_core.log_excerpt import (
    _MAX_EXCERPT_BYTES,
    build_log_excerpt,
    LogExcerpt,
)


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _app_line(level: str, message: str) -> str:
    return json.dumps({"level": level, "message": message})


# ── Header and empty states ──────────────────────────────────────────────────


def test_missing_log_dir_returns_header_only(tmp_path):
    result = build_log_excerpt(str(tmp_path / "nope"))
    assert isinstance(result, LogExcerpt)
    assert "ConversationSimulator log excerpt" in result.text
    assert "No log files found" in result.text
    assert result.sources == []


def test_header_contains_app_version_and_time(tmp_path):
    result = build_log_excerpt(str(tmp_path))
    assert "app: " in result.text
    assert "platform: " in result.text
    assert "time: " in result.text


def test_context_is_included_in_header(tmp_path):
    result = build_log_excerpt(str(tmp_path), context="setup-install:warmup")
    assert "context: setup-install:warmup" in result.text


def test_context_is_sanitized_to_single_line_and_capped(tmp_path):
    nasty = "line one\nline two\t" + "x" * 500
    result = build_log_excerpt(str(tmp_path), context=nasty)
    context_lines = [l for l in result.text.splitlines() if l.startswith("context: ")]
    assert len(context_lines) == 1
    assert "\n" not in context_lines[0]
    assert "line one line two" in context_lines[0]
    assert len(context_lines[0]) <= len("context: ") + 200


def test_blank_context_is_omitted(tmp_path):
    result = build_log_excerpt(str(tmp_path), context="   ")
    assert "context:" not in result.text


# ── app.log selection ────────────────────────────────────────────────────────


def test_app_log_keeps_only_error_level_entries(tmp_path):
    _write(
        tmp_path / "app.log",
        [
            _app_line("INFO", "routine startup"),
            _app_line("ERROR", "something broke"),
            _app_line("DEBUG", "noise"),
            _app_line("CRITICAL", "very broken"),
        ],
    )
    result = build_log_excerpt(str(tmp_path))
    assert "something broke" in result.text
    assert "very broken" in result.text
    assert "routine startup" not in result.text
    assert "app.log" in result.sources


def test_app_log_unparsable_lines_kept_verbatim(tmp_path):
    _write(tmp_path / "app.log", ["not json at all", _app_line("INFO", "fine")])
    result = build_log_excerpt(str(tmp_path))
    assert "not json at all" in result.text


def test_app_log_falls_back_to_plain_tail_when_no_errors(tmp_path):
    _write(tmp_path / "app.log", [_app_line("INFO", "only info here")])
    result = build_log_excerpt(str(tmp_path))
    assert "only info here" in result.text


# ── runtime.log selection ────────────────────────────────────────────────────


def test_runtime_log_slices_from_last_start_marker(tmp_path):
    _write(
        tmp_path / "runtime.log",
        [
            "--- llama-server start 2026-01-01T00:00:00Z ---",
            "cmd: llama-server --model old.gguf",
            "old attempt output",
            "--- llama-server start 2026-01-02T00:00:00Z ---",
            "cmd: llama-server --model new.gguf",
            "ggml_metal buffer allocation failed",
        ],
    )
    result = build_log_excerpt(str(tmp_path))
    assert "new.gguf" in result.text
    assert "ggml_metal buffer allocation failed" in result.text
    assert "old attempt output" not in result.text
    assert "runtime.log" in result.sources


def test_runtime_log_without_marker_uses_plain_tail(tmp_path):
    _write(tmp_path / "runtime.log", ["free-form line one", "free-form line two"])
    result = build_log_excerpt(str(tmp_path))
    assert "free-form line two" in result.text


def test_runtime_log_long_chunk_keeps_marker_and_crash_tail(tmp_path):
    lines = [
        "--- llama-server start 2026-01-02T00:00:00Z ---",
        "cmd: llama-server --model big.gguf",
        *[f"loading tensor {i}" for i in range(500)],
        "fatal: out of memory",
    ]
    _write(tmp_path / "runtime.log", lines)
    result = build_log_excerpt(str(tmp_path))
    assert "--- llama-server start" in result.text
    assert "cmd: llama-server --model big.gguf" in result.text
    assert "lines omitted" in result.text
    assert "fatal: out of memory" in result.text
    assert "loading tensor 0" not in result.text


# ── kokoro.log ───────────────────────────────────────────────────────────────


def test_kokoro_log_included_when_present(tmp_path):
    _write(tmp_path / "kokoro.log", ["tts engine crashed"])
    result = build_log_excerpt(str(tmp_path))
    assert "tts engine crashed" in result.text
    assert "kokoro.log" in result.sources


def test_kokoro_log_absent_not_listed(tmp_path):
    _write(tmp_path / "app.log", [_app_line("ERROR", "x")])
    result = build_log_excerpt(str(tmp_path))
    assert "kokoro.log" not in result.sources


# ── Redaction and budgets ────────────────────────────────────────────────────


def test_home_directory_is_redacted(tmp_path):
    home = str(Path.home())
    _write(
        tmp_path / "runtime.log",
        [f"error loading model at {home}/models/foo.gguf"],
    )
    result = build_log_excerpt(str(tmp_path))
    assert home not in result.text
    assert "~/models/foo.gguf" in result.text


def test_very_long_lines_are_clamped(tmp_path):
    _write(tmp_path / "runtime.log", ["x" * 5000])
    result = build_log_excerpt(str(tmp_path))
    assert "x" * 500 not in result.text
    assert "[…]" in result.text


def test_total_size_is_capped(tmp_path):
    _write(
        tmp_path / "app.log",
        [_app_line("ERROR", f"padding {i} " + "y" * 300) for i in range(200)],
    )
    _write(
        tmp_path / "runtime.log",
        ["--- llama-server start now ---", "cmd: llama-server", *["z" * 300] * 200],
    )
    result = build_log_excerpt(str(tmp_path))
    # Header (~5 short lines) plus capped body.
    assert len(result.text.encode("utf-8")) < _MAX_EXCERPT_BYTES + 1000
    assert "truncated" in result.text


def test_excerpt_never_raises_on_directory_as_log_file(tmp_path):
    (tmp_path / "app.log").mkdir(parents=True)
    result = build_log_excerpt(str(tmp_path))
    assert "ConversationSimulator log excerpt" in result.text


def test_huge_runtime_log_reads_only_the_tail(tmp_path):
    """A multi-megabyte runtime.log (unrotated sidecar stdout) must not be
    read whole; the excerpt still carries the newest lines."""
    from convsim_core.log_excerpt import _MAX_READ_BYTES

    filler = ("spam " * 50).strip()
    big = tmp_path / "runtime.log"
    with big.open("w", encoding="utf-8") as fh:
        fh.write("--- llama-server start ancient ---\n")
        while fh.tell() < _MAX_READ_BYTES * 2:
            fh.write(filler + "\n")
        fh.write("final crash line at the very end\n")
    result = build_log_excerpt(str(tmp_path))
    assert "final crash line at the very end" in result.text
    # The marker sits outside the bounded tail read, so it cannot appear.
    assert "llama-server start ancient" not in result.text


def test_redaction_survives_line_clamping(tmp_path):
    """A long line whose home path would be cut by the clamp must not leak a
    partial username: redaction happens before clamping."""
    home = str(Path.home())
    padding = "y" * 390  # pushes the path across the clamp boundary
    _write(tmp_path / "runtime.log", [f"{padding} error at {home}/models/foo.gguf"])
    result = build_log_excerpt(str(tmp_path))
    assert home not in result.text
    # No partial fragment of the home prefix beyond "~" appears.
    assert home[: len(home) // 2] not in result.text.replace("~", "")
