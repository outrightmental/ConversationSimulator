# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — the D-05 automated pre-check (issue #580).

``scripts/demo-gate-replay.py`` replays the five demo conversations against a
running convsim-core on the real model; its assertions live in
``scripts/demo_gate_checks.py``. A real-model replay cannot run in CI, so
these tests pin the harness instead:

  * each check, on synthetic transcripts: the issue's own failing lines are
    caught (Ray repeating his closing question, Diane saying her agenda
    aloud, Ray naming his $13,800 floor in any form, the baseline-only and
    zero-change state deltas, the invented rubric ids, a fallback debrief, a
    canned fallback turn), and the boundaries are where the issue puts them
    (a 6-word repeat, a 4-word closing question, a 5-word agenda run, a
    3-digit agenda number);
  * severities: (a), (b), (e), (f) hard and (c), (d) warnings by default,
    ``--strict`` and per-check overrides, and the exit status that follows;
  * the facts the checks read come from the files that own them: the five
    conversations from ``edition.py``, the baseline variables from
    ``scenario_state.py``, the fallback line from the prompt composer, the
    agenda, authored variables and rubric ids from each pack;
  * the scripted player turns: 5-6 per conversation, inside the player brief,
    and never quoting the NPC's hidden agenda or its numbers (or an NPC echo
    would read as a leak);
  * the replay's flow, against a scripted stand-in for the API and against an
    in-process demo-edition convsim-core on the fake runtime, whose identical
    NPC lines the repetition check must fail: it refuses an engine that is
    not the demo edition unless told otherwise, and it deletes the NPC
    relationship memory around every run (also on an interrupt or a crash)
    so that no run's prompt carries an earlier debrief.

No model and no server: the in-process app is a FastAPI TestClient.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pytest
import yaml

from convsim_core.edition import DEMO_SCENARIOS
from convsim_core.scenario_state import BASELINE_VARIABLES
from convsim_prompt.turn_output import SAFE_FALLBACK_UTTERANCE

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_PACKS = _REPO_ROOT / "packs" / "official"
_TURNS_FILE = _REPO_ROOT / "tests" / "fixtures" / "demo-gate" / "player-turns.yaml"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checks = _load("demo_gate_checks", _SCRIPTS / "demo_gate_checks.py")
replay = _load("demo_gate_replay", _SCRIPTS / "demo-gate-replay.py")

NpcLine = checks.NpcLine


def _lines(*texts: str, opening: Optional[str] = None) -> List[Any]:
    out = []
    if opening is not None:
        out.append(NpcLine(turn=0, text=opening, authored=True))
    out.extend(NpcLine(turn=i, text=t) for i, t in enumerate(texts, start=1))
    return out


# Verbatim from the issue #580 transcripts.
RAY_T3 = (
    "That's a solid offer, and I see your point. Let me check if we can make it work. "
    "We do have new tires on hand, so that could be a nice addition. What's the "
    "smallest you'd be open to for the car?"
)
RAY_T4 = (
    "I understand your offer. Let me check if we can make this work. We do have new "
    "tires on hand, so that’s a good match. What’s the smallest you’d be "
    "open to for the car?"
)
DIANE_T2 = (
    "I see the market rate. But without specific data on the cost to the company of "
    "not giving you the raise, I can't justify this request. What's the financial "
    "impact of not adjusting your compensation?"
)
DANA_SCORES = {
    "ambiguous_problem_handling": 52.0, "mistake_management": 51.0, "cultural_fit": 52.0,
    "specificity": 48.0, "self_reflection": 50.0, "problem_solving": 52.0,
    "specific_examples": 52.0,
}


