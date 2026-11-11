"""Layered prompt composer for simulator NPC turns."""
from __future__ import annotations

from typing import Dict, List, Sequence

from .layers import (
    _one_line,
    build_current_state_layer,
    build_global_rules_layer,
    build_memory_summary_layer,
    build_npc_private_persona_layer,
    build_npc_public_persona_layer,
    build_output_schema_layer,
    build_player_utterance_layer,
    build_previous_npc_line_layer,
    build_recent_transcript_layer,
    build_relationship_memory_layer,
    build_repetition_retry_layer,
    build_response_style_layer,
    build_rubric_layer,
    build_safety_policy_layer,
    build_scenario_brief_layer,
    build_scenario_events_layer,
    build_state_variables_layer,
)
from .types import PromptBundle, PromptComposerInput, turn_output_schema_for

# Conservative chars-per-token estimate for budget calculations.
_CHARS_PER_TOKEN = 4

# Canonical system-prompt layer ordering.
#
# Invariants enforced by this order:
#   - GLOBAL_RULES and SAFETY_POLICY always precede untrusted scenario content.
#   - OUTPUT_SCHEMA is always the final system-prompt section so it cannot be
#     displaced or overridden by anything in the scenario or player input.
#   - The UNTRUSTED_CONTENT_BEGIN / UNTRUSTED_CONTENT_END sentinels (inserted by
#     the scenario brief and response style layers respectively) bracket
#     SCENARIO_BRIEF through RESPONSE_STYLE (every layer below between them,
#     RELATIONSHIP_MEMORY and SCENARIO_EVENTS included), making the untrusted
#     region verifiable by adapters.
#   - RUBRIC and STATE_VARIABLES are constant for a session, so they sit with
#     the stable layers, ahead of CURRENT_STATE, where a prompt cache can reuse
#     them (issue #524). Everything from CURRENT_STATE on can change per turn.
#   - SCENARIO_EVENTS changes per turn, so it sits after CURRENT_STATE, inside
#     the untrusted region with the other authored text (issue #580).
#   - RUBRIC, STATE_VARIABLES and SCENARIO_EVENTS are empty, and left out of
#     the prompt, when there is nothing to say: no rubric, no state of the
#     scenario's own, no event fired for this turn (OPTIONAL_SYSTEM_LAYERS).
SYSTEM_LAYER_ORDER: List[str] = [
    "GLOBAL_RULES",
    "SAFETY_POLICY",
    "SCENARIO_BRIEF",          # untrusted region begins here
    "NPC_PUBLIC_PERSONA",
    "NPC_PRIVATE_PERSONA",
    "RUBRIC",                  # the scenario rubric's dimension ids (issue #578)
    "STATE_VARIABLES",         # what each variable means; update them every turn (issue #580)
    "CURRENT_STATE",           # first per-turn layer
    "RECENT_TRANSCRIPT",
    "MEMORY_SUMMARY",
    "RELATIONSHIP_MEMORY",     # bounded cross-session player recap (issue #314)
    "SCENARIO_EVENTS",         # instructions of the events that fired for this turn (issue #580)
    "RESPONSE_STYLE",          # untrusted region closes here (END sentinel appended by this layer)
    "OUTPUT_SCHEMA",           # always last in system prompt
]

# System layers a prompt may leave out because they have nothing to say.
OPTIONAL_SYSTEM_LAYERS = frozenset({"RUBRIC", "STATE_VARIABLES", "SCENARIO_EVENTS"})

# User-turn layer ordering. Text that changes every turn goes here, after every
# system layer, so it never sits in front of stable text (issue #524).
#   - PREVIOUS_NPC_LINE is empty, and left out of the user prompt, until the
#     transcript window holds an NPC line.
#   - PLAYER_UTTERANCE is always last: it is the line the NPC answers.
USER_LAYER_ORDER: List[str] = [
    "PREVIOUS_NPC_LINE",       # the NPC's own last line, not to be reused (issue #580)
    "PLAYER_UTTERANCE",        # always last
]

# Full ordering including the user turn.
LAYER_ORDER: List[str] = SYSTEM_LAYER_ORDER + USER_LAYER_ORDER

# Estimated tokens of the SCENARIO_EVENTS layer that do not count toward the
# token budget (issue #580). The layer is there only on a turn an event
# speaks, which is the turn its instruction needs the conversation so far
# ("float a specific number" needs the offers already made). Counted in full,
# it halved the transcript window on exactly those turns: the demo scenarios'
# prompts sit within a few dozen estimated tokens of the budget with a full
# window, and the layer is 150 to 280 with one or two events. So an event
# turn may run over the budget by up to this much; the engine's context
# (8192 tokens by default) has room for it beside the reply cap. Past it, the
# rest of the layer counts, so a pack whose many events fire at once still
# cannot grow the prompt without limit. The reported estimate counts every
# layer.
EVENTS_BUDGET_ALLOWANCE = 512


# The user turn of the repetition guard's one retry (issue #580): the normal
# user turn with what the first reply repeated quoted just before the player's
# line, which stays last. The system prompt is the turn's own, unchanged.
# Derived from USER_LAYER_ORDER, so a user layer added there reaches the retry
# too.
def _insert_before(order: List[str], layer: str, before: str) -> List[str]:
    at = order.index(before)
    return order[:at] + [layer] + order[at:]


