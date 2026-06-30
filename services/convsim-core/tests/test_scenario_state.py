# SPDX-License-Identifier: Apache-2.0
"""Unit tests for convsim_core.scenario_state.

Test plan:
  - Variable initialization from baseline and custom defs.
  - apply_state_delta: clamping, unknown-key rejection, max_delta_per_turn enforcement.
  - evaluate_event_triggers: variable_above, variable_below, max_turns, flag conditions.
  - evaluate_event_triggers: repeat / fire-once semantics.
  - evaluate_ending_condition: success, failure, timeout (implicit and explicit).
  - evaluate_ending_condition: safety_stop and player_exit take priority.
  - partition_state_by_visibility: visible vs hidden separation.
  - Serialization helpers produce expected payload shapes.
"""
import pytest

from convsim_core.scenario_state import (
    BASELINE_VARIABLES,
    ScenarioEvent,
    ScenarioVariableDef,
    VariableVisibility,
    apply_state_delta,
    build_variable_defs,
    evaluate_ending_condition,
    evaluate_event_triggers,
    initialize_state,
    partition_state_by_visibility,
    serialize_ending_event,
    serialize_state_change_event,
    serialize_triggered_events,
)


# ---------------------------------------------------------------------------
# Baseline variable definitions
# ---------------------------------------------------------------------------


class TestBaselineVariables:
    def test_all_six_baseline_variables_present(self):
        expected = {"trust", "patience", "pressure", "rapport", "openness", "objective_progress"}
        assert set(BASELINE_VARIABLES.keys()) == expected

    def test_trust_default_is_50(self):
        assert BASELINE_VARIABLES["trust"].default == 50

    def test_patience_default_is_75(self):
        assert BASELINE_VARIABLES["patience"].default == 75

    def test_pressure_is_hidden(self):
        assert BASELINE_VARIABLES["pressure"].visibility == VariableVisibility.HIDDEN

    def test_all_others_are_visible(self):
        visible_names = {"trust", "patience", "rapport", "openness", "objective_progress"}
        for name in visible_names:
            assert BASELINE_VARIABLES[name].visibility == VariableVisibility.VISIBLE

    def test_default_range_is_0_to_100(self):
        for defn in BASELINE_VARIABLES.values():
            assert defn.min == 0
            assert defn.max == 100

    def test_default_max_delta_per_turn_is_20(self):
        for defn in BASELINE_VARIABLES.values():
            assert defn.max_delta_per_turn == 20


# ---------------------------------------------------------------------------
# build_variable_defs
# ---------------------------------------------------------------------------


class TestBuildVariableDefs:
    def test_returns_all_baseline_without_custom(self):
        defs = build_variable_defs()
        assert "trust" in defs
        assert "patience" in defs
        assert "pressure" in defs
        assert "rapport" in defs
        assert "openness" in defs
        assert "objective_progress" in defs

    def test_custom_dict_spec_overrides_default(self):
        defs = build_variable_defs({"trust": {"default": 30}})
        assert defs["trust"].default == 30

    def test_custom_dict_spec_overrides_range(self):
        defs = build_variable_defs({"trust": {"min": 10, "max": 90}})
        assert defs["trust"].min == 10
        assert defs["trust"].max == 90

    def test_custom_dict_spec_overrides_visibility(self):
        defs = build_variable_defs({"trust": {"visibility": "hidden"}})
        assert defs["trust"].visibility == VariableVisibility.HIDDEN

    def test_custom_dict_spec_overrides_max_delta(self):
        defs = build_variable_defs({"trust": {"max_delta_per_turn": 5}})
        assert defs["trust"].max_delta_per_turn == 5

    def test_custom_integer_spec_updates_default(self):
        defs = build_variable_defs({"rapport": 80})
        assert defs["rapport"].default == 80

    def test_custom_integer_spec_preserves_visibility_of_hidden_baseline(self):
        # pressure is HIDDEN in the baseline; an integer override must not reset it to VISIBLE
        defs = build_variable_defs({"pressure": 15})
        assert defs["pressure"].default == 15
        assert defs["pressure"].visibility == VariableVisibility.HIDDEN

    def test_custom_integer_spec_preserves_max_delta_per_turn(self):
        defs = build_variable_defs({"trust": {"max_delta_per_turn": 5}})
        defs2 = build_variable_defs({"trust": 30})  # integer shorthand should not reset max_delta
        # A fresh integer override on the original baseline should keep baseline max_delta_per_turn=20
        assert defs2["trust"].max_delta_per_turn == 20

    def test_new_custom_variable_added(self):
        defs = build_variable_defs({"motivation": {"default": 60, "min": 0, "max": 100}})
        assert "motivation" in defs
        assert defs["motivation"].default == 60

    def test_new_custom_variable_integer_spec(self):
        defs = build_variable_defs({"anxiety": 40})
        assert "anxiety" in defs
        assert defs["anxiety"].default == 40

    def test_none_custom_returns_baseline_only(self):
        defs = build_variable_defs(None)
        assert set(defs.keys()) == set(BASELINE_VARIABLES.keys())


