# SPDX-License-Identifier: Apache-2.0
"""Tests for the network_policy module.

Verifies that play-mode network calls are blocked when LOCAL_MODE is True,
that EXPLICIT_DOWNLOAD calls are always permitted, and that NetworkBlockedError
carries the expected attributes and message content.
"""
import pytest

import convsim_core.network_policy as policy
from convsim_core.network_policy import NetworkBlockedError, NetworkMode


@pytest.fixture(autouse=True)
def _reset_local_mode():
    """Restore LOCAL_MODE to its original value after every test."""
    original = policy.LOCAL_MODE
    yield
    policy.LOCAL_MODE = original


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------


def test_local_mode_default_is_false():
    assert policy.LOCAL_MODE is False


# ---------------------------------------------------------------------------
# Play-mode calls
# ---------------------------------------------------------------------------


def test_play_mode_raises_when_local_mode_enabled():
    policy.LOCAL_MODE = True
    with pytest.raises(NetworkBlockedError):
        policy.require_network(NetworkMode.PLAY)


def test_play_mode_allowed_when_local_mode_disabled():
    policy.LOCAL_MODE = False
    policy.require_network(NetworkMode.PLAY)  # must not raise


def test_play_mode_blocked_error_carries_mode_attribute():
    policy.LOCAL_MODE = True
    with pytest.raises(NetworkBlockedError) as exc_info:
        policy.require_network(NetworkMode.PLAY)
    assert exc_info.value.mode is NetworkMode.PLAY


def test_play_mode_blocked_error_message_names_mode():
    err = NetworkBlockedError(NetworkMode.PLAY)
    assert "play" in str(err)


def test_play_mode_blocked_error_message_mentions_local_mode():
    err = NetworkBlockedError(NetworkMode.PLAY)
    assert "LOCAL_MODE" in str(err)


def test_play_mode_blocked_error_message_mentions_explicit_download():
    err = NetworkBlockedError(NetworkMode.PLAY)
    assert "EXPLICIT_DOWNLOAD" in str(err)


def test_play_mode_blocked_error_is_runtime_error():
    err = NetworkBlockedError(NetworkMode.PLAY)
    assert isinstance(err, RuntimeError)


# ---------------------------------------------------------------------------
# Explicit-download calls
# ---------------------------------------------------------------------------


def test_explicit_download_always_allowed_in_local_mode():
    policy.LOCAL_MODE = True
    policy.require_network(NetworkMode.EXPLICIT_DOWNLOAD)  # must not raise


def test_explicit_download_allowed_when_local_mode_disabled():
    policy.LOCAL_MODE = False
    policy.require_network(NetworkMode.EXPLICIT_DOWNLOAD)  # must not raise


def test_explicit_download_logs_permitted_message(caplog):
    import logging

    policy.LOCAL_MODE = False
    with caplog.at_level(logging.INFO, logger="convsim_core.network_policy"):
        policy.require_network(NetworkMode.EXPLICIT_DOWNLOAD)
    assert any("explicit_download" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Offline smoke test: play-mode guard fires in test environments
# ---------------------------------------------------------------------------


def test_offline_smoke_play_mode_guard():
    """Simulate the test-environment pattern: set LOCAL_MODE before a play-mode
    call and confirm the guard fires.  This is the canonical offline smoke test
    described in the network_policy module docstring."""
    policy.LOCAL_MODE = True

    raised = False
    try:
        policy.require_network(NetworkMode.PLAY)
    except NetworkBlockedError:
        raised = True

    assert raised, "NetworkBlockedError must be raised for PLAY calls in LOCAL_MODE"


def test_offline_smoke_explicit_download_is_never_blocked():
    """EXPLICIT_DOWNLOAD must always pass through regardless of LOCAL_MODE,
    so that user-initiated model and pack downloads are never suppressed."""
    policy.LOCAL_MODE = True
    # Should complete without raising
    policy.require_network(NetworkMode.EXPLICIT_DOWNLOAD)


# ---------------------------------------------------------------------------
# NetworkMode enum values
# ---------------------------------------------------------------------------


def test_network_mode_play_value():
    assert NetworkMode.PLAY.value == "play"


def test_network_mode_explicit_download_value():
    assert NetworkMode.EXPLICIT_DOWNLOAD.value == "explicit_download"


# ---------------------------------------------------------------------------
# Zero-model tutorial plays with the offline guard enforced (issue #305)
# ---------------------------------------------------------------------------
# The DoD requires the scripted "First Words" tutorial to work fully offline,
# asserted in both the packaged smoke suite (test_packaged_smoke.py) and this
# offline guard suite.  The packaged smoke test proves the tutorial plays when
# nothing tries to reach the network; this test proves the stronger property:
# the scripted runtime plays with play-mode network calls actively BLOCKED
# (LOCAL_MODE=True), so a future network dependency sneaking into the scripted
# path would fail here instead of shipping a tutorial that breaks offline.


@pytest.mark.asyncio
async def test_scripted_tutorial_plays_with_offline_guard_enforced():
    from convsim_prompt import NPC_TURN_OUTPUT_SCHEMA

    from convsim_core.runtime.scripted import ScriptedChatRuntime
    from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest

    policy.LOCAL_MODE = True  # enforce the offline guard for play-mode calls
    runtime = ScriptedChatRuntime()

    # Health checks must succeed with no network — the guard must not fire.
    health = await runtime.health()
    assert health.status.name == "READY"

    # Drive every scripted turn plus the keyword-branched ending.  If any part of
    # the scripted path attempted a play-mode network call, require_network would
    # raise NetworkBlockedError and fail this test.
    player_turns = [
        "Hello!",
        "I want to practise interviews.",
        "The meter is moving!",
        "Something changed.",
        "Feeling good.",
        "Yes, I'm excited and ready!",
    ]
    for idx, text in enumerate(player_turns, start=1):
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=text)],
            json_schema=NPC_TURN_OUTPUT_SCHEMA,
            scripted_turn_index=idx,
        )
        final = None
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                final = chunk
        assert final is not None and final.structured is not None
        assert final.structured["npc_utterance"]

    # The final turn ends the session — confirming the whole tutorial completed
    # offline with the guard enforced.
    assert final.structured["session_control"]["continue_session"] is False
