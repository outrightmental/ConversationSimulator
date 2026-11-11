"""How the debrief judges the player (issue #580, the D-05 replay's debriefs).

On Qwen3-4B every replayed debrief banded every dimension high although each
scripted player had deliberate weak moments the rubric's own low and medium
descriptions name; missed_opportunities was empty in all of them although the
players left the NPC's questions unanswered; and strengths credited the
player with what the NPC had said. These tests pin the prompt-composer half
of the fix:

  - missed_opportunities is required and generated first, before the bands,
    and the lists are capped to fit the debrief's output budget;
  - the rubric block keeps a dimension out of high when any player line
    matches its low or medium description;
  - HOW TO JUDGE lists the missed questions and slips, has every strength and
    improvement quote the player's own words from a turn, and forbids
    suggesting what the player already did or inventing a weakness;
  - an NPC line that closes on a question (its last sentence, or the one
    before) is marked with it and the turn of the player's next line;
    nothing decides whether the player answered.
"""
import json

import pytest

from convsim_prompt import (
    DEBRIEF_NARRATIVE_SCHEMA,
    DEBRIEF_SYSTEM_PREAMBLE,
    DebriefComposerInput,
    DebriefTurnRecord,
    build_debrief_narrative_schema,
    compose_debrief_prompt,
)
from convsim_prompt.debrief_composer import _closing_question
from _helpers import make_interview_rubric

_NARRATIVE = {
    "missed_opportunities": ["Turn 2: you did not say how you measured it."],
    "summary": "You gave one concrete example.",
    "strengths": ['Turn 1: "I cut checkout latency in half" names a result.'],
    "improvements": ['Turn 2: "I just care" is generic; name an incident.'],
    "turning_points": [{"turn_number": 1, "description": "A specific example.", "impact": "positive"}],
    "replay_suggestions": ["Lead with the result."],
}


def _turns(*lines):
    """Records from (turn, role, content) triples."""
    return [DebriefTurnRecord(turn_number=n, role=r, content=c) for n, r, c in lines]


def _input(rubric: bool = True, **overrides) -> DebriefComposerInput:
    values = dict(
        session_id="sess-1",
        scenario_id="behavioral_interview",
        scenario_title="Behavioral Interview",
        player_role_label="Candidate",
        outcome="player_exit",
        total_turns=2,
        final_state={"trust": 55},
        scores={"specificity": 52.0},
        turns=_turns(
            (0, "npc_opening", "Thanks for coming in. Tell me about a project?"),
            (1, "player", "I cut checkout latency in half. Want the numbers?"),
            (1, "npc", "I'm not convinced yet. How did you measure it?"),
            (2, "player", "Honestly, I just really care about quality."),
            (2, "npc", "Which part was yours? Take your time."),
            (3, "player", "Sure."),
            (3, "npc", "What would your last manager say about you?"),
        ),
        rubric_dimensions=list(make_interview_rubric().dimensions) if rubric else [],
        npc_name="Maya Chen",
    )
    values.update(overrides)
    return DebriefComposerInput(**values)


