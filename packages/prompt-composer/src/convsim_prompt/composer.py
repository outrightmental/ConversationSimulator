"""Layered prompt composer for simulator NPC turns."""
from __future__ import annotations

from typing import Dict, List

from .layers import (
    build_current_state_layer,
    build_global_rules_layer,
    build_memory_summary_layer,
    build_npc_private_persona_layer,
    build_npc_public_persona_layer,
    build_output_schema_layer,
    build_player_utterance_layer,
    build_recent_transcript_layer,
    build_response_style_layer,
    build_safety_policy_layer,
    build_scenario_brief_layer,
)
from .types import PromptBundle, PromptComposerInput

# Conservative chars-per-token estimate for budget calculations.
_CHARS_PER_TOKEN = 4

# Canonical system-prompt layer ordering.
#
# Invariants enforced by this order:
#   - GLOBAL_RULES and SAFETY_POLICY always precede untrusted scenario content.
#   - OUTPUT_SCHEMA is always the final system-prompt section so it cannot be
#     displaced or overridden by anything in the scenario or player input.
#   - The UNTRUSTED_CONTENT_BEGIN / UNTRUSTED_CONTENT_END sentinels (inserted by
#     the scenario brief and output schema layers respectively) bracket items 3–9,
#     making the untrusted region verifiable by adapters.
SYSTEM_LAYER_ORDER: List[str] = [
    "GLOBAL_RULES",
    "SAFETY_POLICY",
    "SCENARIO_BRIEF",       # untrusted region begins here
    "NPC_PUBLIC_PERSONA",
    "NPC_PRIVATE_PERSONA",
    "CURRENT_STATE",
    "RECENT_TRANSCRIPT",
    "MEMORY_SUMMARY",
    "RESPONSE_STYLE",
    "OUTPUT_SCHEMA",        # untrusted region closes here; schema always last
]

# Full ordering including the user turn.
LAYER_ORDER: List[str] = SYSTEM_LAYER_ORDER + ["PLAYER_UTTERANCE"]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _build_layers(inp: PromptComposerInput, max_transcript_turns: int) -> Dict[str, str]:
    return {
        "GLOBAL_RULES": build_global_rules_layer(),
        "SAFETY_POLICY": build_safety_policy_layer(inp.safety_policy),
        "SCENARIO_BRIEF": build_scenario_brief_layer(inp.scenario),
        "NPC_PUBLIC_PERSONA": build_npc_public_persona_layer(inp.scenario),
        "NPC_PRIVATE_PERSONA": build_npc_private_persona_layer(inp.scenario),
        "CURRENT_STATE": build_current_state_layer(inp.session_state),
        "RECENT_TRANSCRIPT": build_recent_transcript_layer(
            inp.recent_transcript,
            max_turns=max_transcript_turns,
        ),
        "MEMORY_SUMMARY": build_memory_summary_layer(inp.memory_summary),
        "RESPONSE_STYLE": build_response_style_layer(inp.scenario),
        "PLAYER_UTTERANCE": build_player_utterance_layer(inp.player_utterance),
        "OUTPUT_SCHEMA": build_output_schema_layer(),
    }


def compose_turn_prompt(inp: PromptComposerInput) -> PromptBundle:
    """
    Build a deterministic layered prompt bundle for a single NPC turn.

    Returns the same output for identical inputs (deterministic).

    Ordering guarantees:
    - GLOBAL_RULES and SAFETY_POLICY precede all scenario content.
    - Untrusted scenario content (SCENARIO_BRIEF onwards) is bracketed with
      explicit sentinel strings that adapters can verify.
    - OUTPUT_SCHEMA is always the final system-prompt section and cannot be
      displaced by scenario text or player input.
    - PLAYER_UTTERANCE is always the user turn, kept separate from the system
      prompt so chat-format adapters can enforce the boundary natively.

    Token budget:
    - Estimates token count using a conservative chars-per-token heuristic.
    - If over budget, halves the transcript window once (placeholder strategy).
      Full summarization would call a separate summarization pass.
    """
    max_turns = inp.max_transcript_turns
    layers = _build_layers(inp, max_turns)

    system_prompt = "\n\n".join(layers[name] for name in SYSTEM_LAYER_ORDER)
    user_prompt = layers["PLAYER_UTTERANCE"]

    estimated_tokens = _estimate_tokens(system_prompt + user_prompt)
    was_truncated = False

    if estimated_tokens > inp.token_budget and max_turns > 2:
        reduced_max = max(2, max_turns // 2)
        layers = _build_layers(inp, reduced_max)
        system_prompt = "\n\n".join(layers[name] for name in SYSTEM_LAYER_ORDER)
        estimated_tokens = _estimate_tokens(system_prompt + user_prompt)
        was_truncated = True

    return PromptBundle(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        layer_map=layers,
        estimated_token_count=estimated_tokens,
        was_truncated=was_truncated,
    )
