# SPDX-License-Identifier: Apache-2.0
"""HTTP routes for flyting — the turn-scored game mode.

  GET  /api/flyting/scenarios                        installed flyting scenarios
  GET  /api/flyting/scenarios/{id}                   setup: formats, brief, boards
  GET  /api/flyting/scenarios/{id}/high-scores       the local board
  POST /api/flyting/sessions                         start a run
  GET  /api/flyting/sessions/{id}                    run state and the volley log
  POST /api/flyting/sessions/{id}/volley             submit one volley, get a scorecard
  POST /api/flyting/sessions/{id}/end                finish the run, get the debrief
  POST /api/flyting/preview                          score a draft volley (Workbench)

A flyting run is an ordinary ``turn_sessions`` row, so transcript export,
session deletion, and the Logbook keep working on one without special cases;
what is flyting-specific is the volley log and the run state.

Everything stays local. There is no outbound call anywhere in this router — the
high-score table is a SQLite table on the player's own machine.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from convsim_core.edition import EDITION_RESTRICTED, is_demo
from convsim_core.flyting.config import (
    BattingFormat,
    PlayFormat,
    SET_FORMAT_VOLLEYS,
    TIER_PROFILES,
    TIMED_FORMAT_SECONDS,
    daily_seed as compute_daily_seed,
    visible_attack_surface,
)
from convsim_core.flyting.loader import (
    FlytingScenario,
    list_flyting_scenarios,
    resolve_flyting_scenario,
)
from convsim_core.flyting.pipeline import FlytingRunOver, process_volley
from convsim_core.flyting.service import VolleyScoringService
from convsim_core.flyting.session import (
    ENDLESS_MAX_WHIFFS,
    FlytingRunState,
    RunOutcome,
    resolve_batting_practice,
    summarize_run,
)
from convsim_core.flyting.volley import MAX_VOLLEY_CHARS, VolleyInputError
from convsim_core.runtime.active import unpinned_session_runtime_is_model_free
from convsim_core.runtime.base import ChatRuntime
from convsim_core.scenario_state import ScenarioVariableDef, build_variable_defs
from convsim_core.storage.repositories import flyting_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flyting", tags=["flyting"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunCreateRequest(BaseModel):
    scenario_id: str
    play_format: Literal["bout", "batting_practice"] = "batting_practice"
    batting_format: Optional[Literal["timed_90", "set_10", "endless"]] = None
    use_daily_seed: bool = False
    save_transcript: bool = True
    runtime_id: Optional[Literal["scripted", "fake"]] = None


class VolleySubmitRequest(BaseModel):
    content: str
    # Seconds since the player was prompted, measured by the client that owns
    # the shot clock. Absent means "not timed" (the Workbench, a test).
    elapsed_since_prompt_s: Optional[float] = Field(default=None, ge=0)
    elapsed_total_s: Optional[float] = Field(default=None, ge=0)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A volley cannot be blank")
        if len(value.strip()) > MAX_VOLLEY_CHARS:
            raise ValueError(f"A volley cannot exceed {MAX_VOLLEY_CHARS} characters")
        return value


class RunEndRequest(BaseModel):
    """The closing clock reading from whoever owned the run's clock.

    Optional, because ending a run is also how a reopened debrief re-reads one,
    and a debrief opened a week later has no clock to report. It matters for the
    timed drill: that drill finishes when ninety seconds pass, which only the
    client watching the clock can observe, so without this the drill would be
    recorded as a retirement.
    """

    elapsed_total_s: Optional[float] = Field(default=None, ge=0)


class PreviewRequest(BaseModel):
    """Score a draft volley without starting a run (the Workbench test box)."""

    scenario_id: str
    content: str
    prior_volleys: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A volley cannot be blank")
        return value


class RunResponse(BaseModel):
    session_id: str
    scenario_id: str
    state: str
    run: Dict[str, Any]
    created_at: str


class VolleyResponse(BaseModel):
    session_id: str
    state: str
    player_volley: Dict[str, Any]
    npc_line: Optional[str] = None
    npc_volley: Optional[Dict[str, Any]] = None
    exchange: Optional[Dict[str, Any]] = None
    run: Dict[str, Any]
    run_outcome: Optional[str] = None
    # The same derived counters the GET route reports. They ride on the volley
    # response so a client can show "volleys left" and "whiffs left" without
    # re-deriving the format rules — which would mean a second copy of
    # SET_FORMAT_VOLLEYS and ENDLESS_MAX_WHIFFS living in the UI, free to drift
    # from the engine that enforces them.
    volleys_remaining: Optional[int] = None
    seconds_remaining: Optional[float] = None
    whiffs_remaining: Optional[int] = None
    # The surface as the run knows it *after* this volley: a discoverable trait
    # struck just now is revealed here, which is what "revealed when first
    # struck" has to mean on the screen the player is looking at.
    target_surface: List[Dict[str, Any]] = Field(default_factory=list)


class RunSummaryResponse(BaseModel):
    session_id: str
    scenario_id: str
    summary: Dict[str, Any]
    volleys: List[Dict[str, Any]]
    high_score_rank: Optional[int] = None
    personal_best: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_full_app(request: Request) -> None:
    """Flyting is a full-app mode; the demo plays its five curated conversations."""
    if is_demo(request.app.state.service_config):
        raise HTTPException(
            status_code=403,
            detail={
                "message": (
                    "Flyting is not part of the demo. The full version of "
                    "Conversation Simulator includes the Flyting School pack."
                ),
                "code": EDITION_RESTRICTED,
            },
        )


def _scenario_or_404(request: Request, scenario_id: str) -> FlytingScenario:
    conn = request.app.state.db.connection()
    scenario = resolve_flyting_scenario(scenario_id, conn)
    if scenario is None:
        raise HTTPException(
            status_code=404,
            detail=f"No flyting scenario named {scenario_id!r} is installed",
        )
    return scenario


def _session_or_404(request: Request, session_id: str):
    """The session row for a flyting run, or 404.

    A conversation session lives in the same table and carries no run state, so
    these routes have to refuse it rather than default the state and carry on.
    ``/end`` writes to the row it is given: ending somebody's half-finished
    interview as a retired flyting run — and putting it on a flyting board — is
    worse than a 404.
    """
    conn = request.app.state.db.connection()
    row = conn.execute(
        "SELECT * FROM turn_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None or _run_state_of(row) is None:
        raise HTTPException(
            status_code=404, detail=f"No flyting run named {session_id!r}"
        )
    return row


def _resolve_runtime(request: Request, setup: Dict[str, Any]) -> Optional[ChatRuntime]:
    """The runtime this run judges with, or None to score mechanically.

    A run pinned to a model-free runtime (tests, dev tooling) gets that runtime;
    everything else gets the active one. When no runtime can be resolved the
    pipeline scores from mechanics and flags every volley, rather than failing
    the request — a drill with no judge is degraded, not broken.
    """
    pinned = setup.get("runtime_id")
    if pinned:
        from convsim_core.runtime import build_runtime

        try:
            return build_runtime(pinned)
        except Exception:  # noqa: BLE001
            return None
    return getattr(request.app.state, "runtime", None)


def _service(scenario: FlytingScenario) -> VolleyScoringService:
    return VolleyScoringService(scenario.scoring_context())


def _momentum_def(scenario: FlytingScenario) -> ScenarioVariableDef:
    """The scenario's own momentum definition, including max_delta_per_turn."""
    from convsim_core.flyting.session import FLYTING_VARIABLE_DEFAULTS

    defs = build_variable_defs(scenario.state_variables)
    return defs.get("momentum", FLYTING_VARIABLE_DEFAULTS["momentum"])


