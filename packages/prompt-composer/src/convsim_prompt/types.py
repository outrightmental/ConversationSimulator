"""Shared data types for the layered prompt composer."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class NpcPublicPersona:
    occupation: str
    speaking_style: str
    demeanor: str


@dataclass
class NpcPrivatePersona:
    hidden_agenda: List[str]
    biases_to_simulate: List[str] = field(default_factory=list)
    boundaries: List[str] = field(default_factory=list)


@dataclass
class NpcData:
    npc_id: str
    display_name: str
    public_persona: NpcPublicPersona
    private_persona: NpcPrivatePersona


@dataclass
class DifficultySettings:
    """Knob values for one named difficulty preset.

    Each knob is 0-100.  The midpoint (50) is the neutral baseline; values above
    or below steer NPC behaviour in the direction described.

    ``description`` is the preset's authored one-line description from the
    scenario YAML (``difficulty.options.<preset>.description``), e.g. "Ray
    holds his position but responds to good arguments". It is the only
    behaviour text a mid-range preset such as ``standard`` has, since the knob
    fragments only speak at the extremes.
    """
    patience: int = 50       # higher → NPC stays engaged longer
    volatility: int = 50     # higher → state meters shift more per turn
    disclosure: int = 50     # higher → NPC volunteers more information
    time_pressure: int = 50  # higher → NPC signals urgency / turn budget pressure
    description: Optional[str] = None


@dataclass
class ResponseStyleOverrides:
    """Per-scenario overrides for NPC response style constraints."""
    max_words: int = 90
    max_questions_per_turn: int = 2
    allow_short_responses: bool = True
    avoid_monologues: bool = True


@dataclass
class RubricDimension:
    """One scoring dimension of a scenario rubric (a rubric file's ``dimensions[]``).

    ``low``, ``medium`` and ``high`` are the authored band descriptions
    (``scoring.low`` and so on). ``weight`` is the optional relative weight
    the overall score uses; None when the rubric gives the dimension none.
    """
    id: str
    name: str
    description: str = ""
    low: str = ""
    medium: str = ""
    high: str = ""
    weight: Optional[float] = None


@dataclass
class ScenarioRubric:
    """The rubric a scenario's ``rubric: ref:`` names, as play uses it (issue #578)."""
    rubric_id: str
    title: str
    dimensions: List[RubricDimension] = field(default_factory=list)

    @property
    def dimension_ids(self) -> List[str]:
        return [d.id for d in self.dimensions]


@dataclass
class StateVariableCue:
    """What an authored event says one level of a variable means (issue #580).

    ``direction`` is "above" or "below" and ``threshold`` the event's
    threshold; ``text`` is the event's ``npc_instruction``, of which the
    STATE_VARIABLES layer quotes the first sentence when the variable has no
    authored description.
    """
    direction: str
    threshold: int
    text: str


@dataclass
class StateVariable:
    """One state variable the model updates every turn (issue #580).

    ``description`` is the meaning the scenario authored for it (or, for an
    engine baseline the scenario relies on, the engine's own one-line
    meaning); "" when there is none, and then ``cues`` from the scenario's
    events say what its levels mean. ``max_delta_per_turn`` is the engine's
    per-turn clamp, which the STATE_VARIABLES layer states; the turn schema
    leaves the value unbounded (see ``_state_delta_schema``).
    """
    name: str
    min: int = 0
    max: int = 100
    max_delta_per_turn: int = 20
    description: str = ""
    cues: List[StateVariableCue] = field(default_factory=list)


@dataclass
class ScenarioData:
    scenario_id: str
    title: str
    player_role_label: str
    player_role_brief: str
    npc: NpcData
    difficulty: str = "standard"
    difficulty_settings: Optional[DifficultySettings] = None
    response_style: Optional[ResponseStyleOverrides] = None
    opening_npc_says: Optional[str] = None
    player_visible_goals: List[str] = field(default_factory=list)
    # The scenario's rubric, loaded from its pack (issue #578). None for the
    # hardcoded catalog entries and for a pack scenario whose rubric file is
    # missing or unreadable: those play, and debrief, as they always have.
    rubric: Optional[ScenarioRubric] = None
    # The state variables the scenario plays, in prompt order: the ones it
    # declares, then the engine baselines its events or endings read (issue
    # #580). The STATE_VARIABLES layer explains them, CURRENT_STATE lists only
    # them and the turn schema requires each in state_delta. Empty for a
    # scenario that configures no state (most of the hardcoded catalog): its
    # prompt lists every variable and its state_delta stays free-form, as
    # before.
    state_variables: List[StateVariable] = field(default_factory=list)

    @property
    def rubric_dimension_ids(self) -> List[str]:
        """The rubric's dimension ids, or [] when the scenario has no rubric."""
        return self.rubric.dimension_ids if self.rubric else []

    @property
    def state_variable_names(self) -> List[str]:
        """The names of ``state_variables``, or [] when the scenario plays none."""
        return [v.name for v in self.state_variables]


@dataclass
class SafetyPolicy:
    policy_id: str
    content_rating: str
    prohibited: List[str]
    redirects: Dict[str, str] = field(default_factory=dict)


@dataclass
class SessionState:
    variables: Dict[str, int]
    turn_number: int = 0


@dataclass
class TranscriptEntry:
    speaker: str  # "player" or "npc"
    text: str
    turn_number: int


# Canonical structured output schema for NPC turns (SPEC §6.4).
# Adapters may pass this to native JSON-mode APIs (Ollama, llama.cpp grammar)
# in addition to embedding it in the prompt.
NPC_TURN_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "npc_utterance",
        "npc_emotion",
        "state_delta",
        "event_flags",
        "rubric_observations",
        "safety",
        "session_control",
    ],
    "properties": {
        "npc_utterance": {
            "type": "string",
            "description": "The exact words the NPC says to the player.",
        },
        "npc_emotion": {
            "type": "string",
            "enum": [
                "neutral", "warm", "curious", "skeptical", "impatient",
                "defensive", "confused", "impressed", "concerned", "angry",
            ],
        },
        "state_delta": {
            "type": "object",
            "additionalProperties": {
                "type": "integer",
                "minimum": -20,
                "maximum": 20,
            },
        },
        "event_flags": {"type": "array", "items": {"type": "string"}},
        "rubric_observations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rubric_id", "observation"],
                "properties": {
                    "rubric_id": {"type": "string"},
                    "observation": {"type": "string"},
                    "score_delta": {
                        "type": "integer",
                        "minimum": -3,
                        "maximum": 3,
                    },
                },
            },
        },
        "safety": {
            "type": "object",
            "required": ["status"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ok", "redirect", "stop"],
                },
                "reason": {"type": "string"},
            },
        },
        "session_control": {
            "type": "object",
            "required": ["continue_session"],
            "properties": {
                "continue_session": {"type": "boolean"},
                "ending_type": {
                    "type": "string",
                    "enum": [
                        "none", "success", "failure",
                        "timeout", "safety_stop", "player_exit",
                    ],
                },
                "ending_summary": {"type": "string"},
            },
        },
    },
}


