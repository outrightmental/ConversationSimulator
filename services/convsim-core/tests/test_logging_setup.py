# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the logging setup module.

Tests for configure_logging avoid depending on the root-logger handler count
because pytest installs its own LogCaptureHandler on the root logger for each
test call phase.  Instead they either test private helpers directly or force
a clean state inline before calling configure_logging.
"""
import json
import logging
import logging.handlers
from pathlib import Path

import pytest

from convsim_core.logging_setup import _JsonFormatter, _RuntimeFilter, configure_logging


# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------


def _make_record(name, level, msg, exc_info=None):
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


def test_json_formatter_produces_valid_json():
    entry = json.loads(_JsonFormatter().format(_make_record("x", logging.INFO, "hello")))
    assert isinstance(entry, dict)


def test_json_formatter_has_ts_field():
    entry = json.loads(_JsonFormatter().format(_make_record("x", logging.WARNING, "msg")))
    assert "ts" in entry


def test_json_formatter_has_level_field():
    entry = json.loads(_JsonFormatter().format(_make_record("x", logging.ERROR, "msg")))
    assert entry["level"] == "ERROR"


def test_json_formatter_has_message_field():
    entry = json.loads(_JsonFormatter().format(_make_record("x", logging.INFO, "the text")))
    assert entry["message"] == "the text"


def test_json_formatter_has_logger_name():
    entry = json.loads(_JsonFormatter().format(_make_record("mylogger", logging.INFO, "msg")))
    assert entry["logger"] == "mylogger"


def test_json_formatter_includes_exc_info_when_present():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record("x", logging.ERROR, "err", exc_info=sys.exc_info())
        entry = json.loads(_JsonFormatter().format(record))
    assert "exc_info" in entry
    assert "ValueError" in entry["exc_info"]


# ---------------------------------------------------------------------------
# _RuntimeFilter
# ---------------------------------------------------------------------------


def test_runtime_filter_accepts_runtime_logger():
    f = _RuntimeFilter()
    record = _make_record("convsim_core.runtimes.llm", logging.INFO, "msg")
    assert f.filter(record) is True


def test_runtime_filter_accepts_runtimes_root():
    f = _RuntimeFilter()
    record = _make_record("convsim_core.runtimes", logging.INFO, "msg")
    assert f.filter(record) is True


def test_runtime_filter_rejects_app_logger():
    f = _RuntimeFilter()
    record = _make_record("convsim_core.app", logging.WARNING, "msg")
    assert f.filter(record) is False


def test_runtime_filter_rejects_root_logger():
    f = _RuntimeFilter()
    record = _make_record("root", logging.WARNING, "msg")
    assert f.filter(record) is False


def test_runtime_filter_rejects_partial_prefix():
    f = _RuntimeFilter()
    record = _make_record("convsim_core.runtimes_extra", logging.INFO, "msg")
    assert f.filter(record) is False


# ---------------------------------------------------------------------------
# configure_logging — called with an isolated fresh logger to avoid conflicts
# with pytest's own root-logger capture handler.
# ---------------------------------------------------------------------------


def _call_configure_logging_isolated(log_dir: str, debug: bool = False) -> None:
    """Call configure_logging with a clean root logger.

    Clears root-logger handlers immediately before calling so the guard inside
    configure_logging does not fire even when pytest has re-installed its own
    capture handler between fixture setup and the test function.  Restores all
    original handlers and any new ones after the call, leaving global state
    intact for the remainder of the test.
    """
    root = logging.getLogger()
    original = root.handlers[:]
    root.handlers.clear()
    try:
        configure_logging(log_dir, debug=debug)
    finally:
        # Keep the newly added file handlers so the test can assert on files,
        # but also restore any original handlers that were removed.
        new_handlers = [h for h in root.handlers if h not in original]
        for h in original:
            if h not in root.handlers:
                root.addHandler(h)
        # Register cleanup: close and remove file handlers after the test.
        _handlers_to_close.extend(new_handlers)


_handlers_to_close: list[logging.Handler] = []


@pytest.fixture(autouse=True)
def _cleanup_file_handlers():
    _handlers_to_close.clear()
    yield
    root = logging.getLogger()
    rt = logging.getLogger("convsim_core.runtimes")
    for h in list(_handlers_to_close):
        h.flush()
        h.close()
        if h in root.handlers:
            root.removeHandler(h)
        if h in rt.handlers:
            rt.removeHandler(h)
    _handlers_to_close.clear()


def test_configure_logging_creates_log_directory(tmp_path):
    log_dir = tmp_path / "logs" / "nested"
    _call_configure_logging_isolated(str(log_dir))
    assert log_dir.is_dir()


def test_configure_logging_sets_info_level_by_default(tmp_path):
    _call_configure_logging_isolated(str(tmp_path / "logs"))
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_sets_debug_level_when_requested(tmp_path):
    _call_configure_logging_isolated(str(tmp_path / "logs"), debug=True)
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_is_idempotent(tmp_path):
    """Second call with handlers already present must not add more handlers."""
    log_dir = str(tmp_path / "logs")
    _call_configure_logging_isolated(log_dir)
    count_after_first = len(logging.getLogger().handlers)
    configure_logging(log_dir)  # handlers exist → no-op
    assert len(logging.getLogger().handlers) == count_after_first


def test_configure_logging_creates_app_log_on_first_write(tmp_path):
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.startup").info("startup probe")
    assert (log_dir / "app.log").exists()


def test_configure_logging_creates_runtime_log_on_first_write(tmp_path):
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.runtimes.llm").info("runtime probe")
    assert (log_dir / "runtime.log").exists()


def test_log_entries_are_valid_json(tmp_path):
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.json_check").warning("json structure check")
    content = (log_dir / "app.log").read_text(encoding="utf-8")
    for line in content.strip().splitlines():
        entry = json.loads(line)
        assert "ts" in entry and "level" in entry and "message" in entry


def test_log_entry_level_field_matches(tmp_path):
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.level_check").error("level field test")
    lines = (log_dir / "app.log").read_text(encoding="utf-8").strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["level"] == "ERROR"


def test_runtime_events_appear_in_runtime_log(tmp_path):
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.runtimes.tts").warning("runtime segregation test")
    content = (log_dir / "runtime.log").read_text(encoding="utf-8")
    assert "runtime segregation test" in content


def test_runtime_events_also_propagate_to_app_log(tmp_path):
    """Runtime logger propagates to root so events appear in app.log as well."""
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.runtimes.stt").warning("propagation test")
    content = (log_dir / "app.log").read_text(encoding="utf-8")
    assert "propagation test" in content


def test_non_runtime_events_absent_from_runtime_log(tmp_path):
    """Events from non-runtime loggers must not appear in runtime.log."""
    log_dir = tmp_path / "logs"
    _call_configure_logging_isolated(str(log_dir))
    logging.getLogger("convsim_core.app").warning("app-only event")
    runtime_log = log_dir / "runtime.log"
    if runtime_log.exists():
        assert "app-only event" not in runtime_log.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Rotation configuration
# ---------------------------------------------------------------------------


def test_app_log_uses_rotating_handler(tmp_path):
    _call_configure_logging_isolated(str(tmp_path / "logs"))
    root = logging.getLogger()
    rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert any("app.log" in str(h.baseFilename) for h in rotating)


def test_rotation_max_bytes_is_capped(tmp_path):
    _call_configure_logging_isolated(str(tmp_path / "logs"))
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            assert h.maxBytes > 0
            assert h.maxBytes <= 10 * 1024 * 1024  # no more than 10 MB per file
