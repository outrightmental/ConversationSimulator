"""Shared data types for the layered prompt composer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    """
    patience: int = 50       # higher → NPC stays engaged longer
    volatility: int = 50     # higher → state meters shift more per turn
    disclosure: int = 50     # higher → NPC volunteers more information
    time_pressure: int = 50  # higher → NPC signals urgency / turn budget pressure


@dataclass
class ResponseStyleOverrides:
    """Per-scenario overrides for NPC response style constraints."""
    max_words: int = 90
    max_questions_per_turn: int = 2
    allow_short_responses: bool = True
    avoid_monologues: bool = True


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
