# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — the D-05 automated pre-check (issue #580).

``scripts/demo-gate-replay.py`` replays the five demo conversations against a
running convsim-core on the real model; its assertions live in
``scripts/demo_gate_checks.py``. A real-model replay cannot run in CI, so
these tests pin the harness instead:

  * each check, on synthetic transcripts: the issue's own failing lines are
    caught (Ray repeating his closing question, Diane saying her agenda
    aloud, the baseline-only state deltas, the invented rubric ids, a
    fallback debrief), and the boundaries are where the issue puts them (a
    6-word repeat, a 5-word agenda run);
  * severities: (a), (b), (e) hard and (c), (d) warnings by default,
    ``--strict`` and per-check overrides, and the exit status that follows;
  * the facts the checks read come from the files that own them: the five
    conversations from ``edition.py``, the baseline variables from
    ``scenario_state.py``, the agenda, authored variables and rubric ids from
    each pack;
  * the scripted player turns: 5-6 per conversation, inside the player brief,
    and never quoting the NPC's hidden agenda (or an NPC echo would read as a
    leak);
  * the replay's flow, against a scripted stand-in for the API and against an
    in-process convsim-core on the fake runtime, whose identical NPC lines
    the repetition check must fail.

No model and no server: the in-process app is a FastAPI TestClient.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pytest
import yaml

from convsim_core.edition import DEMO_SCENARIOS
from convsim_core.scenario_state import BASELINE_VARIABLES

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
        assert [f.evidence for f in found] == ["real minimum on this unit"]

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


# ---------------------------------------------------------------------------
# Severity and verdicts
# ---------------------------------------------------------------------------


class TestSeverity:
    def test_defaults(self) -> None:
        assert checks.resolve_severity() == {
            "a": "hard", "b": "hard", "c": "warn", "d": "warn", "e": "hard",
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
        assert status == {"a": "FAIL", "b": "pass", "c": "warn", "d": "warn", "e": "pass"}
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
        assert [r.letter for r in results] == ["a", "b", "c", "d", "e"]


class TestTranscriptShape:
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


# ---------------------------------------------------------------------------
# The replay's flow
# ---------------------------------------------------------------------------


class ScriptedApi:
    """A stand-in for convsim-core's REST API, one scripted conversation per session."""

    def __init__(
        self,
        npc_lines: List[str],
        *,
        deltas: Optional[List[Dict[str, int]]] = None,
        scores: Optional[Dict[str, float]] = None,
        end_after: Optional[int] = None,
        fail_turn: Optional[int] = None,
        runtime_id: str = "llama_cpp",
    ):
        self.npc_lines = npc_lines
        self.deltas = deltas or [{} for _ in npc_lines]
        self.scores = scores if scores is not None else {}
        self.end_after = end_after
        self.fail_turn = fail_turn
        self.runtime_id = runtime_id
        self.calls: List[tuple] = []
        self.sessions = 0
        self.transcript: List[Dict[str, Any]] = []
        self.turn = 0

    def request(self, method: str, path: str, body: Any = None, *, timeout: float = 30.0):
        self.calls.append((method, path, body))
        if path == "/api/health":
            return 200, {"version": "test", "edition": "full",
                         "llm_runtime": {"runtime_id": self.runtime_id},
                         "active_model": {}, "runtime": {"llm_model_name": "Test model"}}
        if path.startswith("/api/scenarios/"):
            return 200, {"supported_languages": ["es", "en"], "player_role": {"label": "Learner"}}
        if path == "/api/sessions":
            self.sessions += 1
            self.turn = 0
            self.transcript = []
            return 201, {"session_id": f"s{self.sessions}"}
        if path.endswith("/start"):
            self.transcript.append({"turn_number": 0, "role": "npc_opening", "content": "Opening line."})
            return 200, {"state": "PlayerTurnListening", "events": [
                {"event_type": "npc_opening", "payload": {"content": "Opening line."}}]}
        if path.endswith("/turn"):
            self.turn += 1
            if self.turn == self.fail_turn:
                raise replay.ApiError(method, path, 504, {"detail": {"message": "stalled"}})
            line = self.npc_lines[self.turn - 1]
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
                    "rubric_observations": [], "visible_state": {}}}],
            }
        if path.endswith("/end"):
            return 200, {"state": "Ended", "ending_type": "player_exit"}
        if path.endswith("/debrief"):
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
        assert [c["letter"] for c in record["checks"]] == ["a", "b", "c", "d", "e"]
        assert len(record["turns"]) == 6
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        assert "**Verdict: PASS.**" in summary
        assert "does not replace the manual D-05 judgement" in summary
        assert "| spanish_coffee | 2 | 43 | 6 | pass | pass | pass | pass | pass | PASS |" in summary

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


def test_replay_against_in_process_engine_on_the_fake_runtime(tmp_path: Path, monkeypatch) -> None:
    """The API contract the replay relies on, end to end, without a model.

    The fake runtime says the same line every turn, so the repetition check
    must fail every run, and the run must still be played to the debrief.
    """
    from fastapi.testclient import TestClient

    from convsim_core.app import create_app
    from convsim_core.config import ServiceConfig

    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_PACKS),
    )
    out = tmp_path / "out"
    with TestClient(create_app(config)) as client:
        code = replay.main(
            ["--only", "behavioral_interview,spanish_coffee", "--repeat", "1",
             "--runtime-id", "fake", "--out", str(out)],
            transport=_TestClientTransport(client),
            log=_quiet,
        )
    assert code == 1
    for scenario_id, language in (("behavioral_interview", "en"), ("spanish_coffee", "es")):
        record = json.loads((out / f"{scenario_id}-run1.json").read_text(encoding="utf-8"))
        assert record["error"] is None, record["error"]
        assert record["language"] == language
        assert record["player_role_name"]
        assert len(record["turns"]) == 6
        assert record["debrief"]["status"] == 200
        assert record["transcript"]["transcript_saved"] is True
        by_letter = {c["letter"]: c for c in record["checks"]}
        assert by_letter["a"]["status"] == "FAIL"
        assert by_letter["a"]["findings"][0]["turn"] == 2
        assert record["verdict"] == "fail"
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "model-free `fake` runtime" in summary