def _revealed_surface(
    scenario: Optional[FlytingScenario], state: FlytingRunState
) -> List[Dict[str, Any]]:
    """The target's traits this run is allowed to show, briefs included.

    The visible ones from the start, plus every discoverable one the player has
    already struck. ``npc.schema.json`` promises a discoverable trait is
    "revealed when first struck, and worth double on discovery"; the doubling
    was there from the first commit, and this is the revealing. Nothing hidden
    is sent, so the brief of a trait still to be found never reaches the client
    to be read out of the payload.

    ``discovered`` carries the engine's own meaning of the word — a
    *discoverable* trait the player has now found — and not "struck at some
    point". ``state.discovered_traits`` is every trait any verified hook has
    ever named, visible ones included, because that is the ledger
    ``HookClaim.discovered`` consults to pay the x2 once. Reporting membership
    in it directly tagged a trait the brief had named from the first screen as a
    discovery: the play screen coloured it as found, titled it "You found this
    one", and counted it in "one discovered" — which both says something untrue
    and spends the signal that is supposed to mark the two traits actually worth
    double.
    """
    if scenario is None:
        return []
    found = set(state.discovered_traits)
    return [
        {
            "id": trait.id,
            "brief": trait.brief,
            "discovered": trait.discoverable and trait.id in found,
        }
        for trait in visible_attack_surface(scenario.attack_surface, found)
    ]