def _npc_doc(rel: str) -> Dict[str, Any]:
    return yaml.safe_load((_PACKS / rel).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------


class TestWords:
    def test_case_punctuation_and_curly_apostrophes_are_ignored(self) -> None:
        assert checks.words("What’s the SMALLEST you'd be open to?") == [
            "whats", "the", "smallest", "youd", "be", "open", "to",
        ]

    def test_accented_words_stay_whole(self) -> None:
        assert checks.words("¿Te gustaría un café?") == ["te", "gustaría", "un", "café"]

    def test_shared_runs_are_maximal_and_do_not_overlap(self) -> None:
        a = checks.words("we do have new tires on hand so that could be nice")
        b = checks.words("honestly we do have new tires on hand today")
        assert checks.shared_runs(a, b, 6) == [["we", "do", "have", "new", "tires", "on", "hand"]]
        assert checks.shared_runs(a, b, 8) == []
        assert checks.shared_runs(a, [], 1) == []
        # A word sequence repeated in b is still one run of a.
        assert checks.shared_runs(["x", "y", "z"], ["x", "y", "z", "x", "y", "z"], 2) == [["x", "y", "z"]]

    def test_shared_runs_finds_every_run(self) -> None:
        a = checks.words("alpha beta gamma delta or else one two three four")
        b = checks.words("one two three four and alpha beta gamma delta")
        assert checks.shared_runs(a, b, 4) == [
            ["alpha", "beta", "gamma", "delta"], ["one", "two", "three", "four"],
        ]

    def test_ending_question_is_the_last_sentence(self) -> None:
        assert checks.ending_question(RAY_T4) == tuple(
            "whats the smallest youd be open to for the car".split()
        )
        assert checks.ending_question("Okay. That works for me.") is None
        # A decimal is not a sentence break.
        assert checks.ending_question("The total is 8.50 euros, okay?") == (
            "the", "total", "is", "8", "50", "euros", "okay",
        )

    def test_ending_question_in_spanish(self) -> None:
        line = "¡Qué bien! ¿Te gusta el cruasán? ¡Es muy popular! ¿Vives en Madrid?"
        assert checks.ending_question(line) == ("vives", "en", "madrid")
        assert checks.ending_question("¿Algo más?”") == ("algo", "más")


# ---------------------------------------------------------------------------
# (a) repetition
# ---------------------------------------------------------------------------


class TestRepetition:
    def test_ray_t4_repeats_t3(self) -> None:
        findings = checks.find_repetition(_lines("Hi there, welcome in.", RAY_T3, RAY_T4))
        assert {f.turn for f in findings} == {3}
        assert len(findings) == 2
        runs, question = findings
        assert runs.message == "repeats 3 runs (7, 9, 10 words) of the previous NPC line (turn 2)"
        assert runs.evidence.split(" / ") == [
            "let me check if we can make",
            "work we do have new tires on hand so",
            "whats the smallest youd be open to for the car",
        ]
        assert question.message == "ends with the same question as the previous NPC line (turn 2)"
        assert question.evidence == "whats the smallest youd be open to for the car"

    def test_six_words_fail_five_pass(self) -> None:
        five = _lines("one two three four five alpha", "beta one two three four five")
        six = _lines("one two three four five six alpha", "beta one two three four five six")
        assert checks.find_repetition(five) == []
        found = checks.find_repetition(six)
        assert len(found) == 1 and found[0].evidence == "one two three four five six"

    def test_insensitive_to_case_and_punctuation(self) -> None:
        found = checks.find_repetition(_lines(
            "We do have new tires on hand.", "Well -- WE DO have new tires, on hand!"
        ))
        assert len(found) == 1

    def test_opening_is_the_previous_line_of_turn_one(self) -> None:
        opening = "Hey there! So, what were you thinking? Shall we talk numbers?"
        found = checks.find_repetition(
            _lines("Sure thing. Shall we talk numbers?", opening=opening)
        )
        assert [(f.turn, "same question" in f.message) for f in found] == [(1, True)]
        assert "(turn 0)" in found[0].message

    def test_only_the_previous_line_counts(self) -> None:
        diane_t1 = "Can you quantify it? What specific metrics or outcomes have you observed?"
        diane_t3 = "Let's focus on this cycle. What specific metrics or outcomes have you observed?"
        assert checks.find_repetition(_lines(diane_t1, "Where does that number come from?", diane_t3)) == []
        assert len(checks.find_repetition(_lines(diane_t1, diane_t3))) == 2

    def test_a_different_question_and_a_repeated_greeting_pass(self) -> None:
        rosa = _lines(
            "¡Hola! Marchando un café con leche. ¿Algo para comer?",
            "¡Hola! Tenemos cruasanes y tostadas. ¿Te pongo uno?",
            opening="¡Hola! Buenos días. ¿Qué vas a tomar hoy?",
        )
        assert checks.find_repetition(rosa) == []

    def test_the_authored_opening_is_never_flagged(self) -> None:
        lines = [NpcLine(turn=0, text="Same words here in a row again ok?", authored=True)]
        assert checks.find_repetition(lines) == []

    @pytest.mark.parametrize("question", ["Okay?", "Is that right?", "¿Algo más?"])
    def test_a_short_closing_question_twice_is_not_a_repeat(self, question: str) -> None:
        lines = _lines(f"The tires are new. {question}", f"Service records are in the file. {question}")
        assert checks.find_repetition(lines) == []

    def test_a_four_word_closing_question_twice_is_a_repeat(self) -> None:
        lines = _lines(
            "The tires are new. Does that work for you?",
            "Service records are in the file. Does that work for you?",
        )
        # "does that work for you" is 5 words; a 4-word one is the boundary.
        assert len(checks.find_repetition(lines)) == 1
        four = _lines("The tires are new. Shall we talk numbers?",
                      "Records are in the file. Shall we talk numbers?")
        found = checks.find_repetition(four)
        assert [f.evidence for f in found] == ["shall we talk numbers"]
        assert checks.SAME_QUESTION_MIN_WORDS == 4

    def test_a_repeat_the_player_asked_for_is_not_judged(self) -> None:
        """spanish_coffee turn 3 asks Rosa to say it again, more slowly: a repair
        strategy the rubric rewards, which the engine does not retry either."""
        rosa = "¡Claro! Un café con leche. ¿Quieres algo para comer?"
        again = "¡Claro! Te lo repito más despacio: un café con leche. ¿Quieres algo para comer?"
        lines = _lines(rosa, again, again)
        assert {f.turn for f in checks.find_repetition(lines)} == {2, 3}
        assert {f.turn for f in checks.find_repetition(lines, repeat_requested=[2])} == {3}
        players = {1: "Quisiera un café con leche.", 2: "Perdón, ¿puede repetir más despacio?", 3: "Vale."}
        assert checks.repeat_request_turns(players) == [2]


class TestEngineAgreement:
    """Check (a) and the engine's repetition guard count a repeat the same way.

    The engine retries a reply that repeats one of the NPC's last two lines
    (issue #580); check (a) fails a line that repeats the previous one. Both
    read their words from ``convsim_prompt.repetition``, so every line check
    (a) fails is one the engine flagged and tried to replace: a D-05 failure
    on (a) means the retry did not help, never that the two disagree.
    """

    def test_the_word_functions_are_the_engines(self) -> None:
        from convsim_prompt import repetition

        assert checks.asks_for_repeat is repetition.asks_for_repeat
        assert checks.words is repetition.words
        assert checks.shared_runs is repetition.shared_runs
        assert checks.ending_question is repetition.ending_question
        assert checks.REPEAT_RUN_WORDS == repetition.REPEAT_RUN_WORDS == 6
        assert checks.SAME_QUESTION_MIN_WORDS == repetition.SAME_QUESTION_MIN_WORDS == 4

    @pytest.mark.parametrize("previous, line", [
        (RAY_T3, RAY_T4),
        ("one two three four five six alpha", "beta one two three four five six"),
        ("one two three four five alpha", "beta one two three four five"),
        ("We do have new tires on hand.", "Well -- WE DO have new tires, on hand!"),
        ("Hey there! So, what were you thinking? Shall we talk numbers?", "Sure thing. Shall we talk numbers?"),
        ("The tires are new. Okay?", "Service records are in the file. Okay?"),
        ("The tires are new. Does that work for you?", "Service records are in the file. Does that work for you?"),
        ("¡Hola! Buenos días. ¿Qué vas a tomar hoy?", "¡Hola! Marchando un café con leche. ¿Algo para comer?"),
        (DIANE_T2, "Fair enough. Walk me through the numbers again, slowly."),
    ])
    def test_every_line_check_a_fails_the_engine_flags(self, previous: str, line: str) -> None:
        from convsim_prompt.repetition import check_repetition

        failed = bool(checks.find_repetition(_lines(previous, line)))
        flagged = check_repetition(line, [previous]).flagged
        assert flagged or not failed
        # On the run and the closing question alone, the two give one verdict;
        # the engine also counts a near-copy by trigram similarity.
        assert check_repetition(line, [previous], similarity=False).flagged == failed

    def test_neither_judges_the_answer_to_a_request_for_the_line_again(self) -> None:
        """The engine leaves the repeat alone (turn_pipeline's exemption); so does (a)."""
        rosa = "¡Claro! Un café con leche. ¿Quieres algo para comer?"
        again = "¡Claro! Te lo repito más despacio: un café con leche. ¿Quieres algo para comer?"
        ask = "Perdón, no entendí bien. ¿Puede repetirlo más despacio, por favor?"
        from convsim_prompt.repetition import asks_for_repeat, check_repetition

        assert check_repetition(again, [rosa]).flagged and asks_for_repeat(ask)
        results = checks.evaluate_run(
            npc_lines=_lines(rosa, again), turn_deltas=[], debrief_status=200,
            debrief={"used_fallback": False, "scores": {"x": 50.0}}, hidden_agenda=[],
            authored_variables=[], rubric_ids=["x"], player_lines={1: "Hola.", 2: ask},
        )
        rep = next(r for r in results if r.letter == "a")
        assert rep.passed
        assert rep.detail == (
            "2 generated NPC line(s) checked; not judged: the line of turn(s) 2, "
            "where the player asked for the line again"
        )

    def test_the_checks_still_need_only_the_standard_library(self) -> None:
        """``-I -S``: no site-packages and no PYTHONPATH, so nothing installed."""
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); import demo_gate_checks, convsim_prompt; "
            "print(convsim_prompt.__file__)"
        )
        done = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", code, str(_SCRIPTS)],
            capture_output=True, text=True, timeout=60,
        )
        assert done.returncode == 0, done.stderr
        expected = _REPO_ROOT / "packages" / "prompt-composer" / "src" / "convsim_prompt" / "__init__.py"
        assert Path(done.stdout.strip()) == expected


# ---------------------------------------------------------------------------
# (b) agenda leak
# ---------------------------------------------------------------------------


class TestAgendaLeak:
    def test_diane_says_the_cost_lever_aloud(self) -> None:
        agenda = checks.hidden_agenda(_npc_doc("difficult-conversations/npcs/skeptical_manager.yaml"))
        found = checks.find_agenda_leaks(_lines("Walk me through it.", DIANE_T2), agenda)
        assert len(found) == 1
        assert found[0].turn == 2
        assert "agenda item 2" in found[0].message
        assert "cost to the company of not giving" in found[0].evidence

    def test_ray_names_his_floor(self) -> None:
        agenda = checks.hidden_agenda(_npc_doc("everyday-negotiation/npcs/car_dealer.yaml"))
        found = checks.find_agenda_leaks(
            _lines("Honestly, thirteen-eight is my real minimum on this unit."), agenda
        )
        # The agenda words, and the floor itself in dealer shorthand.
        assert [f.evidence for f in found] == ["real minimum on this unit", "thirteen-eight"]
        assert found[1].message == "says the number 13,800 of hidden agenda item 3 aloud"

    def test_five_words_fail_four_pass(self) -> None:
        agenda = ["alpha beta gamma delta epsilon zeta"]
        assert checks.find_agenda_leaks(_lines("so alpha beta gamma delta, right"), agenda) == []
        assert len(checks.find_agenda_leaks(_lines("so alpha beta gamma delta epsilon"), agenda)) == 1

    def test_runs_do_not_span_agenda_items(self) -> None:
        agenda = ["one two three", "four five six"]
        assert checks.find_agenda_leaks(_lines("one two three four five six"), agenda) == []

    def test_the_authored_opening_is_not_checked(self) -> None:
        agenda = ["alpha beta gamma delta epsilon"]
        lines = _lines("Nothing to see.", opening="alpha beta gamma delta epsilon")
        assert checks.find_agenda_leaks(lines, agenda) == []


