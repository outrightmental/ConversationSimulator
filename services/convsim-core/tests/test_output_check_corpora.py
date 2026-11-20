# SPDX-License-Identifier: Apache-2.0
"""The output check against the official packs themselves (issue #526).

``packages/prompt-composer/tests/corpora/`` holds the check's two corpora. The
prompt-composer suite runs every line with no scenario context; this one runs
them as play does, against each line's scenario: its NPC's hidden agenda and
its public brief (``scenario_public_brief``), loaded from the pack by the same
loader play uses.

It also pins the acceptance criterion that no official NPC's agenda turns the
scenario's own public brief into a ``hidden_agenda_leak``: an NPC talking
about what the scenario tells the player is doing its job. And the three
lines the issue measured pass with no retry and no session end.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import pytest
import yaml

from convsim_core.scenarios import ScenarioInfo, load_scenario_info_from_pack
from convsim_core.services.utterance_stream import SentenceGate
from convsim_prompt import (
    TurnEvent,
    count_rejections,
    parse_turn_output,
    scenario_public_brief,
    validate_npc_output,
)
from convsim_prompt.types import ScenarioData

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"
_CORPORA = _REPO_ROOT / "packages" / "prompt-composer" / "tests" / "corpora"


def _scenario_files() -> Dict[str, Path]:
    """``"<pack dir>/<scenario id>"`` → scenario file, for every official scenario."""
    return {
        f"{path.parent.parent.name}/{path.stem}": path
        for path in sorted(_OFFICIAL_PACKS.glob("*/scenarios/*.yaml"))
    }


_SCENARIOS = _scenario_files()
_INFO: Dict[str, ScenarioInfo] = {}


def _info(key: str) -> ScenarioInfo:
    if key not in _INFO:
        path = _SCENARIOS[key]
        _INFO[key] = load_scenario_info_from_pack(path.parent.parent, f"scenarios/{path.name}")
    return _INFO[key]


def _scenario(key: str, difficulty: str = "standard") -> ScenarioData:
    return _info(key).get_scenario_data(difficulty)


def _check(line: str, key: str, difficulty: str = "standard"):
    data = _scenario(key, difficulty)
    return validate_npc_output(
        line,
        hidden_agenda=data.npc.private_persona.hidden_agenda,
        public_brief=scenario_public_brief(data),
    )


_BENIGN = json.loads((_CORPORA / "benign.json").read_text(encoding="utf-8"))["lines"]
_VIOLATIONS = json.loads((_CORPORA / "violations.json").read_text(encoding="utf-8"))
_BENIGN_LINES = [(key, line) for key, lines in _BENIGN.items() for line in lines]
_BY_SCENARIO = [
    (key, v["category"], v["text"]) for key, items in _VIOLATIONS["by_scenario"].items() for v in items
]


def test_every_official_scenario_is_loaded():
    assert len(_SCENARIOS) >= 21
    for key in _SCENARIOS:
        data = _scenario(key)
        assert data.npc.private_persona.hidden_agenda, key
        assert data.summary, f"{key}: the summary is part of the public brief"


# ── The corpora, in their scenarios ──────────────────────────────────────────


@pytest.mark.parametrize("key, line", _BENIGN_LINES, ids=[f"{k}:{i}" for i, (k, _) in enumerate(_BENIGN_LINES)])
def test_a_benign_line_passes_against_its_scenario(key, line):
    result = _check(line, key)
    assert result.is_safe, f"{key}: {line!r} → {[(v.category, v.reason) for v in result.violations]}"


@pytest.mark.parametrize("key, category, text", _BY_SCENARIO, ids=[f"{k}:{i}" for i, (k, _, _) in enumerate(_BY_SCENARIO)])
def test_an_agenda_leak_fails_against_its_scenario(key, category, text):
    result = _check(text, key)
    assert category in [v.category for v in result.violations], f"{key}: {text!r} passed"


# ── The public brief is the NPC's to talk about ──────────────────────────────

_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+")


def _public_texts(path: Path, difficulty: str) -> Iterator[str]:
    """What the scenario file and its NPC file show the player, read straight from the YAML.

    Read independently of ``scenario_public_brief``, so a public field the
    brief leaves out shows up here as a leak.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    yield raw.get("title") or ""
    yield raw.get("summary") or ""
    role = raw.get("player_role") or {}
    yield role.get("label") or ""
    yield role.get("brief") or ""
    yield from (raw.get("goals") or {}).get("player_visible") or []
    yield (raw.get("opening") or {}).get("npc_says") or ""
    option = ((raw.get("difficulty") or {}).get("options") or {}).get(difficulty) or {}
    yield option.get("description") or ""
    npc = yaml.safe_load((path.parent / raw["npc"]["ref"]).read_text(encoding="utf-8"))
    yield npc.get("display_name") or ""
    yield from (npc.get("public_persona") or {}).values()