def _scenario_payload(scenario: FlytingScenario, conn: Any) -> Dict[str, Any]:
    flyting = scenario.flyting
    formats = [f.value for f in flyting.formats]
    boards = {
        play_format: flyting_repo.personal_best(
            conn, scenario_id=scenario.scenario_id, play_format=play_format
        )
        for play_format in formats
    }
    return {
        "scenario_id": scenario.scenario_id,
        "pack_id": scenario.pack_id,
        "title": scenario.title,
        "summary": scenario.summary,
        "mode": "flyting",
        "content_rating": scenario.content_rating,
        "player_role": {
            "label": scenario.player_role_label,
            "brief": scenario.player_role_brief,
        },
        # The provocation the run opens on. Every scenario declares one and in a
        # bout it is what the first volley answers, so it has to reach the
        # player rather than stopping at the YAML.
        "opening": scenario.opening_npc_says,
        "target": {
            "npc_id": scenario.npc.npc_id,
            "display_name": scenario.npc.display_name,
            # Only the visible half of the surface: a discoverable trait is
            # worth double when the player finds it, and that is only possible
            # if the brief has not already told them about it.
            "attack_surface": [
                {"id": trait.id, "brief": trait.brief}
                for trait in visible_attack_surface(scenario.attack_surface)
            ],
            "discoverable_count": sum(
                1 for t in scenario.attack_surface if t.discoverable
            ),
        },
        "formats": formats,
        "batting_formats": [f.value for f in flyting.batting_practice.formats],
        "shot_clock_s": flyting.batting_practice.shot_clock_s,
        "bout": {
            "rounds": flyting.bout.rounds,
            "momentum_win": flyting.bout.momentum_win,
            "riposte_bonus": flyting.bout.riposte_bonus,
            "npc_tier": flyting.bout.npc_tier.value,
            "npc_tier_label": TIER_PROFILES[flyting.bout.npc_tier].label,
        },
        "difficulty_multiplier": flyting.difficulty_multiplier,
        "verse_required": flyting.verse.required,
        "requires_surface_politeness": flyting.register.require_surface_politeness,
        # Surfaced as hints at low difficulty; the engine never requires them.
        "lexicon_hints": list(flyting.lexicon.encouraged),
        "judge_flavor": flyting.judge_flavor,
        "audience": (
            {"label": scenario.audience.label} if scenario.audience else None
        ),
        "personal_bests": boards,
        "goals": list(scenario.player_visible_goals),
        "limits": {
            "max_volley_chars": MAX_VOLLEY_CHARS,
            "set_volleys": SET_FORMAT_VOLLEYS,
            "timed_seconds": TIMED_FORMAT_SECONDS,
            "endless_whiffs": ENDLESS_MAX_WHIFFS,
        },
    }


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------


