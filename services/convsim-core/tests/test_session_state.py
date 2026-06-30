# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.session_state.

Verifies that Python SessionState values match the canonical string values
defined in packages/shared-types/src/session.ts so both sides of the API
always agree on state names.
"""

import pytest

from convsim_core.session_state import SessionState


# Canonical values from packages/shared-types/src/session.ts SessionState enum.
EXPECTED_VALUES = {
    "NotStarted",
    "LoadingModel",
    "LoadingScenario",
    "Briefing",
    "NpcOpening",
    "PlayerTurnListening",
    "PlayerTurnReview",
    "NpcThinking",
    "NpcSpeaking",
    "ScenarioEvent",
    "DebriefGenerating",
    "DebriefReady",
    "Ended",
    "Error",
}


class TestSessionStateValues:
    def test_all_expected_values_present(self):
        assert {s.value for s in SessionState} == EXPECTED_VALUES

    def test_count_matches_typescript_enum(self):
        assert len(SessionState) == 14

    @pytest.mark.parametrize("value", sorted(EXPECTED_VALUES))
    def test_value_is_accessible(self, value):
        state = SessionState(value)
        assert state.value == value

    def test_is_string_subclass(self):
        assert isinstance(SessionState.NOT_STARTED, str)
        assert SessionState.NOT_STARTED == "NotStarted"