class TestSecretNumbers:
    """(b) also catches a number from the agenda: Ray's $13,800 floor."""

    ray = checks.hidden_agenda(_npc_doc("everyday-negotiation/npcs/car_dealer.yaml"))

    def test_rays_floor_is_his_only_secret_number(self) -> None:
        assert checks.secret_numbers(self.ray) == {13800: (3, "13,800")}

    @pytest.mark.parametrize("line, evidence", [
        ("Look, I can't go under $13,800 on this one.", "13,800"),
        ("Best I can do is 13800 out the door.", "13800"),
        ("Final answer: $13,800.00, tires included.", "13,800.00"),
        ("Call it 13.8k and we shake on it.", "13.8k"),
        ("Thirteen thousand eight hundred, and that's my number.", "thirteen thousand eight hundred"),
        ("Thirteen thousand, eight hundred. Take it or leave it.", "thirteen thousand eight hundred"),
        ("I could maybe do thirteen-eight if you sign today.", "thirteen-eight"),
    ])
    def test_the_floor_in_any_form_fails(self, line: str, evidence: str) -> None:
        found = checks.find_agenda_leaks(_lines(line), self.ray)
        assert [f.evidence for f in found] == [evidence]
        assert found[0].message == "says the number 13,800 of hidden agenda item 3 aloud"
        assert found[0].turn == 1

    @pytest.mark.parametrize("line", [
        "Thirteen-nine with new tires, and we have a deal.",
        "I can do $13,900 out the door.",
        "Fourteen-two is where comps like this sell.",
        "Thirteen thousand six hundred? That's too low for me.",
        "It's $1,380 for the extended warranty.",
        "Two other buyers looked at it, and 138 people viewed the listing.",
        "The total is 8.50 for the oil change.",
    ])
    def test_other_numbers_pass(self, line: str) -> None:
        assert checks.find_agenda_leaks(_lines(line), self.ray) == []

    def test_the_number_is_reported_once_per_line(self) -> None:
        line = "13,800. Yes, $13,800, thirteen thousand eight hundred."
        assert len(checks.find_agenda_leaks(_lines(line), self.ray)) == 1

    def test_small_agenda_numbers_are_not_secrets(self) -> None:
        agenda = ["She has 2 offers and wants 15 percent more within 90 days"]
        assert checks.secret_numbers(agenda) == {}
        assert checks.find_agenda_leaks(_lines("Two offers, 15 percent, 90 days."), agenda) == []

    def test_a_three_digit_agenda_number_is_a_secret(self) -> None:
        agenda = ["Her real budget ceiling is 450 euros a month"]
        assert checks.secret_numbers(agenda) == {450: (1, "450")}
        found = checks.find_agenda_leaks(_lines("I can stretch to four hundred and fifty."), agenda)
        assert [f.evidence for f in found] == ["four hundred and fifty"]

    @pytest.mark.parametrize("text, expected", [
        ("$13,800", [13800]),
        ("13.800 euros", [13800]),
        ("8.50", [8]),
        ("p95 went from four seconds to three hundred milliseconds", [4, 300]),
        ("fifteen hundred", [1500]),
        ("a hundred and ten percent", [110]),
        ("twenty-five", [25]),
        ("five, six hundred", [5, 600]),
        ("one hundred thousand", [100000]),
        ("thirteen thousand eight hundred and fifty", [13850]),
        ("13 km away", [13]),
    ])
    def test_numbers_in(self, text: str, expected: List[int]) -> None:
        assert sorted(v for v, _ in checks.numbers_in(text)) == sorted(expected)

    def test_numbers_in_reads_dealer_shorthand_beside_the_words(self) -> None:
        # The words alone read 13 and 8; only the shorthand reads 13,800.
        assert sorted(v for v, _ in checks.numbers_in("thirteen-eight")) == [8, 13, 13800]


# ---------------------------------------------------------------------------
# (c) authored state, (d) rubric ids, (e) debrief
# ---------------------------------------------------------------------------


class TestAuthoredState:
    def test_baseline_only_deltas_fail(self) -> None:
        passed, findings, _ = checks.check_authored_state(
            [(1, {"trust": 10, "patience": -5}), (2, {"trust": 10})],
            ["deal_progress", "leverage"],
        )
        assert not passed
        assert "deal_progress, leverage" in findings[0].message
        assert "patience x1, trust x2" in findings[0].message

    def test_one_authored_move_passes(self) -> None:
        passed, findings, detail = checks.check_authored_state(
            [(1, {"trust": 10}), (2, {"evidence_strength": 10})],
            ["evidence_strength", "case_clarity"],
        )
        assert passed and findings == []
        assert detail == "moved: evidence_strength +10 (turn 2)"

    def test_no_turns_fail(self) -> None:
        passed, _, _ = checks.check_authored_state([], ["impression"])
        assert not passed

    def test_a_zero_change_is_not_a_move(self) -> None:
        # The engine reports an authored variable with 0 when the model
        # proposed 0 or the move was clamped at a bound.
        passed, findings, _ = checks.check_authored_state(
            [(1, {"deal_progress": 0, "trust": 10}), (2, {"deal_progress": 0, "leverage": 0})],
            ["deal_progress", "leverage"],
        )
        assert not passed
        assert "reported with no change: deal_progress x2, leverage x1" in findings[0].message
        assert "moved instead: trust x1" in findings[0].message

    def test_a_zero_baseline_change_is_not_listed_as_moved(self) -> None:
        passed, findings, _ = checks.check_authored_state([(1, {"trust": 0})], ["leverage"])
        assert not passed and "moved instead" not in findings[0].message

    def test_a_negative_change_is_a_move(self) -> None:
        passed, _, detail = checks.check_authored_state(
            [(1, {"deal_progress": 0}), (2, {"deal_progress": -5})], ["deal_progress"]
        )
        assert passed
        assert detail == "moved: deal_progress -5 (turn 2)"

    @pytest.mark.parametrize("value", [None, "", "n/a", False, 0.0])
    def test_a_non_numeric_or_empty_change_is_not_a_move(self, value: Any) -> None:
        passed, _, _ = checks.check_authored_state([(1, {"leverage": value})], ["leverage"])
        assert not passed

    def test_a_redeclared_baseline_is_not_authored(self) -> None:
        the_ask = yaml.safe_load(
            (_PACKS / "dating-confidence-boundaries/scenarios/the_ask.yaml").read_text(encoding="utf-8")
        )
        authored = checks.authored_variables(the_ask, BASELINE_VARIABLES)
        assert "rapport" not in authored
        assert authored == ["confidence", "jordan_interest", "jordan_comfort"]
        passed, _, _ = checks.check_authored_state([(1, {"rapport": 15})], authored)
        assert not passed


