"""convsim_prompt — Layered prompt composer for Conversation Simulator NPC turns."""

from .composer import LAYER_ORDER, SYSTEM_LAYER_ORDER, compose_turn_prompt
from .inspection import PromptInspector
from .layers import UNTRUSTED_CONTENT_BEGIN, UNTRUSTED_CONTENT_END
from .turn_output import (
    RubricObservation,
    RuntimeProtocol,
    SAFE_FALLBACK_UTTERANCE,
    SafetyStatus,
    SessionControl,
    TurnOutput,
    ValidationError,
    parse_turn_output,
)
from .types import (
    DifficultySettings,
    NPC_TURN_OUTPUT_SCHEMA,
    NpcData,
    NpcPrivatePersona,
    NpcPublicPersona,
    PromptBundle,
    PromptComposerInput,
    ResponseStyleOverrides,
    SafetyPolicy,
    ScenarioData,
    SessionState,
    TranscriptEntry,
)

__all__ = [
    "compose_turn_prompt",
    "LAYER_ORDER",
    "SYSTEM_LAYER_ORDER",
    "UNTRUSTED_CONTENT_BEGIN",
    "UNTRUSTED_CONTENT_END",
    "PromptInspector",
    "DifficultySettings",
    "NPC_TURN_OUTPUT_SCHEMA",
    "NpcData",
    "NpcPrivatePersona",
    "NpcPublicPersona",
    "PromptBundle",
    "PromptComposerInput",
    "ResponseStyleOverrides",
    "SafetyPolicy",
    "ScenarioData",
    "SessionState",
    "TranscriptEntry",
    # Turn output parser
    "parse_turn_output",
    "TurnOutput",
    "RubricObservation",
    "SafetyStatus",
    "SessionControl",
    "ValidationError",
    "RuntimeProtocol",
    "SAFE_FALLBACK_UTTERANCE",
]