# ---------------------------------------------------------------------------
# initialize_state
# ---------------------------------------------------------------------------


class TestInitializeState:
    def test_state_keys_match_defs(self):
        defs = build_variable_defs()
        state = initialize_state(defs)
        assert set(state.keys()) == set(defs.keys())

    def test_values_equal_defaults(self):
        defs = build_variable_defs()
        state = initialize_state(defs)
        for name, defn in defs.items():
            assert state[name] == defn.default

    def test_custom_default_reflected(self):
        defs = build_variable_defs({"trust": {"default": 20}})
        state = initialize_state(defs)
        assert state["trust"] == 20

    def test_default_above_max_is_clamped_to_max(self):
        defs = build_variable_defs({"trust": {"min": 0, "max": 50, "default": 75}})
        state = initialize_state(defs)
        assert state["trust"] == 50

    def test_default_below_min_is_clamped_to_min(self):
        defs = build_variable_defs({"trust": {"min": 10, "max": 100, "default": 5}})
        state = initialize_state(defs)
        assert state["trust"] == 10


# ---------------------------------------------------------------------------
# apply_state_delta — clamping
# ---------------------------------------------------------------------------


class TestApplyStateDeltaClamping:
    def setup_method(self):
        self.defs = build_variable_defs()
        self.state = initialize_state(self.defs)

    def test_simple_positive_delta_applied(self):
        result = apply_state_delta(self.state, {"trust": 10}, self.defs)
        assert result.new_state["trust"] == 60

    def test_simple_negative_delta_applied(self):
        result = apply_state_delta(self.state, {"patience": -10}, self.defs)
        assert result.new_state["patience"] == 65

    def test_value_clamped_at_max(self):
        result = apply_state_delta(self.state, {"trust": 100}, self.defs)
        assert result.new_state["trust"] == 70  # 50 + 20 (clamped delta)

    def test_value_clamped_at_min(self):
        result = apply_state_delta(self.state, {"trust": -100}, self.defs)
        assert result.new_state["trust"] == 30  # 50 - 20 (clamped delta)

    def test_value_never_exceeds_variable_max(self):
        # Start near the top
        state = dict(self.state)
        state["trust"] = 95
        result = apply_state_delta(state, {"trust": 20}, self.defs)
        assert result.new_state["trust"] == 100

    def test_value_never_goes_below_variable_min(self):
        state = dict(self.state)
        state["trust"] = 5
        result = apply_state_delta(state, {"trust": -20}, self.defs)
        assert result.new_state["trust"] == 0

    def test_delta_clamped_to_max_delta_per_turn(self):
        result = apply_state_delta(self.state, {"trust": 30}, self.defs)
        # max_delta_per_turn=20, so delta capped at 20
        assert result.new_state["trust"] == 70

    def test_negative_delta_clamped_to_max_delta_per_turn(self):
        result = apply_state_delta(self.state, {"trust": -30}, self.defs)
        assert result.new_state["trust"] == 30

    def test_custom_max_delta_per_turn_respected(self):
        defs = build_variable_defs({"trust": {"max_delta_per_turn": 5}})
        state = initialize_state(defs)  # trust = 50
        result = apply_state_delta(state, {"trust": 20}, defs)
        assert result.new_state["trust"] == 55

    def test_actual_changes_reflect_real_change(self):
        result = apply_state_delta(self.state, {"trust": 10}, self.defs)
        assert result.actual_changes["trust"] == 10

    def test_actual_changes_reflect_clamped_change(self):
        state = dict(self.state)
        state["trust"] = 95
        result = apply_state_delta(state, {"trust": 20}, self.defs)
        assert result.actual_changes["trust"] == 5  # 100 - 95

    def test_actual_changes_reflect_change_clamped_at_min(self):
        state = dict(self.state)
        state["trust"] = 5
        result = apply_state_delta(state, {"trust": -20}, self.defs)
        assert result.actual_changes["trust"] == -5  # 0 - 5

    def test_zero_delta_produces_zero_actual_change(self):
        result = apply_state_delta(self.state, {"trust": 0}, self.defs)
        assert result.actual_changes["trust"] == 0

    def test_unchanged_variables_not_in_actual_changes(self):
        result = apply_state_delta(self.state, {"trust": 5}, self.defs)
        assert "patience" not in result.actual_changes

    def test_original_state_not_mutated(self):
        original_trust = self.state["trust"]
        apply_state_delta(self.state, {"trust": 20}, self.defs)
        assert self.state["trust"] == original_trust


