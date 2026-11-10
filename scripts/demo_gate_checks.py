# SPDX-License-Identifier: Apache-2.0
"""The assertions of the D-05 automated pre-check (issue #580).

``scripts/demo-gate-replay.py`` plays the five demo conversations against a
running convsim-core and hands what came back to the functions here. Every
function is pure: it takes plain data (lines of a transcript, a turn's
``state_delta``, a debrief body, the text of an authored file) and returns
findings, so the checks are unit-tested on synthetic transcripts in
``tests/acceptance/test_demo_gate_checks.py`` without a model or a server.

Standard library only, plus this checkout's prompt composer
(``packages/prompt-composer``, itself standard library only): check (a)
counts a repeat with the engine's own word functions, from
``convsim_prompt.repetition``, so the pre-check and the engine's repetition
guard agree on what a repeat is. The replay parses the pack YAML with PyYAML
and passes the parsed documents in.

The six checks, with the letters the issue and the demo doc use:

  (a) repetition      per turn: no run of 6+ consecutive words shared with the
                      previous NPC line, and no NPC line ending with the same
                      question (of 4+ words) as the previous one.
  (b) agenda_leak     per turn: no run of 5+ consecutive words from the NPC's
                      ``private_persona.hidden_agenda`` said aloud, and no
                      number of 3+ digits from it (Ray's $13,800 floor) in an
                      NPC line, in digits or in English words.
  (c) authored_state  per run: some turn's ``state_delta`` applied a non-zero
                      change to a variable the scenario authors (not an
                      engine baseline variable).
  (d) rubric_ids      per run: the debrief scored at least one dimension, and
                      only the scenario rubric's dimension ids.
  (e) debrief         per run: the debrief generated (HTTP 200) without the
                      template fallback.
  (f) turn_fallback   per turn: no NPC reply was the engine's canned safe
                      fallback line.

Words are compared case- and punctuation-insensitively: text is NFKC
normalised and case-folded, apostrophes are dropped (so "What's" and
"What’s" are one word), and every other non-word character separates words.
"""
from __future__ import annotations

import ast
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# The prompt composer of this checkout, next to the script, so the checks count
# a repeat as the engine built from the same files does. A process that already
# imported the package (the tests, with it installed) keeps the copy it has.
_PROMPT_COMPOSER_SRC = Path(__file__).resolve().parents[1] / "packages" / "prompt-composer" / "src"
if "convsim_prompt" not in sys.modules and _PROMPT_COMPOSER_SRC.is_dir():
    sys.path.insert(0, str(_PROMPT_COMPOSER_SRC))

from convsim_prompt.repetition import (  # noqa: E402 - the path above comes first
    REPEAT_RUN_WORDS,
    SAME_QUESTION_MIN_WORDS,
    ending_question,
    shared_runs,
    words,
)

HARD = "hard"
WARN = "warn"
SEVERITIES = (HARD, WARN)

AGENDA_RUN_WORDS = 5
# Agenda numbers from this value (3+ digits) are secrets: a price floor, a
# budget. Smaller ones ("two offers") are ordinary talk.
SECRET_NUMBER_MIN = 100


@dataclass(frozen=True)
class CheckSpec:
    letter: str
    name: str
    title: str
    scope: str  # "turn" or "run"


CHECKS: Tuple[CheckSpec, ...] = (
    CheckSpec("a", "repetition", "No repeat of the previous NPC line", "turn"),
    CheckSpec("b", "agenda_leak", "Hidden agenda never said aloud", "turn"),
    CheckSpec("c", "authored_state", "An authored state variable moved", "run"),
    CheckSpec("d", "rubric_ids", "Debrief scores the rubric's own ids", "run"),
    CheckSpec("e", "debrief", "Debrief generated, no template fallback", "run"),
    CheckSpec("f", "turn_fallback", "No turn fell back to the canned line", "turn"),
)
CHECKS_BY_LETTER: Dict[str, CheckSpec] = {c.letter: c for c in CHECKS}

# (c) and (d) fail until the engine wires authored state and the rubric
# (fixes 3 and 4 of issue #580), so they report as warnings unless --strict.
DEFAULT_SEVERITY: Dict[str, str] = {
    "a": HARD, "b": HARD, "c": WARN, "d": WARN, "e": HARD, "f": HARD,
}