def _block(text: str, start: str) -> str:
    """The ``---``-separated section of a prompt that starts with ``start``."""
    section = text[text.index(start):]
    return section.split("\n\n---\n\n", 1)[0]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_missed_opportunities_are_required_and_generated_first(self):
        """Optional, llama.cpp's grammar wrote them last, and they were always empty."""
        assert list(DEBRIEF_NARRATIVE_SCHEMA["properties"])[0] == "missed_opportunities"
        assert DEBRIEF_NARRATIVE_SCHEMA["required"] == [
            "missed_opportunities", "summary", "strengths", "improvements",
            "turning_points", "replay_suggestions",
        ]
        # Every property is required, so the grammar writes them in this order.
        assert list(DEBRIEF_NARRATIVE_SCHEMA["properties"]) == DEBRIEF_NARRATIVE_SCHEMA["required"]
        assert "minItems" not in DEBRIEF_NARRATIVE_SCHEMA["properties"]["missed_opportunities"]

    def test_with_a_rubric_the_bands_follow_the_missed_opportunities(self):
        schema = build_debrief_narrative_schema(rubric_ids=["specificity"])
        assert schema["required"] == [
            "missed_opportunities", "dimension_bands", "summary", "strengths",
            "improvements", "turning_points", "replay_suggestions",
        ]
        assert list(schema["properties"]) == schema["required"]

    def test_the_lists_are_capped_to_fit_the_output_budget(self):
        props = DEBRIEF_NARRATIVE_SCHEMA["properties"]
        assert {k: v.get("maxItems") for k, v in props.items() if v["type"] == "array"} == {
            "missed_opportunities": 4,
            "strengths": 3,
            "improvements": 3,
            "turning_points": 3,
            "replay_suggestions": 2,
        }
        assert props["strengths"]["minItems"] == 1 and props["improvements"]["minItems"] == 1

    def test_the_descriptions_say_what_each_list_holds(self):
        props = DEBRIEF_NARRATIVE_SCHEMA["properties"]
        missed = props["missed_opportunities"]["description"]
        assert "Each NPC question the player's next line left unanswered" in missed
        assert "each slip in the player's own words (a wrong fact, a grammar mistake)" in missed
        assert "its turn" in missed
        assert "Empty only if there were none." in missed
        for key in ("strengths", "improvements"):
            assert "citing a turn and quoting the player's own words from it" in props[key]["description"]
        assert "never something the player already did" in props["improvements"]["description"]

    def test_valid_json_schema_that_enforces_order_and_caps(self):
        jsonschema = pytest.importorskip("jsonschema")
        schema = build_debrief_narrative_schema(rubric_ids=["specificity"])
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        good = {**_NARRATIVE, "dimension_bands": {"specificity": "medium"}}
        assert validator.is_valid(good)
        assert validator.is_valid({**good, "missed_opportunities": []})
        missing = {k: v for k, v in good.items() if k != "missed_opportunities"}
        assert not validator.is_valid(missing)
        assert not validator.is_valid({**good, "strengths": ["a", "b", "c", "d"]})
        assert not validator.is_valid({**good, "missed_opportunities": ["a"] * 5})
        assert not validator.is_valid({**good, "replay_suggestions": ["a", "b", "c"]})


# ---------------------------------------------------------------------------
# The rules in the prompt
# ---------------------------------------------------------------------------


class TestRules:
    def test_high_only_when_no_player_line_matches_low_or_medium(self):
        rubric = _block(compose_debrief_prompt(_input()).system_prompt, "RUBRIC —")
        assert (
            "Give high only if the high description holds across the whole conversation; if any "
            "player line matches the low or medium description, choose medium or low."
        ) in rubric
        # It comes before the dimensions it applies to.
        assert rubric.index("Give high only") < rubric.index("- specificity:")

    def test_no_band_rule_without_a_rubric(self):
        sp = compose_debrief_prompt(_input(rubric=False)).system_prompt
        assert "Give high only" not in sp

    @pytest.mark.parametrize("rubric", [True, False])
    def test_how_to_judge(self, rubric):
        sp = compose_debrief_prompt(_input(rubric=rubric)).system_prompt
        block = _block(sp, "HOW TO JUDGE:")
        assert block.splitlines() == [
            "HOW TO JUDGE:",
            "- List in missed_opportunities each \"Question to the player\" that the player's "
            "next line left unanswered, and each slip in the player's own words (a wrong fact, "
            "a grammar mistake), with its turn. Leave it empty only if there were none.",
            "- Each strength and improvement cites a turn and quotes the player's own words from "
            "that turn. Words in an NPC line are the NPC's, never the player's.",
            "- Do not suggest what the player already did, and name no weakness the transcript "
            "does not show.",
        ]
        # Right before the schema, after the rubric and the NPC framing.
        assert sp.index("HOW TO JUDGE:") > sp.index("The NPC is a character the simulator plays.")
        assert sp.index("HOW TO JUDGE:") < sp.index("OUTPUT SCHEMA")

    def test_the_rules_stay_compact(self):
        """The debrief runs on a 4B model with an 8K context: a few short lines."""
        sp = compose_debrief_prompt(_input()).system_prompt
        assert len(_block(sp, "HOW TO JUDGE:")) < 600

    def test_the_preamble_credits_the_player_only_with_their_own_lines(self):
        assert (
            "- Credit the player only with the player's own lines: what the NPC said is the "
            "NPC's, never the player's.\n"
        ) in DEBRIEF_SYSTEM_PREAMBLE
        # The line continuation no longer leaves a run of spaces in the rule.
        assert "  do not invent" not in DEBRIEF_SYSTEM_PREAMBLE
        assert "only — do not invent content" in DEBRIEF_SYSTEM_PREAMBLE

    def test_the_closing_instruction_points_at_the_rules(self):
        up = compose_debrief_prompt(_input()).user_prompt
        last = up.rsplit("\n\n", 1)[1]
        assert last.startswith(
            "Generate a coaching debrief in the JSON format specified above, following "
            "HOW TO JUDGE. Reference specific turn numbers when citing transcript evidence, "
            "and quote only the player's own words as theirs."
        )
        assert "do not make claims about real-world performance or outcomes" in last

    def test_the_schema_in_the_prompt_is_the_one_sent(self):
        sp = compose_debrief_prompt(_input()).system_prompt
        quoted = json.loads(sp[sp.index("{", sp.index("OUTPUT SCHEMA")):])
        assert quoted == build_debrief_narrative_schema(rubric_ids=["specificity", "self_awareness"])