# ---------------------------------------------------------------------------
# apply_state_delta — unknown-key rejection
# ---------------------------------------------------------------------------


class TestApplyStateDeltaRejection:
    def setup_method(self):
        self.defs = build_variable_defs()
        self.state = initialize_state(self.defs)

    def test_unknown_key_not_applied(self):
        result = apply_state_delta(self.state, {"nonexistent": 10}, self.defs)
        assert "nonexistent" not in result.new_state

    def test_unknown_key_in_rejected_list(self):
        result = apply_state_delta(self.state, {"nonexistent": 10}, self.defs)
        assert "nonexistent" in result.rejected_keys

    def test_known_keys_still_applied_alongside_unknown(self):
        result = apply_state_delta(self.state, {"trust": 5, "ghost": 10}, self.defs)
        assert result.new_state["trust"] == 55
        assert "ghost" in result.rejected_keys

    def test_empty_delta_no_rejections(self):
        result = apply_state_delta(self.state, {}, self.defs)
        assert result.rejected_keys == []
        assert result.actual_changes == {}

    def test_multiple_unknown_keys_all_rejected(self):
        result = apply_state_delta(self.state, {"x": 1, "y": 2, "z": 3}, self.defs)
        assert set(result.rejected_keys) == {"x", "y", "z"}


# ---------------------------------------------------------------------------
# evaluate_event_triggers — condition types
# ---------------------------------------------------------------------------