class TestRubricIds:
    rubric = ["clarity", "specificity", "rapport", "self_awareness"]

    def test_invented_ids_fail(self) -> None:
        passed, findings, detail = checks.check_rubric_ids({"scores": DANA_SCORES}, self.rubric)
        assert not passed
        assert findings[0].message == "6 of 7 scored id(s) are not in the rubric"
        assert "specificity" not in findings[0].evidence.split(", ")
        assert detail.endswith("matched: specificity")

    def test_rubric_ids_pass(self) -> None:
        passed, findings, detail = checks.check_rubric_ids(
            {"scores": {"clarity": 55.0, "specificity": 61.0}}, self.rubric
        )
        assert passed and findings == []
        assert detail == "scored: clarity, specificity"

    @pytest.mark.parametrize("debrief", [None, {}, {"scores": {}}])
    def test_no_scores_fail(self, debrief: Optional[Mapping[str, Any]]) -> None:
        passed, findings, _ = checks.check_rubric_ids(debrief, self.rubric)
        assert not passed and "no rubric dimension" in findings[0].message


class TestDebrief:
    def test_generated_without_fallback_passes(self) -> None:
        assert checks.check_debrief(200, {"used_fallback": False})[0]

    @pytest.mark.parametrize("status, body, needle", [
        (200, {"used_fallback": True}, "template fallback"),
        (200, {}, "does not say"),
        (500, None, "HTTP 500"),
        (None, None, "no response"),
    ])
    def test_failures(self, status: Optional[int], body: Any, needle: str) -> None:
        passed, findings, _ = checks.check_debrief(status, body, error="boom")
        assert not passed and needle in findings[0].message


class TestTurnFallback:
    canned = SAFE_FALLBACK_UTTERANCE

    def test_a_turn_flagged_as_fallback_fails(self) -> None:
        found = checks.find_fallback_turns([(1, False), (2, True), (3, None)])
        assert [f.turn for f in found] == [2]
        assert "timing.fallback true" in found[0].message

    def test_the_canned_line_fails_even_without_the_flag(self) -> None:
        lines = _lines("Sure, the tires are new.", self.canned.upper())
        found = checks.find_fallback_turns([(1, None), (2, None)], lines, fallback_utterance=self.canned)
        assert [f.turn for f in found] == [2]
        assert "canned safe fallback line" in found[0].message

    def test_a_turn_is_reported_once(self) -> None:
        lines = _lines(self.canned)
        found = checks.find_fallback_turns([(1, True)], lines, fallback_utterance=self.canned)
        assert len(found) == 1

    def test_ordinary_turns_and_the_opening_pass(self) -> None:
        lines = _lines("Could you repeat that? The line was bad.", opening=self.canned)
        assert checks.find_fallback_turns([(1, False)], lines, fallback_utterance=self.canned) == []

    def test_a_fallback_turn_fails_the_run(self) -> None:
        results = checks.evaluate_run(
            npc_lines=_lines("Fourteen-nine, with the tires.", self.canned),
            turn_deltas=[(1, {"leverage": 5}), (2, {})],
            debrief_status=200,
            debrief={"used_fallback": False, "scores": {"clarity": 50.0}},
            hidden_agenda=[],
            authored_variables=["leverage"],
            rubric_ids=["clarity"],
            turn_fallbacks=[(1, False), (2, True)],
            fallback_utterance=self.canned,
        )
        by_letter = {r.letter: r for r in results}
        assert by_letter["f"].status == "FAIL"
        assert [f.turn for f in by_letter["f"].findings] == [2]
        assert checks.run_verdict(results) == "fail"


# ---------------------------------------------------------------------------
# Severity and verdicts
# ---------------------------------------------------------------------------


class TestSeverity:
    def test_defaults(self) -> None:
        assert checks.resolve_severity() == {
            "a": "hard", "b": "hard", "c": "warn", "d": "warn", "e": "hard", "f": "hard",
        }

    def test_strict_makes_everything_hard(self) -> None:
        sev = checks.resolve_severity(strict=True, warn=["a"])
        assert set(sev.values()) == {"hard"}

    def test_per_check_overrides_by_letter_or_name(self) -> None:
        sev = checks.resolve_severity(hard=["authored_state"], warn=["a"])
        assert sev["c"] == "hard" and sev["a"] == "warn" and sev["d"] == "warn"

    def test_conflicts_and_unknown_checks_are_errors(self) -> None:
        with pytest.raises(ValueError, match="both hard and warn"):
            checks.resolve_severity(hard=["c"], warn=["authored_state"])
        with pytest.raises(ValueError, match="unknown check"):
            checks.resolve_severity(hard=["z"])

    def _results(self, failing: str, severity: Optional[Dict[str, str]] = None):
        return [
            checks.CheckResult(
                letter=c.letter, name=c.name, title=c.title, scope=c.scope,
                severity=(severity or checks.DEFAULT_SEVERITY)[c.letter],
                passed=c.letter not in failing,
            )
            for c in checks.CHECKS
        ]

    def test_verdicts(self) -> None:
        assert checks.run_verdict(self._results("")) == "pass"
        assert checks.run_verdict(self._results("cd")) == "warn"
        assert checks.run_verdict(self._results("a")) == "fail"
        assert checks.run_verdict(self._results("cd", checks.resolve_severity(strict=True))) == "fail"
        assert checks.run_verdict(self._results(""), error="turn 2: HTTP 504") == "fail"

    def test_status_labels(self) -> None:
        by_letter = {r.letter: r for r in self._results("ac")}
        assert by_letter["a"].status == "FAIL"
        assert by_letter["c"].status == "warn"
        assert by_letter["b"].status == "pass"
        assert by_letter["a"].to_dict()["status"] == "FAIL"


class TestEvaluateRun:
    def test_the_issues_used_car_run(self) -> None:
        agenda = checks.hidden_agenda(_npc_doc("everyday-negotiation/npcs/car_dealer.yaml"))
        results = checks.evaluate_run(
            npc_lines=_lines(
                "Great! The car has a clean title. What were your thoughts on the price?",
                "I see what you're saying. What's the lowest you'd be willing to go?",
                RAY_T3,
                RAY_T4,
                opening="Hey there! Welcome to Riverside Auto. Did you want to talk numbers?",
            ),
            turn_deltas=[(1, {"trust": 10}), (2, {"trust": 10, "patience": -5}),
                         (3, {"trust": 10}), (4, {"trust": 10})],
            debrief_status=200,
            debrief={"used_fallback": False, "scores": {"comprehensive_inquiry": 52.0}},
            hidden_agenda=agenda,
            authored_variables=["deal_progress", "perceived_fairness", "firmness",
                                "concession_level", "leverage"],
            rubric_ids=["clarity", "preparation", "empathy", "holding_firm", "outcome_framing"],
        )
        status = {r.letter: r.status for r in results}
        assert status == {"a": "FAIL", "b": "pass", "c": "warn", "d": "warn", "e": "pass", "f": "pass"}
        assert checks.run_verdict(results) == "fail"

    def test_a_clean_run_passes(self) -> None:
        results = checks.evaluate_run(
            npc_lines=_lines(
                "Fourteen-nine is where I can start, with the tires done.",
                "I hear you on the comps. Fourteen-five, and that is a real move.",
                opening="Hey there! Did you want to talk numbers?",
            ),
            turn_deltas=[(1, {"leverage": 10}), (2, {"deal_progress": 15})],
            debrief_status=200,
            debrief={"used_fallback": False, "scores": {"preparation": 58.0}},
            hidden_agenda=["Protect the floor price at all costs and never say it"],
            authored_variables=["deal_progress", "leverage"],
            rubric_ids=["preparation", "clarity"],
        )
        assert checks.run_verdict(results) == "pass"
        assert [r.letter for r in results] == ["a", "b", "c", "d", "e", "f"]


