# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.errors — error handler and logging behaviour."""
import asyncio
import json
import logging
from unittest.mock import MagicMock

from fastapi.exceptions import RequestValidationError

from convsim_core.errors import (
    ConvsimError,
    convsim_error_handler,
    request_validation_error_handler,
)


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


# ── Request validation errors (issue #508) ───────────────────────────────────
#
# A 422 used to answer "Request validation failed" and nothing else, and left
# no trace in the logs — so neither the error card nor the log excerpt that
# "Copy diagnostics" collects said which field was wrong.


def _validation_exc(errors: list) -> RequestValidationError:
    return RequestValidationError(errors)


def _body(response) -> dict:
    return json.loads(bytes(response.body).decode())


def test_validation_message_names_the_failing_field():
    exc = _validation_exc(
        [{"type": "string_type", "loc": ("body", "tts_voice_id"), "msg": "Input should be a valid string", "input": None}]
    )
    body = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc)))
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "tts_voice_id" in body["error"]["message"]
    assert "Input should be a valid string" in body["error"]["message"]


def test_validation_message_names_every_failing_field():
    exc = _validation_exc(
        [
            {"type": "literal_error", "loc": ("body", "difficulty"), "msg": "Input should be 'warm'", "input": "brutal"},
            {"type": "int_parsing", "loc": ("body", "seed"), "msg": "Input should be a valid integer", "input": "abc"},
        ]
    )
    message = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc)))["error"]["message"]
    assert "difficulty" in message
    assert "seed" in message


def test_validation_message_truncates_a_long_field_list():
    errors = [
        {"type": "missing", "loc": ("body", f"field_{i}"), "msg": "Field required", "input": None}
        for i in range(9)
    ]
    message = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), _validation_exc(errors))))["error"]["message"]
    assert "field_0" in message
    assert "field_8" not in message
    assert "and 4 more" in message


def test_validation_details_drop_the_rejected_input():
    """The rejected value is caller content; a 422 body is pasted into issue reports."""
    exc = _validation_exc(
        [
            {
                "type": "value_error",
                "loc": ("body", "player_role_name"),
                "msg": "Value error, player_role_name cannot be blank",
                "input": "   my real name   ",
            }
        ]
    )
    body = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc)))
    assert "my real name" not in json.dumps(body)
    detail = body["error"]["details"][0]
    assert "input" not in detail
    assert detail["loc"] == ["body", "player_role_name"]


def test_validation_details_stringify_a_validator_exception():
    """Pydantic puts the original exception under ctx["error"]; it is not JSON-serializable."""
    exc = _validation_exc(
        [
            {
                "type": "value_error",
                "loc": ("body", "player_role_name"),
                "msg": "Value error, blank",
                "input": "",
                "ctx": {"error": ValueError("player_role_name cannot be blank")},
            }
        ]
    )
    body = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc)))
    assert body["error"]["details"][0]["ctx"]["error"] == "player_role_name cannot be blank"


def test_validation_error_is_logged_with_field_and_type(caplog):
    """Without this the log excerpt in a copied diagnostics report is silent about the 422."""
    exc = _validation_exc(
        [{"type": "string_type", "loc": ("body", "tts_voice_id"), "msg": "Input should be a valid string", "input": None}]
    )
    with caplog.at_level(logging.WARNING, logger="convsim_core.errors"):
        _invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc))
    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("/api/sessions" in m and "tts_voice_id=string_type" in m for m in msgs)


def test_validation_log_does_not_contain_the_rejected_input(caplog):
    exc = _validation_exc(
        [
            {
                "type": "value_error",
                "loc": ("body", "player_role_name"),
                "msg": "Value error, blank",
                "input": "sensitive transcript content",
            }
        ]
    )
    with caplog.at_level(logging.WARNING, logger="convsim_core.errors"):
        _invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc))
    for r in caplog.records:
        assert "sensitive transcript content" not in r.getMessage()


def test_validation_query_parameter_keeps_its_section_prefix():
    """"body" is dropped as noise, but "query" says where to look."""
    exc = _validation_exc(
        [{"type": "missing", "loc": ("query", "context"), "msg": "Field required", "input": None}]
    )
    message = _body(_invoke(request_validation_error_handler(_make_request("GET", "/api/diag/log-excerpt"), exc)))["error"]["message"]
    assert "query.context" in message


def test_malformed_json_body_reads_as_body_not_an_offset():
    """FastAPI's loc for a JSON decode error is an offset, which names no field."""
    exc = _validation_exc(
        [{"type": "json_invalid", "loc": ("body", 0), "msg": "JSON decode error", "input": {}}]
    )
    message = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc)))["error"]["message"]
    assert message == "Request validation failed — body: JSON decode error"


def test_a_list_item_keeps_its_index():
    exc = _validation_exc(
        [{"type": "missing", "loc": ("body", "turns", 0, "content"), "msg": "Field required", "input": {}}]
    )
    message = _body(_invoke(request_validation_error_handler(_make_request("POST", "/api/sessions"), exc)))["error"]["message"]
    assert "turns.0.content" in message
