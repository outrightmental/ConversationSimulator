# SPDX-License-Identifier: Apache-2.0
"""Reply speed — the plain-language front for "make the model respond faster".

Issue #501: a player partway through the tutorial went to Settings to speed the
model up and was "a little unclear on how to do that". Nothing in the settings
panel was named after the thing they wanted; the knobs that exist (context
length, GPU layers, CPU threads, sampling) are all written in runtime terms and
none of them is the dominant cost of a turn on local hardware.

The dominant cost is how many tokens the NPC generates. A local model emits
them one at a time, so halving the length of a reply roughly halves the wait.
This module turns that into one named choice with three settings:

    fast      — shorter replies, the quickest option
    balanced  — the scenario's own pacing (default; matches pre-#501 behaviour)
    detailed  — longer replies, slower on most machines

``fast`` and ``detailed`` *scale* the scenario's authored word cap rather than
replacing it, so a pack that deliberately writes terse NPCs stays terse relative
to a pack that writes expansive ones. The token budget moves with it: the
structured turn output lands in the 300–600 token range at the default 90-word
cap, so a shorter reply needs less headroom and a longer one needs more.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

ReplySpeed = Literal["fast", "balanced", "detailed"]

#: Persisted under the same ``runtime_setting.`` namespace as the numeric runtime
#: settings, so one Settings screen and one reset path cover all of them.
REPLY_SPEED_SETTING_KEY = "runtime_setting.reply_speed"

DEFAULT_REPLY_SPEED: ReplySpeed = "balanced"


@dataclass(frozen=True)
class ReplySpeedProfile:
    """How one reply-speed choice changes a turn."""

    #: Multiplier applied to the scenario's authored ``response_style.max_words``.
    word_scale: float
    #: Ceiling for the runtime's generation budget for the structured turn JSON.
    max_tokens: int


#: Floors and ceilings for the scaled word cap. The floor keeps an NPC from
#: being cut down to a grunt on a pack that already writes short lines; the
#: ceiling keeps "detailed" from inviting the monologues RESPONSE_STYLE forbids.
MIN_SCALED_MAX_WORDS = 30
MAX_SCALED_MAX_WORDS = 200

REPLY_SPEED_PROFILES: dict[str, ReplySpeedProfile] = {
    "fast": ReplySpeedProfile(word_scale=0.5, max_tokens=640),
    # Unchanged from the hardcoded pre-#501 behaviour, so the default player
    # experience is byte-for-byte what it was.
    "balanced": ReplySpeedProfile(word_scale=1.0, max_tokens=1024),
    "detailed": ReplySpeedProfile(word_scale=1.5, max_tokens=1536),
}


def normalize_reply_speed(value: object) -> ReplySpeed:
    """Coerce a stored/incoming value to a known reply speed.

    Anything unrecognised (a null row, a value written by a newer build, a typo
    in a hand-edited database) falls back to the default rather than failing a
    turn: reply pacing is a preference, not a correctness guarantee.
    """
    if isinstance(value, str) and value in REPLY_SPEED_PROFILES:
        return value  # type: ignore[return-value]
    return DEFAULT_REPLY_SPEED


def profile_for(speed: object) -> ReplySpeedProfile:
    return REPLY_SPEED_PROFILES[normalize_reply_speed(speed)]


def load_reply_speed(conn: sqlite3.Connection) -> ReplySpeed:
    """Read the persisted reply speed, defaulting when unset."""
    row = conn.execute(
        "SELECT value FROM user_settings WHERE key = ?", (REPLY_SPEED_SETTING_KEY,)
    ).fetchone()
    return normalize_reply_speed(row["value"] if row is not None else None)


def scaled_max_words(authored_max_words: int, speed: object) -> int:
    """Apply the reply-speed scale to a scenario's authored NPC word cap."""
    scaled = round(authored_max_words * profile_for(speed).word_scale)
    return max(MIN_SCALED_MAX_WORDS, min(MAX_SCALED_MAX_WORDS, scaled))
