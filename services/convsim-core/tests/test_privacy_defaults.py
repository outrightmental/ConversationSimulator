# SPDX-License-Identifier: Apache-2.0
"""Enforce local-first privacy defaults and network policy rules.

These tests act as ratchets: they fail immediately if any new code sets
telemetry_enabled or save_raw_audio to True by default, and they verify
that the network policy correctly blocks play-mode calls in local-only mode.
"""
import pytest

import convsim_core.network_policy as _np
from convsim_core.models import AppSettings
from convsim_core.network_policy import NetworkBlockedError, NetworkMode, require_network
from convsim_core.privacy import (
    CRASH_LOG_NOTICE,
    LOCAL_FIRST_STATEMENT,
    RAW_AUDIO_NOTICE,
    TELEMETRY_POLICY,
    TRANSCRIPT_SAVING_NOTICE,
    TTS_CACHE_NOTICE,
)


# ---------------------------------------------------------------------------
# Default settings ratchets
# ---------------------------------------------------------------------------


def test_telemetry_disabled_by_default():
    """RATCHET: changing this default leaks usage data — do not remove this test."""
    settings = AppSettings(data_dir="/tmp/d", log_dir="/tmp/l")
    assert settings.telemetry_enabled is False


def test_raw_audio_save_disabled_by_default():
    """RATCHET: raw audio is highly sensitive — default must stay False."""
    settings = AppSettings(data_dir="/tmp/d", log_dir="/tmp/l")
    assert settings.save_raw_audio is False


def test_save_transcripts_disabled_by_default():
    settings = AppSettings(data_dir="/tmp/d", log_dir="/tmp/l")
    assert settings.save_transcripts is False


def test_crash_logging_disabled_by_default():
    settings = AppSettings(data_dir="/tmp/d", log_dir="/tmp/l")
    assert settings.crash_logging_enabled is False


def test_tts_cache_enabled_by_default():
    settings = AppSettings(data_dir="/tmp/d", log_dir="/tmp/l")
    assert settings.tts_cache_enabled is True


# ---------------------------------------------------------------------------
# Network policy
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_local_mode():
    """Restore LOCAL_MODE to False after every test."""
    _np.LOCAL_MODE = False
    yield
    _np.LOCAL_MODE = False


def test_play_mode_allowed_when_local_mode_off():
    require_network(NetworkMode.PLAY)  # must not raise


def test_explicit_download_allowed_when_local_mode_off():
    require_network(NetworkMode.EXPLICIT_DOWNLOAD)  # must not raise


def test_play_mode_blocked_when_local_mode_on():
    _np.LOCAL_MODE = True
    with pytest.raises(NetworkBlockedError):
        require_network(NetworkMode.PLAY)


def test_explicit_download_allowed_when_local_mode_on():
    _np.LOCAL_MODE = True
    require_network(NetworkMode.EXPLICIT_DOWNLOAD)  # must not raise


def test_network_blocked_error_carries_mode():
    _np.LOCAL_MODE = True
    with pytest.raises(NetworkBlockedError) as exc_info:
        require_network(NetworkMode.PLAY)
    assert exc_info.value.mode == NetworkMode.PLAY


def test_network_blocked_error_message_mentions_mode():
    _np.LOCAL_MODE = True
    with pytest.raises(NetworkBlockedError) as exc_info:
        require_network(NetworkMode.PLAY)
    assert "play" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Privacy copy constants
# ---------------------------------------------------------------------------


def test_privacy_copy_constants_are_non_empty():
    for constant in (
        LOCAL_FIRST_STATEMENT,
        TELEMETRY_POLICY,
        TRANSCRIPT_SAVING_NOTICE,
        RAW_AUDIO_NOTICE,
        TTS_CACHE_NOTICE,
        CRASH_LOG_NOTICE,
    ):
        assert isinstance(constant, str) and len(constant) > 0


def test_telemetry_policy_mentions_disabled():
    assert "disabled" in TELEMETRY_POLICY.lower()


def test_raw_audio_notice_mentions_never():
    assert "never" in RAW_AUDIO_NOTICE.lower()