def _state_delta_schema(state_variables: Sequence["StateVariable"]) -> Optional[Dict[str, Any]]:
    """``state_delta`` with one required integer per played variable, or None for none.

    Every variable is ``required`` and no other key is allowed: llama.cpp's
    converter writes required properties as mandatory keys, in ``properties``
    order, and has no ``minProperties``, so an optional property leaves
    ``{}`` the shortest path through the grammar, which is what the starter
    model took (issue #580, P4: one authored variable written in twenty
    turns). Zero stays a valid value, so "no change" is still one token.
    Without ``additionalProperties: false`` the grammar would also offer
    free-form keys, where the model wrote the generic baseline names the
    prompt no longer shows.

    The values carry no ``minimum``/``maximum``. The per-turn limit is in the
    STATE_VARIABLES layer and the engine clamps to it (``apply_state_delta``).
    A bounded integer becomes a digit-by-digit grammar, and the starter
    model's tokenizer writes numbers one digit at a time, so under a bound of
    6 an intended 10 stops after its "1": the grammar would turn a strong
    move into a weak one, where the clamp keeps it the strongest allowed.
    """
    properties: Dict[str, Any] = {}
    for variable in state_variables:
        name = variable.name
        if not isinstance(name, str) or not name or name in properties:
            continue
        properties[name] = {"type": "integer"}
    if not properties:
        return None
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def build_npc_turn_output_schema(
    *,
    rubric_ids: Optional[Sequence[str]] = None,
    state_variables: Optional[Sequence["StateVariable"]] = None,
) -> Dict[str, Any]:
    """The NPC turn output schema for one session: a fresh copy of the canonical one.

    With ``rubric_ids``, ``rubric_observations[].rubric_id`` becomes an
    ``enum`` of those ids (issue #578). The runtimes hand this schema to the
    engine (llama.cpp's ``response_format.schema``, Ollama's ``format``),
    whose schema-to-grammar conversion then cannot emit any other id; the
    free-string id let the starter model score dimensions the rubric does not
    have.

    With ``state_variables``, ``state_delta`` names each of them, each a
    required integer, and no other key (issue #580; see
    ``_state_delta_schema``). Without either (a scenario with no rubric and
    no state of its own) the result equals NPC_TURN_OUTPUT_SCHEMA.

    The schema is constant for a session, and it is the last system layer,
    after the per-turn state and transcript, so making it per scenario costs
    the prompt cache nothing (issue #524).

    Only keywords both converters handle are used: ``type``, ``properties``,
    ``required``, ``enum`` of strings, ``items``, ``additionalProperties``
    and integer ``minimum``/``maximum``.
    """
    schema = copy.deepcopy(NPC_TURN_OUTPUT_SCHEMA)
    ids = list(dict.fromkeys(i for i in (rubric_ids or ()) if isinstance(i, str) and i))
    if ids:
        item = schema["properties"]["rubric_observations"]["items"]
        item["properties"]["rubric_id"] = {"type": "string", "enum": ids}
    state_delta = _state_delta_schema(state_variables or ())
    if state_delta is not None:
        schema["properties"]["state_delta"] = state_delta
    return schema