# ---------------------------------------------------------------------------
# The transcript marks each question the player is left to answer
# ---------------------------------------------------------------------------


class TestQuestionMarkers:
    def test_an_npc_question_names_the_players_next_turn(self):
        up = compose_debrief_prompt(_input()).user_prompt
        assert (
            "[Turn 1] Maya Chen (NPC): I'm not convinced yet. How did you measure it?\n"
            "  Question to the player (their next line is Turn 2): \"How did you measure it?\"\n"
            "[Turn 2] Player: Honestly, I just really care about quality."
        ) in up

    def test_the_openings_question_is_for_turn_1(self):
        up = compose_debrief_prompt(_input()).user_prompt
        assert (
            "[Turn 0] Maya Chen (NPC), opening line: Thanks for coming in. Tell me about a project?\n"
            "  Question to the player (their next line is Turn 1): \"Tell me about a project?\""
        ) in up

    def test_a_question_the_line_goes_on_past_is_marked(self):
        up = compose_debrief_prompt(_input()).user_prompt
        assert (
            "[Turn 2] Maya Chen (NPC): Which part was yours? Take your time.\n"
            "  Question to the player (their next line is Turn 3): \"Which part was yours?\"\n"
            "[Turn 3] Player: Sure."
        ) in up

    def test_the_d05_question_before_a_short_follow_on(self):
        """the_ask-run2: Jordan's question, then a sentence; the player asks their own instead."""
        turns = _turns(
            (2, "player", "What's the paper you're reading?"),
            (2, "npc", "I'm writing about green corridors and songbirds. What's your favorite "
                       "part of the problem set? Maybe we could swap notes."),
            (3, "player", "Wait, that's really cool. How did you end up researching that?"),
        )
        up = compose_debrief_prompt(_input(turns=turns, npc_name="Jordan Chen")).user_prompt
        assert (
            "Maybe we could swap notes.\n"
            "  Question to the player (their next line is Turn 3): "
            "\"What's your favorite part of the problem set?\"\n"
            "[Turn 3] Player: Wait, that's really cool."
        ) in up

    def test_the_last_line_has_no_marker_when_no_player_line_follows(self):
        up = compose_debrief_prompt(_input()).user_prompt
        assert "[Turn 3] Maya Chen (NPC): What would your last manager say about you?" in up
        assert "What would your last manager say about you?\"" not in up
        assert up.count("Question to the player") == 3

    def test_player_questions_are_not_marked(self):
        up = compose_debrief_prompt(_input()).user_prompt
        assert "Want the numbers?\"" not in up

    def test_the_marker_comes_before_the_notes_and_signals(self):
        turns = _turns((1, "player", "I cut it in half."))
        turns.append(DebriefTurnRecord(
            turn_number=1, role="npc", content="How did you measure it?",
            rubric_observations=[{"rubric_id": "specificity", "observation": "A figure.", "score_delta": 2}],
            event_flags=["npc_skeptical"],
        ))
        turns += _turns((2, "player", "With p95 latency."))
        # Notes are in a debrief's transcript only without a rubric.
        up = compose_debrief_prompt(_input(rubric=False, turns=turns)).user_prompt
        assert (
            "[Turn 1] Maya Chen (NPC): How did you measure it?\n"
            "  Question to the player (their next line is Turn 2): \"How did you measure it?\"\n"
            "  Note on the player's line, specificity (+2): A figure.\n"
            "  NPC signal: npc_skeptical\n"
        ) in up
        up = compose_debrief_prompt(_input(turns=turns)).user_prompt
        assert (
            "  Question to the player (their next line is Turn 2): \"How did you measure it?\"\n"
            "  NPC signal: npc_skeptical\n"
        ) in up

    def test_the_same_markers_without_a_rubric_or_a_name(self):
        up = compose_debrief_prompt(_input(rubric=False, npc_name=None)).user_prompt
        assert (
            "[Turn 1] NPC: I'm not convinced yet. How did you measure it?\n"
            "  Question to the player (their next line is Turn 2): \"How did you measure it?\""
        ) in up
        assert up.count("Question to the player") == 3

    def test_a_spanish_question(self):
        turns = _turns(
            (4, "npc", "¡Perfecto! Un cruasán, entonces. ¿Quieres algo más para beber?"),
            (5, "player", "¿Usted es de Madrid?"),
        )
        up = compose_debrief_prompt(_input(turns=turns)).user_prompt
        assert (
            "  Question to the player (their next line is Turn 5): "
            "\"¿Quieres algo más para beber?\""
        ) in up


