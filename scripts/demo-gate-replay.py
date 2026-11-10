#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""D-05 automated pre-check: replay the five demo conversations on a real model.

Demo gate D-05 (docs/steam-next-fest-demo.md) asks that each of the five demo
conversations, played to the debrief at ``standard``, has no incoherent NPC
turn and a debrief with rubric scores and no template fallback. Issue #580
found that judging this on one hand-played sample per conversation tells a fix
from noise badly. This script makes the run repeatable: it drives a RUNNING
convsim-core over its REST API through each conversation with the scripted
player turns in ``tests/fixtures/demo-gate/player-turns.yaml``, several times
each, and asserts on every turn and every run:

  (a) repetition      no run of 6+ words shared with the previous NPC line, and
                      no NPC line ending with the same question as the last
  (b) agenda_leak     no run of 5+ words of the NPC's hidden agenda said aloud
  (c) authored_state  some turn moved a variable the scenario authors (not an
                      engine baseline variable)
  (d) rubric_ids      the debrief scored the scenario rubric's dimension ids,
                      and only those
  (e) debrief         the debrief generated (HTTP 200), used_fallback false

By default (a), (b) and (e) are hard failures and (c) and (d) are warnings:
the engine does not wire authored state or the rubric into play yet (fixes 3
and 4 of issue #580), so both fail on every run today. ``--strict`` makes all
five hard; ``--hard`` and ``--warn`` set one check at a time.

It does not start anything. Start convsim-core on the real runtime first (the
desktop app, or ``scripts/dev.sh`` with a model installed) and point ``--api``
at it. Turns take minutes on a CPU-only machine; the timeouts are generous.

Usage
-----
All five, twice each, against the default local engine::

    python scripts/demo-gate-replay.py

Two conversations, three runs each, everything hard, into a chosen folder::

    python scripts/demo-gate-replay.py --only used_car_negotiation,ask_for_raise \\
        --repeat 3 --strict --out out/demo-gate/rc1

Exercise the harness without a model (sessions pinned to the fake runtime;
not a D-05 result)::

    python scripts/demo-gate-replay.py --only behavioral_interview --repeat 1 \\
        --runtime-id fake

Output
------
``--out DIR`` (default ``out/demo-gate/<UTC time>`` under the repository root,
which git ignores) receives one ``<scenario>-run<N>.json`` per run, with the
session setup, every turn's player and NPC line, state delta, rubric
observations and timing, the debrief, the stored transcript and each check's
result, plus ``summary.md``: a table of every run against every check, the
findings with the words that tripped them, and latency (noted, not judged).
Both are rewritten after every run, so an interrupted replay keeps what it
finished.

Seeds are recorded on each session (``--seed`` is the first; run N adds N-1).
The engine does not pass a session's seed to the model yet, so runs differ
through sampling at the engine's temperature either way.

This is a pre-check, not the gate. A release candidate should pass it before
the manual D-05 run on reference hardware, which still judges what these
checks cannot: whether each reply makes sense, keeps its role and answers the
player, and whether the debrief is right about the conversation.

Exit codes
----------
0  No hard failure (warnings allowed).
1  A hard check failed, or a run could not be played to the debrief.
2  Usage or setup error: bad arguments, an engine that does not answer, a
   conversation with no scripted turns.
130  Interrupted; the summary covers the runs that finished.

Standard library and PyYAML only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only without PyYAML
    sys.stderr.write("demo-gate-replay needs PyYAML: pip install pyyaml\n")
    raise SystemExit(2)

_SCRIPTS_DIR = Path(__file__).resolve().parent
try:
    # Run as a script, its own folder is first on sys.path.
    import demo_gate_checks as checks
except ImportError:  # loaded from elsewhere by path
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import demo_gate_checks as checks

REPO_ROOT = _SCRIPTS_DIR.parent
DEFAULT_API = "http://127.0.0.1:7355"
DEFAULT_TURNS = REPO_ROOT / "tests" / "fixtures" / "demo-gate" / "player-turns.yaml"
DEFAULT_PACKS_DIR = REPO_ROOT / "packs" / "official"
EDITION_PY = REPO_ROOT / "services" / "convsim-core" / "convsim_core" / "edition.py"
SCENARIO_STATE_PY = REPO_ROOT / "services" / "convsim-core" / "convsim_core" / "scenario_state.py"

DIFFICULTIES = ("warm", "standard", "hard", "adversarial")
MODEL_FREE_RUNTIMES = ("fake", "scripted")
RECORD_SCHEMA = "convsim.demo-gate-replay/1"
FALLBACK_ROLE_NAME = "Demo Gate Tester"

# Requests that do not wait on the model.
SHORT_TIMEOUT_S = 30.0

Log = Callable[[str], None]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """A request that did not answer 2xx. ``status`` is None when nothing answered."""

    def __init__(self, method: str, path: str, status: Optional[int], detail: Any):
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail
        what = f"HTTP {status}" if status is not None else "no response"
        super().__init__(f"{method} {path}: {what}: {_detail_text(detail)}")


def _detail_text(detail: Any) -> str:
    if isinstance(detail, Mapping):
        inner = detail.get("detail", detail)
        if isinstance(inner, Mapping):
            inner = inner.get("message") or inner
        if isinstance(inner, str):
            return inner
        return json.dumps(inner, ensure_ascii=False)[:300]
    return str(detail)[:300]


class HttpTransport:
    """JSON over urllib against convsim-core's REST API."""

    def __init__(self, base_url: str):
        base = base_url.rstrip("/")
        if base.endswith("/api"):
            base = base[: -len("/api")]
        self.base_url = base

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        *,
        timeout: float = SHORT_TIMEOUT_S,
    ) -> Tuple[int, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, _parse_body(resp.read())
        except urllib.error.HTTPError as exc:
            raise ApiError(method, path, exc.code, _parse_body(exc.read())) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ApiError(method, path, None, str(reason)) from exc


def _parse_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Authored facts
# ---------------------------------------------------------------------------


@dataclass
class ScenarioFacts:
    pack_id: str
    scenario_id: str
    scenario_path: Path
    npc_path: Path
    rubric_path: Path
    npc_name: str
    hidden_agenda: List[str]
    authored_variables: List[str]
    rubric_ids: List[str]


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return doc


def find_pack_dir(packs_dir: Path, pack_id: str) -> Path:
    for manifest in sorted(packs_dir.glob("*/manifest.yaml")):
        if _load_yaml(manifest).get("pack_id") == pack_id:
            return manifest.parent
    raise FileNotFoundError(f"no pack with pack_id {pack_id!r} under {packs_dir}")


def load_scenario_facts(
    packs_dir: Path, pack_id: str, scenario_id: str, baseline: Sequence[str]
) -> ScenarioFacts:
    """What the checks compare against, read from the conversation's pack files."""
    pack_dir = find_pack_dir(packs_dir, pack_id)
    scenario_path = pack_dir / "scenarios" / f"{scenario_id}.yaml"
    scenario = _load_yaml(scenario_path)
    if scenario.get("scenario_id") != scenario_id:
        raise ValueError(f"{scenario_path} declares scenario_id {scenario.get('scenario_id')!r}")
    npc_path = (scenario_path.parent / scenario["npc"]["ref"]).resolve()
    rubric_path = (scenario_path.parent / scenario["rubric"]["ref"]).resolve()
    npc = _load_yaml(npc_path)
    rubric = _load_yaml(rubric_path)
    return ScenarioFacts(
        pack_id=pack_id,
        scenario_id=scenario_id,
        scenario_path=scenario_path,
        npc_path=npc_path,
        rubric_path=rubric_path,
        npc_name=str(npc.get("display_name") or npc.get("npc_id") or "NPC"),
        hidden_agenda=checks.hidden_agenda(npc),
        authored_variables=checks.authored_variables(scenario, baseline),
        rubric_ids=checks.rubric_dimension_ids(rubric),
    )


def demo_scenarios() -> List[Tuple[str, str]]:
    return checks.parse_demo_scenarios(EDITION_PY.read_text(encoding="utf-8"))


def baseline_variables() -> List[str]:
    return checks.parse_baseline_variables(SCENARIO_STATE_PY.read_text(encoding="utf-8"))


def load_player_turns(path: Path) -> Dict[str, List[str]]:
    """``scenario_id -> [player line, ...]`` from the player-turns file."""
    doc = _load_yaml(path)
    out: Dict[str, List[str]] = {}
    for scenario_id, entry in (doc.get("scenarios") or {}).items():
        turns = (entry or {}).get("turns") or []
        lines: List[str] = []
        for t in turns:
            text = t.get("say") if isinstance(t, Mapping) else t
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{path}: {scenario_id} has a turn with no text")
            lines.append(" ".join(text.split()))
        out[str(scenario_id)] = lines
    return out


# ---------------------------------------------------------------------------
# Playing one conversation
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event(events: Sequence[Mapping[str, Any]], event_type: str) -> Mapping[str, Any]:
    for ev in events or []:
        if ev.get("event_type") == event_type:
            return ev.get("payload") or {}
    return {}


def _quote(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def play_conversation(
    transport: Any,
    facts: ScenarioFacts,
    player_turns: Sequence[str],
    *,
    run: int,
    seed: int,
    difficulty: str = "standard",
    turn_timeout: float = 900.0,
    debrief_timeout: float = 900.0,
    runtime_id: Optional[str] = None,
    log: Log = print,
) -> Dict[str, Any]:
    """Create, start, play, end and debrief one session; return its raw record.

    Never raises on an API error: the step that failed is recorded in
    ``error`` and the session is still ended and debriefed where it exists,
    so the record keeps whatever evidence there is.
    """
    tag = f"[{facts.scenario_id} run {run} seed {seed}]"
    record: Dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "scenario_id": facts.scenario_id,
        "pack_id": facts.pack_id,
        "npc_name": facts.npc_name,
        "run": run,
        "seed": seed,
        "difficulty": difficulty,
        "runtime_id": runtime_id,
        "started_at": _now(),
        "finished_at": None,
        "session_id": None,
        "language": None,
        "player_role_name": None,
        "opening": None,
        "turns": [],
        "ended_early": False,
        "ending_type": None,
        "end": None,
        "debrief": {"status": None, "seconds": None, "body": None, "error": None},
        "transcript": None,
        "error": None,
    }
    step = "scenario lookup"
    session_id: Optional[str] = None
    state: Optional[str] = None
    try:
        _, detail = transport.request("GET", f"/api/scenarios/{_quote(facts.scenario_id)}")
        languages = list((detail or {}).get("supported_languages") or ["en"])
        role = ((detail or {}).get("player_role") or {}).get("label") or FALLBACK_ROLE_NAME
        record["language"] = languages[0]
        record["player_role_name"] = role

        step = "create session"
        setup: Dict[str, Any] = {
            "scenario_id": facts.scenario_id,
            "difficulty": difficulty,
            "player_role_name": role,
            "language": languages[0],
            "input_mode": "text-only",
            "tts_enabled": False,
            "show_state_meters": True,
            "save_transcript": True,
            "seed": seed,
        }
        if runtime_id:
            setup["runtime_id"] = runtime_id
        _, session = transport.request("POST", "/api/sessions", setup)
        session_id = str(session["session_id"])
        record["session_id"] = session_id
        sid = _quote(session_id)

        step = "start"
        _, started = transport.request("POST", f"/api/sessions/{sid}/start", {}, timeout=turn_timeout)
        record["opening"] = _event(started.get("events"), "npc_opening").get("content")
        state = started.get("state")
        log(f"{tag} session {session_id} started")

        for number, text in enumerate(player_turns, start=1):
            if state != "PlayerTurnListening":
                record["ended_early"] = True
                log(f"{tag} the session ended before turn {number} ({record['ending_type']})")
                break
            step = f"turn {number}"
            t0 = time.monotonic()
            _, resp = transport.request(
                "POST", f"/api/sessions/{sid}/turn", {"content": text}, timeout=turn_timeout
            )
            seconds = round(time.monotonic() - t0, 1)
            npc = _event(resp.get("events"), "npc_turn")
            state = resp.get("state")
            record["ending_type"] = resp.get("ending_type") or npc.get("ending_type")
            record["turns"].append({
                "turn": number,
                "player": text,
                "npc": npc.get("content"),
                "emotion": npc.get("emotion"),
                "state_delta": npc.get("state_delta") or {},
                "visible_state": npc.get("visible_state") or {},
                "event_flags": npc.get("event_flags") or [],
                "triggered_scenario_events": npc.get("triggered_scenario_events") or [],
                "rubric_observations": npc.get("rubric_observations") or [],
                "safety": npc.get("safety"),
                "ending_type": npc.get("ending_type"),
                "state": state,
                "seconds": seconds,
                "timing": npc.get("timing"),
            })
            log(f"{tag} turn {number}/{len(player_turns)} {seconds:.1f}s: {_short(npc.get('content'))}")
    except ApiError as exc:
        record["error"] = f"{step}: {exc}"
        log(f"{tag} ERROR {record['error']}")
    except (KeyError, TypeError, AttributeError) as exc:
        record["error"] = f"{step}: unexpected response shape ({exc!r})"
        log(f"{tag} ERROR {record['error']}")

    if session_id is not None:
        sid = _quote(session_id)
        if state not in ("Ended", "DebriefReady"):
            try:
                status, body = transport.request("POST", f"/api/sessions/{sid}/end", {})
                record["end"] = {"status": status, "body": body}
                record["ending_type"] = record["ending_type"] or (body or {}).get("ending_type")
            except ApiError as exc:
                record["end"] = {"status": exc.status, "body": exc.detail}
                record["error"] = record["error"] or f"end: {exc}"

        log(f"{tag} generating the debrief")
        t0 = time.monotonic()
        try:
            status, body = transport.request(
                "POST", f"/api/sessions/{sid}/debrief", {}, timeout=debrief_timeout
            )
            record["debrief"].update(status=status, body=body)
        except ApiError as exc:
            record["debrief"].update(status=exc.status, error=str(exc), body=None)
        record["debrief"]["seconds"] = round(time.monotonic() - t0, 1)

        try:
            _, transcript = transport.request("GET", f"/api/sessions/{sid}/transcript")
            record["transcript"] = transcript
        except ApiError as exc:
            record["transcript"] = None
            record["error"] = record["error"] or f"transcript: {exc}"

    record["finished_at"] = _now()
    return record


def _short(text: Any, limit: int = 90) -> str:
    s = " ".join(str(text or "").split())
    return json.dumps(s if len(s) <= limit else s[: limit - 1] + "\u2026", ensure_ascii=False)


def npc_lines_of(record: Mapping[str, Any]) -> List[checks.NpcLine]:
    """The NPC lines the player saw: the stored transcript, else the responses."""
    transcript = record.get("transcript") or {}
    if transcript.get("transcript_saved") and transcript.get("turns"):
        return checks.npc_lines_from_transcript(transcript["turns"])
    lines: List[checks.NpcLine] = []
    if record.get("opening"):
        lines.append(checks.NpcLine(turn=0, text=record["opening"], authored=True))
    for t in record.get("turns") or []:
        if t.get("npc"):
            lines.append(checks.NpcLine(turn=int(t["turn"]), text=t["npc"]))
    return lines


def evaluate_record(
    record: Dict[str, Any], facts: ScenarioFacts, severity: Mapping[str, str]
) -> List[checks.CheckResult]:
    """Run the five checks on a played record and store them on it."""
    debrief = record.get("debrief") or {}
    results = checks.evaluate_run(
        npc_lines=npc_lines_of(record),
        turn_deltas=[(int(t["turn"]), t.get("state_delta") or {}) for t in record.get("turns") or []],
        debrief_status=debrief.get("status"),
        debrief=debrief.get("body") if isinstance(debrief.get("body"), Mapping) else None,
        hidden_agenda=facts.hidden_agenda,
        authored_variables=facts.authored_variables,
        rubric_ids=facts.rubric_ids,
        severity=severity,
        debrief_error=debrief.get("error"),
    )
    record["checks"] = [r.to_dict() for r in results]
    record["verdict"] = checks.run_verdict(results, error=record.get("error"))
    return results


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _cell(check: Mapping[str, Any]) -> str:
    status = check["status"]
    n = len(check.get("findings") or [])
    return status if status == "pass" else f"{status} ({n})"


def _md(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_summary(records: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    sev = meta["severity"]
    failed = [r for r in records if r.get("verdict") == "fail"]
    warned = [r for r in records if r.get("verdict") == "warn"]
    if failed:
        verdict = "FAIL"
    elif warned:
        verdict = "PASS with warnings"
    else:
        verdict = "PASS"
    out: List[str] = []
    out.append("# D-05 automated pre-check")
    out.append("")
    out.append(f"- Started: {meta['started_at']}")
    engine = meta.get("engine") or {}
    out.append(
        f"- Engine: {meta['api']} (convsim-core {engine.get('version', '?')}, edition "
        f"{engine.get('edition', '?')}, runtime {engine.get('runtime_id') or '?'}, model "
        f"{engine.get('model_name') or engine.get('model_id') or '?'})"
    )
    if meta.get("runtime_id"):
        out.append(
            f"- Sessions pinned to the model-free `{meta['runtime_id']}` runtime: a harness "
            "self-test, not a D-05 result."
        )
    out.append(
        f"- Difficulty `{meta['difficulty']}`, {meta['repeat']} run(s) per conversation, "
        f"player turns from `{meta['turns_file']}`"
    )
    out.append(
        "- Severity: "
        + ", ".join(f"({c.letter}) {c.name} {sev[c.letter]}" for c in checks.CHECKS)
        + (" (--strict)" if meta.get("strict") else "")
    )
    if meta.get("interrupted"):
        out.append("- Interrupted: only the runs below finished.")
    out.append("")
    out.append(
        f"**Verdict: {verdict}.** {len(failed)} of {len(records)} run(s) failed a hard check "
        f"or did not finish; {len(warned)} passed with warnings."
    )
    out.append("")
    out.append(
        "This pre-check does not replace the manual D-05 judgement. It catches the "
        "failures a script can see (repetition, agenda said aloud, state that never "
        "moves, debriefs off the rubric or on the template); whether each reply makes "
        "sense, keeps its role and answers the player is still read by a person."
    )
    out.append("")
    head = "| Conversation | Run | Seed | Turns | " + " | ".join(
        f"({c.letter}) {c.name}" for c in checks.CHECKS
    ) + " | Verdict |"
    out.append(head)
    out.append("|" + "---|" * (len(checks.CHECKS) + 5))
    for r in records:
        by_letter = {c["letter"]: c for c in r.get("checks") or []}
        cells = [_cell(by_letter[c.letter]) if c.letter in by_letter else "-" for c in checks.CHECKS]
        verdict_cell = r.get("verdict", "?").upper()
        if r.get("error"):
            verdict_cell += " (error)"
        out.append(
            f"| {r['scenario_id']} | {r['run']} | {r['seed']} | {len(r.get('turns') or [])} | "
            + " | ".join(cells)
            + f" | {verdict_cell} |"
        )
    out.append("")
    out.append("## Findings")
    out.append("")
    for r in records:
        out.append(
            f"### {r['scenario_id']}, run {r['run']} (seed {r['seed']}, session "
            f"`{r.get('session_id') or '-'}`)"
        )
        out.append("")
        if r.get("error"):
            out.append(f"- **Run error:** {_md(r['error'])}")
        if r.get("ended_early"):
            out.append(f"- The session ended after {len(r.get('turns') or [])} turn(s): `{r.get('ending_type')}`.")
        for c in r.get("checks") or []:
            label = f"({c['letter']}) {c['name']}"
            if c["passed"]:
                out.append(f"- {label}: pass. {_md(c.get('detail') or '')}".rstrip())
                continue
            out.append(f"- {label}: **{c['status']}**. {_md(c.get('detail') or '')}".rstrip())
            for f in c.get("findings") or []:
                where = f"turn {f['turn']}: " if f.get("turn") is not None else ""
                ev = f" \u2014 \u201c{_md(f['evidence'])}\u201d" if f.get("evidence") else ""
                out.append(f"  - {where}{_md(f['message'])}{ev}")
        out.append("")
    out.append("## Latency (noted, not judged)")
    out.append("")
    out.append("| Conversation | Run | Mean turn s | Max turn s | Debrief s |")
    out.append("|---|---|---|---|---|")
    for r in records:
        secs = [t["seconds"] for t in r.get("turns") or [] if t.get("seconds") is not None]
        mean = f"{sum(secs) / len(secs):.1f}" if secs else "-"
        top = f"{max(secs):.1f}" if secs else "-"
        deb = (r.get("debrief") or {}).get("seconds")
        out.append(
            f"| {r['scenario_id']} | {r['run']} | {mean} | {top} | "
            f"{deb if deb is not None else '-'} |"
        )
    out.append("")
    return "\n".join(out)


def write_record(out_dir: Path, record: Mapping[str, Any]) -> Path:
    path = out_dir / f"{record['scenario_id']}-run{record['run']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="demo-gate-replay.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--api", default=DEFAULT_API, help=f"convsim-core base URL (default {DEFAULT_API})")
    p.add_argument(
        "--only", action="append", default=[], metavar="ID[,ID]",
        help="play only these demo conversations (repeatable or comma-separated)",
    )
    p.add_argument("--repeat", type=int, default=2, help="runs per conversation (default 2)")
    p.add_argument("--seed", type=int, default=42, help="seed of each conversation's first run (default 42)")
    p.add_argument("--difficulty", choices=DIFFICULTIES, default="standard", help="difficulty (default standard)")
    p.add_argument("--turns", type=Path, default=DEFAULT_TURNS, help="player-turns YAML")
    p.add_argument("--packs-dir", type=Path, default=DEFAULT_PACKS_DIR, help="official packs to read the authored files from")
    p.add_argument("--out", type=Path, default=None, help="output folder (default out/demo-gate/<UTC time>)")
    p.add_argument("--turn-timeout", type=float, default=900.0, help="seconds to wait for one NPC turn (default 900)")
    p.add_argument("--debrief-timeout", type=float, default=900.0, help="seconds to wait for the debrief (default 900)")
    p.add_argument("--strict", action="store_true", help="make every check a hard failure")
    p.add_argument("--hard", action="append", default=[], metavar="CHECK", help="make one check (letter or name) a hard failure")
    p.add_argument("--warn", action="append", default=[], metavar="CHECK", help="make one check (letter or name) a warning")
    p.add_argument(
        "--runtime-id", choices=MODEL_FREE_RUNTIMES, default=None,
        help="pin sessions to a model-free runtime to exercise the harness (not a D-05 result)",
    )
    return p


def _engine_info(health: Mapping[str, Any]) -> Dict[str, Any]:
    llm = health.get("llm_runtime") or {}
    active = health.get("active_model") or {}
    readiness = health.get("runtime") or {}
    return {
        "version": health.get("version"),
        "edition": health.get("edition"),
        "runtime_id": llm.get("runtime_id") or active.get("runtime_id"),
        "model_id": active.get("model_id"),
        "model_name": readiness.get("llm_model_name"),
    }


def main(argv: Optional[Sequence[str]] = None, *, transport: Any = None, log: Log = print) -> int:
    args = build_parser().parse_args(argv)

    def fail_setup(msg: str) -> int:
        sys.stderr.write(f"demo-gate-replay: {msg}\n")
        return 2

    if args.repeat < 1:
        return fail_setup("--repeat must be at least 1")
    try:
        severity = checks.resolve_severity(strict=args.strict, hard=args.hard, warn=args.warn)
    except ValueError as exc:
        return fail_setup(str(exc))

    demo = demo_scenarios()
    pack_of = dict((s, p) for p, s in demo)
    selected = [s for _, s in demo]
    if args.only:
        wanted = [s.strip() for item in args.only for s in item.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in pack_of]
        if unknown:
            return fail_setup(
                f"not a demo conversation: {', '.join(unknown)} (demo: {', '.join(selected)})"
            )
        selected = [s for s in selected if s in wanted]

    try:
        player_turns = load_player_turns(args.turns)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return fail_setup(f"cannot read the player turns: {exc}")
    missing = [s for s in selected if not player_turns.get(s)]
    if missing:
        return fail_setup(f"{args.turns} has no turns for: {', '.join(missing)}")

    baseline = baseline_variables()
    try:
        facts = {
            s: load_scenario_facts(args.packs_dir, pack_of[s], s, baseline) for s in selected
        }
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        return fail_setup(f"cannot read the authored pack files: {exc}")

    transport = transport or HttpTransport(args.api)
    try:
        _, health = transport.request("GET", "/api/health")
    except ApiError as exc:
        return fail_setup(f"convsim-core does not answer at {args.api} ({exc}); start it first")
    engine = _engine_info(health or {})
    if not args.runtime_id and engine.get("runtime_id") in MODEL_FREE_RUNTIMES:
        log(
            f"warning: the engine's runtime is {engine['runtime_id']!r}; "
            "this is not a real-model D-05 run"
        )

    started_at = _now()
    out_dir = args.out or REPO_ROOT / "out" / "demo-gate" / started_at.replace(":", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: Dict[str, Any] = {
        "started_at": started_at,
        "api": args.api,
        "engine": engine,
        "difficulty": args.difficulty,
        "repeat": args.repeat,
        "turns_file": _display_path(args.turns),
        "severity": severity,
        "strict": args.strict,
        "runtime_id": args.runtime_id,
        "interrupted": False,
    }
    log(
        f"D-05 pre-check: {len(selected)} conversation(s) x {args.repeat} run(s) at "
        f"{args.difficulty} against {args.api}; writing to {out_dir}"
    )

    records: List[Dict[str, Any]] = []
    summary_path = out_dir / "summary.md"
    try:
        for scenario_id in selected:
            for run in range(1, args.repeat + 1):
                record = play_conversation(
                    transport,
                    facts[scenario_id],
                    player_turns[scenario_id],
                    run=run,
                    seed=args.seed + run - 1,
                    difficulty=args.difficulty,
                    turn_timeout=args.turn_timeout,
                    debrief_timeout=args.debrief_timeout,
                    runtime_id=args.runtime_id,
                    log=log,
                )
                evaluate_record(record, facts[scenario_id], severity)
                records.append(record)
                write_record(out_dir, record)
                summary_path.write_text(render_summary(records, meta), encoding="utf-8")
                statuses = " ".join(f"({c['letter']}) {c['status']}" for c in record["checks"])
                log(f"[{scenario_id} run {run}] {record['verdict'].upper()}: {statuses}")
    except KeyboardInterrupt:
        meta["interrupted"] = True
        summary_path.write_text(render_summary(records, meta), encoding="utf-8")
        log(f"interrupted; summary of {len(records)} finished run(s): {summary_path}")
        return 130

    summary_path.write_text(render_summary(records, meta), encoding="utf-8")
    failed = sum(1 for r in records if r["verdict"] == "fail")
    warned = sum(1 for r in records if r["verdict"] == "warn")
    log(
        f"{len(records)} run(s): {failed} failed, {warned} with warnings, "
        f"{len(records) - failed - warned} clean. Summary: {summary_path}"
    )
    return 1 if failed else 0


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