def turn_output_schema_for(scenario: "ScenarioData") -> Dict[str, Any]:
    """The turn output schema a session of ``scenario`` is played with."""
    return build_npc_turn_output_schema(
        rubric_ids=scenario.rubric_dimension_ids,
        state_variables=scenario.state_variables,
    )


def state_variables_in_schema(schema: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """The variables a turn output schema's ``state_delta`` is closed to, or None.

    None when ``state_delta`` takes any key (the canonical schema): then every
    variable the scenario defines may be moved, as before issue #580.
    """
    try:
        delta = schema["properties"]["state_delta"]  # type: ignore[index]
        properties = delta["properties"]
    except (KeyError, TypeError):
        return None
    if not isinstance(properties, dict) or delta.get("additionalProperties") is not False:
        return None
    names = [n for n in properties if isinstance(n, str) and n]
    return names or None


def rubric_ids_in_schema(schema: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """The ``rubric_id`` enum of a turn output schema, or None when it has none."""
    try:
        item = schema["properties"]["rubric_observations"]["items"]  # type: ignore[index]
        enum = item["properties"]["rubric_id"]["enum"]
    except (KeyError, TypeError):
        return None
    if not isinstance(enum, list):
        return None
    ids = [i for i in enum if isinstance(i, str) and i]
    return ids or None


@dataclass
class PromptBundle:
    """Fully assembled prompt bundle ready for submission to an LLM adapter."""
    system_prompt: str
    user_prompt: str
    # Per-layer content map for dev inspection and adapter reuse.
    layer_map: Dict[str, str]
    estimated_token_count: int
    was_truncated: bool = False


@dataclass
class PromptComposerInput:
    scenario: ScenarioData
    session_state: SessionState
    safety_policy: SafetyPolicy
    player_utterance: str
    recent_transcript: List[TranscriptEntry] = field(default_factory=list)
    memory_summary: Optional[str] = None
    relationship_recap: Optional[Dict[str, Any]] = None
    max_transcript_turns: int = 6
    token_budget: int = 4096
    # The npc_instruction of each scenario event that fired for this turn, in
    # the scenario's event order (issue #580): the SCENARIO_EVENTS layer.
    scenario_event_instructions: List[str] = field(default_factory=list)
