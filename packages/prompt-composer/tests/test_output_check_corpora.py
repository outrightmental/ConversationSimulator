# SPDX-License-Identifier: Apache-2.0
"""The output check's two corpora (issue #526).

``corpora/benign.json`` holds lines a simulated character may say, in every
official pack's subject vocabulary; every one must pass. ``corpora/
violations.json`` holds lines that must still fail, each with the category the
check must report. A change to any pattern in ``convsim_prompt.output_validator``
keeps both green (docs/safety-policy.md, "Changing a pattern").

This package's CI step has no YAML parser, so here every line is checked with
no scenario context. ``services/convsim-core/tests/test_output_check_corpora.py``
checks the same lines again against each scenario's NPC hidden agenda and
public brief, loaded from the pack, and runs the ``by_scenario`` violations,
which only fail against their agenda.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from convsim_prompt import (
    SAFE_REDIRECT_UTTERANCE,
    SAFE_STOP_UTTERANCE,
    TurnEvent,
    count_rejections,
    parse_turn_output,
    validate_npc_output,
)

_CORPORA = Path(__file__).parent / "corpora"
_OFFICIAL_PACKS = Path(__file__).resolve().parents[3] / "packs" / "official"

_CATEGORIES = {
    "hidden_agenda_leak": True,
    "system_rule_leak": True,
    "real_person_impersonation": True,
    "nsfw_content": False,
    "illegal_advice": False,
    "therapy_or_diagnosis": False,
}  # category → is_recoverable

_BENIGN: Dict[str, List[str]] = json.loads((_CORPORA / "benign.json").read_text(encoding="utf-8"))["lines"]
_VIOLATIONS = json.loads((_CORPORA / "violations.json").read_text(encoding="utf-8"))

_BENIGN_LINES = [(key, line) for key, lines in _BENIGN.items() for line in lines]
_CONTEXT_FREE = [(v["category"], v["text"]) for v in _VIOLATIONS["context_free"]]
_BY_SCENARIO = [
    (key, v["category"], v["text"]) for key, items in _VIOLATIONS["by_scenario"].items() for v in items
]


def _official_scenarios() -> List[str]:
    return sorted(
        f"{path.parent.parent.name}/{path.stem}"
        for path in _OFFICIAL_PACKS.glob("*/scenarios/*.yaml")
    )


# ── What the corpora cover ───────────────────────────────────────────────────


def test_the_benign_corpus_has_at_least_100_lines():
    assert len(_BENIGN_LINES) >= 100


def test_the_benign_corpus_covers_every_official_scenario():
    scenarios = _official_scenarios()
    assert scenarios, f"no official scenarios under {_OFFICIAL_PACKS}"
    assert sorted(_BENIGN) == scenarios
    packs = {key.split("/")[0] for key in scenarios}
    assert {key.split("/")[0] for key in _BENIGN} == packs


def test_the_violation_corpus_names_real_scenarios_and_categories():
    scenarios = set(_official_scenarios())
    assert set(_VIOLATIONS["by_scenario"]) <= scenarios
    reported = {category for category, _ in _CONTEXT_FREE} | {c for _, c, _ in _BY_SCENARIO}
    assert reported == set(_CATEGORIES)


def test_the_corpora_do_not_overlap():
    benign = {line for _, line in _BENIGN_LINES}
    assert len(benign) == len(_BENIGN_LINES), "a benign line is listed twice"
    violating = [text for _, text in _CONTEXT_FREE] + [text for _, _, text in _BY_SCENARIO]
    assert not benign & set(violating)


# ── The lines themselves ─────────────────────────────────────────────────────


@pytest.mark.parametrize("key, line", _BENIGN_LINES, ids=[f"{k}:{i}" for i, (k, _) in enumerate(_BENIGN_LINES)])
def test_a_benign_line_passes(key, line):
    result = validate_npc_output(line)
    assert result.is_safe, f"{key}: {line!r} → {[(v.category, v.reason) for v in result.violations]}"


@pytest.mark.parametrize("category, text", _CONTEXT_FREE, ids=[f"{c}:{i}" for i, (c, _) in enumerate(_CONTEXT_FREE)])
def test_a_violation_fails_with_its_category(category, text):
    result = validate_npc_output(text)
    assert result.first_violation is not None, f"{text!r} passed"
    assert result.first_violation.category == category, (
        f"{text!r}: {[v.category for v in result.violations]}"
    )
    assert result.has_hard_violation is (not _CATEGORIES[category])


@pytest.mark.parametrize("key, category, text", _BY_SCENARIO, ids=[f"{k}:{i}" for i, (k, _, _) in enumerate(_BY_SCENARIO)])
def test_an_agenda_leak_passes_without_its_agenda(key, category, text):
    """Each of these fails only against its scenario's agenda (checked in
    convsim-core); with none, nothing else in it may trip the check, or the
    convsim-core test would pass for the wrong reason."""
    assert validate_npc_output(text).is_safe, text


# ── The three lines of the issue, through the parser ─────────────────────────


class _CountingRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def call_llm(self, prompt: str) -> str:
        self.calls += 1
        return "{}"


def _turn(utterance: str) -> str:
    return json.dumps({
        "npc_utterance": utterance,
        "npc_emotion": "neutral",
        "state_delta": {},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    })


@pytest.mark.parametrize("line", [
    "Our market penetration in mid-sized banks doubled after the rebuild. How would your design have held up under that load?",
    "I really want to hear specifics, not buzzwords.",
    "I really need you to separate what you decided from what your team decided.",
    "I actually want to know what you gave up to get that outcome.",
])
def test_an_ordinary_line_costs_no_retry_and_ends_no_session(line):
    runtime = _CountingRuntime()
    events: List[TurnEvent] = []
    output = parse_turn_output(_turn(line), runtime=runtime, turn_events=events)
    assert runtime.calls == 0
    assert output.npc_utterance == line
    assert output.npc_utterance not in (SAFE_REDIRECT_UTTERANCE, SAFE_STOP_UTTERANCE)
    assert output.session_control.continue_session is True
    assert count_rejections(events) == {}