class TestTranscriptShape:
    def test_player_lines_from_transcript(self) -> None:
        entries = [
            {"turn_number": 0, "role": "npc_opening", "content": "Opening."},
            {"turn_number": 1, "role": "player", "content": "Player one."},
            {"turn_number": 2, "role": "npc", "content": "Reply one."},
            {"turn_number": 3, "role": "player", "content": "Player two."},
        ]
        assert checks.player_lines_from_transcript(entries) == {1: "Player one.", 2: "Player two."}
        assert replay.player_lines_of({"transcript": {"transcript_saved": True, "turns": entries}}) == {
            1: "Player one.", 2: "Player two.",
        }
        # Without a stored transcript, the lines the replay sent.
        assert replay.player_lines_of({"turns": [{"turn": 1, "player": "Hi."}]}) == {1: "Hi."}

    def test_npc_lines_from_transcript(self) -> None:
        entries = [
            {"turn_number": 2, "role": "npc", "content": "Reply one."},
            {"turn_number": 0, "role": "npc_opening", "content": "Opening."},
            {"turn_number": 1, "role": "player", "content": "Player one."},
            {"turn_number": 3, "role": "player", "content": "Player two."},
            {"turn_number": 4, "role": "npc", "content": "Reply two."},
        ]
        assert checks.npc_lines_from_transcript(entries) == [
            NpcLine(turn=0, text="Opening.", authored=True),
            NpcLine(turn=1, text="Reply one."),
            NpcLine(turn=2, text="Reply two."),
        ]


# ---------------------------------------------------------------------------
# The facts come from the files that own them
# ---------------------------------------------------------------------------


class TestSourcesOfTruth:
    def test_demo_scenarios_match_edition(self) -> None:
        assert replay.demo_scenarios() == [(s.pack_id, s.scenario_id) for s in DEMO_SCENARIOS]

    def test_baseline_variables_match_scenario_state(self) -> None:
        assert replay.baseline_variables() == list(BASELINE_VARIABLES)

    def test_safe_fallback_utterance_matches_the_prompt_composer(self) -> None:
        assert replay.safe_fallback_utterance() == SAFE_FALLBACK_UTTERANCE
        with pytest.raises(ValueError):
            checks.parse_string_constant("X = 1\n", "X")

    def test_demo_scenarios_keyword_form(self) -> None:
        src = (
            "DEMO_SCENARIOS: tuple = (\n"
            "    DemoScenario(pack_id='p.one', scenario_id='s_one'),\n"
            "    DemoScenario('p.two', 's_two'),\n"
            ")\n"
        )
        assert checks.parse_demo_scenarios(src) == [("p.one", "s_one"), ("p.two", "s_two")]
        with pytest.raises(ValueError):
            checks.parse_demo_scenarios("OTHER = 1\n")

    @pytest.mark.parametrize("pack_id, scenario_id", [(s.pack_id, s.scenario_id) for s in DEMO_SCENARIOS])
    def test_facts_load_for_every_demo_conversation(self, pack_id: str, scenario_id: str) -> None:
        facts = replay.load_scenario_facts(_PACKS, pack_id, scenario_id, list(BASELINE_VARIABLES))
        assert facts.hidden_agenda, "the NPC file has no hidden agenda to check against"
        assert facts.authored_variables, "the scenario authors no state of its own"
        assert not set(facts.authored_variables) & set(BASELINE_VARIABLES)
        assert facts.rubric_ids
        scenario = yaml.safe_load(facts.scenario_path.read_text(encoding="utf-8"))
        assert set(facts.authored_variables) <= set(scenario["state"]["variables"])

    def test_used_car_facts(self) -> None:
        facts = replay.load_scenario_facts(
            _PACKS, "official.everyday_negotiation", "used_car_negotiation", list(BASELINE_VARIABLES)
        )
        assert facts.npc_name == "Ray Kowalski"
        assert facts.npc_id == "car_dealer"
        assert facts.authored_variables == [
            "deal_progress", "perceived_fairness", "firmness", "concession_level", "leverage",
        ]
        assert facts.rubric_ids == ["clarity", "preparation", "empathy", "holding_firm", "outcome_framing"]


# ---------------------------------------------------------------------------
# The scripted player turns
# ---------------------------------------------------------------------------


class TestPlayerTurns:
    turns = replay.load_player_turns(_TURNS_FILE)

    def test_one_entry_per_demo_conversation(self) -> None:
        assert set(self.turns) == {s.scenario_id for s in DEMO_SCENARIOS}

    @pytest.mark.parametrize("scenario_id", [s.scenario_id for s in DEMO_SCENARIOS])
    def test_five_or_six_turns(self, scenario_id: str) -> None:
        assert 5 <= len(self.turns[scenario_id]) <= 6

    def test_every_turn_says_what_it_presses_on(self) -> None:
        doc = yaml.safe_load(_TURNS_FILE.read_text(encoding="utf-8"))
        for scenario_id, entry in doc["scenarios"].items():
            for turn in entry["turns"]:
                assert turn.get("presses"), f"{scenario_id}: a turn without `presses`"

    @pytest.mark.parametrize("pack_id, scenario_id", [(s.pack_id, s.scenario_id) for s in DEMO_SCENARIOS])
    def test_no_turn_quotes_the_hidden_agenda(self, pack_id: str, scenario_id: str) -> None:
        facts = replay.load_scenario_facts(_PACKS, pack_id, scenario_id, list(BASELINE_VARIABLES))
        player = [NpcLine(turn=i, text=t) for i, t in enumerate(self.turns[scenario_id], start=1)]
        assert checks.find_agenda_leaks(player, facts.hidden_agenda) == []

    def test_the_car_buyer_pays_cash(self) -> None:
        text = " ".join(self.turns["used_car_negotiation"]).lower()
        assert "cash" in text
        assert "financing is approved" not in text and "financing approved" not in text

    def test_the_car_buyer_never_names_rays_floor(self) -> None:
        # The offers around the floor are read as numbers, and none is the floor,
        # so Ray repeating the player's figure cannot read as a leak.
        said = {v for t in self.turns["used_car_negotiation"] for v, _ in checks.numbers_in(t)}
        assert {13000, 13500, 13600, 13900, 14200, 15500} <= said
        assert 13800 not in said


# ---------------------------------------------------------------------------
# The replay's flow
# ---------------------------------------------------------------------------


