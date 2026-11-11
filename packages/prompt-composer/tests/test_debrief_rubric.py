"""The debrief prompt and output schema with a scenario rubric (issues #578, #580 P6).

On the starter model every debrief scored dimensions the model had made up,
put each at 50 give or take a few points, and blamed the NPC's skepticism on
the player. These tests pin the prompt-composer half of the fix:

  - the debrief schema asks for a band per rubric dimension, right after the
    missed opportunities, as a grammar-friendly object of enums;
  - the parser keeps well-formed bands and never fails a narrative over one;
  - the prompt lists the rubric by name, with weights and bands, labels every
    transcript line with whose it is, and leaves the turn notes out (#580);
  - with no rubric, the prompt is as before, its notes labelled as the
    player's, and the schema the canonical one.

The judging rules (#580, the D-05 replay's debriefs) are pinned in
test_debrief_judging.py.
"""
import json

import pytest

from convsim_prompt import (
    DEBRIEF_NARRATIVE_SCHEMA,
    DIMENSION_BANDS,
    DebriefComposerInput,
    DebriefTurnRecord,
    build_debrief_narrative_schema,
    compose_debrief_prompt,
    parse_debrief_narrative,
)
from _helpers import make_interview_rubric

_NARRATIVE = {
    "missed_opportunities": [],
    "summary": "You gave one concrete example and owned a miss.",
    "strengths": ["You named the latency figure at turn 1."],
    "improvements": ["Say what you would do differently."],
    "turning_points": [{"turn_number": 1, "description": "A specific example.", "impact": "positive"}],
    "replay_suggestions": ["Lead with the result."],
}


def _input(rubric: bool = True, **overrides) -> DebriefComposerInput:
    rubric_doc = make_interview_rubric()
    values = dict(
        session_id="sess-1",
        scenario_id="behavioral_interview",
        scenario_title="Behavioral Interview",
        player_role_label="Candidate",
        outcome="player_exit",
        total_turns=1,
        final_state={"trust": 55},
        scores={"specificity": 52.0},
        turns=[
            DebriefTurnRecord(turn_number=0, role="npc_opening", content="Tell me about a project."),
            DebriefTurnRecord(turn_number=1, role="player", content="I cut checkout latency in half."),
            DebriefTurnRecord(
                turn_number=1, role="npc", content="I'm not convinced yet. How did you measure it?",
                rubric_observations=[
                    {"rubric_id": "specificity", "observation": "Named a figure.", "score_delta": 2},
                    {"rubric_id": "Self Awareness", "observation": "No reflection yet."},
                    {"rubric_id": "experience_gap", "observation": "Invented id.", "score_delta": -2},
                ],
                event_flags=["npc_skeptical"],
            ),
        ],
        rubric_dimensions=list(rubric_doc.dimensions) if rubric else [],
        player_visible_goals=["Answer with specific examples."],
        npc_name="Maya Chen",
    )
    values.update(overrides)
    return DebriefComposerInput(**values)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestDebriefSchema:
    def test_no_rubric_is_the_canonical_schema(self):
        for ids in (None, []):
            schema = build_debrief_narrative_schema(rubric_ids=ids)
            assert schema == DEBRIEF_NARRATIVE_SCHEMA
            assert schema is not DEBRIEF_NARRATIVE_SCHEMA

    def test_bands_are_required_right_after_the_missed_opportunities(self):
        schema = build_debrief_narrative_schema(rubric_ids=["specificity", "self_awareness"])
        order = ["missed_opportunities", "dimension_bands", "summary"]
        assert list(schema["properties"])[:3] == order
        assert schema["required"][:3] == order
        assert schema["properties"]["dimension_bands"] == {
            "type": "object",
            "description": "Each rubric dimension's band, judged only on what the player said.",
            "properties": {
                "specificity": {"type": "string", "enum": list(DIMENSION_BANDS)},
                "self_awareness": {"type": "string", "enum": list(DIMENSION_BANDS)},
            },
            "required": ["specificity", "self_awareness"],
            "additionalProperties": False,
        }
        # The rest is unchanged, and the canonical schema untouched.
        rest = {k: v for k, v in schema["properties"].items() if k != "dimension_bands"}
        assert rest == DEBRIEF_NARRATIVE_SCHEMA["properties"]
        assert "dimension_bands" not in DEBRIEF_NARRATIVE_SCHEMA["properties"]
        # The fake and scripted runtimes tell a debrief request by this key.
        assert "replay_suggestions" in schema["properties"]

    def test_bands(self):
        assert DIMENSION_BANDS == ("low", "medium", "high", "not_observed")

    def test_valid_json_schema_that_enforces_the_bands(self):
        jsonschema = pytest.importorskip("jsonschema")
        schema = build_debrief_narrative_schema(rubric_ids=["specificity", "self_awareness"])
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        good = {**_NARRATIVE, "dimension_bands": {"specificity": "high", "self_awareness": "not_observed"}}
        assert validator.is_valid(good)
        assert not validator.is_valid({**_NARRATIVE, "dimension_bands": {"specificity": "high"}})
        assert not validator.is_valid({**_NARRATIVE, "dimension_bands": {
            "specificity": "excellent", "self_awareness": "low"}})
        assert not validator.is_valid({**_NARRATIVE, "dimension_bands": {
            "specificity": "high", "self_awareness": "low", "rapport": "low"}})


