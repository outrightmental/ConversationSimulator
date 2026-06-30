# SPDX-License-Identifier: Apache-2.0
"""Central network policy — every outbound network call must clear this gate.

Usage
-----
Play-mode code (LLM inference, TTS, STT) that would make automatic network
calls must call ``require_network(NetworkMode.PLAY)`` before opening any
connection. User-initiated operations (pack install, model download) call
``require_network(NetworkMode.EXPLICIT_DOWNLOAD)`` instead.

In tests, set ``LOCAL_MODE = True`` to make any play-mode network attempt
raise ``NetworkBlockedError``, catching accidental outbound calls early.

Example::

    import convsim_core.network_policy as policy

    policy.LOCAL_MODE = True          # at test setup
    policy.require_network(NetworkMode.PLAY)  # raises NetworkBlockedError
"""

from enum import Enum


class NetworkMode(str, Enum):
    """Context in which an outbound network call is being attempted."""

    PLAY = "play"
    """Automatic calls during a live conversation session (LLM, TTS, STT).
    Blocked when LOCAL_MODE is True."""

    EXPLICIT_DOWNLOAD = "explicit_download"
    """User-initiated downloads such as pack install or model download.
    Always permitted regardless of LOCAL_MODE."""


class NetworkBlockedError(RuntimeError):
    """Raised when a play-mode network call is attempted in local-only mode."""

    def __init__(self, mode: NetworkMode) -> None:
        super().__init__(
            f"Outbound network call blocked in local-only mode "
            f"(mode={mode.value!r}). "
            "Play-mode network calls are not permitted when LOCAL_MODE is True. "
            "Use NetworkMode.EXPLICIT_DOWNLOAD for user-initiated downloads."
        )
        self.mode = mode


# Set to True in tests or environments that must never make play-mode network
# calls.  Import the module and mutate this flag before calling require_network.
LOCAL_MODE: bool = False


def require_network(mode: NetworkMode) -> None:
    """Assert that an outbound network call is permitted for *mode*.

    Args:
        mode: The context of the network call.

    Raises:
        NetworkBlockedError: If LOCAL_MODE is True and mode is PLAY.
    """
    if LOCAL_MODE and mode == NetworkMode.PLAY:
        raise NetworkBlockedError(mode)
