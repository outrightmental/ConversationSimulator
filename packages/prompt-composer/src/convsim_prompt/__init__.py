"""convsim_prompt — Layered prompt composer for Conversation Simulator NPC turns."""

from .composer import LAYER_ORDER, SYSTEM_LAYER_ORDER, compose_turn_prompt
from .inspection import PromptInspector
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
]