# ---------------------------------------------------------------------------
# Parsing the bands
# ---------------------------------------------------------------------------


class TestParseBands:
    def test_bands_are_parsed(self):
        narrative = parse_debrief_narrative(json.dumps({
            **_NARRATIVE, "dimension_bands": {"specificity": "high", "self_awareness": "low"},
        }))
        assert not narrative.used_fallback
        assert narrative.dimension_bands == {"specificity": "high", "self_awareness": "low"}

    def test_a_bad_band_costs_the_band_not_the_narrative(self):
        narrative = parse_debrief_narrative(json.dumps({
            **_NARRATIVE,
            "dimension_bands": {"specificity": "excellent", "self_awareness": "medium", "x": 3},
        }))
        assert not narrative.used_fallback
        assert narrative.dimension_bands == {"self_awareness": "medium"}
        for bad in ([], "high", None):
            narrative = parse_debrief_narrative(json.dumps({**_NARRATIVE, "dimension_bands": bad}))
            assert not narrative.used_fallback and narrative.dimension_bands == {}

    def test_no_bands_is_still_a_narrative(self):
        narrative = parse_debrief_narrative(json.dumps(_NARRATIVE))
        assert not narrative.used_fallback and narrative.dimension_bands == {}

    def test_the_fallback_has_no_bands_and_uses_rubric_names(self):
        narrative = parse_debrief_narrative(
            "not json",
            fallback_scores={"specificity": 85.0, "self_awareness": 25.0},
            fallback_dimension_names={"specificity": "Specificity", "self_awareness": "Self-awareness"},
            fallback_overall_score=61.0,
        )
        assert narrative.used_fallback and narrative.dimension_bands == {}
        assert narrative.strengths == ["Strong performance on 'Specificity' (score: 85)."]
        assert narrative.improvements == ["Focus on 'Self-awareness' in your next attempt (score: 25)."]
        assert "Your overall score across tracked dimensions was 61/100." in narrative.summary

    def test_the_fallback_without_names_is_as_before(self):
        narrative = parse_debrief_narrative("not json", fallback_scores={"clarity": 70.0, "pace": 30.0})
        assert narrative.strengths == ["Strong performance on 'clarity' (score: 70)."]
        assert "Your overall average score across tracked dimensions was 50/100." in narrative.summary


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


