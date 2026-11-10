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

    @property
    def rubric_dimension_ids(self) -> List[str]:
        """The rubric's dimension ids, or [] when the scenario has no rubric."""
        return self.rubric.dimension_ids if self.rubric else []


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


def build_npc_turn_output_schema(
    *,
    rubric_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """The NPC turn output schema for one session: a fresh copy of the canonical one.

    With ``rubric_ids``, ``rubric_observations[].rubric_id`` becomes an
    ``enum`` of those ids (issue #578). The runtimes hand this schema to the
    engine (llama.cpp's ``response_format.schema``, Ollama's ``format``),
    whose schema-to-grammar conversion then cannot emit any other id; the
    free-string id let the starter model score dimensions the rubric does not
    have. Without ids (a scenario with no rubric) the result equals
    NPC_TURN_OUTPUT_SCHEMA.

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
    return schema


def turn_output_schema_for(scenario: "ScenarioData") -> Dict[str, Any]:
    """The turn output schema a session of ``scenario`` is played with."""
    return build_npc_turn_output_schema(rubric_ids=scenario.rubric_dimension_ids)


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