class TestEventTriggers:
    def _make_event(self, id, when, repeat=False):
        return ScenarioEvent(id=id, when=when, npc_instruction="test", repeat=repeat)

    def test_variable_above_fires_when_exceeded(self):
        state = {"trust": 85}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" in result

    def test_variable_above_does_not_fire_when_equal(self):
        state = {"trust": 80}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" not in result

    def test_variable_above_does_not_fire_when_below(self):
        state = {"trust": 70}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" not in result

    def test_variable_below_fires_when_below(self):
        state = {"patience": 15}
        events = [self._make_event("evt1", {"type": "variable_below", "variable": "patience", "threshold": 20})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" in result

    def test_variable_below_does_not_fire_when_equal(self):
        state = {"patience": 20}
        events = [self._make_event("evt1", {"type": "variable_below", "variable": "patience", "threshold": 20})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" not in result

    def test_variable_below_does_not_fire_when_above(self):
        state = {"patience": 30}
        events = [self._make_event("evt1", {"type": "variable_below", "variable": "patience", "threshold": 20})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" not in result

    def test_max_turns_fires_at_threshold(self):
        state = {}
        events = [self._make_event("evt1", {"type": "max_turns", "value": 5})]
        fired = set()
        result = evaluate_event_triggers(state, 5, events, fired)
        assert "evt1" in result

    def test_max_turns_fires_after_threshold(self):
        state = {}
        events = [self._make_event("evt1", {"type": "max_turns", "value": 5})]
        fired = set()
        result = evaluate_event_triggers(state, 7, events, fired)
        assert "evt1" in result

    def test_max_turns_does_not_fire_before_threshold(self):
        state = {}
        events = [self._make_event("evt1", {"type": "max_turns", "value": 5})]
        fired = set()
        result = evaluate_event_triggers(state, 4, events, fired)
        assert "evt1" not in result

    def test_flag_fires_when_set(self):
        state = {}
        events = [self._make_event("evt1", {"type": "flag", "flag_id": "intro_done"})]
        fired = set()
        active_flags = {"intro_done"}
        result = evaluate_event_triggers(state, 1, events, fired, active_flags)
        assert "evt1" in result

    def test_flag_does_not_fire_when_not_set(self):
        state = {}
        events = [self._make_event("evt1", {"type": "flag", "flag_id": "intro_done"})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" not in result

    def test_unknown_condition_type_does_not_fire(self):
        state = {"trust": 99}
        events = [self._make_event("evt1", {"type": "bogus_condition"})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" not in result


# ---------------------------------------------------------------------------
# evaluate_event_triggers — repeat / fire-once semantics
# ---------------------------------------------------------------------------


class TestEventRepeatSemantics:
    def _make_event(self, id, when, repeat=False):
        return ScenarioEvent(id=id, when=when, npc_instruction="test", repeat=repeat)

    def test_non_repeat_event_fires_first_time(self):
        state = {"trust": 85}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80})]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" in result

    def test_non_repeat_event_does_not_fire_second_time(self):
        state = {"trust": 85}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80})]
        fired = {"evt1"}  # already fired
        result = evaluate_event_triggers(state, 2, events, fired)
        assert "evt1" not in result

    def test_repeat_event_fires_multiple_times(self):
        state = {"trust": 85}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80}, repeat=True)]
        fired = {"evt1"}  # already fired once
        result = evaluate_event_triggers(state, 2, events, fired)
        assert "evt1" in result

    def test_fired_set_updated_after_trigger(self):
        state = {"trust": 85}
        events = [self._make_event("evt1", {"type": "variable_above", "variable": "trust", "threshold": 80})]
        fired = set()
        evaluate_event_triggers(state, 1, events, fired)
        assert "evt1" in fired

    def test_multiple_events_fire_in_order(self):
        state = {"trust": 85, "patience": 10}
        events = [
            self._make_event("evt_trust", {"type": "variable_above", "variable": "trust", "threshold": 80}),
            self._make_event("evt_patience", {"type": "variable_below", "variable": "patience", "threshold": 20}),
        ]
        fired = set()
        result = evaluate_event_triggers(state, 1, events, fired)
        assert result == ["evt_trust", "evt_patience"]


# ---------------------------------------------------------------------------
# evaluate_ending_condition
# ---------------------------------------------------------------------------


