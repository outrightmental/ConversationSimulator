# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the NPC thinking-pause timing model (issue #308)."""
from __future__ import annotations

import random

import pytest

from convsim_core.services.timing import (
    compute_thinking_pause_ms,
    thinking_pause_ms_for_difficulty,
)


class TestComputeThinkingPauseMs:
    """Verify the core pause-computation function."""

    def _rng(self, seed: int = 42) -> random.Random:
        return random.Random(seed)

    def test_patience_zero_yields_short_pause(self):
        """patience=0 (adversarial) yields the shortest possible pause."""
        pauses = [compute_thinking_pause_ms(0, rng=self._rng(i)) for i in range(20)]
        # mean at patience=0 is 300 ms; all samples should be well under 1 s
        assert max(pauses) < 1_000, f"Expected < 1000 ms, got {max(pauses)}"

    def test_patience_100_yields_longer_pause(self):
        """patience=100 (very patient NPC) yields a longer pause than patience=0."""
        high = [compute_thinking_pause_ms(100, rng=self._rng(i)) for i in range(20)]
        low  = [compute_thinking_pause_ms(0,   rng=self._rng(i)) for i in range(20)]
        assert sum(high) > sum(low), "Higher patience should yield longer pauses on average"

    def test_result_is_non_negative(self):
        """Returned value must never be negative."""
        for seed in range(50):
            pause = compute_thinking_pause_ms(50, rng=self._rng(seed))
            assert pause >= 0, f"Negative pause: {pause}"

    def test_result_within_reasonable_range(self):
        """No sample should exceed 5 seconds."""
        for patience in (0, 25, 50, 75, 100):
            for seed in range(30):
                pause = compute_thinking_pause_ms(patience, rng=self._rng(seed))
                assert pause <= 5_000, f"Pause {pause} ms exceeds 5 s ceiling"

    def test_patience_clamped_to_0_100(self):
        """Out-of-range patience values should be silently clamped."""
        p_neg = compute_thinking_pause_ms(-50, rng=self._rng(1))
        p_zero = compute_thinking_pause_ms(0, rng=self._rng(1))
        # Same seed, same clamped value
        assert p_neg == p_zero

        p_over = compute_thinking_pause_ms(200, rng=self._rng(2))
        p_100  = compute_thinking_pause_ms(100, rng=self._rng(2))
        assert p_over == p_100

    def test_returns_integer(self):
        """Return type is always int (safe for setTimeout)."""
        result = compute_thinking_pause_ms(50, rng=self._rng(99))
        assert isinstance(result, int)

    def test_deterministic_with_fixed_rng(self):
        """Same seed → same result (deterministic for tests)."""
        a = compute_thinking_pause_ms(50, rng=self._rng(7))
        b = compute_thinking_pause_ms(50, rng=self._rng(7))
        assert a == b


class TestThinkingPauseMsForDifficulty:
    """Verify the enabled/disabled wrapper."""

    def _rng(self, seed: int = 42) -> random.Random:
        return random.Random(seed)

    def test_disabled_returns_zero(self):
        """When enabled=False, always returns 0 regardless of patience."""
        for patience in (0, 50, 100):
            assert thinking_pause_ms_for_difficulty(patience, enabled=False) == 0

    def test_enabled_returns_positive(self):
        """When enabled=True with patience>0, returns a positive integer."""
        result = thinking_pause_ms_for_difficulty(50, enabled=True, rng=self._rng(1))
        assert result > 0

    def test_default_enabled(self):
        """enabled defaults to True."""
        result = thinking_pause_ms_for_difficulty(50, rng=self._rng(1))
        assert result > 0

    def test_patience_zero_with_enabled(self):
        """patience=0, enabled=True still returns a non-negative result."""
        result = thinking_pause_ms_for_difficulty(0, enabled=True, rng=self._rng(1))
        assert result >= 0
