# SPDX-License-Identifier: Apache-2.0
"""Scenario state variable engine: clamping, event triggers, and ending conditions.

Responsibilities:
  - Initialize state from baseline and custom variable definitions.
  - Name the variables a scenario plays: the ones it declares, then the
    baselines its events and endings read (``played_variable_names``).
  - Apply LLM-proposed deltas with clamping and unknown-key rejection.
  - Evaluate event trigger conditions (variable_above, variable_below, max_turns, flag).
  - Evaluate ending conditions (success, failure, timeout, safety_stop, player_exit).
  - Partition state into visible vs hidden sets for UI output; a scenario
    with state of its own shows only variables it plays.
  - Serialize state changes into turn_event payloads for storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Collection, Dict, List, Optional, Set, Tuple


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
    # The authored one-line meaning (``state.variables.<name>.description``),
    # which the turn prompt's STATE_VARIABLES layer shows the model (#580).
    description: str = ""


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


# What each baseline means, for a scenario that relies on one without saying
# (issue #580): the turn prompt's STATE_VARIABLES layer shows it to the NPC,
# hence the second person.
BASELINE_DESCRIPTIONS: Dict[str, str] = {
    "trust": "How much you trust the player's honesty and intentions.",
    "patience": "How much patience you have left for this conversation.",
    "pressure": "How pressured or cornered you feel.",
    "rapport": "How warm and connected the conversation feels to you.",
    "openness": "How willing you are to share and to consider the player's view.",
    "objective_progress": "How far the conversation has moved toward the scenario's goal.",
}


def _description_of(spec: Dict[str, Any], fallback: str) -> str:
    value = spec.get("description")
    return " ".join(value.split()) if isinstance(value, str) else fallback


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
                    description=existing.description,
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
                description=_description_of(spec, existing.description),
            )
    return defs


def _declares(name: str, spec: Any) -> bool:
    """Whether a ``state.variables`` entry makes ``name`` a variable the scenario plays.

    Every entry for a name of the scenario's own does. An entry for a
    baseline does too, unless all it does is hide it: the First Words
    tutorial hides every baseline so only its own two meters show.
    """
    if isinstance(spec, bool) or not isinstance(spec, (int, dict)):
        return False
    if name not in BASELINE_VARIABLES or isinstance(spec, int):
        return True
    return set(spec) != {"visibility"} or spec.get("visibility") != VariableVisibility.HIDDEN.value


def _condition_variable(condition: Any) -> Optional[str]:
    if not isinstance(condition, dict):
        return None
    if condition.get("type") not in ("variable_above", "variable_below"):
        return None
    variable = condition.get("variable")
    return variable if isinstance(variable, str) and variable else None


def played_variable_names(
    custom: Optional[Dict[str, Any]] = None,
    events: Optional[List["ScenarioEvent"]] = None,
    ending_conditions: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """The variables a scenario plays, in the order the turn prompt lists them.

    First every variable the scenario declares in ``state.variables``, in its
    order, a baseline it re-declares (the_ask's ``rapport``) included; then
    each baseline its events or ending conditions read without declaring it
    (the catalog coworker_feedback's ``patience``), in baseline order. Issue
    #580: the model is told to update exactly these, and the turn schema
    takes no other, so a baseline nothing reads stops moving at random.

    Returns [] for a scenario that configures no state at all (most of the
    hardcoded catalog). Its only variables are the baselines, and it plays all
    of them as it always has.
    """
    defs = build_variable_defs(custom)
    names: List[str] = []
    for name, spec in (custom or {}).items():
        if name in defs and _declares(name, spec) and name not in names:
            names.append(name)
    read: Set[str] = set()
    for event in events or []:
        variable = _condition_variable(event.when)
        if variable:
            read.add(variable)
    for condition in (ending_conditions or {}).values():
        variable = _condition_variable(condition)
        if variable:
            read.add(variable)
    for name in BASELINE_VARIABLES:
        if name in read and name not in names:
            names.append(name)
    return names


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
    allowed: Optional[Collection[str]] = None,
) -> DeltaResult:
    """Apply an LLM-proposed delta to the current state.

    Rules enforced:
    1. Keys absent from ``variable_defs`` are rejected (not applied), and so
       are keys outside ``allowed`` when it is given: the variables the
       session's turn schema names (issue #580). A runtime that enforces the
       schema never writes another; one that ignores it, and the parser's own
       repair calls, can.
    2. Each applied delta is clamped to ±``max_delta_per_turn``.
    3. The resulting value is clamped to [min, max] for the variable.

    Returns a DeltaResult with the new state, what was actually changed, and
    any rejected keys.
    """
    new_state: Dict[str, int] = dict(current)
    actual_changes: Dict[str, int] = {}
    rejected_keys: List[str] = []

    for key, proposed in delta.items():
        if key not in variable_defs or (allowed is not None and key not in allowed):
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
    played: Optional[Collection[str]] = None,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Split state into (visible, hidden) dicts for UI output.

    Variables absent from ``variable_defs`` default to visible.

    ``played`` is the variables the scenario plays (``played_variable_names``,
    the names the session's turn schema takes). When it names any, every
    other variable is hidden as well (issue #580): no delta for it is
    accepted, so it holds its default all session, and its meter would sit
    beside the scenario's own ones without ever moving (the_ask showed trust,
    patience, openness and objective_progress frozen next to rapport and
    confidence). With ``played`` empty or None, as for a scenario that
    configures no state of its own, each variable keeps its own visibility.
    """
    shown = set(played or ())
    visible: Dict[str, int] = {}
    hidden: Dict[str, int] = {}
    for name, value in state.items():
        defn = variable_defs.get(name)
        if (defn and defn.visibility == VariableVisibility.HIDDEN) or (shown and name not in shown):
            hidden[name] = value
        else:
            visible[name] = value
    return visible, hidden


def hidden_variable_names(
    variable_defs: Dict[str, ScenarioVariableDef],
    played: Optional[Collection[str]] = None,
) -> Set[str]:
    """The variables ``partition_state_by_visibility`` keeps from the player."""
    _, hidden = partition_state_by_visibility(
        {name: defn.default for name, defn in variable_defs.items()}, variable_defs, played,
    )
    return set(hidden)


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
