# SPDX-License-Identifier: Apache-2.0
"""NPC thinking-pause model for conversational timing realism.

Maps the active difficulty's ``patience`` knob (0-100) to a sampled delay
that clients apply between STT-final and TTS-start so turn-taking feels
natural rather than instant.

Pause formula (linear on patience):
  mean_ms  = 300 + patience * 12        # patience=10→420ms, 50→900ms, 80→1260ms
  jitter_ms = 150                       # Gaussian σ = jitter_ms / 2

A warm, patient NPC (patience≈80) pauses ~1.3 s while an adversarial NPC
(patience≈10) fires back in ~420 ms — matching the issue spec note that
"an adversarial negotiator answers fast; a hesitant NPC pauses".

The returned value is clamped to [0, mean_ms * 2] and is always an integer
number of milliseconds suitable for a client-side ``setTimeout`` call.
"""
from __future__ import annotations

import random
from typing import Optional

# Gaussian σ expressed as the jitter band: actual σ = JITTER_MS / 2
_JITTER_MS = 150

# Absolute ceiling: no pause can exceed 5 s regardless of knob values.
_MAX_PAUSE_MS = 5_000


def compute_thinking_pause_ms(
    patience: int = 50,
    *,
    rng: Optional[random.Random] = None,
) -> int:
    """Return a sampled NPC thinking-pause duration in milliseconds.

    Args:
        patience: The difficulty ``patience`` knob (0-100).  Higher values
            produce longer, more reflective pauses.  The neutral baseline (50)
            yields ~900 ms.
        rng: Optional Random instance for deterministic tests.  Defaults to
            the module-level ``random`` instance (non-deterministic).
    """
    patience = max(0, min(100, patience))
    mean_ms = 300 + patience * 12
    _rng = rng or random
    raw = mean_ms + _rng.gauss(0, _JITTER_MS / 2)
    return max(0, min(int(raw), min(mean_ms * 2, _MAX_PAUSE_MS)))


def thinking_pause_ms_for_difficulty(
    difficulty_settings_patience: int = 50,
    *,
    enabled: bool = True,
    rng: Optional[random.Random] = None,
) -> int:
    """Convenience wrapper: returns 0 when the feature is disabled.

    Args:
        difficulty_settings_patience: The patience knob from the active
            difficulty preset.
        enabled: When False returns 0 immediately so callers always get an
            integer (0 = no pause).
        rng: Forwarded to :func:`compute_thinking_pause_ms`.
    """
    if not enabled:
        return 0
    return compute_thinking_pause_ms(patience=difficulty_settings_patience, rng=rng)