def _lines_from_public_brief(path: Path, difficulty: str) -> List[str]:
    """Lines an NPC could build from the brief: each text, each sentence, each pair of sentences."""
    lines: List[str] = []
    for text in _public_texts(path, difficulty):
        text = " ".join(str(text).split())
        if not text:
            continue
        sentences = [s for s in _SENTENCE.split(text) if s]
        lines.append(text)
        lines.extend(sentences)
        lines.extend(f"{a} {b}" for a, b in zip(sentences, sentences[1:]))
        lines.extend(f"As I said, {s[0].lower()}{s[1:]}" for s in sentences)
    return lines


def _scenario_difficulties() -> List[Tuple[str, str]]:
    return [(key, difficulty) for key in _SCENARIOS for difficulty in sorted(_info(key).difficulty_options or {"standard": None})]


@pytest.mark.parametrize("key, difficulty", _scenario_difficulties())
def test_no_official_agenda_turns_the_public_brief_into_a_leak(key, difficulty):
    lines = _lines_from_public_brief(_SCENARIOS[key], difficulty)
    assert lines
    leaks = [
        line for line in lines
        if any(v.category == "hidden_agenda_leak" for v in _check(line, key, difficulty).violations)
    ]
    assert leaks == [], f"{key} ({difficulty}): {leaks[:3]}"


def test_without_the_brief_some_official_agenda_would_flag_its_own_brief():
    """The exemption is load-bearing: some official NPC's agenda shares a
    phrase with its scenario's public text, and only the brief keeps that
    from being a leak."""
    flagged = []
    for key in _SCENARIOS:
        agenda = _scenario(key).npc.private_persona.hidden_agenda
        for line in _lines_from_public_brief(_SCENARIOS[key], "standard"):
            if any(v.category == "hidden_agenda_leak" for v in validate_npc_output(line, agenda).violations):
                flagged.append((key, line))
    assert flagged


def test_every_scripted_tutorial_line_passes_against_the_tutorial():
    """The first-words tutorial's replies are authored, and they go through the
    same output check as a model's: none of them may be rejected."""
    from convsim_core.runtime import scripted

    lines = [turn["npc_utterance"] for turn in scripted._FIRST_WORDS_SCRIPT]
    lines += [
        scripted._with_answer(turn, answer)["npc_utterance"]
        for turn in scripted._FIRST_WORDS_SCRIPT
        for _, answer in scripted._INTERJECTIONS
    ]
    lines += [scripted._pick_ending_turn(text)["npc_utterance"] for text in ("amazing", "how?", "ok")]
    rejected = [
        (line, [v.category for v in result.violations])
        for line in lines
        for result in [_check(line, "first-words/first_words_tutorial")]
        if not result.is_safe
    ]
    assert rejected == []


# ── The three lines of the issue ─────────────────────────────────────────────

_VICTOR = "job-interview-basic/hostile_executive_interview"
_ISSUE_LINES = [
    (_VICTOR, "Our market penetration in mid-sized banks doubled after the rebuild. Defend your design."),
    ("everyday-negotiation/used_car_negotiation", "Civics have serious market penetration around here. They hold their value."),
    ("difficult-conversations/ask_for_raise", "Your market penetration numbers for the new region are strong."),
    (_VICTOR, "I really want to hear specifics, not buzzwords."),
    (_VICTOR, "I want evidence. Tell me whether you held that position when the pressure was on."),
]


class _CountingRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def call_llm(self, prompt: str) -> str:
        self.calls += 1
        return "{}"


@pytest.mark.parametrize("key, line", _ISSUE_LINES)
def test_an_issue_line_costs_no_retry_and_ends_no_session(key, line):
    data = _scenario(key)
    runtime = _CountingRuntime()
    events: List[TurnEvent] = []
    output = parse_turn_output(
        json.dumps({
            "npc_utterance": line,
            "npc_emotion": "neutral",
            "state_delta": {},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": True},
        }),
        runtime=runtime,
        hidden_agenda=data.npc.private_persona.hidden_agenda,
        turn_events=events,
        public_brief=scenario_public_brief(data),
    )
    assert runtime.calls == 0
    assert output.npc_utterance == line
    assert output.safety.status == "ok"
    assert output.session_control.continue_session is True
    assert count_rejections(events) == {}


def test_the_sentence_gate_releases_victors_line_as_the_parser_passes_it():
    data = _scenario(_VICTOR)
    gate = SentenceGate(
        hidden_agenda=data.npc.private_persona.hidden_agenda,
        public_brief=scenario_public_brief(data),
    )
    line = "I want evidence. Tell me whether you held that position when the pressure was on."
    assert gate.feed(line, done=True) == [
        "I want evidence.",
        " Tell me whether you held that position when the pressure was on.",
    ]
    assert gate.blocked is None
    # The gate holds back what the parser rejects, with the same context.
    leaky = SentenceGate(
        hidden_agenda=data.npc.private_persona.hidden_agenda,
        public_brief=scenario_public_brief(data),
    )
    leaky.feed("Good. Disagreement is fine; wounded pride is not.", done=True)
    assert leaky.released_text == "Good."
    assert leaky.blocked is not None
    assert leaky.blocked.first_violation.category == "hidden_agenda_leak"
