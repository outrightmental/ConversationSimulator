# SPDX-License-Identifier: Apache-2.0
"""The debrief's output budget (issue #580).

A debrief reply cut off at ``_DEBRIEF_MAX_TOKENS`` is invalid JSON, and the
debrief falls back to the template: the demo gate's check (e) fails, and the
rubric bands are lost with the narrative. The narrative schema caps its lists
(``maxItems``). These tests check that a reply filled to every cap fits the
budget, and that the longest session's prompt leaves the budget room in the
starter models' context.

Token counts are estimated from characters. Counted with the starter model's
own tokenizer (Qwen3-4B-Instruct-2507), the ten D-05 replay debriefs' replies
ran 4.39-5.08 characters a token, pretty-printed as the model writes them,
the reply filled to every cap below 5.10 (1270 tokens), and the debriefs'
prompts 4.31-4.54. The prompt's own estimate is a character count over 4
(compose_debrief_prompt), so it is on the high side.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

import pytest

from convsim_core.runtime.launch import DEFAULT_CONTEXT_LENGTH
from convsim_core.scenario_state import build_variable_defs, initialize_state
from convsim_core.scenarios import ScenarioInfo, load_scenario_info_from_pack
from convsim_core.services.debrief_engine import _DEBRIEF_MAX_TOKENS
from convsim_prompt import DebriefTurnRecord, build_debrief_narrative_schema, compose_debrief_prompt
from convsim_prompt.debrief_composer import DebriefComposerInput

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKS = _REPO_ROOT / "packs"

# Characters a token in a debrief reply, below and above what the D-05
# replies ran: for a high token estimate and a low one.
_REPLY_CHARS_PER_TOKEN_MIN = 4.3
_REPLY_CHARS_PER_TOKEN_MAX = 5.2

# The budget before #580's review: a reply filled to the caps overran it.
_OLD_BUDGET = 1024

# The longest item each list of the D-05 debriefs held (missed_opportunities
# was empty in all ten, so it takes the longest improvement).
_LONGEST_IMPROVEMENT = (
    "While the ask was well-timed and clear, it would be stronger if the player had slightly "
    "delayed the ask until after a more explicit signal of openness from Jordan — for example, "
    "if Jordan had mentioned enjoying the conversation or expressed interest in continuing the "
    "dialogue. The current moment is strong but could have been even more natural with one "
    "additional layer of connection before making the ask."
)
_LONGEST_ITEMS: Dict[str, Any] = {
    "missed_opportunities": _LONGEST_IMPROVEMENT,
    "strengths": (
        "In Turn 1, the candidate clearly described a situation where checkout timeouts occurred "
        "under holiday load, took specific actions (traced an N+1 query, shipped a batched "
        "query), and cited a measurable result (p95 latency reduced from four seconds to three "
        "hundred milliseconds). This demonstrates high specificity and clarity, with strong "
        "narrative structure."
    ),
    "improvements": _LONGEST_IMPROVEMENT,
    "turning_points": {
        "turn_number": 2,
        "description": (
            "Player asks about Jordan's paper topic, specifically referencing urban green "
            "corridors and bird species — a direct response to what Jordan shared. This marks "
            "the first clear sign of deep engagement with Jordan’s personal research."
        ),
        "impact": "positive",
    },
    "replay_suggestions": (
        "When asked about weaknesses or failures, provide a real example with context: time, "
        "impact, action taken, and learning. For instance, 'I once ran a migration without "
        "rollback, causing a 20-minute outage — since then, I’ve implemented a mandatory "
        "rollback checklist for all schema changes.'"
    ),
}
_LONGEST_SUMMARY = (
    "The player effectively used market research to anchor their negotiation, consistently "
    "presenting clear price points supported by comparable sales data. They maintained firmness "
    "throughout while demonstrating empathy and mutual interest in key moments, leading to a "
    "favorable outcome where the final price was reduced to $13,900 with new tires — below the "
    "original list and within competitive range. However, a shift in strategy during turn 5 "
    "weakened their position by introducing walkaway language without supporting it with data "
    "or collaborative framing."
)

# The D-05 transcripts' 90th-percentile line lengths, in characters, and
# their longest opening line.
_PLAYER_LINE_CHARS = 213
_NPC_LINE_CHARS = 259
_OPENING_CHARS = 364


def _scenarios() -> List[ScenarioInfo]:
    """Every pack scenario, as the engine loads it."""
    return [
        load_scenario_info_from_pack(f.parent.parent, f"scenarios/{f.name}")
        for f in sorted(_PACKS.glob("*/*/scenarios/*.yaml"))
    ]


def _rubric_ids_with_the_most_dimensions() -> List[str]:
    rubrics = [s.scenario_data.rubric for s in _scenarios() if s.scenario_data.rubric]
    widest = max(rubrics, key=lambda r: (len(r.dimension_ids), len("".join(r.dimension_ids))))
    return list(widest.dimension_ids)


def _reply_filled_to_every_cap(schema: Dict[str, Any], rubric_ids: List[str]) -> Dict[str, Any]:
    reply: Dict[str, Any] = {}
    for key, prop in schema["properties"].items():
        if key == "dimension_bands":
            # The longest band, for every dimension.
            reply[key] = {i: "not_observed" for i in rubric_ids}
        elif key == "summary":
            reply[key] = _LONGEST_SUMMARY
        else:
            reply[key] = [_LONGEST_ITEMS[key]] * prop["maxItems"]
    return reply


def test_a_reply_filled_to_every_cap_fits_the_budget() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    rubric_ids = _rubric_ids_with_the_most_dimensions()
    schema = build_debrief_narrative_schema(rubric_ids=rubric_ids)
    reply = _reply_filled_to_every_cap(schema, rubric_ids)
    jsonschema.validate(reply, schema)

    text = json.dumps(reply, ensure_ascii=False, indent=2)
    most = math.ceil(len(text) / _REPLY_CHARS_PER_TOKEN_MIN)
    least = math.floor(len(text) / _REPLY_CHARS_PER_TOKEN_MAX)
    assert most <= _DEBRIEF_MAX_TOKENS, (most, _DEBRIEF_MAX_TOKENS)
    # The budget it replaced was too small for it.
    assert least > _OLD_BUDGET, least


@pytest.mark.parametrize("info", _scenarios(), ids=lambda i: i.scenario_data.scenario_id)
def test_the_longest_session_leaves_the_budget_room_in_the_context(info: ScenarioInfo) -> None:
    """Every turn played, every line as long as D-05's 90th percentile, every NPC line a question."""
    sd = info.scenario_data
    rubric = sd.rubric
    npc_line = ("That is a fair point, and I can see you have thought about it. " * 9)
    player_line = ("I hear you, and here is what I would add from my own experience. " * 9)
    turns = [DebriefTurnRecord(0, "npc_opening", npc_line[:_OPENING_CHARS - 1] + "?")]
    for n in range(1, info.max_turns + 1):
        turns.append(DebriefTurnRecord(n, "player", player_line[:_PLAYER_LINE_CHARS]))
        turns.append(DebriefTurnRecord(n, "npc", npc_line[:_NPC_LINE_CHARS - 1] + "?"))
    prompt = compose_debrief_prompt(DebriefComposerInput(
        session_id="sess-budget",
        scenario_id=sd.scenario_id,
        scenario_title=sd.title,
        player_role_label=sd.player_role_label,
        outcome="timeout",
        total_turns=info.max_turns,
        final_state=initialize_state(build_variable_defs(info.state_variable_overrides)),
        scores={},
        turns=turns,
        rubric_dimension_names={d.id: d.name for d in rubric.dimensions} if rubric else {},
        difficulty_preset="standard",
        rubric_dimensions=list(rubric.dimensions) if rubric else [],
        player_visible_goals=list(sd.player_visible_goals),
        npc_name=sd.npc.display_name,
    ))
    assert prompt.estimated_token_count + _DEBRIEF_MAX_TOKENS <= DEFAULT_CONTEXT_LENGTH, (
        prompt.estimated_token_count
    )