def check_letter(token: str) -> str:
    """Map a check letter or name (``a``, ``repetition``) to its letter."""
    t = token.strip().lower()
    if t in CHECKS_BY_LETTER:
        return t
    for spec in CHECKS:
        if t == spec.name:
            return spec.letter
    known = ", ".join(f"{c.letter}/{c.name}" for c in CHECKS)
    raise ValueError(f"unknown check {token!r} (known: {known})")


def resolve_severity(
    *,
    strict: bool = False,
    hard: Iterable[str] = (),
    warn: Iterable[str] = (),
) -> Dict[str, str]:
    """The severity of each check: the defaults, then ``warn``, then ``hard``.

    ``strict`` makes every check hard and wins over everything else. A check
    named in both ``hard`` and ``warn`` is a usage error.
    """
    hard_set = {check_letter(h) for h in hard}
    warn_set = {check_letter(w) for w in warn}
    both = hard_set & warn_set
    if both:
        raise ValueError(f"checks named both hard and warn: {', '.join(sorted(both))}")
    severity = dict(DEFAULT_SEVERITY)
    for letter in warn_set:
        severity[letter] = WARN
    for letter in hard_set:
        severity[letter] = HARD
    if strict:
        severity = {letter: HARD for letter in severity}
    return severity


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """One failed assertion: which turn (None for a per-run check), and why."""

    message: str
    turn: Optional[int] = None
    evidence: Optional[str] = None


@dataclass
class CheckResult:
    letter: str
    name: str
    title: str
    scope: str
    severity: str
    passed: bool
    findings: List[Finding] = field(default_factory=list)
    # What the check saw when it passed (or the context of a failure), for the
    # summary: e.g. which authored variables moved.
    detail: str = ""

    @property
    def status(self) -> str:
        if self.passed:
            return "pass"
        return "FAIL" if self.severity == HARD else "warn"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status
        return d


def run_verdict(results: Sequence[CheckResult], *, error: Optional[str] = None) -> str:
    """``fail`` on a hard failure or a run that could not finish, ``warn`` on a
    warning only, else ``pass``."""
    if error:
        return "fail"
    if any(not r.passed and r.severity == HARD for r in results):
        return "fail"
    if any(not r.passed for r in results):
        return "warn"
    return "pass"


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------

# ``words``, ``shared_runs`` and ``ending_question``, with ``REPEAT_RUN_WORDS``
# (6) and ``SAME_QUESTION_MIN_WORDS`` (4, so "Okay?" or "Right?" twice in a
# row is a tic, not a loop), are the engine's own, imported above from
# ``convsim_prompt.repetition``: check (a) counts a repeat exactly as the
# engine's repetition guard does. They keep their names here.


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

# A number in digits: thousands grouped with commas ("13,800") or periods
# ("13.800", the Spanish way), or plain digits; then optional decimals, which
# are dropped ("13,800.00"), and an optional "k"/"thousand" multiplier
# ("13.8k"). A "$" or "€" in front is not part of the match, so "$13,800",
# "13,800" and "13800" all read 13800, while "8.50" reads 8.
_DIGIT_NUMBER = re.compile(
    r"(?<![\w.,])"
    r"(\d{1,3}(?:,\d{3})+(?!\d)|\d{1,3}(?:\.\d{3})+(?![\d,])|\d+)"
    r"(?:[.,](\d+))?"
    r"(?:\s?(k|thousand)\b)?",
    re.IGNORECASE,
)

_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
# Which kind of number word may follow which, in standard English numerals
# ("thirteen thousand eight hundred and fifty", "fifteen hundred", "a
# thousand"). Anything else ends the number, so "five, six hundred" is two.
_WORD_FOLLOWS = {
    None: {"unit", "teen", "tens", "a"},
    "unit": {"hundred", "thousand"},
    "teen": {"hundred", "thousand"},
    "tens": {"unit", "thousand"},
    "hundred": {"unit", "teen", "tens", "thousand", "and"},
    "thousand": {"unit", "teen", "tens", "and"},
    "and": {"unit", "teen", "tens"},
    "a": {"hundred", "thousand"},
}
# Dealer shorthand: "thirteen-eight" is 13,800. Only a teen hyphenated to a
# single digit, which is never a standard English numeral ("twenty-five" is).
_DEALER_SHORTHAND = re.compile(
    r"\b(" + "|".join(_TEENS) + r")[-‐‑–](" + "|".join(_UNITS) + r")\b"
)