class TestEndingConditions:
    def test_none_returned_when_no_conditions_met(self):
        state = {"trust": 50, "objective_progress": 30}
        result = evaluate_ending_condition(state, turn_number=3, max_turns=10)
        assert result is None

    def test_success_fires_on_variable_above(self):
        state = {"objective_progress": 90}
        conditions = {
            "success": {"type": "variable_above", "variable": "objective_progress", "threshold": 80}
        }
        result = evaluate_ending_condition(state, turn_number=5, max_turns=20, ending_conditions=conditions)
        assert result == "success"

    def test_failure_fires_on_variable_below(self):
        state = {"patience": 5}
        conditions = {
            "failure": {"type": "variable_below", "variable": "patience", "threshold": 10}
        }
        result = evaluate_ending_condition(state, turn_number=5, max_turns=20, ending_conditions=conditions)
        assert result == "failure"

    def test_timeout_fires_at_max_turns(self):
        state = {"trust": 50}
        result = evaluate_ending_condition(state, turn_number=10, max_turns=10)
        assert result == "timeout"

    def test_timeout_fires_past_max_turns(self):
        state = {"trust": 50}
        result = evaluate_ending_condition(state, turn_number=11, max_turns=10)
        assert result == "timeout"

    def test_timeout_does_not_fire_before_max_turns(self):
        state = {"trust": 50}
        result = evaluate_ending_condition(state, turn_number=9, max_turns=10)
        assert result is None

    def test_safety_stop_takes_priority(self):
        state = {"objective_progress": 90}
        conditions = {
            "success": {"type": "variable_above", "variable": "objective_progress", "threshold": 80}
        }
        result = evaluate_ending_condition(
            state, turn_number=5, max_turns=20,
            ending_conditions=conditions, safety_stopped=True
        )
        assert result == "safety_stop"

    def test_player_exit_takes_priority_over_success(self):
        state = {"objective_progress": 90}
        conditions = {
            "success": {"type": "variable_above", "variable": "objective_progress", "threshold": 80}
        }
        result = evaluate_ending_condition(
            state, turn_number=5, max_turns=20,
            ending_conditions=conditions, player_exited=True
        )
        assert result == "player_exit"

    def test_player_exit_takes_priority_over_failure(self):
        state = {"patience": 5}
        conditions = {
            "failure": {"type": "variable_below", "variable": "patience", "threshold": 10}
        }
        result = evaluate_ending_condition(
            state, turn_number=5, max_turns=20,
            ending_conditions=conditions, player_exited=True
        )
        assert result == "player_exit"

    def test_player_exit_takes_priority_over_implicit_timeout(self):
        result = evaluate_ending_condition(
            {}, turn_number=10, max_turns=10, player_exited=True
        )
        assert result == "player_exit"

    def test_safety_stop_takes_priority_over_player_exit(self):
        result = evaluate_ending_condition(
            {}, turn_number=1, max_turns=20,
            safety_stopped=True, player_exited=True
        )
        assert result == "safety_stop"

    def test_success_takes_priority_over_failure(self):
        state = {"objective_progress": 90, "patience": 5}
        conditions = {
            "success": {"type": "variable_above", "variable": "objective_progress", "threshold": 80},
            "failure": {"type": "variable_below", "variable": "patience", "threshold": 10},
        }
        result = evaluate_ending_condition(state, turn_number=5, max_turns=20, ending_conditions=conditions)
        assert result == "success"

    def test_failure_takes_priority_over_timeout_from_condition(self):
        # Turn hasn't reached max_turns yet, but failure condition met.
        state = {"patience": 5}
        conditions = {
            "failure": {"type": "variable_below", "variable": "patience", "threshold": 10},
        }
        result = evaluate_ending_condition(state, turn_number=5, max_turns=20, ending_conditions=conditions)
        assert result == "failure"

    def test_success_takes_priority_over_implicit_timeout_at_max_turns(self):
        # When success fires on the final turn, success wins over implicit timeout.
        state = {"objective_progress": 90}
        conditions = {
            "success": {"type": "variable_above", "variable": "objective_progress", "threshold": 80}
        }
        result = evaluate_ending_condition(state, turn_number=10, max_turns=10, ending_conditions=conditions)
        assert result == "success"

    def test_failure_takes_priority_over_implicit_timeout_at_max_turns(self):
        # When failure fires on the final turn, failure wins over implicit timeout.
        state = {"patience": 5}
        conditions = {
            "failure": {"type": "variable_below", "variable": "patience", "threshold": 10}
        }
        result = evaluate_ending_condition(state, turn_number=10, max_turns=10, ending_conditions=conditions)
        assert result == "failure"

    def test_explicit_timeout_condition_fires_before_max_turns(self):
        # Explicit variable-based timeout fires before max_turns is reached.
        state = {"pressure": 90}
        conditions = {
            "timeout": {"type": "variable_above", "variable": "pressure", "threshold": 80}
        }
        result = evaluate_ending_condition(state, turn_number=3, max_turns=20, ending_conditions=conditions)
        assert result == "timeout"

    def test_explicit_timeout_condition_does_not_fire_when_not_met(self):
        state = {"pressure": 50}
        conditions = {
            "timeout": {"type": "variable_above", "variable": "pressure", "threshold": 80}
        }
        result = evaluate_ending_condition(state, turn_number=3, max_turns=20, ending_conditions=conditions)
        assert result is None

    def test_empty_ending_conditions_does_not_crash(self):
        state = {"trust": 50}
        result = evaluate_ending_condition(state, turn_number=3, max_turns=10, ending_conditions={})
        assert result is None

    def test_none_ending_conditions_does_not_crash(self):
        state = {"trust": 50}
        result = evaluate_ending_condition(state, turn_number=3, max_turns=10, ending_conditions=None)
        assert result is None


