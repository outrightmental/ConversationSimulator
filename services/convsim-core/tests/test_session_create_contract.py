# SPDX-License-Identifier: Apache-2.0
"""POST /api/sessions request contract (issue #508).

A player who presses "Start conversation" and is told only
``VALIDATION_ERROR: Request validation failed`` has no way forward: the message
names no field, the 422 left no trace in the logs, and the "Copy diagnostics"
report it offers therefore says nothing either. Two things keep that from
happening: the request model forgives an explicit ``null`` wherever it has a
default, and whatever still fails says which field and why.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app

_SETUP = {
    "scenario_id": "first_words_tutorial",
    "difficulty": "standard",
    "player_role_name": "New Player",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": True,
    "save_transcript": True,
    "seed": None,
    # Pinned so the create reaches 201 without a model installed; the request
    # contract under test is identical either way.
    "runtime_id": "scripted",
}


@pytest.fixture()
def api(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as client:
        yield client


def _error(response) -> dict:
    return response.json()["error"]


# ── An explicit null means "use the default" ─────────────────────────────────


@pytest.mark.parametrize(
    "field",
    ["tts_voice_id", "difficulty", "language", "input_mode", "tts_enabled",
     "show_state_meters", "save_transcript", "npc_thinking_pause_enabled"],
)
def test_null_for_a_defaulted_field_is_accepted(api, field):
    """A client that sends an unset option as null must not dead-end on a 422.

    The web UI documents `tts_voice_id` as "omitted when no voice is selected,
    in which case the backend applies its default" — a null plainly means the
    same thing, and no amount of retrying clears a 422 that says otherwise.
    """
    res = api.post("/api/sessions", json={**_SETUP, field: None})
    assert res.status_code == 201, res.text


def test_null_tts_voice_id_falls_back_to_the_default_voice(api):
    res = api.post("/api/sessions", json={**_SETUP, "tts_voice_id": None})
    assert res.status_code == 201, res.text
    assert res.json()["setup"]["tts_voice_id"] == "af_heart"


def test_omitting_a_defaulted_field_still_works(api):
    body = {k: v for k, v in _SETUP.items() if k != "difficulty"}
    res = api.post("/api/sessions", json=body)
    assert res.status_code == 201, res.text
    assert res.json()["setup"]["difficulty"] == "standard"


# ── What still fails, fails legibly ──────────────────────────────────────────


def test_null_for_a_required_field_is_still_refused_by_name(api):
    res = api.post("/api/sessions", json={**_SETUP, "player_role_name": None})
    assert res.status_code == 422
    assert "player_role_name" in _error(res)["message"]


def test_missing_required_field_is_refused_by_name(api):
    body = {k: v for k, v in _SETUP.items() if k != "scenario_id"}
    res = api.post("/api/sessions", json=body)
    assert res.status_code == 422
    assert "scenario_id" in _error(res)["message"]


def test_unapproved_voice_is_still_refused(api):
    """Null means "default"; a real value is still checked against the approved list."""
    res = api.post("/api/sessions", json={**_SETUP, "tts_voice_id": "af_heart_but_wrong"})
    assert res.status_code == 422
    message = _error(res)["message"]
    assert "tts_voice_id" in message
    assert "approved built-in voice" in message


def test_rejected_voice_id_is_not_echoed_back(api):
    """The message is shown in the card and copied into public bug reports.

    An id a caller invented can carry anything — a real person's name is the
    case the approved-voice list exists to refuse in the first place — so the
    422 names the constraint, not the value. Same rule as dropping Pydantic's
    "input" key.
    """
    res = api.post("/api/sessions", json={**_SETUP, "tts_voice_id": "cloned_jane_doe"})
    assert res.status_code == 422
    assert "cloned_jane_doe" not in res.text


def test_the_voice_rejection_stays_short_enough_for_a_compact_card(api):
    """ApiErrorView renders this on one line; the approved list does not fit.

    It used to be inlined, which made a 359-character message out of a
    one-field failure. The ids are discoverable at GET /api/tts/voices.
    """
    res = api.post("/api/sessions", json={**_SETUP, "tts_voice_id": "nope"})
    assert res.status_code == 422
    assert len(_error(res)["message"]) < 160, _error(res)["message"]


def test_blank_player_name_names_the_field(api):
    res = api.post("/api/sessions", json={**_SETUP, "player_role_name": "   "})
    assert res.status_code == 422
    assert "player_role_name" in _error(res)["message"]


def test_a_rejected_field_is_named_once_and_without_pydantic_jargon(api):
    """What the error card actually shows has to read like a sentence.

    The summary prefixes the field path itself, and Pydantic wraps anything one
    of our validators raises in "Value error, " — so a validator that also
    names the field produced "player_role_name: Value error, player_role_name
    cannot be blank" (issue #508).
    """
    res = api.post("/api/sessions", json={**_SETUP, "player_role_name": "   "})
    assert res.status_code == 422
    message = _error(res)["message"]
    assert message == "Request validation failed \u2014 player_role_name: cannot be blank"
    assert message.count("player_role_name") == 1
    assert "Value error" not in message


def test_validation_error_does_not_echo_the_rejected_value(api):
    """The 422 body is copied to the clipboard and pasted into public reports.

    Pydantic reports the rejected value under "input"; here that is the
    player's own name, which has no business travelling into an issue report.
    """
    res = api.post("/api/sessions", json={**_SETUP, "player_role_name": ["Ada Lovelace"]})
    assert res.status_code == 422
    assert "player_role_name" in _error(res)["message"]
    assert "Ada Lovelace" not in res.text


def test_unknown_runtime_id_is_refused_by_name(api):
    res = api.post("/api/sessions", json={**_SETUP, "runtime_id": "llama"})
    assert res.status_code == 422
    assert "runtime_id" in _error(res)["message"]


# ── The report a stranded player can actually send ───────────────────────────


@contextmanager
def _real_log_files():
    """Let create_app() wire up the real file handlers, then undo all of it.

    configure_logging() is a no-op once the root logger has handlers, and
    pytest's capture plugin has already attached its own, so stand them down
    for the duration. (A context manager entered from the test body rather than
    a fixture: pytest re-attaches its capture handlers between fixture setup
    and the test call, which would make configure_logging() a no-op again.)

    configure_logging() touches more than the root handler list: it sets the
    root level, hangs the runtime.log handler on the two runtime loggers, and
    sets the uvicorn.access level. Every one of those is put back, and the
    handlers it added are closed, so later tests neither run at INFO nor keep
    writing into this test's tmp_path.
    """
    root = logging.getLogger()
    runtime_loggers = [logging.getLogger(name) for name in ("convsim_core.runtime", "convsim_core.runtimes")]
    access = logging.getLogger("uvicorn.access")

    # Copies: addHandler() mutates the lists in place, and the saved ones must
    # still describe the state before configure_logging() ran.
    saved_root_handlers, saved_root_level = root.handlers[:], root.level
    saved_runtime = [(lg, lg.handlers[:], lg.propagate) for lg in runtime_loggers]
    saved_access_level = access.level
    root.handlers = []
    try:
        yield
    finally:
        added = [h for h in root.handlers if h not in saved_root_handlers]
        for lg, handlers, propagate in saved_runtime:
            added.extend(h for h in lg.handlers if h not in handlers)
            lg.handlers = handlers
            lg.propagate = propagate
        root.handlers = saved_root_handlers
        root.setLevel(saved_root_level)
        access.setLevel(saved_access_level)
        # The runtime.log handler sits on both runtime loggers; close it once.
        for handler in {id(h): h for h in added}.values():
            handler.close()


def test_a_rejected_request_shows_up_in_the_diagnostics_log_excerpt(tmp_config):
    """Closes the loop the issue describes: the failure AND the copyable report.

    "Copy diagnostics" assembles GET /api/diag/log-excerpt, which collects the
    most recent WARNING+ entries from app.log. A 422 used to be logged nowhere,
    so a player who copied the report after a failed launch sent a report that
    said nothing about the launch.
    """
    with _real_log_files():
        app = create_app(tmp_config)
        with TestClient(app) as client:
            res = client.post("/api/sessions", json={**_SETUP, "seed": 1.5})
            assert res.status_code == 422
            excerpt = client.get("/api/diag/log-excerpt").json()["excerpt"]

    assert "/api/sessions" in excerpt
    assert "seed=" in excerpt


def test_the_diag_excerpt_test_leaves_logging_as_it_found_it(tmp_config):
    """The stand-down above must not leak: a later test that reads caplog at
    its default level, or runs with the root at WARNING, would otherwise see
    this test's INFO records and runtime.log handler."""
    root = logging.getLogger()
    runtime = logging.getLogger("convsim_core.runtime")
    access = logging.getLogger("uvicorn.access")
    before = (root.handlers[:], root.level, runtime.handlers[:], access.level)

    with _real_log_files():
        app = create_app(tmp_config)
        with TestClient(app) as client:
            assert client.post("/api/sessions", json={**_SETUP, "seed": 1.5}).status_code == 422
        # The stand-down did its job: the real handlers were wired up.
        assert any(isinstance(h, logging.FileHandler) for h in root.handlers)
        assert any(isinstance(h, logging.FileHandler) for h in runtime.handlers)

    assert (root.handlers, root.level, runtime.handlers, access.level) == before