RETRY_USER_LAYER_ORDER: List[str] = _insert_before(
    USER_LAYER_ORDER, "REPETITION_RETRY", "PLAYER_UTTERANCE"
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _budgeted_tokens(layers: Dict[str, str]) -> int:
    """The estimate the token budget is held to.

    The prompt's without the SCENARIO_EVENTS layer, plus whatever of that
    layer exceeds EVENTS_BUDGET_ALLOWANCE. With no event fired, the
    prompt's own estimate.
    """
    rest = {name: ("" if name == "SCENARIO_EVENTS" else text) for name, text in layers.items()}
    tokens = _estimate_tokens(_join(rest, SYSTEM_LAYER_ORDER) + _join(rest, USER_LAYER_ORDER))
    events = layers.get("SCENARIO_EVENTS", "")
    if events:
        tokens += max(0, _estimate_tokens(events) - EVENTS_BUDGET_ALLOWANCE)
    return tokens


def _build_layers(inp: PromptComposerInput, max_transcript_turns: int) -> Dict[str, str]:
    return {
        "GLOBAL_RULES": build_global_rules_layer(),
        "SAFETY_POLICY": build_safety_policy_layer(inp.safety_policy),
        "SCENARIO_BRIEF": build_scenario_brief_layer(inp.scenario),
        "NPC_PUBLIC_PERSONA": build_npc_public_persona_layer(inp.scenario),
        "NPC_PRIVATE_PERSONA": build_npc_private_persona_layer(inp.scenario),
        "RUBRIC": build_rubric_layer(inp.scenario),
        "STATE_VARIABLES": build_state_variables_layer(inp.scenario),
        "CURRENT_STATE": build_current_state_layer(inp.session_state, inp.scenario),
        "RECENT_TRANSCRIPT": build_recent_transcript_layer(
            inp.recent_transcript,
            max_turns=max_transcript_turns,
            npc_name=inp.scenario.npc.display_name,
            player_label=inp.scenario.player_role_label,
        ),
        "MEMORY_SUMMARY": build_memory_summary_layer(inp.memory_summary),
        "RELATIONSHIP_MEMORY": build_relationship_memory_layer(inp.relationship_recap),
        "SCENARIO_EVENTS": build_scenario_events_layer(inp.scenario_event_instructions),
        "RESPONSE_STYLE": build_response_style_layer(inp.scenario),
        "PREVIOUS_NPC_LINE": build_previous_npc_line_layer(
            inp.recent_transcript,
            max_turns=max_transcript_turns,
        ),
        "PLAYER_UTTERANCE": build_player_utterance_layer(inp.player_utterance),
        "OUTPUT_SCHEMA": build_output_schema_layer(turn_output_schema_for(inp.scenario)),
    }


def _join(layers: Dict[str, str], order: List[str]) -> str:
    """Join the named layers in order, leaving out any that are empty."""
    return "\n\n".join(layers[name] for name in order if layers[name])


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
    - PLAYER_UTTERANCE is always in the user turn, and last in it, kept
      separate from the system prompt so chat-format adapters can enforce the
      boundary natively. The only other user-turn text is PREVIOUS_NPC_LINE,
      which changes every turn and so must not sit in front of stable system
      text (issue #524). Both quote untrusted text, each inside its own
      sentinel frame that marks it as unable to override the rules.

    Token budget:
    - Estimates token count using a conservative chars-per-token heuristic.
    - If over budget, halves the transcript window once (placeholder strategy).
      Full summarization would call a separate summarization pass.
    - The events that fired for this turn (the SCENARIO_EVENTS layer) count
      toward that decision only past EVENTS_BUDGET_ALLOWANCE;
      ``estimated_token_count`` counts all of it.
    """
    max_turns = inp.max_transcript_turns
    layers = _build_layers(inp, max_turns)

    system_prompt = _join(layers, SYSTEM_LAYER_ORDER)
    user_prompt = _join(layers, USER_LAYER_ORDER)
    estimated_tokens = _estimate_tokens(system_prompt + user_prompt)
    was_truncated = False

    if _budgeted_tokens(layers) > inp.token_budget and max_turns > 2:
        reduced_max = max(2, max_turns // 2)
        layers = _build_layers(inp, reduced_max)
        system_prompt = _join(layers, SYSTEM_LAYER_ORDER)
        user_prompt = _join(layers, USER_LAYER_ORDER)
        estimated_tokens = _estimate_tokens(system_prompt + user_prompt)
        was_truncated = True

    return PromptBundle(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        layer_map=layers,
        estimated_token_count=estimated_tokens,
        was_truncated=was_truncated,
    )


def compose_repetition_retry_prompt(
    bundle: PromptBundle,
    repeated_lines: Sequence[str],
) -> PromptBundle:
    """The turn's prompt for the repetition guard's one retry (issue #580).

    ``bundle`` is the prompt the first reply was generated from, and
    ``repeated_lines`` the NPC's earlier line(s) that reply repeated. The
    system prompt is reused as it is, so a prompt cache keeps all of it
    (issue #524); only the user turn changes, with the REPETITION_RETRY layer
    quoting the repeated line(s) just before the player's line, which stays
    last. When a line repeated is the one PREVIOUS_NPC_LINE already quotes,
    that layer is left out rather than quote the same line twice.

    Returns ``bundle`` itself when there is nothing to quote.
    """
    retry_layer = build_repetition_retry_layer(list(repeated_lines))
    if not retry_layer:
        return bundle
    layers = dict(bundle.layer_map)
    previous = layers.get("PREVIOUS_NPC_LINE", "")
    quoted = {f'"{_one_line(line)}"' for line in repeated_lines}
    if previous and any(row in quoted for row in previous.split("\n")):
        layers["PREVIOUS_NPC_LINE"] = ""
    layers["REPETITION_RETRY"] = retry_layer
    user_prompt = _join(layers, RETRY_USER_LAYER_ORDER)
    return PromptBundle(
        system_prompt=bundle.system_prompt,
        user_prompt=user_prompt,
        layer_map=layers,
        estimated_token_count=_estimate_tokens(bundle.system_prompt + user_prompt),
        was_truncated=bundle.was_truncated,
    )