# ---------------------------------------------------------------------------
# partition_state_by_visibility
# ---------------------------------------------------------------------------


class TestPartitionStateByVisibility:
    def test_visible_and_hidden_are_disjoint(self):
        defs = build_variable_defs()
        state = initialize_state(defs)
        visible, hidden = partition_state_by_visibility(state, defs)
        assert set(visible.keys()).isdisjoint(set(hidden.keys()))

    def test_visible_and_hidden_cover_all_variables(self):
        defs = build_variable_defs()
        state = initialize_state(defs)
        visible, hidden = partition_state_by_visibility(state, defs)
        assert set(visible.keys()) | set(hidden.keys()) == set(state.keys())

    def test_pressure_is_in_hidden(self):
        defs = build_variable_defs()
        state = initialize_state(defs)
        _, hidden = partition_state_by_visibility(state, defs)
        assert "pressure" in hidden

    def test_trust_is_in_visible(self):
        defs = build_variable_defs()
        state = initialize_state(defs)
        visible, _ = partition_state_by_visibility(state, defs)
        assert "trust" in visible

    def test_custom_hidden_variable_goes_to_hidden(self):
        defs = build_variable_defs({"motivation": {"default": 60, "visibility": "hidden"}})
        state = initialize_state(defs)
        _, hidden = partition_state_by_visibility(state, defs)
        assert "motivation" in hidden

    def test_unknown_variable_defaults_to_visible(self):
        defs = build_variable_defs()
        state = dict(initialize_state(defs))
        state["unlisted"] = 42  # not in defs
        visible, hidden = partition_state_by_visibility(state, defs)
        assert "unlisted" in visible


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_state_change_event_has_correct_type(self):
        payload = serialize_state_change_event({"trust": 5}, [])
        assert payload["event_type"] == "state_delta"

    def test_state_change_event_includes_actual_changes(self):
        payload = serialize_state_change_event({"trust": 5, "rapport": -3}, [])
        assert payload["actual_changes"] == {"trust": 5, "rapport": -3}

    def test_state_change_event_includes_rejected_keys(self):
        payload = serialize_state_change_event({}, ["ghost_key"])
        assert "ghost_key" in payload["rejected_keys"]

    def test_triggered_events_serialization(self):
        payloads = serialize_triggered_events(["evt1", "evt2"])
        assert len(payloads) == 2
        assert all(p["event_type"] == "scenario_event" for p in payloads)
        assert payloads[0]["event_id"] == "evt1"
        assert payloads[1]["event_id"] == "evt2"

    def test_triggered_events_empty_list(self):
        payloads = serialize_triggered_events([])
        assert payloads == []

    def test_ending_event_has_correct_type(self):
        payload = serialize_ending_event("success")
        assert payload["event_type"] == "session_ending"
        assert payload["ending_type"] == "success"

    def test_ending_event_includes_summary_when_provided(self):
        payload = serialize_ending_event("failure", summary="NPC walked out.")
        assert payload["summary"] == "NPC walked out."

    def test_ending_event_no_summary_key_when_absent(self):
        payload = serialize_ending_event("timeout")
        assert "summary" not in payload