def _word_kind(token: str) -> Tuple[Optional[str], int]:
    if token in _UNITS:
        return "unit", _UNITS[token]
    if token in _TEENS:
        return "teen", _TEENS[token]
    if token in _TENS:
        return "tens", _TENS[token]
    if token in ("hundred", "thousand", "and", "a"):
        return token, 0
    return None, 0


def _word_numbers(tokens: Sequence[str]) -> List[Tuple[int, str]]:
    """English numerals in ``tokens``, as ``(value, the words)``."""
    out: List[Tuple[int, str]] = []
    total = current = 0
    last: Optional[str] = None
    start = 0
    best: Optional[Tuple[int, int]] = None  # (value, end) of the longest valid prefix

    def flush() -> None:
        if best is not None:
            out.append((best[0], " ".join(tokens[start:best[1]])))

    for i, token in enumerate(tokens):
        kind, value = _word_kind(token)
        if last is not None and kind not in _WORD_FOLLOWS[last]:
            flush()
            total = current = 0
            last, best = None, None
        if last is None:
            if kind not in _WORD_FOLLOWS[None]:
                continue
            start = i
        if kind in ("unit", "teen", "tens"):
            current += value
        elif kind == "a":
            current = 1
        elif kind == "hundred":
            current = (current or 1) * 100
        elif kind == "thousand":
            total += (current or 1) * 1000
            current = 0
        last = kind
        if kind not in ("and", "a"):
            best = (total + current, i + 1)
    flush()
    return out


def numbers_in(text: str) -> List[Tuple[int, str]]:
    """The whole numbers ``text`` says, as ``(value, how it was written)``.

    Digits in any of the forms ``_DIGIT_NUMBER`` reads, English numerals
    ("thirteen thousand eight hundred") and dealer shorthand
    ("thirteen-eight"). Decimals are dropped. Numbers in other languages'
    words are not read; digits are.
    """
    found: List[Tuple[int, str]] = []
    folded = unicodedata.normalize("NFKC", text or "")
    for m in _DIGIT_NUMBER.finditer(folded):
        whole = int(re.sub(r"[,.]", "", m.group(1)))
        if m.group(3):
            fraction = float("0." + m.group(2)) if m.group(2) else 0.0
            value = int(round((whole + fraction) * 1000))
        else:
            value = whole
        found.append((value, m.group(0).strip()))
    lowered = folded.casefold()
    for m in _DEALER_SHORTHAND.finditer(lowered):
        found.append((_TEENS[m.group(1)] * 1000 + _UNITS[m.group(2)] * 100, m.group(0)))
    found.extend(_word_numbers(words(lowered)))
    return found


def secret_numbers(hidden_agenda: Sequence[str]) -> Dict[int, Tuple[int, str]]:
    """``value -> (agenda item, as written)`` for each 3+ digit agenda number."""
    secrets: Dict[int, Tuple[int, str]] = {}
    for index, item in enumerate(hidden_agenda, start=1):
        for value, written in numbers_in(item):
            if value >= SECRET_NUMBER_MIN and value not in secrets:
                secrets[value] = (index, written)
    return secrets


# ---------------------------------------------------------------------------
# Transcript shape
# ---------------------------------------------------------------------------

NPC_ROLES = ("npc_opening", "npc")


@dataclass(frozen=True)
class NpcLine:
    """One NPC line. ``turn`` is the game turn; 0 is the authored opening."""

    turn: int
    text: str
    authored: bool = False


def npc_lines_from_transcript(entries: Iterable[Mapping[str, Any]]) -> List[NpcLine]:
    """NPC lines from ``GET /api/sessions/{id}/transcript`` ``turns``.

    The transcript stores the opening at ``turn_number`` 0, a player line at
    ``2n - 1`` and the NPC's reply to it at ``2n``.
    """
    lines: List[NpcLine] = []
    for e in sorted(entries, key=lambda e: int(e.get("turn_number") or 0)):
        role = e.get("role")
        if role not in NPC_ROLES:
            continue
        number = int(e.get("turn_number") or 0)
        lines.append(NpcLine(
            turn=0 if role == "npc_opening" else number // 2,
            text=str(e.get("content") or ""),
            authored=role == "npc_opening",
        ))
    return lines


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def find_repetition(
    lines: Sequence[NpcLine],
    *,
    min_run: int = REPEAT_RUN_WORDS,
    min_question: int = SAME_QUESTION_MIN_WORDS,
) -> List[Finding]:
    """(a) Each generated NPC line against the NPC line before it.

    A shared closing question counts from ``min_question`` words, so a short
    tag ("Okay?") said twice is not a repeat.
    """
    findings: List[Finding] = []
    for prev, line in zip(lines, lines[1:]):
        if line.authored:
            continue
        runs = shared_runs(words(line.text), words(prev.text), min_run)
        if runs:
            findings.append(Finding(
                turn=line.turn,
                message=(
                    f"repeats {_runs_text(runs)} of the previous NPC line (turn {prev.turn})"
                ),
                evidence=" / ".join(" ".join(r) for r in runs),
            ))
        q = ending_question(line.text)
        if q is not None and len(q) >= min_question and q == ending_question(prev.text):
            findings.append(Finding(
                turn=line.turn,
                message=f"ends with the same question as the previous NPC line (turn {prev.turn})",
                evidence=" ".join(q),
            ))
    return findings