@router.get("/scenarios")
async def list_scenarios(request: Request) -> List[Dict[str, Any]]:
    """Every installed flyting scenario, with its formats and personal bests."""
    _require_full_app(request)
    conn = request.app.state.db.connection()
    return [_scenario_payload(s, conn) for s in list_flyting_scenarios(conn)]


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str, request: Request) -> Dict[str, Any]:
    _require_full_app(request)
    scenario = _scenario_or_404(request, scenario_id)
    return _scenario_payload(scenario, request.app.state.db.connection())


@router.get("/scenarios/{scenario_id}/high-scores")
async def get_high_scores(
    scenario_id: str,
    request: Request,
    play_format: Optional[str] = Query(default=None),
    batting_format: Optional[str] = Query(default=None),
    daily_seed: Optional[int] = Query(default=None),
    today: bool = Query(default=False),
    limit: int = Query(default=flyting_repo.HIGH_SCORE_BOARD_SIZE, ge=1, le=50),
) -> Dict[str, Any]:
    """The local high-score board for one scenario and format.

    ``today=true`` narrows the board to the runs played under today's seed for
    this scenario and format, which is the comparison a daily seed exists to
    make; ``daily_seed`` asks for a specific one. Both are computed locally — the
    seed is a function of the date and the ids, so nothing leaves the machine.
    """
    _require_full_app(request)
    conn = request.app.state.db.connection()
    if today and daily_seed is None and play_format:
        daily_seed = compute_daily_seed(scenario_id, play_format)
    return {
        "scenario_id": scenario_id,
        "play_format": play_format,
        "batting_format": batting_format,
        "daily_seed": daily_seed,
        "entries": flyting_repo.list_high_scores(
            conn,
            scenario_id=scenario_id,
            play_format=play_format,
            batting_format=batting_format,
            daily_seed=daily_seed,
            limit=limit,
        ),
    }


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.post("/sessions", status_code=201, response_model=RunResponse)
async def create_run(body: RunCreateRequest, request: Request) -> RunResponse:
    _require_full_app(request)
    scenario = _scenario_or_404(request, body.scenario_id)
    play_format = PlayFormat(body.play_format)
    if not scenario.flyting.supports(play_format):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Scenario {body.scenario_id!r} does not offer the "
                f"{body.play_format!r} format"
            ),
        )

    batting_format: Optional[BattingFormat] = None
    if play_format is PlayFormat.BATTING_PRACTICE:
        requested = body.batting_format or scenario.flyting.batting_practice.formats[0].value
        batting_format = BattingFormat(requested)
        if batting_format not in scenario.flyting.batting_practice.formats:
            raise HTTPException(
                status_code=400,
                detail=f"Scenario {body.scenario_id!r} does not offer the {requested!r} drill",
            )

    conn = request.app.state.db.connection()
    if body.runtime_id is None and unpinned_session_runtime_is_model_free(request.app, conn):
        raise HTTPException(
            status_code=409,
            detail=(
                "No AI model is configured, so the judge cannot score your volleys. "
                "Finish setup (install the recommended model, or connect Ollama or a "
                "local GGUF file) and try again."
            ),
        )

    state = FlytingRunState(
        play_format=play_format,
        batting_format=batting_format,
        shot_clock_s=scenario.flyting.batting_practice.shot_clock_s,
        daily_seed=(
            compute_daily_seed(scenario.scenario_id, play_format.value)
            if body.use_daily_seed
            else None
        ),
    )

    session_id = f"flyt-{secrets.token_hex(8)}"
    now = _now_iso()
    setup = body.model_dump()
    setup["mode"] = "flyting"
    if body.runtime_id is None:
        setup.pop("runtime_id", None)

    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, state_vars_json, fired_events_json, "
        "turn_count, setup_json, flyting_state_json, created_at) "
        "VALUES (?, ?, 'PlayerTurnListening', ?, '[]', 0, ?, ?, ?)",
        (
            session_id,
            scenario.scenario_id,
            json.dumps({"momentum": state.momentum}),
            json.dumps(setup),
            json.dumps(state.to_dict()),
            now,
        ),
    )
    # The scenario's opening line, as turn zero, exactly where the conversation
    # loop puts it — same role, so the transcript export labels it "NPC
    # (Opening)" without knowing about flyting. The volley pipeline numbers its
    # own turns from 1 (player odd, opponent even), so turn zero is free.
    #
    # It is a line, not a volley: nothing scores it, it never enters the volley
    # log, and it does not count toward the opponent's total. In a bout it is
    # the opponent's last line when the first volley arrives, which is what
    # makes a riposte possible on the opening exchange rather than only from
    # the second one on.
    if scenario.opening_npc_says:
        conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, flow_state_after, created_at) "
            "VALUES (?, 0, 'npc_opening', ?, 'PlayerTurnListening', ?)",
            (session_id, scenario.opening_npc_says, now),
        )
        if body.save_transcript:
            conn.execute(
                "INSERT INTO session_transcript_fts(session_id, turn_number, role, content) "
                "VALUES (?, 0, 'npc_opening', ?)",
                (session_id, scenario.opening_npc_says),
            )
    conn.commit()

    return RunResponse(
        session_id=session_id,
        scenario_id=scenario.scenario_id,
        state="PlayerTurnListening",
        run=state.to_dict(),
        created_at=now,
    )