class ScriptedApi:
    """A stand-in for convsim-core's REST API, one scripted conversation per session.

    Like the engine, each debrief stores a relationship recap for the
    session's NPC (keyed by npc_id and scenario id), and ``/start`` notes the
    recaps that exist when a session starts, the ones its prompt would read.
    """

    def __init__(
        self,
        npc_lines: List[str],
        *,
        deltas: Optional[List[Dict[str, int]]] = None,
        scores: Optional[Dict[str, float]] = None,
        end_after: Optional[int] = None,
        fail_turn: Optional[int] = None,
        runtime_id: str = "llama_cpp",
        edition: Optional[str] = "demo",
        recaps: Optional[List[Dict[str, Any]]] = None,
        memory_api: bool = True,
        fallback_turns: Tuple[int, ...] = (),
        raise_at_debrief: Optional[BaseException] = None,
    ):
        self.npc_lines = npc_lines
        self.deltas = deltas or [{} for _ in npc_lines]
        self.scores = scores if scores is not None else {}
        self.end_after = end_after
        self.fail_turn = fail_turn
        self.runtime_id = runtime_id
        self.edition = edition
        self.recaps: Dict[tuple, Dict[str, Any]] = {
            (r["npc_id"], r["pack_id"]): dict(r) for r in recaps or []
        }
        self.memory_api = memory_api
        self.fallback_turns = fallback_turns
        self.raise_at_debrief = raise_at_debrief
        self.calls: List[tuple] = []
        self.sessions = 0
        self.scenario_id: Optional[str] = None
        self.recaps_at_start: List[List[tuple]] = []
        self.transcript: List[Dict[str, Any]] = []
        self.turn = 0

    def request(self, method: str, path: str, body: Any = None, *, timeout: float = 30.0):
        self.calls.append((method, path, body))
        if path == "/api/health":
            health: Dict[str, Any] = {
                "version": "test", "llm_runtime": {"runtime_id": self.runtime_id},
                "active_model": {}, "runtime": {"llm_model_name": "Test model"},
            }
            if self.edition is not None:
                health["edition"] = self.edition
            return 200, health
        if path.startswith("/api/relationship-memory"):
            if not self.memory_api:
                raise replay.ApiError(method, path, 404, {"detail": "Not Found"})
            if method == "GET":
                recaps = list(self.recaps.values())
                return 200, {"recaps": recaps, "total": len(recaps)}
            npc_id, pack_id = path.rsplit("/", 2)[-2:]
            if self.recaps.pop((npc_id, pack_id), None) is None:
                raise replay.ApiError(method, path, 404, {"detail": "No relationship recap"})
            return 204, None
        if path.startswith("/api/scenarios/"):
            return 200, {"supported_languages": ["es", "en"], "player_role": {"label": "Learner"}}
        if path == "/api/sessions":
            self.sessions += 1
            self.scenario_id = body["scenario_id"]
            self.turn = 0
            self.transcript = []
            return 201, {"session_id": f"s{self.sessions}"}
        if path.endswith("/start"):
            self.recaps_at_start.append(sorted(self.recaps))
            self.transcript.append({"turn_number": 0, "role": "npc_opening", "content": "Opening line."})
            return 200, {"state": "PlayerTurnListening", "events": [
                {"event_type": "npc_opening", "payload": {"content": "Opening line."}}]}
        if path.endswith("/turn"):
            self.turn += 1
            if self.turn == self.fail_turn:
                raise replay.ApiError(method, path, 504, {"detail": {"message": "stalled"}})
            fallback = self.turn in self.fallback_turns
            line = SAFE_FALLBACK_UTTERANCE if fallback else self.npc_lines[self.turn - 1]
            self.transcript += [
                {"turn_number": 2 * self.turn - 1, "role": "player", "content": body["content"]},
                {"turn_number": 2 * self.turn, "role": "npc", "content": line},
            ]
            ended = self.end_after is not None and self.turn >= self.end_after
            return 200, {
                "state": "Ended" if ended else "PlayerTurnListening",
                "ending_type": "success" if ended else None,
                "events": [{"event_type": "npc_turn", "payload": {
                    "content": line, "state_delta": self.deltas[self.turn - 1],
                    "rubric_observations": [], "visible_state": {},
                    "timing": {"fallback": fallback, "total_ms": 10.0}}}],
            }
        if path.endswith("/end"):
            return 200, {"state": "Ended", "ending_type": "player_exit"}
        if path.endswith("/debrief"):
            npc_id = _facts(self.scenario_id).npc_id
            previous = self.recaps.get((npc_id, self.scenario_id), {})
            self.recaps[(npc_id, self.scenario_id)] = {
                "npc_id": npc_id, "pack_id": self.scenario_id,
                "session_count": previous.get("session_count", 0) + 1,
                "updated_at": "2026-11-10T00:00:00Z", "key_observations": [],
                "player_style_tags": [], "last_outcome": "player_exit", "last_session_at": None,
            }
            if self.raise_at_debrief is not None:
                raise self.raise_at_debrief
            return 200, {"used_fallback": False, "scores": self.scores}
        if path.endswith("/transcript"):
            return 200, {"transcript_saved": True, "turns": list(self.transcript)}
        raise AssertionError(f"unexpected call {method} {path}")


def _facts(scenario_id: str = "spanish_coffee"):
    pack = dict((s.scenario_id, s.pack_id) for s in DEMO_SCENARIOS)[scenario_id]
    return replay.load_scenario_facts(_PACKS, pack, scenario_id, list(BASELINE_VARIABLES))


def _quiet(_msg: str) -> None:
    pass


class TestPlayConversation:
    lines = ["Marchando un café.", "Tenemos cruasanes.", "Claro, más despacio.",
             "Un cruasán, perfecto.", "Sí, de Madrid.", "Son cinco euros."]

    def test_setup_turns_end_debrief_transcript(self) -> None:
        api = ScriptedApi(self.lines)
        record = replay.play_conversation(api, _facts(), ["uno", "dos"], run=2, seed=43, log=_quiet)
        create = next(body for m, p, body in api.calls if p == "/api/sessions")
        assert create == {
            "scenario_id": "spanish_coffee", "difficulty": "standard",
            "player_role_name": "Learner", "language": "es", "input_mode": "text-only",
            "tts_enabled": False, "show_state_meters": True, "save_transcript": True,
            "seed": 43,
        }
        assert [p.rsplit("/", 1)[-1] for _, p, _ in api.calls[2:]] == [
            "start", "turn", "turn", "end", "debrief", "transcript",
        ]
        assert record["error"] is None
        assert [t["npc"] for t in record["turns"]] == self.lines[:2]
        assert [t["fallback"] for t in record["turns"]] == [False, False]
        assert record["opening"] == "Opening line."
        assert record["debrief"]["status"] == 200
        assert record["transcript"]["transcript_saved"] is True

    def test_runtime_pin_is_passed_through(self) -> None:
        api = ScriptedApi(self.lines)
        replay.play_conversation(api, _facts(), ["uno"], run=1, seed=1, runtime_id="fake", log=_quiet)
        create = next(body for m, p, body in api.calls if p == "/api/sessions")
        assert create["runtime_id"] == "fake"

    def test_a_session_that_ends_stops_the_script(self) -> None:
        api = ScriptedApi(self.lines, end_after=2)
        record = replay.play_conversation(api, _facts(), ["1", "2", "3", "4"], run=1, seed=1, log=_quiet)
        assert len(record["turns"]) == 2
        assert record["ended_early"] is True
        assert record["ending_type"] == "success"
        assert not any(p.endswith("/end") for _, p, _ in api.calls)
        assert record["debrief"]["status"] == 200

    def test_a_failed_turn_is_an_error_but_keeps_the_evidence(self) -> None:
        api = ScriptedApi(self.lines, fail_turn=2)
        record = replay.play_conversation(api, _facts(), ["1", "2", "3"], run=1, seed=1, log=_quiet)
        assert record["error"].startswith("turn 2: POST /api/sessions/s1/turn: HTTP 504: stalled")
        assert len(record["turns"]) == 1
        assert any(p.endswith("/debrief") for _, p, _ in api.calls)
        replay.evaluate_record(record, _facts(), checks.resolve_severity())
        assert record["verdict"] == "fail"

    def test_a_fallback_turn_is_recorded_and_fails_check_f(self) -> None:
        api = ScriptedApi(self.lines, fallback_turns=(2,))
        record = replay.play_conversation(api, _facts(), ["1", "2", "3"], run=1, seed=1, log=_quiet)
        assert [t["fallback"] for t in record["turns"]] == [False, True, False]
        replay.evaluate_record(
            record, _facts(), checks.resolve_severity(),
            fallback_utterance=replay.safe_fallback_utterance(),
        )
        f = {c["letter"]: c for c in record["checks"]}["f"]
        assert f["status"] == "FAIL"
        assert [x["turn"] for x in f["findings"]] == [2]
        assert record["verdict"] == "fail"

    def test_the_canned_line_fails_check_f_without_the_flag(self) -> None:
        api = ScriptedApi(self.lines, fallback_turns=(1,))
        record = replay.play_conversation(api, _facts(), ["1"], run=1, seed=1, log=_quiet)
        record["turns"][0]["fallback"] = None
        record["turns"][0]["timing"] = None
        replay.evaluate_record(
            record, _facts(), checks.resolve_severity(),
            fallback_utterance=replay.safe_fallback_utterance(),
        )
        assert {c["letter"]: c for c in record["checks"]}["f"]["status"] == "FAIL"