class TestDebriefPromptWithRubric:
    def test_lists_each_dimension_with_name_weight_and_bands(self):
        sp = compose_debrief_prompt(_input()).system_prompt
        block = sp[sp.index("RUBRIC —"):]
        assert (
            "- specificity: Specificity, weight 60%\n"
            "    low: Mostly generic claims.\n"
            "    medium: Some examples but thin details.\n"
            "    high: Specific examples with context, action, and result.\n"
            "- self_awareness: Self-awareness, weight 40%\n"
            "    low: Blames others or avoids weakness.\n"
        ) in block
        assert "Band each one in dimension_bands by comparing the player's own lines" in block
        assert "Use not_observed only for a dimension the conversation gave the player no chance" in block

    def test_the_turn_scores_are_not_shown_with_a_rubric(self):
        """They are 50 plus a few points until the bands are placed, and would
        anchor every band at medium."""
        sp = compose_debrief_prompt(_input()).system_prompt
        assert "DIMENSION SCORES" not in sp
        assert "52/100" not in sp

    def test_the_schema_in_the_prompt_asks_for_the_bands(self):
        sp = compose_debrief_prompt(_input()).system_prompt
        quoted = json.loads(sp[sp.index("{", sp.index("OUTPUT SCHEMA")):])
        assert quoted == build_debrief_narrative_schema(rubric_ids=["specificity", "self_awareness"])

    def test_goals_are_given(self):
        sp = compose_debrief_prompt(_input()).system_prompt
        assert "PLAYER GOALS (shown to the player):\n  - Answer with specific examples." in sp

    def test_every_line_says_whose_it_is(self):
        up = compose_debrief_prompt(_input()).user_prompt
        assert "[Turn 0] Maya Chen (NPC), opening line: Tell me about a project." in up
        assert "[Turn 1] Player: I cut checkout latency in half." in up
        assert "[Turn 1] Maya Chen (NPC): I'm not convinced yet." in up
        assert "  NPC signal: npc_skeptical" in up
        # No bare, ownerless lines.
        assert "[Rubric '" not in up and "[Flags]" not in up and "Npc" not in up

    def test_the_turn_notes_are_left_out(self):
        """The bands are judged from the player's own lines (#580). In the D-05
        replay the turn model's notes credited the player with the NPC's words
        and praised a grammar slip, and the debrief copied them; the engine
        still adds their net to each banded score."""
        bundle = compose_debrief_prompt(_input())
        up, sp = bundle.user_prompt, bundle.system_prompt
        assert "Note on the player's line" not in up
        for text in ("Named a figure.", "No reflection yet.", "Invented id.", "experience_gap"):
            assert text not in up
        assert up.startswith("SESSION TRANSCRIPT:\n\n[Turn 0]")
        assert "RUBRIC OBSERVATIONS" not in up
        assert "Notes on the player's line" not in sp
        # The NPC's signals are still there, as the character's.
        assert "  NPC signal: npc_skeptical" in up

    def test_the_npcs_reactions_are_framed_as_the_characters(self):
        sp = compose_debrief_prompt(_input()).system_prompt
        assert "Its doubts, objections and moods are the character's, not mistakes by the player" in sp
        assert "lines marked NPC signal are the character's reactions." in sp


class TestDebriefPromptWithoutRubric:
    def test_scores_and_schema_as_before(self):
        bundle = compose_debrief_prompt(_input(rubric=False, rubric_dimension_names={}))
        sp = bundle.system_prompt
        assert "DIMENSION SCORES (computed from per-turn rubric observations):\n\n  specificity (specificity): 52/100" in sp
        assert "RUBRIC —" not in sp
        quoted = json.loads(sp[sp.index("{", sp.index("OUTPUT SCHEMA")):])
        assert quoted == DEBRIEF_NARRATIVE_SCHEMA

    def test_every_note_is_kept_under_its_written_id(self):
        """The scores the prompt shows come from the notes, which are their evidence."""
        bundle = compose_debrief_prompt(_input(rubric=False))
        up = bundle.user_prompt
        assert up.startswith("SESSION TRANSCRIPT WITH RUBRIC OBSERVATIONS:\n\n")
        assert "  Note on the player's line, specificity (+2): Named a figure." in up
        assert "  Note on the player's line, experience_gap (-2): Invented id." in up
        assert "  Note on the player's line, Self Awareness: No reflection yet." in up
        assert (
            "Notes on the player's line were written during the conversation and may be "
            "wrong: check them against the transcript."
        ) in bundle.system_prompt

    def test_notes_on_the_opening_are_left_out(self):
        turns = [DebriefTurnRecord(turn_number=0, role="npc_opening", content="Hi.", rubric_observations=[
            {"rubric_id": "specificity", "observation": "Nothing to judge yet."},
        ])]
        up = compose_debrief_prompt(_input(rubric=False, turns=turns)).user_prompt
        assert "Nothing to judge yet." not in up

    def test_no_npc_name_reads_npc(self):
        up = compose_debrief_prompt(_input(rubric=False, npc_name=None)).user_prompt
        assert "[Turn 1] NPC: I'm not convinced yet." in up
        assert "[Turn 0] NPC, opening line:" in up

    def test_malformed_notes_are_skipped(self):
        turns = [DebriefTurnRecord(turn_number=1, role="npc", content="Hm.", rubric_observations=[
            "not a dict", {"rubric_id": 3, "observation": "x"}, {"rubric_id": "a"},
            {"rubric_id": "b", "observation": "ok", "score_delta": True},
        ])]
        up = compose_debrief_prompt(_input(rubric=False, turns=turns)).user_prompt
        assert up.count("Note on the player's line") == 1
        assert "  Note on the player's line, b: ok" in up