@router.get("/sessions/{session_id}")
async def get_run(session_id: str, request: Request) -> Dict[str, Any]:
    _require_full_app(request)
    row = _session_or_404(request, session_id)
    conn = request.app.state.db.connection()
    state = FlytingRunState.from_dict(_run_state_of(row))
    scenario = resolve_flyting_scenario(row["scenario_id"], conn)
    return {
        "session_id": session_id,
        "scenario_id": row["scenario_id"],
        "state": row["flow_state"],
        "run": state.to_dict(),
        "volleys": flyting_repo.list_volleys(conn, session_id),
        "volleys_remaining": state.volleys_remaining,
        "seconds_remaining": state.seconds_remaining,
        "whiffs_remaining": state.whiffs_remaining,
        # The line the run opened on, so a reloaded screen still shows what is
        # being answered, and the surface as this run currently knows it.
        "opening": scenario.opening_npc_says if scenario else "",
        "target_surface": _revealed_surface(scenario, state),
    }


@router.post("/sessions/{session_id}/volley", response_model=VolleyResponse)
async def submit_volley(
    session_id: str, body: VolleySubmitRequest, request: Request
) -> VolleyResponse:
    _require_full_app(request)
    row = _session_or_404(request, session_id)
    scenario = _scenario_or_404(request, row["scenario_id"])
    conn = request.app.state.db.connection()
    setup = json.loads(row["setup_json"] or "{}")

    try:
        result = await process_volley(
            row,
            body.content,
            service=_service(scenario),
            npc=scenario.npc,
            runtime=_resolve_runtime(request, setup),
            conn=conn,
            player_role_label=scenario.player_role_label,
            player_role_brief=scenario.player_role_brief,
            elapsed_since_prompt_s=body.elapsed_since_prompt_s,
            elapsed_total_s=body.elapsed_total_s,
            save_transcript=bool(setup.get("save_transcript", True)),
            momentum_variable_def=_momentum_def(scenario),
        )
    except VolleyInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FlytingRunOver as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "code": "RUN_ALREADY_ENDED"},
        ) from exc

    payload = result.to_dict()
    return VolleyResponse(
        session_id=session_id,
        state="Ended" if result.run_outcome else "PlayerTurnListening",
        player_volley=payload["player_volley"],
        npc_line=result.npc_line,
        npc_volley=payload["npc_volley"],
        exchange=payload["exchange"],
        run=payload["run"],
        run_outcome=result.run_outcome,
        volleys_remaining=result.state.volleys_remaining,
        seconds_remaining=result.state.seconds_remaining,
        whiffs_remaining=result.state.whiffs_remaining,
        target_surface=_revealed_surface(scenario, result.state),
    )


