#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a pack's flyting calibration suites against the volley scoring pipeline.

A calibration suite (``<pack>/calibration/*.yaml``, validated by
``schemas/flyting-calibration.schema.json``) is a set of reference volleys with
the outcome each one must receive. It exists to catch drift: a change to the
Stage 0 gates, the cliché corpus, the craft metrics, or the judge prompt that
quietly moves scoring is a change players feel before anyone else notices.

Two tiers of expectation, because only one of them is deterministic:

*   **Mechanical** — ``gate``, ``foul``, ``flags``, and the plagiarism score cap.
    These are pure functions of the volley and the pack, identical on every
    machine with no model present, so they run in CI on every commit (see
    ``services/convsim-core/tests/test_flyting_calibration.py``).
*   **Judged** — ``band``, ``min_score``, ``max_score``, ``hooks``. These need a
    judge, so they are skipped unless ``--judge RUNTIME_ID`` names a runtime to
    score with; that is the nightly, recommended-model run.

Usage:
    python scripts/flyting-calibration.py                      # every official pack
    python scripts/flyting-calibration.py --pack packs/official/flyting-school
    python scripts/flyting-calibration.py --judge llama_cpp    # include judged tiers
    python scripts/flyting-calibration.py --judge llama_cpp --limit 4   # a bounded sample
    python scripts/flyting-calibration.py --json report.json

Exit codes:
    0  Every checked expectation held (skipped judged tiers are not failures).
    1  At least one expectation failed, or a suite could not be loaded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

REPO_ROOT = Path(__file__).parent.parent
OFFICIAL_PACKS = REPO_ROOT / "packs" / "official"

# convsim-core is normally pip-installed (``pip install -e services/convsim-core``).
# Fall back to the source tree so the script runs from a bare checkout.
for _candidate in (REPO_ROOT / "services" / "convsim-core", REPO_ROOT / "packages" / "prompt-composer" / "src"):
    if str(_candidate) not in sys.path:
        sys.path.append(str(_candidate))

from convsim_core.flyting.loader import FlytingScenario, load_flyting_scenario  # noqa: E402
from convsim_core.flyting.service import VolleyScoringService  # noqa: E402
from convsim_core.flyting.volley import VolleyInputError  # noqa: E402

# Expectation keys that need a judge; everything else is deterministic.
JUDGED_KEYS = frozenset({"band", "min_score", "max_score", "hooks"})


@dataclass
class VolleyResult:
    """One reference volley, checked."""

    volley_id: str
    score: int
    band: str
    failures: List[str] = field(default_factory=list)
    checked: int = 0
    skipped: int = 0
    # What the volley actually scored on, so a report is enough to retune a
    # suite or to see which half of the pipeline moved. Empty on a run with no
    # judge, where the mechanical fallback produced the score.
    dimensions: Dict[str, int] = field(default_factory=dict)
    hooks: List[str] = field(default_factory=list)
    dropped_hooks: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.volley_id,
            "score": self.score,
            "band": self.band,
            "checked": self.checked,
            "skipped": self.skipped,
            "failures": list(self.failures),
            "dimensions": dict(self.dimensions),
            "hooks": list(self.hooks),
            "dropped_hooks": list(self.dropped_hooks),
            "flags": list(self.flags),
        }


@dataclass
class SuiteResult:
    """One calibration file, run end to end."""

    path: str
    scenario_id: str
    volleys: List[VolleyResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.errors) or any(v.failures for v in self.volleys)

    @property
    def checked(self) -> int:
        return sum(v.checked for v in self.volleys)

    @property
    def skipped(self) -> int:
        return sum(v.skipped for v in self.volleys)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "scenario_id": self.scenario_id,
            "checked": self.checked,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "volleys": [v.to_dict() for v in self.volleys],
        }


def _load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _flyting_scenarios(pack_dir: Path) -> Dict[str, FlytingScenario]:
    """Every ``mode: flyting`` scenario in a pack, by scenario_id."""
    found: Dict[str, FlytingScenario] = {}
    scenarios_dir = pack_dir / "scenarios"
    if not scenarios_dir.is_dir():
        return found
    for path in sorted(scenarios_dir.glob("*.yaml")):
        scenario = load_flyting_scenario(pack_dir, f"scenarios/{path.name}")
        if scenario is not None:
            found[scenario.scenario_id] = scenario
    return found


def _check_volley(
    volley_id: str,
    expect: Dict[str, Any],
    score: Any,
    *,
    judged: bool,
) -> VolleyResult:
    """Compare one scored volley against its expectations."""
    result = VolleyResult(volley_id=volley_id, score=score.score, band=score.band)
    gate = score.gate
    result.flags = list(score.flags)
    if score.judgment is not None:
        result.dimensions = {k: int(v) for k, v in score.judgment.dimensions().items()}
        result.hooks = [h.trait for h in score.judgment.hooks]
        result.dropped_hooks = [
            f"{d.trait}:{d.reason}" for d in score.judgment.dropped_hooks
        ]

    if "gate" in expect:
        result.checked += 1
        actual = gate.outcome.value
        if actual != expect["gate"]:
            result.failures.append(f"gate: expected {expect['gate']}, got {actual}")

    if "foul" in expect:
        result.checked += 1
        actual_foul = gate.foul.value if gate.foul is not None else None
        if actual_foul != expect["foul"]:
            result.failures.append(f"foul: expected {expect['foul']}, got {actual_foul}")

    for flag in expect.get("flags") or []:
        # judge_unavailable is a property of the run, not of the volley: it is
        # present exactly when no judge scored it, which both tiers already know.
        if flag == "judge_unavailable":
            continue
        result.checked += 1
        if flag not in score.flags:
            result.failures.append(f"flag {flag!r} missing (flags: {score.flags or 'none'})")

    # A capped volley respects its cap whatever the judge says, so the cap half of
    # max_score is deterministic even when the rest of the band is not.
    cap = gate.score_cap
    expected_max = expect.get("max_score")
    if cap is not None and isinstance(expected_max, int):
        result.checked += 1
        if score.score > min(cap, expected_max):
            result.failures.append(
                f"score {score.score} exceeds the capped maximum {min(cap, expected_max)}"
            )

    judged_keys = [key for key in expect if key in JUDGED_KEYS]
    if not judged:
        result.skipped += len(judged_keys)
        return result

    if "band" in expect:
        result.checked += 1
        if score.band != expect["band"]:
            result.failures.append(
                f"band: expected {expect['band']}, got {score.band} (score {score.score})"
            )
    if isinstance(expect.get("min_score"), int):
        result.checked += 1
        if score.score < expect["min_score"]:
            result.failures.append(f"score {score.score} below min_score {expect['min_score']}")
    if isinstance(expected_max, int) and cap is None:
        result.checked += 1
        if score.score > expected_max:
            result.failures.append(f"score {score.score} above max_score {expected_max}")
    if "hooks" in expect:
        result.checked += 1
        landed = {h.trait for h in (score.judgment.hooks if score.judgment else [])}
        missing = sorted(set(expect["hooks"]) - landed)
        if missing:
            result.failures.append(
                "hooks not verified: " + ", ".join(missing)
                + (f" (landed: {', '.join(sorted(landed))})" if landed else " (none landed)")
            )
    return result


async def _score_with_judge(
    service: VolleyScoringService,
    scenario: FlytingScenario,
    text: str,
    runtime: Any,
) -> Any:
    """Score one volley through the full pipeline, judge call included."""
    from convsim_core.flyting.pipeline import judge_volley

    prepared = service.prepare(text)
    judgment = await judge_volley(prepared, service, runtime, speaker="player")
    return service.compose(prepared, judgment, volley_number=1)


def _entries_for(data: Dict[str, Any], limit: Optional[int]) -> List[Dict[str, Any]]:
    """The volleys to run, trimmed to ``limit`` if one was given.

    A limited run is a *sample*, and the only expensive volleys are the ones a
    judge has to read, so the budget goes to the volleys carrying judged
    expectations. Gated volleys never reach the model anyway.
    """
    entries = [entry for entry in (data.get("volleys") or []) if isinstance(entry, dict)]
    if limit is None or limit >= len(entries):
        return entries
    judged_first = sorted(
        entries,
        key=lambda e: not any(k in JUDGED_KEYS for k in (e.get("expect") or {})),
    )
    chosen = {id(e) for e in judged_first[: max(0, limit)]}
    # Keep file order, so a report reads in the order the suite was authored.
    return [entry for entry in entries if id(entry) in chosen]


def run_suite(
    path: Path,
    scenarios: Dict[str, FlytingScenario],
    *,
    runtime: Any = None,
    limit: Optional[int] = None,
) -> SuiteResult:
    """Run one calibration file and return its result."""
    data = _load_yaml(path)
    scenario_id = str(data.get("scenario_id") or "")
    result = SuiteResult(
        path=str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        scenario_id=scenario_id,
    )

    scenario = scenarios.get(scenario_id)
    if scenario is None:
        result.errors.append(
            f"scenario_id {scenario_id!r} is not a mode: flyting scenario in this pack"
        )
        return result

    service = VolleyScoringService(scenario.scoring_context())
    for entry in _entries_for(data, limit):
        volley_id = str(entry.get("id") or "<unnamed>")
        text = str(entry.get("text") or "")
        expect = entry.get("expect")
        expect = expect if isinstance(expect, dict) else {}
        try:
            if runtime is None:
                score = service.score_mechanically(text, volley_number=1)
            else:
                score = asyncio.run(_score_with_judge(service, scenario, text, runtime))
        except VolleyInputError as exc:
            result.errors.append(f"{volley_id}: {exc}")
            continue
        result.volleys.append(
            _check_volley(volley_id, expect, score, judged=runtime is not None)
        )
    return result


def run_pack(
    pack_dir: Path, *, runtime: Any = None, limit: Optional[int] = None
) -> List[SuiteResult]:
    """Run every calibration suite in one pack."""
    calibration_dir = pack_dir / "calibration"
    if not calibration_dir.is_dir():
        return []
    scenarios = _flyting_scenarios(pack_dir)
    return [
        run_suite(path, scenarios, runtime=runtime, limit=limit)
        for path in sorted(calibration_dir.glob("*.yaml"))
    ]


def default_pack_dirs() -> List[Path]:
    """Official packs that ship a calibration suite."""
    if not OFFICIAL_PACKS.is_dir():
        return []
    return [
        entry
        for entry in sorted(OFFICIAL_PACKS.iterdir())
        if entry.is_dir() and (entry / "calibration").is_dir()
    ]


def report(results: Sequence[SuiteResult], *, judged: bool, quiet: bool = False) -> int:
    """Print a human-readable report and return the exit code."""
    failed = False
    for suite in results:
        status = "FAIL" if suite.failed else "ok"
        if not quiet or suite.failed:
            print(f"{status:>4}  {suite.path}  ({suite.checked} checked, {suite.skipped} skipped)")
        for error in suite.errors:
            print(f"        ! {error}")
        for volley in suite.volleys:
            for failure in volley.failures:
                print(f"        ! {volley.volley_id}: {failure}")
        failed = failed or suite.failed

    checked = sum(s.checked for s in results)
    skipped = sum(s.skipped for s in results)
    print()
    if not results:
        print("No calibration suites found.")
        return 0
    if skipped and not judged:
        print(
            f"{skipped} judged expectation(s) skipped — pass --judge RUNTIME_ID to "
            "check bands and hooks against a model."
        )
    if failed:
        print(f"Flyting calibration FAILED ({checked} expectations checked).")
        return 1
    print(f"Flyting calibration PASSED ({checked} expectations checked).")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pack",
        action="append",
        default=None,
        help="Pack directory to run (repeatable). Defaults to every official pack "
             "with a calibration/ directory.",
    )
    parser.add_argument(
        "--judge",
        default=None,
        metavar="RUNTIME_ID",
        help="Runtime id to judge with (e.g. llama_cpp). Without it, only the "
             "deterministic expectations are checked.",
    )
    parser.add_argument("--json", default=None, help="Write the full report to this path.")
    parser.add_argument("--quiet", action="store_true", help="Print failures only.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Check at most this many volleys per suite, judged ones first. One "
             "judge call per volley is the whole cost of a judged run, so this is "
             "how a judged sample is kept inside a time budget.",
    )
    args = parser.parse_args(argv)

    pack_dirs = [Path(p) for p in args.pack] if args.pack else default_pack_dirs()
    missing = [p for p in pack_dirs if not p.is_dir()]
    if missing:
        for path in missing:
            print(f"Pack directory not found: {path}")
        return 1

    runtime = None
    if args.judge:
        from convsim_core.runtime import build_runtime

        try:
            runtime = build_runtime(args.judge)
        except Exception as exc:  # noqa: BLE001 — a bad runtime id is a usage error
            print(f"Could not build runtime {args.judge!r}: {exc}")
            return 1

    results: List[SuiteResult] = []
    for pack_dir in pack_dirs:
        results.extend(run_pack(pack_dir, runtime=runtime, limit=args.limit))

    exit_code = report(results, judged=runtime is not None, quiet=args.quiet)

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "judged": runtime is not None,
                    "suites": [s.to_dict() for s in results],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
