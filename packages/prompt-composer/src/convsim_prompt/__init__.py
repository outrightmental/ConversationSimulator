"""convsim_prompt — Layered prompt composer for Conversation Simulator NPC turns."""

from .composer import LAYER_ORDER, SYSTEM_LAYER_ORDER, compose_turn_prompt
from .debrief_composer import DebriefComposerInput, DebriefTurnRecord, compose_debrief_prompt
from .debrief_output import (
    DEBRIEF_NARRATIVE_SCHEMA,
    DEBRIEF_SYSTEM_PREAMBLE,
    DebriefNarrative,
    DebriefValidationError,
    TurningPoint,
    parse_debrief_narrative,
)
from .inspection import PromptInspector
from .layers import UNTRUSTED_CONTENT_BEGIN, UNTRUSTED_CONTENT_END
from .output_validator import (
    OutputValidationResult,
    OutputViolation,
    validate_npc_output,
)
from .turn_output import (
    RubricObservation,
    RuntimeProtocol,
    SAFE_FALLBACK_UTTERANCE,
    SAFE_REDIRECT_UTTERANCE,
    SAFE_STOP_UTTERANCE,
    SafetyStatus,
    SessionControl,
    TurnEvent,
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
    "TurnEvent",
    "RubricObservation",
    "SafetyStatus",
    "SessionControl",
    "ValidationError",
    "RuntimeProtocol",
    "SAFE_FALLBACK_UTTERANCE",
    "SAFE_REDIRECT_UTTERANCE",
    "SAFE_STOP_UTTERANCE",
    # Output content validator
    "validate_npc_output",
    "OutputValidationResult",
    "OutputViolation",
]
