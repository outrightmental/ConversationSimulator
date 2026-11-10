"""What counts as an NPC repeat (issue #580, P2).

On the starter model Ray ended two turns running with the same question, word
for word, and said "We do have new tires on hand" three turns running; Diane's
question from her first turn came back in her third. These tests pin what
counts as a repeat of one of the NPC's last two lines (a 6-word run, the same
4+ word closing question, trigram similarity above 0.5), which earlier lines
are read, and how two replies are ranked.
"""
import pytest

from convsim_prompt.repetition import (
    GUARD_WINDOW,
    QUESTION,
    REPEAT_RUN_WORDS,
    RUN,
    SAME_QUESTION_MIN_WORDS,
    SIMILAR,
    SIMILARITY_THRESHOLD,
    RepetitionMatch,
    RepetitionReport,
    check_repetition,
    ending_question,
    less_repetitive,
    shared_runs,
    trigram_similarity,
    words,
)

# Verbatim from the issue #580 transcripts.
RAY_T3 = (
    "That's a solid offer, and I see your point. Let me check if we can make it work. "
    "What's the smallest you'd be open to for the car?"
)
RAY_T4 = (
    "I hear you, and I respect that. We do have new tires on hand, which adds value. "
    "What's the smallest you'd be open to for the car?"
)
DIANE_T1 = (
    "Thank you for sharing those accomplishments. "
    "What specific metrics or outcomes have you observed from your work?"
)
DIANE_T3 = (
    "I appreciate the context. What specific metrics or outcomes have you observed "
    "that show the impact on the team?"
)


class TestWords:
    def test_words_fold_case_apostrophes_and_punctuation(self):
        assert words("What’s the SMALLEST you'd be open to?") == [
            "whats", "the", "smallest", "youd", "be", "open", "to",
        ]
        assert words("¿Te gustaría un café?") == ["te", "gustaría", "un", "café"]
        assert words("") == [] and words(None) == []  # type: ignore[arg-type]

    def test_shared_runs_are_maximal_and_do_not_overlap(self):
        a = words("we do have new tires on hand so that could be nice")
        b = words("honestly we do have new tires on hand today")
        assert shared_runs(a, b, 6) == [["we", "do", "have", "new", "tires", "on", "hand"]]
        assert shared_runs(a, b, 8) == []
        assert shared_runs(["x", "y", "z"], ["x", "y", "z", "x", "y", "z"], 2) == [["x", "y", "z"]]

    def test_ending_question_is_the_last_sentence(self):
        assert ending_question(RAY_T4) == tuple(words("What's the smallest you'd be open to for the car?"))
        assert ending_question("Okay. That works for me.") is None
        assert ending_question("The total is 8.50 euros, okay?") == ("the", "total", "is", "8", "50", "euros", "okay")
        assert ending_question("¿Algo más?”") == ("algo", "más")

    def test_trigram_similarity(self):
        a = words("hola que te pongo")
        b = words("hola que te pongo hoy")
        assert trigram_similarity(a, b) == pytest.approx(2 / 3)
        assert trigram_similarity(a, a) == 1.0
        assert trigram_similarity(["sí", "claro"], ["sí", "claro"]) == 0.0
        assert trigram_similarity(a, []) == 0.0


