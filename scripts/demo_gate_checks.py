# SPDX-License-Identifier: Apache-2.0
"""The assertions of the D-05 automated pre-check (issue #580).

``scripts/demo-gate-replay.py`` plays the five demo conversations against a
running convsim-core and hands what came back to the functions here. Every
function is pure: it takes plain data (lines of a transcript, a turn's
``state_delta``, a debrief body, the text of an authored file) and returns
findings, so the checks are unit-tested on synthetic transcripts in
``tests/acceptance/test_demo_gate_checks.py`` without a model or a server.

Standard library only. The replay parses the pack YAML with PyYAML and passes
the parsed documents in.

The five checks, with the letters the issue and the demo doc use:

  (a) repetition      per turn: no run of 6+ consecutive words shared with the
                      previous NPC line, and no NPC line ending with the same
                      question as the previous one.
  (b) agenda_leak     per turn: no run of 5+ consecutive words from the NPC's
                      ``private_persona.hidden_agenda`` said aloud.
  (c) authored_state  per run: some turn's ``state_delta`` moved a variable
                      the scenario authors (not an engine baseline variable).
  (d) rubric_ids      per run: the debrief scored at least one dimension, and
                      only the scenario rubric's dimension ids.
  (e) debrief         per run: the debrief generated (HTTP 200) without the
                      template fallback.

Words are compared case- and punctuation-insensitively: text is NFKC
normalised and case-folded, apostrophes are dropped (so "What's" and
"What’s" are one word), and every other non-word character separates words.
"""
from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

HARD = "hard"
WARN = "warn"
SEVERITIES = (HARD, WARN)

REPEAT_RUN_WORDS = 6
AGENDA_RUN_WORDS = 5


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
)
CHECKS_BY_LETTER: Dict[str, CheckSpec] = {c.letter: c for c in CHECKS}

# (c) and (d) fail until the engine wires authored state and the rubric
# (fixes 3 and 4 of issue #580), so they report as warnings unless --strict.
DEFAULT_SEVERITY: Dict[str, str] = {"a": HARD, "b": HARD, "c": WARN, "d": WARN, "e": HARD}


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

_APOSTROPHES = re.compile(r"['‘’ʼ`´]")
_WORD = re.compile(r"\w+")


def words(text: str) -> List[str]:
    """Case- and punctuation-insensitive words of ``text``."""
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    return _WORD.findall(_APOSTROPHES.sub("", folded))


def shared_runs(a: Sequence[str], b: Sequence[str], min_len: int) -> List[List[str]]:
    """Runs of ``min_len``+ consecutive words that appear in both ``a`` and ``b``.

    Each run is maximal (it cannot be extended on either side), and runs do not
    overlap in ``a``: the longest are kept first. Returned in ``a``'s order.
    """
    n, m = len(a), len(b)
    # common[i][j]: length of the common run ending at a[i-1] and b[j-1].
    common = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                common[i][j] = common[i - 1][j - 1] + 1
    candidates: List[Tuple[int, int]] = []  # (length, start in a)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            length = common[i][j]
            if length < min_len:
                continue
            if i < n and j < m and a[i] == b[j]:
                continue  # extends further; the longer run is collected later
            candidates.append((length, i - length))
    taken: List[Tuple[int, int]] = []  # (start, end) in a
    for length, start in sorted(candidates, key=lambda c: (-c[0], c[1])):
        end = start + length
        if any(start < t_end and t_start < end for t_start, t_end in taken):
            continue
        taken.append((start, end))
    return [list(a[s:e]) for s, e in sorted(taken)]


_CLOSERS = "\"'”’»)]*_ \t\r\n"
_QUESTION_MARKS = ("?", "？")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…！？。])\s+")


def ending_question(text: str) -> Optional[Tuple[str, ...]]:
    """The words of the question ``text`` ends with, or None if it ends otherwise.

    The question is the last sentence, where sentences break at whitespace after
    ``.``, ``!``, ``?`` or an ellipsis (so "8.50" stays one sentence). Spanish
    "¿...?" questions work the same way: the opening mark is punctuation.
    """
    s = (text or "").rstrip(_CLOSERS)
    if not s.endswith(_QUESTION_MARKS):
        return None
    last = _SENTENCE_BREAK.split(s)[-1]
    w = tuple(words(last))
    return w or None


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
    lines: Sequence[NpcLine], *, min_run: int = REPEAT_RUN_WORDS
) -> List[Finding]:
    """(a) Each generated NPC line against the NPC line before it."""
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
        if q is not None and q == ending_question(prev.text):
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
    """(b) Generated NPC lines that say part of the hidden agenda aloud."""
    agenda_words = [(i, words(item)) for i, item in enumerate(hidden_agenda, start=1)]
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
    return findings


def _runs_text(runs: Sequence[Sequence[str]]) -> str:
    sizes = ", ".join(str(len(r)) for r in runs)
    return f"a {sizes}-word run" if len(runs) == 1 else f"{len(runs)} runs ({sizes} words)"


def check_authored_state(
    turn_deltas: Sequence[Tuple[int, Mapping[str, Any]]],
    authored_variables: Iterable[str],
) -> Tuple[bool, List[Finding], str]:
    """(c) Did any turn's ``state_delta`` move a scenario-authored variable?

    ``turn_deltas`` is ``(game_turn, state_delta)`` per played turn.
    """
    authored = sorted(set(authored_variables))
    if not authored:
        return True, [], "the scenario authors no variables beyond the engine baselines"
    moved: List[str] = []
    others: Dict[str, int] = {}
    for turn, delta in turn_deltas:
        for name, value in (delta or {}).items():
            if name in authored:
                moved.append(f"{name} {_signed(value)} (turn {turn})")
            else:
                others[name] = others.get(name, 0) + 1
    other_text = (
        "; moved instead: " + ", ".join(f"{n} x{c}" for n, c in sorted(others.items()))
        if others else ""
    )
    if moved:
        return True, [], "moved: " + ", ".join(moved)
    return False, [Finding(
        message=(
            f"no turn moved an authored variable ({', '.join(authored)}) "
            f"over {len(turn_deltas)} turn(s){other_text}"
        ),
    )], "authored: " + ", ".join(authored)


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
) -> List[CheckResult]:
    """All five checks over one played conversation, in letter order."""
    sev = dict(DEFAULT_SEVERITY)
    if severity:
        sev.update(severity)

    generated = sum(1 for line in npc_lines if not line.authored)
    rep = find_repetition(npc_lines)
    leak = find_agenda_leaks(npc_lines, hidden_agenda)
    outcomes: Dict[str, Tuple[bool, List[Finding], str]] = {
        "a": (not rep, rep, f"{generated} generated NPC line(s) checked"),
        "b": (not leak, leak, f"{len(hidden_agenda)} agenda item(s) checked"),
        "c": check_authored_state(turn_deltas, authored_variables),
        "d": check_rubric_ids(debrief, rubric_ids),
        "e": check_debrief(debrief_status, debrief, error=debrief_error),
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
