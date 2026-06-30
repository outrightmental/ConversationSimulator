# SPDX-License-Identifier: Apache-2.0
"""Scenario state variable engine: clamping, event triggers, and ending conditions.

Responsibilities:
  - Initialize state from baseline and custom variable definitions.
  - Apply LLM-proposed deltas with clamping and unknown-key rejection.
  - Evaluate event trigger conditions (variable_above, variable_below, max_turns, flag).
  - Evaluate ending conditions (success, failure, timeout, safety_stop, player_exit).
  - Partition state into visible vs hidden sets for UI output.
  - Serialize state changes into turn_event payloads for storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Variable definitions
# ---------------------------------------------------------------------------


class VariableVisibility(str, Enum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


@dataclass
class ScenarioVariableDef:
    name: str
    min: int = 0
    max: int = 100
    default: int = 50
    visibility: VariableVisibility = VariableVisibility.VISIBLE
    max_delta_per_turn: int = 20


# Baseline variables present in every scenario unless overridden by custom defs.
BASELINE_VARIABLES: Dict[str, ScenarioVariableDef] = {
    "trust": ScenarioVariableDef(
        name="trust", default=50, visibility=VariableVisibility.VISIBLE
    ),
    "patience": ScenarioVariableDef(
        name="patience", default=75, visibility=VariableVisibility.VISIBLE
    ),
    "pressure": ScenarioVariableDef(
        name="pressure", default=25, visibility=VariableVisibility.HIDDEN
    ),
    "rapport": ScenarioVariableDef(
        name="rapport", default=50, visibility=VariableVisibility.VISIBLE
    ),
    "openness": ScenarioVariableDef(
        name="openness", default=50, visibility=VariableVisibility.VISIBLE
    ),
    "objective_progress": ScenarioVariableDef(
        name="objective_progress",
        default=0,
        visibility=VariableVisibility.VISIBLE,
    ),
}


def build_variable_defs(
    custom: Optional[Dict[str, Any]] = None,
) -> Dict[str, ScenarioVariableDef]:
    """Merge baseline variable defs with scenario-specific overrides/additions.

    Custom entries may override any baseline field by name. Entirely new names
    are treated as additional variables. Values are expected to come from the
    scenario's ``state.variables`` block (parsed from YAML/JSON).
    """
    defs: Dict[str, ScenarioVariableDef] = dict(BASELINE_VARIABLES)
    if not custom:
        return defs
    for name, spec in custom.items():
        if isinstance(spec, int):
            # Legacy simple format: name → default_value (0-100 integer).
            if name in defs:
                existing = defs[name]
                defs[name] = ScenarioVariableDef(
                    name=name,
                    min=existing.min,
                    max=existing.max,
                    default=spec,
                    visibility=existing.visibility,
                    max_delta_per_turn=existing.max_delta_per_turn,
                )
            else:
                defs[name] = ScenarioVariableDef(name=name, default=spec)
        elif isinstance(spec, dict):
            existing = defs.get(name, ScenarioVariableDef(name=name))
            defs[name] = ScenarioVariableDef(
                name=name,
                min=spec.get("min", existing.min),
                max=spec.get("max", existing.max),
                default=spec.get("default", existing.default),
                visibility=VariableVisibility(
                    spec.get("visibility", existing.visibility.value)
                ),
                max_delta_per_turn=spec.get(
                    "max_delta_per_turn", existing.max_delta_per_turn
                ),
            )
    return defs


def initialize_state(
    variable_defs: Dict[str, ScenarioVariableDef],
) -> Dict[str, int]:
    """Return initial state dict from variable defaults, clamped to [min, max]."""
    return {
        name: max(defn.min, min(defn.max, defn.default))
        for name, defn in variable_defs.items()
    }


# ---------------------------------------------------------------------------
# Delta application
# ---------------------------------------------------------------------------


@dataclass
class DeltaResult:
    new_state: Dict[str, int]
    actual_changes: Dict[str, int]
    rejected_keys: List[str]


def apply_state_delta(
    current: Dict[str, int],
    delta: Dict[str, int],
    variable_defs: Dict[str, ScenarioVariableDef],
) -> DeltaResult:
    """Apply an LLM-proposed delta to the current state.

    Rules enforced:
    1. Keys absent from ``variable_defs`` are rejected (not applied).
    2. Each applied delta is clamped to ±``max_delta_per_turn``.
    3. The resulting value is clamped to [min, max] for the variable.

    Returns a DeltaResult with the new state, what was actually changed, and
    any rejected keys.
    """
    new_state: Dict[str, int] = dict(current)
    actual_changes: Dict[str, int] = {}
    rejected_keys: List[str] = []

    for key, proposed in delta.items():
        if key not in variable_defs:
            rejected_keys.append(key)
            continue

        defn = variable_defs[key]
        # Clamp the proposed change to the per-turn limit.
        clamped_delta = max(-defn.max_delta_per_turn, min(defn.max_delta_per_turn, proposed))
        old_value = new_state.get(key, defn.default)
        new_value = max(defn.min, min(defn.max, old_value + clamped_delta))
        new_state[key] = new_value
        actual_changes[key] = new_value - old_value

    return DeltaResult(
        new_state=new_state,
        actual_changes=actual_changes,
        rejected_keys=rejected_keys,
    )


# ---------------------------------------------------------------------------
# Event triggers
# ---------------------------------------------------------------------------


@dataclass
class ScenarioEvent:
    id: str
    when: Dict[str, Any]
    npc_instruction: str
    repeat: bool = False


def _evaluate_condition(
    condition: Dict[str, Any],
    state: Dict[str, int],
    turn_number: int,
    active_flags: Set[str],
) -> bool:
    """Evaluate a single event condition dict against current simulation state."""
    condition_type = condition.get("type", "")

    if condition_type == "variable_above":
        variable = condition.get("variable", "")
        threshold = condition.get("threshold", 0)
        return state.get(variable, 0) > threshold

    if condition_type == "variable_below":
        variable = condition.get("variable", "")
        threshold = condition.get("threshold", 0)
        return state.get(variable, 0) < threshold

    if condition_type == "max_turns":
        value = condition.get("value", 0)
        return turn_number >= value

    if condition_type == "flag":
        flag_id = condition.get("flag_id", "")
        return flag_id in active_flags

    return False


def evaluate_event_triggers(
    state: Dict[str, int],
    turn_number: int,
    events: List[ScenarioEvent],
    fired_event_ids: Set[str],
    active_flags: Optional[Set[str]] = None,
) -> List[str]:
    """Return IDs of events that should fire this turn.

    An event fires when:
    - Its ``when`` condition evaluates to True.
    - It has not already fired (unless ``repeat=True``).

    ``fired_event_ids`` is mutated in-place to track fired events so that
    non-repeating events do not fire again on subsequent turns.
    """
    if active_flags is None:
        active_flags = set()

    triggered: List[str] = []
    for event in events:
        if not event.repeat and event.id in fired_event_ids:
            continue
        if _evaluate_condition(event.when, state, turn_number, active_flags):
            triggered.append(event.id)
            fired_event_ids.add(event.id)

    return triggered


# ---------------------------------------------------------------------------
# Ending condition evaluation
# ---------------------------------------------------------------------------


def evaluate_ending_condition(
    state: Dict[str, int],
    turn_number: int,
    max_turns: int,
    ending_conditions: Optional[Dict[str, Any]] = None,
    safety_stopped: bool = False,
    player_exited: bool = False,
) -> Optional[str]:
    """Evaluate all ending conditions and return the first matching ending type.

    Evaluation order: safety_stop → player_exit → success → failure → timeout.
    Returns None if no ending condition is met (session continues).
    """
    if safety_stopped:
        return "safety_stop"

    if player_exited:
        return "player_exit"

    conditions = ending_conditions or {}

    if "success" in conditions and conditions["success"]:
        if _evaluate_condition(conditions["success"], state, turn_number, set()):
            return "success"

    if "failure" in conditions and conditions["failure"]:
        if _evaluate_condition(conditions["failure"], state, turn_number, set()):
            return "failure"

    # Timeout fires implicitly when max_turns is reached, regardless of whether
    # the scenario defines an explicit timeout condition.
    if turn_number >= max_turns:
        return "timeout"

    if "timeout" in conditions and conditions["timeout"]:
        if _evaluate_condition(conditions["timeout"], state, turn_number, set()):
            return "timeout"

    return None


# ---------------------------------------------------------------------------
# Visibility partitioning
# ---------------------------------------------------------------------------


def partition_state_by_visibility(
    state: Dict[str, int],
    variable_defs: Dict[str, ScenarioVariableDef],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Split state into (visible, hidden) dicts for UI output.

    Variables absent from ``variable_defs`` default to visible.
    """
    visible: Dict[str, int] = {}
    hidden: Dict[str, int] = {}
    for name, value in state.items():
        defn = variable_defs.get(name)
        if defn and defn.visibility == VariableVisibility.HIDDEN:
            hidden[name] = value
        else:
            visible[name] = value
    return visible, hidden


# ---------------------------------------------------------------------------
# Turn-event serialization
# ---------------------------------------------------------------------------


def serialize_state_change_event(
    actual_changes: Dict[str, int],
    rejected_keys: List[str],
) -> Dict[str, Any]:
    """Build a turn_event payload for a state delta application."""
    return {
        "event_type": "state_delta",
        "actual_changes": actual_changes,
        "rejected_keys": rejected_keys,
    }


def serialize_triggered_events(triggered_ids: List[str]) -> List[Dict[str, Any]]:
    """Build a list of turn_event payloads for scenario events that fired."""
    return [
        {"event_type": "scenario_event", "event_id": eid}
        for eid in triggered_ids
    ]


def serialize_ending_event(ending_type: str, summary: Optional[str] = None) -> Dict[str, Any]:
    """Build a turn_event payload for a session ending."""
    payload: Dict[str, Any] = {"event_type": "session_ending", "ending_type": ending_type}
    if summary:
        payload["summary"] = summary
    return payload