class TestClosingQuestion:
    @pytest.mark.parametrize("line, question", [
        ("How did you measure it?", "How did you measure it?"),
        ("Haha, that's the one. I counted goldfinches last week. How'd your problem set go?",
         "How'd your problem set go?"),
        ("Oh, really? I study birds. What do you think about that?", "What do you think about that?"),
        # Lower case after the dots: the same sentence goes on.
        ("Fair enough... so what now?", "Fair enough... so what now?"),
        ("Fair enough... So what now?", "So what now?"),
        ("It costs 1.80 euros, okay?", "It costs 1.80 euros, okay?"),
        ("You're citing market data — where did you get that figure?",
         "You're citing market data — where did you get that figure?"),
        ("¡Ah, interesante! Soy de Sevilla. ¿Y tú, ¿de dónde eres?", "¿Y tú, ¿de dónde eres?"),
        ("He said, \"Are you sure?\"", "He said, \"Are you sure?"),
        ("\"Are you sure?\"", "Are you sure?"),
        ("Right? ", "Right?"),
        ("わかりました。コーヒーはいかがですか？", "コーヒーはいかがですか？"),
        ("هل تريد قهوة؟", "هل تريد قهوة؟"),
        ("  Two  spaces.   And  then?  ", "And then?"),
        ('She said "Hi." Are you ok?', "Are you ok?"),
    ])
    def test_the_last_sentence_when_it_asks(self, line, question):
        assert _closing_question(line) == question

    @pytest.mark.parametrize("line, question", [
        # Lines of the D-05 replay (issue #580) that the end-of-line rule
        # left unmarked, although the player had the question to answer.
        ("The one near me has seen a real increase this spring. What's your favorite part of "
         "the problem set? Maybe we could swap notes.",
         "What's your favorite part of the problem set?"),
        ("Great, cash today — that makes it easier. Since you're not looking at a warranty, how "
         "about this: I'll take 14,200 out the door? That's still under your comps and keeps "
         "the tires in good shape for you.",
         "Since you're not looking at a warranty, how about this: I'll take 14,200 out the door?"),
        # The NPC answers it itself: marked all the same, and the model judges.
        ("¡Claro! Vamos a hablar más despacio. ¿Quieres que te lo repita otra vez? Aquí va: un "
         "cruasán, 1,80 €.", "¿Quieres que te lo repita otra vez?"),
        ("Is that so? Let's move on.", "Is that so?"),
        ("Coffee? Tea? Water.", "Tea?"),
        ("What's that? I see", "What's that?"),
        ("元気ですか？私は元気です。", "元気ですか？"),
        ("Bueno… ¿y ahora? Dime.", "¿y ahora?"),
    ])
    def test_a_question_one_sentence_before_the_end(self, line, question):
        assert _closing_question(line) == question

    @pytest.mark.parametrize("line", [
        "", None, "Fine.", "Great!", "\"\"", "Really?!",
        # A question mark the sentence goes on past ends no question.
        'He asked "why?" and left.', "「元気ですか？」と聞いた。",
        # Two sentences or more after the question: the line has moved past
        # it (the D-05 replay's the_ask: Jordan echoes the lecture the player
        # named, then goes on to their own paper).
        "Oh, wait — you're in the Tuesday stats lecture? That's a common one. I've seen people "
        "skip to the end of the slides just to get that coffee.",
        "Is it? Yes. Fine.",
    ])
    def test_none_when_neither_of_the_last_two_sentences_asks(self, line):
        assert _closing_question(line) is None