class TestMain:
    def _run(self, tmp_path: Path, api: ScriptedApi, *extra: str) -> int:
        return replay.main(
            ["--only", "spanish_coffee", "--repeat", "2", "--out", str(tmp_path), *extra],
            transport=api, log=_quiet,
        )

    def _clean_api(self, **kw: Any) -> ScriptedApi:
        return ScriptedApi(TestPlayConversation.lines, scores={"comprehension": 55.0}, **kw)

    def test_warnings_only_exit_zero_and_strict_exits_one(self, tmp_path: Path) -> None:
        # Baseline-only deltas: (c) fails, which is a warning unless --strict.
        assert self._run(tmp_path / "default", self._clean_api()) == 0
        assert self._run(tmp_path / "strict", self._clean_api(), "--strict") == 1
        assert self._run(tmp_path / "hard-c", self._clean_api(), "--hard", "c") == 1

    def test_writes_records_and_summary(self, tmp_path: Path) -> None:
        api = self._clean_api(deltas=[{"comprehension": 5}] + [{}] * 5)
        assert self._run(tmp_path, api) == 0
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "spanish_coffee-run1.json", "spanish_coffee-run2.json", "summary.md",
        ]
        record = json.loads((tmp_path / "spanish_coffee-run2.json").read_text(encoding="utf-8"))
        assert record["schema"] == "convsim.demo-gate-replay/1"
        assert record["seed"] == 43 and record["verdict"] == "pass"
        assert [c["letter"] for c in record["checks"]] == ["a", "b", "c", "d", "e", "f"]
        assert len(record["turns"]) == 6
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "**Verdict: PASS.**" in summary
        assert "Not a D-05 result" not in summary
        assert "does not replace the manual D-05 judgement" in summary
        assert "| spanish_coffee | 2 | 43 | 6 | pass | pass | pass | pass | pass | pass | PASS |" in summary

    def test_a_fallback_turn_fails_the_replay(self, tmp_path: Path) -> None:
        api = self._clean_api(deltas=[{"comprehension": 5}] + [{}] * 5, fallback_turns=(4,))
        assert self._run(tmp_path, api) == 1
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "(f) turn_fallback: **FAIL**" in summary
        assert "turn 4: the engine fell back to its canned safe line" in summary

    def test_repeated_npc_line_fails_the_run(self, tmp_path: Path) -> None:
        same = "Hola, bienvenido. ¿Qué te pongo hoy por la mañana?"
        api = ScriptedApi([same] * 6, scores={"comprehension": 55.0})
        assert self._run(tmp_path, api) == 1
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "**Verdict: FAIL.**" in summary
        assert "(a) repetition: **FAIL**" in summary

    def test_setup_errors_exit_two(self, tmp_path: Path) -> None:
        assert replay.main(["--only", "not_a_demo"], transport=ScriptedApi([]), log=_quiet) == 2
        assert replay.main(["--repeat", "0"], transport=ScriptedApi([]), log=_quiet) == 2
        assert replay.main(["--hard", "c", "--warn", "c"], transport=ScriptedApi([]), log=_quiet) == 2
        missing = tmp_path / "turns.yaml"
        missing.write_text("schema_version: 1\nscenarios: {}\n", encoding="utf-8")
        assert replay.main(["--turns", str(missing)], transport=ScriptedApi([]), log=_quiet) == 2

    def test_an_engine_that_does_not_answer_exits_two(self, tmp_path: Path) -> None:
        class Down:
            def request(self, method: str, path: str, body: Any = None, *, timeout: float = 30.0):
                raise replay.ApiError(method, path, None, "connection refused")

        assert replay.main(["--out", str(tmp_path)], transport=Down(), log=_quiet) == 2


class TestEdition:
    """D-05 judges the demo edition: a full-edition engine plays some of the
    five from built-in catalog entries, not the pack files the checks read."""

    @pytest.mark.parametrize("edition", ["full", None])
    def test_an_engine_that_is_not_the_demo_exits_two(
        self, tmp_path: Path, edition: Optional[str], capsys
    ) -> None:
        api = ScriptedApi(TestPlayConversation.lines, edition=edition)
        code = replay.main(["--only", "spanish_coffee", "--out", str(tmp_path / "out")],
                           transport=api, log=_quiet)
        assert code == 2
        err = capsys.readouterr().err
        assert f"runs the {edition or 'unknown'} edition, not the demo" in err
        assert "CONVSIM_EDITION=demo" in err and "--allow-full-edition" in err
        assert not any(p == "/api/sessions" for _, p, _ in api.calls)
        assert not (tmp_path / "out").exists()

    def test_allow_full_edition_runs_and_is_labelled(self, tmp_path: Path) -> None:
        api = ScriptedApi(TestPlayConversation.lines, scores={"comprehension": 55.0}, edition="full",
                          deltas=[{"comprehension": 5}] + [{}] * 5)
        code = replay.main(
            ["--only", "spanish_coffee", "--repeat", "1", "--out", str(tmp_path), "--allow-full-edition"],
            transport=api, log=_quiet,
        )
        assert code == 0
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "- **Not a D-05 result:** the engine runs the `full` edition (--allow-full-edition)" in summary
        assert "**Verdict: PASS (not a D-05 result).**" in summary

    def test_not_d05_reasons(self) -> None:
        demo = {"engine": {"edition": "demo"}}
        assert replay.not_d05_reasons(demo) == []
        assert len(replay.not_d05_reasons({**demo, "runtime_id": "fake"})) == 1
        assert len(replay.not_d05_reasons({"engine": {"edition": "full"}, "runtime_id": "fake"})) == 2


def _recap(npc_id: str, pack_id: str, sessions: int = 3) -> Dict[str, Any]:
    return {
        "npc_id": npc_id, "pack_id": pack_id, "session_count": sessions,
        "updated_at": "2026-11-01T00:00:00Z", "key_observations": ["Asks few questions"],
        "player_style_tags": [], "last_outcome": "success", "last_session_at": None,
    }