@router.post("/sessions/{session_id}/end", response_model=RunSummaryResponse)
async def end_run(
    session_id: str, request: Request, body: Optional[RunEndRequest] = None
) -> RunSummaryResponse:
    """Finish a run and return its debrief, recording the score on the board."""
    _require_full_app(request)
    row = _session_or_404(request, session_id)
    conn = request.app.state.db.connection()
    scenario = resolve_flyting_scenario(row["scenario_id"], conn)

    state = FlytingRunState.from_dict(_run_state_of(row))
    if body is not None and body.elapsed_total_s is not None:
        # Monotonic: the clock only ever advances, so a stale or missing reading
        # cannot shorten a run that already recorded a longer one.
        state.elapsed_s = max(state.elapsed_s, body.elapsed_total_s)
    if not state.is_over:
        # A drill the format itself finished is not a retirement. The volley
        # route resolves the set and endless drills, because those end on a
        # volley; the timed drill ends when ninety seconds pass with nobody
        # typing, which only the clock-watching client sees — so resolve the
        # format here before falling back to RETIRED.
        resolve_batting_practice(state)
    if not state.is_over:
        state.outcome = RunOutcome.RETIRED.value

    volleys = flyting_repo.list_volleys(conn, session_id, speaker="player")
    scores = _rehydrate(volleys)
    theme_decay = scenario.rubric.theme_decay if scenario else 0.75
    summary = summarize_run(state, scores, theme_decay=theme_decay)

    conn.execute(
        "UPDATE turn_sessions SET flow_state = 'Ended', ending_type = ?, "
        "flyting_state_json = ?, ended_at = COALESCE(ended_at, ?) WHERE session_id = ?",
        (state.outcome, json.dumps(state.to_dict()), _now_iso(), session_id),
    )
    conn.commit()

    rank = flyting_repo.record_high_score(
        conn,
        scenario_id=row["scenario_id"],
        pack_id=scenario.pack_id if scenario else None,
        play_format=state.play_format.value,
        batting_format=state.batting_format.value if state.batting_format else None,
        session_id=session_id,
        outcome=state.outcome,
        total_score=summary.total_score,
        volley_count=summary.volley_count,
        best_volley_score=summary.best_volley_score,
        peak_heat=summary.peak_heat,
        daily_seed=state.daily_seed,
    )
    best = flyting_repo.personal_best(
        conn,
        scenario_id=row["scenario_id"],
        play_format=state.play_format.value,
        batting_format=state.batting_format.value if state.batting_format else None,
    )

    return RunSummaryResponse(
        session_id=session_id,
        scenario_id=row["scenario_id"],
        summary=summary.to_dict(),
        volleys=flyting_repo.list_volleys(conn, session_id),
        high_score_rank=rank,
        personal_best=best,
    )


# ---------------------------------------------------------------------------
# Workbench preview
# ---------------------------------------------------------------------------


@router.post("/preview")
async def preview_volley(body: PreviewRequest, request: Request) -> Dict[str, Any]:
    """Score a draft volley against an installed scenario, with no run attached.

    The Creator Workbench's test-volley box: an author can see what the
    deterministic stages make of a line before exporting the pack. No model is
    called, so the result is the mechanical score with its flag — which is also
    the useful thing to see, because it is the part an author controls.
    """
    _require_full_app(request)
    scenario = _scenario_or_404(request, body.scenario_id)
    service = _service(scenario)
    try:
        result = service.score_mechanically(
            body.content, prior_volleys=body.prior_volleys
        )
    except VolleyInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "scenario_id": scenario.scenario_id,
        "volley": result.to_dict(),
        "judge_input": {
            "system_prompt_preview": _judge_prompt_preview(service, body.content),
        },
    }


def _judge_prompt_preview(service: VolleyScoringService, text: str) -> str:
    """The judge's rubric header for this scenario, so an author can read it."""
    from convsim_prompt import compose_volley_judge_prompt

    prepared = service.prepare(text)
    bundle = compose_volley_judge_prompt(service.judge_input(prepared))
    return bundle.system_prompt


# ---------------------------------------------------------------------------
# Shared row helpers
# ---------------------------------------------------------------------------