def find_agenda_leaks(
    lines: Sequence[NpcLine],
    hidden_agenda: Sequence[str],
    *,
    min_run: int = AGENDA_RUN_WORDS,
) -> List[Finding]:
    """(b) Generated NPC lines that say part of the hidden agenda aloud.

    Two ways: a run of ``min_run``+ agenda words, or a number of 3+ digits
    from the agenda (a price floor, a budget) in any form ``numbers_in``
    reads, so "$13,800", "13800", "thirteen thousand eight hundred" and
    "thirteen-eight" are all Ray's floor.
    """
    agenda_words = [(i, words(item)) for i, item in enumerate(hidden_agenda, start=1)]
    secrets = secret_numbers(hidden_agenda)
    findings: List[Finding] = []
    for line in lines:
        if line.authored:
            continue
        line_words = words(line.text)
        for index, item_words in agenda_words:
            runs = shared_runs(line_words, item_words, min_run)
            if runs:
                findings.append(Finding(
                    turn=line.turn,
                    message=f"says {_runs_text(runs)} of hidden agenda item {index} aloud",
                    evidence=" / ".join(" ".join(r) for r in runs),
                ))
        said: set = set()
        for value, written in numbers_in(line.text):
            if value in secrets and value not in said:
                said.add(value)
                index, in_agenda = secrets[value]
                findings.append(Finding(
                    turn=line.turn,
                    message=f"says the number {in_agenda} of hidden agenda item {index} aloud",
                    evidence=written,
                ))
    return findings


def _runs_text(runs: Sequence[Sequence[str]]) -> str:
    sizes = ", ".join(str(len(r)) for r in runs)
    return f"a {sizes}-word run" if len(runs) == 1 else f"{len(runs)} runs ({sizes} words)"


def check_authored_state(
    turn_deltas: Sequence[Tuple[int, Mapping[str, Any]]],
    authored_variables: Iterable[str],
) -> Tuple[bool, List[Finding], str]:
    """(c) Did any turn's ``state_delta`` move a scenario-authored variable?

    ``turn_deltas`` is ``(game_turn, state_delta)`` per played turn, where
    ``state_delta`` is the change the engine applied. The engine reports a
    variable with 0 when the model proposed 0 or the move was clamped at a
    bound, so only a non-zero change counts as a move.
    """
    authored = sorted(set(authored_variables))
    if not authored:
        return True, [], "the scenario authors no variables beyond the engine baselines"
    moved: List[str] = []
    zero: Dict[str, int] = {}
    others: Dict[str, int] = {}
    for turn, delta in turn_deltas:
        for name, value in (delta or {}).items():
            if not _nonzero(value):
                if name in authored:
                    zero[name] = zero.get(name, 0) + 1
                continue
            if name in authored:
                moved.append(f"{name} {_signed(value)} (turn {turn})")
            else:
                others[name] = others.get(name, 0) + 1
    if moved:
        return True, [], "moved: " + ", ".join(moved)
    zero_text = (
        "; reported with no change: " + ", ".join(f"{n} x{c}" for n, c in sorted(zero.items()))
        if zero else ""
    )
    other_text = (
        "; moved instead: " + ", ".join(f"{n} x{c}" for n, c in sorted(others.items()))
        if others else ""
    )
    return False, [Finding(
        message=(
            f"no turn moved an authored variable ({', '.join(authored)}) "
            f"over {len(turn_deltas)} turn(s){zero_text}{other_text}"
        ),
    )], "authored: " + ", ".join(authored)