class TestCheckRepetition:
    def test_rays_repeated_closing_question_is_caught_twice_over(self):
        report = check_repetition(RAY_T4, [RAY_T3])
        assert report.flagged
        kinds = {m.kind for m in report.matches}
        # The 10-word question is a 6+ word run and the same closing question.
        assert kinds == {RUN, QUESTION}
        assert report.longest_run == 10
        assert report.against == (0,)

    def test_a_run_from_the_line_before_the_previous_one_counts(self):
        """Diane's T1 question came back in T3, with T2 in between."""
        report = check_repetition(DIANE_T3, ["Where does that number come from?", DIANE_T1])
        assert report.flagged
        assert [m.kind for m in report.matches] == [RUN]
        assert report.matches[0].against == 1
        assert report.matches[0].words == tuple(words("What specific metrics or outcomes have you observed"))
        assert report.against == (1,)

    def test_only_the_last_two_lines_are_read(self):
        assert GUARD_WINDOW == 2
        older = ["Fine.", "Sounds good to me.", DIANE_T1]
        assert not check_repetition(DIANE_T3, older).flagged
        assert check_repetition(DIANE_T3, older[1:]).flagged

    def test_run_boundary_is_six_words(self):
        assert REPEAT_RUN_WORDS == 6
        prev = "Well, we do have new tires and a clean history."
        five = "Honestly, we do have new tires installed."
        six = "Honestly, we do have new tires and more."
        assert not check_repetition(five, [prev], similarity=False).flagged
        assert check_repetition(six, [prev], similarity=False).longest_run == 6

    def test_closing_question_counts_from_four_words_and_only_against_the_previous_line(self):
        assert SAME_QUESTION_MIN_WORDS == 4
        prev = "That is our best price. Does that work?"
        line = "I can include mats. Does that work?"
        assert not check_repetition(line, [prev]).flagged  # three words: a tic
        prev4 = "That is our best price. Does that work today?"
        line4 = "I can include floor mats as well. Does that work today?"
        report = check_repetition(line4, [prev4])
        assert [m.kind for m in report.matches] == [QUESTION]
        assert report.matches[0].words == ("does", "that", "work", "today")
        # The same question two lines back is not "the previous line's".
        assert not check_repetition(line4, ["Okay then.", prev4]).flagged

    def test_a_short_near_copy_is_caught_by_similarity(self):
        prev = "¡Hola! ¿Qué te pongo hoy?"
        line = "¡Hola! ¿Qué te pongo?"
        report = check_repetition(line, [prev])
        assert [m.kind for m in report.matches] == [SIMILAR]
        assert report.similarity == pytest.approx(2 / 3)
        assert not check_repetition(line, [prev], similarity=False).flagged

    def test_similarity_must_be_above_the_threshold(self):
        assert SIMILARITY_THRESHOLD == 0.5
        # a b c d vs a b c x: one shared trigram of three: 1/3.
        assert not check_repetition("one two three four", ["one two three five"]).flagged
        # Exactly one half is not above it.
        half = check_repetition("one two three four", ["one two three four five six"])
        assert trigram_similarity(words("one two three four"), words("one two three four five six")) == 0.5
        assert not half.flagged

    def test_lines_under_four_words_are_not_judged_by_similarity(self):
        assert not check_repetition("Sí, claro, adelante.", ["Sí, claro, adelante."]).flagged

    def test_a_fresh_reply_is_not_flagged(self):
        report = check_repetition(
            "Twelve-five is a fair number, but I would need you to sign today.",
            [RAY_T4, RAY_T3],
        )
        assert report == RepetitionReport()
        assert not report.flagged and report.describe() == ""

    def test_empty_line_or_no_history_is_never_a_repeat(self):
        assert not check_repetition("", [RAY_T3]).flagged
        assert not check_repetition(RAY_T4, []).flagged
        assert not check_repetition(RAY_T4, ["", "   "]).flagged

    def test_switches_turn_each_test_off(self):
        assert not check_repetition(RAY_T4, [RAY_T3], runs=False, question=False).flagged
        only_runs = check_repetition(RAY_T4, [RAY_T3], question=False, similarity=False)
        assert {m.kind for m in only_runs.matches} == {RUN}

    def test_describe_names_what_repeated_without_quoting_it(self):
        text = check_repetition(DIANE_T3, ["Where does that number come from?", DIANE_T1]).describe()
        assert text == "shares a 8-word run with the NPC line before the previous one"
        assert "metrics" not in text
        q = RepetitionMatch(kind=QUESTION, against=0, words=("a", "b", "c", "d"))
        assert q.describe() == "ends with the same 4-word question as the previous NPC line"
        s = RepetitionMatch(kind=SIMILAR, against=0, similarity=0.6667)
        assert s.describe() == "has trigram similarity 0.67 with the previous NPC line"


class TestLessRepetitive:
    def test_a_reply_that_does_not_repeat_beats_one_that_does(self):
        flagged = check_repetition(RAY_T4, [RAY_T3])
        clean = check_repetition("Let me talk to my manager about twelve-five.", [RAY_T3])
        assert less_repetitive(clean, flagged)
        assert not less_repetitive(flagged, clean)

    def test_a_tie_keeps_the_first_reply(self):
        flagged = check_repetition(RAY_T4, [RAY_T3])
        assert not less_repetitive(flagged, flagged)
        assert not less_repetitive(RepetitionReport(), RepetitionReport())

    def test_fewer_matches_then_a_shorter_run_then_lower_similarity(self):
        both = check_repetition(RAY_T4, [RAY_T3])  # run + question
        run_only = RepetitionReport(matches=(RepetitionMatch(kind=RUN, against=0, words=tuple("abcdefghij")),))
        assert less_repetitive(run_only, both)
        short = RepetitionReport(matches=(RepetitionMatch(kind=RUN, against=0, words=tuple("abcdef")),))
        assert less_repetitive(short, run_only)
        low = RepetitionReport(matches=(RepetitionMatch(kind=SIMILAR, against=0, similarity=0.55),))
        high = RepetitionReport(matches=(RepetitionMatch(kind=SIMILAR, against=0, similarity=0.9),))
        assert less_repetitive(low, high) and not less_repetitive(high, low)