def _run_state_of(row: Any) -> Optional[Dict[str, Any]]:
    try:
        raw = row["flyting_state_json"]
    except (IndexError, KeyError):
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _rehydrate(volleys: List[Dict[str, Any]]) -> List[Any]:
    """Rebuild VolleyScore objects from stored scorecards for the summary pass.

    The summary is a pure aggregate over the volley log, so it is computed from
    the stored scorecards rather than from anything held in memory — a debrief
    opened a month later agrees with the one shown at the end of the run.
    """
    from convsim_prompt import DroppedHook, EvidenceClaim, HookClaim, VolleyJudgment

    from convsim_core.flyting.craft import CraftMetrics
    from convsim_core.flyting.gates import Foul, GateOutcome, GateResult
    from convsim_core.flyting.novelty import FreshnessResult
    from convsim_core.flyting.scoring import VolleyScore

    rebuilt: List[VolleyScore] = []
    for entry in volleys:
        card = entry.get("scorecard") or {}
        gate_raw = card.get("gate") or {}
        craft_raw = card.get("craft_metrics") or {}
        judge_raw = card.get("judge")

        try:
            outcome = GateOutcome(str(gate_raw.get("outcome") or "ok"))
        except ValueError:
            outcome = GateOutcome.OK
        foul_raw = gate_raw.get("foul")
        try:
            foul = Foul(foul_raw) if foul_raw else None
        except ValueError:
            foul = None

        judgment = None
        if isinstance(judge_raw, dict):
            judgment = VolleyJudgment(
                sting=int(judge_raw.get("sting", 0)),
                wit=int(judge_raw.get("wit", 0)),
                craft=int(judge_raw.get("craft", 0)),
                fidelity=int(judge_raw.get("fidelity", 0)),
                hooks=[
                    HookClaim(
                        trait=str(h.get("trait", "")),
                        evidence=str(h.get("evidence", "")),
                        discovered=bool(h.get("discovered", False)),
                    )
                    for h in judge_raw.get("hooks") or []
                ],
                themes=[str(t) for t in judge_raw.get("themes") or []],
                devices=[str(d) for d in judge_raw.get("devices") or []],
                riposte=EvidenceClaim(
                    bool((judge_raw.get("riposte") or {}).get("is_riposte")),
                    (judge_raw.get("riposte") or {}).get("evidence"),
                ),
                callback=EvidenceClaim(
                    bool((judge_raw.get("callback") or {}).get("is_callback")),
                    (judge_raw.get("callback") or {}).get("evidence"),
                ),
                fouls=[str(f) for f in judge_raw.get("fouls") or []],
                umpire_line=str(judge_raw.get("umpire_line") or ""),
                # Refused hook claims are part of the coaching: the debrief tells
                # a player when their own words did not carry the hit they were
                # credited for, and that note is computed from these rows.
                dropped_hooks=[
                    DroppedHook(
                        trait=str(d.get("trait", "")),
                        evidence=d.get("evidence"),
                        reason=str(d.get("reason", "")),
                    )
                    for d in judge_raw.get("dropped_hooks") or []
                    if isinstance(d, dict)
                ],
            )

        rebuilt.append(VolleyScore(
            volley_number=int(card.get("volley_number", len(rebuilt) + 1)),
            speaker=str(card.get("speaker") or entry.get("speaker") or "player"),
            text=str(entry.get("text") or ""),
            score=int(entry.get("score") or 0),
            band=str(entry.get("band") or "dud"),
            gate=GateResult(outcome=outcome, foul=foul, reason=gate_raw.get("reason")),
            craft=CraftMetrics(
                word_count=int(craft_raw.get("word_count", 0)),
                rarest_words=list(craft_raw.get("rarest_words") or []),
                second_person=bool(craft_raw.get("second_person", False)),
            ),
            freshness=FreshnessResult(value=float((card.get("freshness") or {}).get("value", 1.0))),
            judgment=judgment,
            heat=float(entry.get("heat") or 1.0),
            banked_score=int(entry.get("banked_score") or 0),
            flags=[str(f) for f in card.get("flags") or []],
        ))
    return rebuilt