def _nonzero(value: Any) -> bool:
    """A numeric, non-zero applied change. Anything else is not a move."""
    if isinstance(value, bool):
        return False
    try:
        return float(value) != 0
    except (TypeError, ValueError):
        return False


def check_rubric_ids(
    debrief: Optional[Mapping[str, Any]],
    rubric_ids: Iterable[str],
) -> Tuple[bool, List[Finding], str]:
    """(d) The debrief scored only, and at least one of, the rubric's dimensions."""
    allowed = list(dict.fromkeys(rubric_ids))
    rubric_text = "rubric: " + ", ".join(allowed)
    scores = debrief.get("scores") if debrief else None
    if not isinstance(scores, Mapping) or not scores:
        return False, [Finding(message="the debrief scored no rubric dimension")], rubric_text
    invented = [k for k in scores if k not in allowed]
    scored = [k for k in scores if k in allowed]
    if invented:
        return False, [Finding(
            message=(
                f"{len(invented)} of {len(scores)} scored id(s) are not in the rubric"
            ),
            evidence=", ".join(invented),
        )], rubric_text + "; matched: " + (", ".join(scored) or "none")
    return True, [], "scored: " + ", ".join(scored)


def check_debrief(
    status: Optional[int],
    debrief: Optional[Mapping[str, Any]],
    *,
    error: Optional[str] = None,
) -> Tuple[bool, List[Finding], str]:
    """(e) ``POST /debrief`` answered 200 and did not use the template fallback."""
    if status != 200:
        what = f"HTTP {status}" if status is not None else "no response"
        msg = f"the debrief did not generate ({what})"
        if error:
            msg += f": {_clip(error)}"
        return False, [Finding(message=msg)], ""
    fallback = (debrief or {}).get("used_fallback")
    if fallback is not False:
        msg = (
            "the debrief used the template fallback" if fallback
            else "the debrief response does not say whether it used the fallback"
        )
        return False, [Finding(message=msg)], ""
    return True, [], "HTTP 200, used_fallback false"


def find_fallback_turns(
    turn_flags: Sequence[Tuple[int, Any]],
    lines: Sequence[NpcLine] = (),
    *,
    fallback_utterance: Optional[str] = None,
) -> List[Finding]:
    """(f) Turns whose NPC reply was the engine's canned safe fallback line.

    ``turn_flags`` is ``(game_turn, timing.fallback)`` per played turn: the
    flag the engine sets when the parser gave up and spoke
    ``SAFE_FALLBACK_UTTERANCE`` instead of the model's reply. A turn with no
    timing record (an input safety stop) has None. ``lines`` and
    ``fallback_utterance`` catch the same turn by its words, which also works
    for a record whose flag is missing.
    """
    found: Dict[int, Finding] = {}
    for turn, flag in turn_flags:
        if flag is True:
            found[turn] = Finding(
                turn=turn,
                message="the engine fell back to its canned safe line (timing.fallback true)",
            )
    canned = words(fallback_utterance) if fallback_utterance else []
    if canned:
        for line in lines:
            if line.authored or line.turn in found:
                continue
            if words(line.text) == canned:
                found[line.turn] = Finding(
                    turn=line.turn,
                    message="the NPC said the engine's canned safe fallback line",
                    evidence=_clip(line.text),
                )
    return [found[t] for t in sorted(found)]


def _signed(value: Any) -> str:
    try:
        return f"{int(value):+d}"
    except (TypeError, ValueError):
        return str(value)


