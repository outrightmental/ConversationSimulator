# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.errors — error handler and logging behaviour."""
import asyncio
import logging
from unittest.mock import MagicMock

from convsim_core.errors import ConvsimError, convsim_error_handler


def _make_request(method: str = "GET", path: str = "/api/test") -> MagicMock:
    r = MagicMock()
    r.method = method
    r.url.path = path
    return r


def _invoke(coro):
    return asyncio.run(coro)


def test_convsim_error_handler_emits_warning(caplog):
    exc = ConvsimError(code="TEST_ERROR", message="user message", status_code=400)
    with caplog.at_level(logging.WARNING, logger="convsim_core.errors"):
        _invoke(convsim_error_handler(_make_request(), exc))
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_convsim_error_handler_includes_error_code_in_warning(caplog):
    exc = ConvsimError(code="SESSION_NOT_FOUND", message="not found", status_code=404)
    with caplog.at_level(logging.WARNING, logger="convsim_core.errors"):
        _invoke(convsim_error_handler(_make_request("GET", "/api/sessions/99"), exc))
    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("SESSION_NOT_FOUND" in m for m in msgs)


def test_convsim_error_handler_does_not_log_user_message(caplog):
    """The user-facing error message is excluded from logs — it may contain user-derived content."""
    sensitive = "sensitive transcript content"
    exc = ConvsimError(code="VALIDATION_ERROR", message=sensitive, status_code=400)
    with caplog.at_level(logging.WARNING, logger="convsim_core.errors"):
        _invoke(convsim_error_handler(_make_request("POST", "/api/sessions"), exc))
    for r in caplog.records:
        assert sensitive not in r.getMessage()