class TestNpcMemory:
    """Each debrief writes the NPC's relationship recap and the next session's
    prompt reads it, so the replay deletes it around every run."""

    def _run(self, tmp_path: Path, api: ScriptedApi, *extra: str) -> int:
        return replay.main(
            ["--only", "spanish_coffee,used_car_negotiation", "--repeat", "2",
             "--out", str(tmp_path), *extra],
            transport=api, log=_quiet,
        )

    def _api(self, **kw: Any) -> ScriptedApi:
        return ScriptedApi(TestPlayConversation.lines, scores={"comprehension": 55.0}, **kw)

    def test_every_run_starts_without_a_recap_and_none_is_left(self, tmp_path: Path) -> None:
        api = self._api()
        assert self._run(tmp_path, api) == 0
        assert api.sessions == 4
        # The engine wrote a recap at every debrief; no session started with one.
        assert api.recaps_at_start == [[], [], [], []]
        assert api.recaps == {}
        for name in ("used_car_negotiation-run1", "spanish_coffee-run2"):
            record = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
            assert record["npc_memory"]["cleared_before"] == []
            assert record["npc_memory"]["errors"] == []
            [after] = record["npc_memory"]["cleared_after"]
            assert after["npc_id"] == _facts(record["scenario_id"]).npc_id
            assert after["pack_id"] == record["scenario_id"]
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "before and after every run" in summary
        assert "(4 recap(s) written during the replay deleted; none existed before it)" in summary
        assert "throwaway `CONVSIM_DATA_ROOT`" in summary

    def test_other_npcs_memory_is_left_alone(self, tmp_path: Path) -> None:
        other = _recap("hiring_manager", "behavioral_interview")
        api = self._api(recaps=[other])
        assert self._run(tmp_path, api) == 0
        assert list(api.recaps.values()) == [other]

    def test_an_existing_recap_refuses_to_start(self, tmp_path: Path, capsys) -> None:
        api = self._api(recaps=[_recap("car_dealer", "used_car_negotiation")])
        assert self._run(tmp_path / "out", api) == 2
        err = capsys.readouterr().err
        assert "car_dealer/used_car_negotiation (3 session(s))" in err
        assert "CONVSIM_DATA_ROOT" in err and "--clear-npc-memory" in err
        assert api.sessions == 0 and len(api.recaps) == 1
        assert not (tmp_path / "out").exists()

    def test_clear_npc_memory_deletes_and_keeps_a_copy(self, tmp_path: Path) -> None:
        existing = _recap("car_dealer", "used_car_negotiation")
        api = self._api(recaps=[existing])
        assert self._run(tmp_path, api, "--clear-npc-memory") == 0
        assert api.recaps_at_start == [[], [], [], []] and api.recaps == {}
        assert json.loads((tmp_path / "npc-memory-before.json").read_text(encoding="utf-8")) == [existing]
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "1 that existed before it deleted with --clear-npc-memory" in summary

    def test_an_engine_without_the_memory_api_exits_two(self, tmp_path: Path, capsys) -> None:
        assert self._run(tmp_path, self._api(memory_api=False)) == 2
        assert "cannot read the engine's NPC relationship memory" in capsys.readouterr().err

    @pytest.mark.parametrize("exc", [KeyboardInterrupt(), RuntimeError("boom")])
    def test_memory_is_cleared_on_an_interrupt_or_a_crash(self, tmp_path: Path, exc: BaseException) -> None:
        # The engine stored the recap, then the replay stopped inside the debrief.
        api = self._api(raise_at_debrief=exc)
        if isinstance(exc, KeyboardInterrupt):
            assert self._run(tmp_path, api) == 130
            summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
            assert "- Interrupted: only the runs below finished." in summary
            assert "(1 recap(s) written during the replay deleted" in summary
        else:
            with pytest.raises(RuntimeError):
                self._run(tmp_path, api)
        assert api.sessions == 1
        assert api.recaps == {}

    def test_a_recap_that_cannot_be_deleted_fails_the_run(self, tmp_path: Path) -> None:
        api = self._api()
        real = api.request

        def no_delete(method: str, path: str, body: Any = None, *, timeout: float = 30.0):
            if method == "DELETE":
                raise replay.ApiError(method, path, 500, {"detail": "locked"})
            return real(method, path, body, timeout=timeout)

        api.request = no_delete  # type: ignore[method-assign]
        assert self._run(tmp_path, api) == 1
        record = json.loads((tmp_path / "spanish_coffee-run1.json").read_text(encoding="utf-8"))
        assert "NPC memory after the run" in record["error"]
        assert record["verdict"] == "fail"
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "except around 4 run(s) where the delete failed" in summary
        assert "so no run's prompt carried an earlier debrief" not in summary
        assert "**NPC memory not cleared at the end:**" in summary


class _TestClientTransport:
    """The replay's transport interface over an in-process FastAPI app."""

    def __init__(self, client: Any):
        self.client = client

    def request(self, method: str, path: str, body: Any = None, *, timeout: float = 30.0):
        resp = self.client.request(method, path, json=body)
        data = resp.json() if resp.content else None
        if resp.status_code >= 400:
            raise replay.ApiError(method, path, resp.status_code, data)
        return resp.status_code, data


def _engine_config(tmp_path: Path, monkeypatch, **overrides: Any):
    from convsim_core.config import ServiceConfig

    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_PACKS),
        **overrides,
    )


def test_replay_against_in_process_engine_on_the_fake_runtime(tmp_path: Path, monkeypatch) -> None:
    """The API contract the replay relies on, end to end, without a model.

    The engine runs the demo edition (``CONVSIM_EDITION=demo``), as for D-05,
    so it plays the five from their curated packs. The fake runtime says the
    same line every turn, so the repetition check must fail every run, and the
    run must still be played to the debrief. Every debrief stores the NPC's
    relationship recap; the replay must find it under the key the engine
    uses, delete it before the next run, and leave none behind.
    """
    from fastapi.testclient import TestClient

    from convsim_core.app import create_app

    config = _engine_config(tmp_path, monkeypatch, edition="demo")
    out = tmp_path / "out"
    with TestClient(create_app(config)) as client:
        code = replay.main(
            ["--only", "behavioral_interview,spanish_coffee", "--repeat", "2",
             "--runtime-id", "fake", "--out", str(out)],
            transport=_TestClientTransport(client),
            log=_quiet,
        )
        left = client.get("/api/relationship-memory").json()
    assert code == 1
    assert left["total"] == 0, left
    for scenario_id, language in (("behavioral_interview", "en"), ("spanish_coffee", "es")):
        for run in (1, 2):
            record = json.loads((out / f"{scenario_id}-run{run}.json").read_text(encoding="utf-8"))
            assert record["error"] is None, record["error"]
            assert record["language"] == language
            assert record["player_role_name"]
            assert len(record["turns"]) == 6
            assert [t["fallback"] for t in record["turns"]] == [False] * 6
            assert record["debrief"]["status"] == 200
            assert record["transcript"]["transcript_saved"] is True
            by_letter = {c["letter"]: c for c in record["checks"]}
            assert by_letter["a"]["status"] == "FAIL"
            assert by_letter["a"]["findings"][0]["turn"] == 2
            # The engine's repetition guard saw the same repeats and retried
            # each once (issue #580); the fake runtime answered the same line
            # again, so the first reply stood. Turn 1 follows the authored
            # opening, which the fake line does not repeat. In spanish_coffee
            # the player asks Rosa to say it again on turn 3: neither the
            # guard nor check (a) judges that answer.
            asked_again = {"spanish_coffee": 3}.get(scenario_id)
            kinds = [[c["kind"] for c in t["timing"]["extra_calls"]] for t in record["turns"]]
            assert kinds == [
                [] if t in (1, asked_again) else ["repetition_retry"] for t in range(1, 7)
            ]
            assert replay.repetition_retries(record) == (4 if asked_again else 5)
            assert asked_again not in {f["turn"] for f in by_letter["a"]["findings"]}
            if asked_again:
                assert "not judged: the line of turn(s) 3" in by_letter["a"]["detail"]
            assert by_letter["f"]["status"] == "pass"
            assert record["verdict"] == "fail"
            # The debrief's recap was found under the engine's own key and
            # deleted, so run 2 started without run 1's.
            memory = record["npc_memory"]
            assert memory["cleared_before"] == []
            assert [(m["npc_id"], m["pack_id"], m["session_count"]) for m in memory["cleared_after"]] == [
                (_facts(scenario_id).npc_id, scenario_id, 1)
            ]
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "model-free `fake` runtime" in summary
    latency = summary.split("## Latency (noted, not judged)", 1)[1]
    assert "| Conversation | Run | Mean turn s | Max turn s | Repetition retries | Debrief s |" in latency
    rows = [line.split(" | ") for line in latency.splitlines() if line.startswith("| ") and "Conversation" not in line]
    assert [(row[0].lstrip("| "), row[1], row[4]) for row in rows] == [
        (scenario_id, run, retries)
        for scenario_id, retries in (("behavioral_interview", "5"), ("spanish_coffee", "4"))
        for run in ("1", "2")
    ]
    assert "edition (--allow-full-edition)" not in summary
    assert "(4 recap(s) written during the replay deleted; none existed before it)" in summary


def test_replay_refuses_an_in_process_full_edition_engine(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from convsim_core.app import create_app

    with TestClient(create_app(_engine_config(tmp_path, monkeypatch))) as client:
        code = replay.main(
            ["--only", "used_car_negotiation", "--repeat", "1", "--runtime-id", "fake",
             "--out", str(tmp_path / "out")],
            transport=_TestClientTransport(client),
            log=_quiet,
        )
        sessions = client.get("/api/sessions").json()["sessions"]
    assert code == 2
    assert sessions == []