def evaluate_run(
    *,
    npc_lines: Sequence[NpcLine],
    turn_deltas: Sequence[Tuple[int, Mapping[str, Any]]],
    debrief_status: Optional[int],
    debrief: Optional[Mapping[str, Any]],
    hidden_agenda: Sequence[str],
    authored_variables: Iterable[str],
    rubric_ids: Iterable[str],
    severity: Optional[Mapping[str, str]] = None,
    debrief_error: Optional[str] = None,
    turn_fallbacks: Sequence[Tuple[int, Any]] = (),
    fallback_utterance: Optional[str] = None,
) -> List[CheckResult]:
    """All six checks over one played conversation, in letter order."""
    sev = dict(DEFAULT_SEVERITY)
    if severity:
        sev.update(severity)

    generated = sum(1 for line in npc_lines if not line.authored)
    rep = find_repetition(npc_lines)
    leak = find_agenda_leaks(npc_lines, hidden_agenda)
    secrets = secret_numbers(hidden_agenda)
    fallback = find_fallback_turns(
        turn_fallbacks, npc_lines, fallback_utterance=fallback_utterance
    )
    outcomes: Dict[str, Tuple[bool, List[Finding], str]] = {
        "a": (not rep, rep, f"{generated} generated NPC line(s) checked"),
        "b": (not leak, leak, (
            f"{len(hidden_agenda)} agenda item(s) and {len(secrets)} agenda number(s) checked"
        )),
        "c": check_authored_state(turn_deltas, authored_variables),
        "d": check_rubric_ids(debrief, rubric_ids),
        "e": check_debrief(debrief_status, debrief, error=debrief_error),
        "f": (not fallback, fallback, f"{generated} generated NPC line(s) checked"),
    }
    results: List[CheckResult] = []
    for spec in CHECKS:
        passed, findings, detail = outcomes[spec.letter]
        results.append(CheckResult(
            letter=spec.letter,
            name=spec.name,
            title=spec.title,
            scope=spec.scope,
            severity=sev[spec.letter],
            passed=passed,
            findings=findings,
            detail=detail,
        ))
    return results


# ---------------------------------------------------------------------------
# Authored facts
# ---------------------------------------------------------------------------


def hidden_agenda(npc_doc: Mapping[str, Any]) -> List[str]:
    """``private_persona.hidden_agenda`` of a parsed NPC file."""
    persona = npc_doc.get("private_persona") or {}
    items = persona.get("hidden_agenda") or []
    return [str(i) for i in items if str(i).strip()]


def authored_variables(scenario_doc: Mapping[str, Any], baseline: Iterable[str]) -> List[str]:
    """The scenario's ``state.variables`` that are not engine baseline variables.

    A scenario can re-declare a baseline name (the_ask's ``rapport``); that one
    moves for every scenario, so it does not show the scenario's own state
    being played.
    """
    variables = ((scenario_doc.get("state") or {}).get("variables")) or {}
    base = set(baseline)
    return [name for name in variables if name not in base]


def rubric_dimension_ids(rubric_doc: Mapping[str, Any]) -> List[str]:
    """The ``dimensions[].id`` of a parsed rubric file."""
    return [str(d["id"]) for d in rubric_doc.get("dimensions") or [] if isinstance(d, Mapping) and d.get("id")]


def parse_demo_scenarios(edition_source: str) -> List[Tuple[str, str]]:
    """``(pack_id, scenario_id)`` of ``DEMO_SCENARIOS`` in edition.py's source.

    Read from the source rather than imported, so the replay runs with the
    standard library and PyYAML only (edition.py imports FastAPI).
    """
    value = _module_assignment(edition_source, "DEMO_SCENARIOS")
    if not isinstance(value, (ast.Tuple, ast.List)):
        raise ValueError("DEMO_SCENARIOS is not a tuple literal")
    out: List[Tuple[str, str]] = []
    for elt in value.elts:
        if not isinstance(elt, ast.Call):
            raise ValueError("DEMO_SCENARIOS entry is not a DemoScenario(...) call")
        args = [ast.literal_eval(a) for a in elt.args]
        kwargs = {k.arg: ast.literal_eval(k.value) for k in elt.keywords}
        pack_id = args[0] if len(args) > 0 else kwargs["pack_id"]
        scenario_id = args[1] if len(args) > 1 else kwargs["scenario_id"]
        out.append((str(pack_id), str(scenario_id)))
    return out


def parse_baseline_variables(scenario_state_source: str) -> List[str]:
    """The names in ``BASELINE_VARIABLES`` of scenario_state.py's source."""
    value = _module_assignment(scenario_state_source, "BASELINE_VARIABLES")
    if not isinstance(value, ast.Dict):
        raise ValueError("BASELINE_VARIABLES is not a dict literal")
    return [str(ast.literal_eval(k)) for k in value.keys if k is not None]


def parse_string_constant(source: str, name: str) -> str:
    """A module-level string constant of a Python source, such as
    ``SAFE_FALLBACK_UTTERANCE`` in the prompt composer's turn_output.py."""
    value = ast.literal_eval(_module_assignment(source, name))
    if not isinstance(value, str):
        raise ValueError(f"{name} is not a string literal")
    return value


def _module_assignment(source: str, name: str) -> ast.expr:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and node.value is not None:
            return node.value
    raise ValueError(f"{name} is not assigned at module level")
