# SPDX-License-Identifier: Apache-2.0
"""Run state for the two flyting formats.

**The Bout.** Player and opponent alternate volleys. ``momentum`` starts at 50
and shifts after each exchange by ``k · (S_player − S_npc) / 100``. The player
wins by carrying momentum past the threshold — the crowd carries you out on
their shoulders — or by holding the higher cumulative score after N rounds; a
tie forces a sudden-death volley. The opponent's volleys go through the same
scoring pipeline and the numbers are shown, because transparency doubles as
instruction.

**Batting Practice.** A fixed target who reacts but never counters. Consecutive
volleys scoring at or above 60 build a heat multiplier from x1.0 to x2.0 in
steps of 0.1; duds and fouls reset it. Session score is the sum of
``volley score × heat at the moment of scoring``. Three formats: timed (90s),
set (10 volleys), and endless (three whiffs and you are out).

``momentum`` and ``heat`` are ordinary state variables: the momentum shift is
applied through ``scenario_state.apply_state_delta`` so the scenario's own
``max_delta_per_turn`` clamp governs how far one exchange can move the crowd,
exactly as it governs every other meter in the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from convsim_core.flyting.config import (
    HEAT_THRESHOLD,
    BattingFormat,
    BoutConfig,
    ENDLESS_MAX_WHIFFS,
    PlayFormat,
    SET_FORMAT_VOLLEYS,
    TIMED_FORMAT_SECONDS,
)
from convsim_core.flyting.scoring import VolleyScore
from convsim_core.scenario_state import (
    ScenarioVariableDef,
    VariableVisibility,
    apply_state_delta,
)

HEAT_MIN = 1.0
HEAT_MAX = 2.0
HEAT_STEP = 0.1

MOMENTUM_START = 50

# Default definitions for the two flyting meters. A scenario may override either
# through its ordinary state.variables block — including max_delta_per_turn,
# which is what bounds a single exchange's momentum swing.
FLYTING_VARIABLE_DEFAULTS: Dict[str, ScenarioVariableDef] = {
    "momentum": ScenarioVariableDef(
        name="momentum",
        min=0,
        max=100,
        default=MOMENTUM_START,
        visibility=VariableVisibility.VISIBLE,
        max_delta_per_turn=20,
    ),
}


class RunOutcome(str, Enum):
    IN_PROGRESS = "in_progress"
    MOMENTUM_WIN = "momentum_win"
    MOMENTUM_LOSS = "momentum_loss"
    POINTS_WIN = "points_win"
    POINTS_LOSS = "points_loss"
    DRAW = "draw"
    SET_COMPLETE = "set_complete"
    TIME_UP = "time_up"
    THREE_WHIFFS = "three_whiffs"
    FOULED_OUT = "fouled_out"
    RETIRED = "retired"


@dataclass
class FlytingRunState:
    """Mutable state of one flyting run, persisted as JSON on the session row."""

    play_format: PlayFormat = PlayFormat.BATTING_PRACTICE
    batting_format: Optional[BattingFormat] = BattingFormat.SET_10
    shot_clock_s: int = 20
    momentum: int = MOMENTUM_START
    heat: float = HEAT_MIN
    whiffs: int = 0
    player_total: int = 0
    npc_total: int = 0
    banked_total: int = 0
    round_number: int = 0
    player_volleys: int = 0
    npc_volleys: int = 0
    best_volley_score: int = 0
    sudden_death: bool = False
    theme_uses: Dict[str, int] = field(default_factory=dict)
    recent_devices: List[List[str]] = field(default_factory=list)
    discovered_traits: List[str] = field(default_factory=list)
    foul_counts: Dict[str, int] = field(default_factory=dict)
    elapsed_s: float = 0.0
    daily_seed: Optional[int] = None
    outcome: str = RunOutcome.IN_PROGRESS.value

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "play_format": self.play_format.value,
            "batting_format": self.batting_format.value if self.batting_format else None,
            "shot_clock_s": self.shot_clock_s,
            "momentum": self.momentum,
            "heat": round(self.heat, 2),
            "whiffs": self.whiffs,
            "player_total": self.player_total,
            "npc_total": self.npc_total,
            "banked_total": self.banked_total,
            "round_number": self.round_number,
            "player_volleys": self.player_volleys,
            "npc_volleys": self.npc_volleys,
            "best_volley_score": self.best_volley_score,
            "sudden_death": self.sudden_death,
            "theme_uses": dict(self.theme_uses),
            "recent_devices": [list(d) for d in self.recent_devices],
            "discovered_traits": list(self.discovered_traits),
            "foul_counts": dict(self.foul_counts),
            "elapsed_s": round(self.elapsed_s, 2),
            "daily_seed": self.daily_seed,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "FlytingRunState":
        if not isinstance(raw, dict):
            return cls()
        try:
            play_format = PlayFormat(str(raw.get("play_format") or PlayFormat.BATTING_PRACTICE.value))
        except ValueError:
            play_format = PlayFormat.BATTING_PRACTICE
        batting_raw = raw.get("batting_format")
        try:
            batting = BattingFormat(str(batting_raw)) if batting_raw else None
        except ValueError:
            batting = None
        return cls(
            play_format=play_format,
            batting_format=batting,
            shot_clock_s=int(raw.get("shot_clock_s") or 20),
            momentum=int(raw.get("momentum", MOMENTUM_START)),
            heat=float(raw.get("heat", HEAT_MIN)),
            whiffs=int(raw.get("whiffs", 0)),
            player_total=int(raw.get("player_total", 0)),
            npc_total=int(raw.get("npc_total", 0)),
            banked_total=int(raw.get("banked_total", 0)),
            round_number=int(raw.get("round_number", 0)),
            player_volleys=int(raw.get("player_volleys", 0)),
            npc_volleys=int(raw.get("npc_volleys", 0)),
            best_volley_score=int(raw.get("best_volley_score", 0)),
            sudden_death=bool(raw.get("sudden_death", False)),
            theme_uses={str(k): int(v) for k, v in (raw.get("theme_uses") or {}).items()},
            recent_devices=[list(d) for d in (raw.get("recent_devices") or []) if isinstance(d, list)],
            discovered_traits=[str(t) for t in (raw.get("discovered_traits") or [])],
            foul_counts={str(k): int(v) for k, v in (raw.get("foul_counts") or {}).items()},
            elapsed_s=float(raw.get("elapsed_s", 0.0)),
            daily_seed=raw.get("daily_seed"),
            outcome=str(raw.get("outcome") or RunOutcome.IN_PROGRESS.value),
        )

    # ── Derived views ────────────────────────────────────────────────────────

    @property
    def is_over(self) -> bool:
        return self.outcome != RunOutcome.IN_PROGRESS.value

    @property
    def volleys_remaining(self) -> Optional[int]:
        """Volleys left in a set, or None where the format is not volley-bounded."""
        if self.play_format is PlayFormat.BATTING_PRACTICE and self.batting_format is BattingFormat.SET_10:
            return max(0, SET_FORMAT_VOLLEYS - self.player_volleys)
        return None

    @property
    def seconds_remaining(self) -> Optional[float]:
        if self.play_format is PlayFormat.BATTING_PRACTICE and self.batting_format is BattingFormat.TIMED_90:
            return max(0.0, TIMED_FORMAT_SECONDS - self.elapsed_s)
        return None

    @property
    def whiffs_remaining(self) -> Optional[int]:
        if self.play_format is PlayFormat.BATTING_PRACTICE and self.batting_format is BattingFormat.ENDLESS:
            return max(0, ENDLESS_MAX_WHIFFS - self.whiffs)
        return None


# ---------------------------------------------------------------------------
# Heat
# ---------------------------------------------------------------------------


def next_heat(current: float, score: int, *, whiffed: bool) -> float:
    """Heat after a volley: +0.1 for a hit, reset to 1.0 for a dud or foul."""
    if whiffed or score < HEAT_THRESHOLD:
        return HEAT_MIN
    return min(HEAT_MAX, round(current + HEAT_STEP, 2))


# ---------------------------------------------------------------------------
# Applying a scored volley
# ---------------------------------------------------------------------------


def record_player_volley(state: FlytingRunState, score: VolleyScore) -> None:
    """Fold a scored player volley into the run state.

    Heat is applied by the caller *before* composition (the multiplier in force
    at the moment of scoring is the one that pays), so this updates the heat for
    the next volley, not for this one.
    """
    state.player_volleys += 1
    state.player_total += score.score
    state.banked_total += score.banked_score
    state.best_volley_score = max(state.best_volley_score, score.score)

    if score.gate.foul is not None:
        key = score.gate.foul.value
        state.foul_counts[key] = state.foul_counts.get(key, 0) + 1

    whiffed = score.is_whiff
    if whiffed:
        state.whiffs += 1
    # Heat is a batting-practice mechanic. A bout is decided on raw cumulative
    # score against the opponent's, so letting heat build there would put a
    # multiplier on the board total that the win condition never reads — the
    # board would record a different number than the game was decided on.
    if state.play_format is PlayFormat.BATTING_PRACTICE:
        state.heat = next_heat(state.heat, score.score, whiffed=whiffed)

    if score.judgment is not None:
        for theme in score.judgment.themes:
            state.theme_uses[theme] = state.theme_uses.get(theme, 0) + 1
        state.recent_devices.append(list(score.judgment.devices))
        del state.recent_devices[:-6]
        for hook in score.judgment.hooks:
            if hook.trait not in state.discovered_traits:
                state.discovered_traits.append(hook.trait)


def record_npc_volley(state: FlytingRunState, score: VolleyScore) -> None:
    """Fold a scored opponent volley into the run state.

    The opponent's themes count toward theme usage and its text joins the
    novelty corpus (handled by the caller), so parroting the opponent is
    redundancy rather than cleverness.
    """
    state.npc_volleys += 1
    state.npc_total += score.score
    if score.judgment is not None:
        for theme in score.judgment.themes:
            state.theme_uses[theme] = state.theme_uses.get(theme, 0) + 1


# ---------------------------------------------------------------------------
# The bout
# ---------------------------------------------------------------------------


@dataclass
class ExchangeResult:
    """What one bout exchange did to the crowd."""

    momentum: int
    momentum_delta: int
    proposed_delta: float
    clamped: bool
    outcome: str


def resolve_exchange(
    state: FlytingRunState,
    player_score: int,
    npc_score: int,
    bout: BoutConfig,
    *,
    variable_def: Optional[ScenarioVariableDef] = None,
) -> ExchangeResult:
    """Shift momentum by ``k · (S_player − S_npc) / 100`` and test for a win.

    The shift goes through the ordinary state engine so the scenario's
    ``max_delta_per_turn`` bounds it; when the clamp bites, the result says so,
    and the scorecard can show that the crowd only moves so fast.
    """
    defn = variable_def or FLYTING_VARIABLE_DEFAULTS["momentum"]
    proposed = bout.momentum_k * (player_score - npc_score) / 100.0
    # Round away from zero so a won exchange always moves the crowd at least one
    # notch; a 0.4 shift that truncates to nothing makes the meter look broken.
    proposed_int = int(proposed + (0.5 if proposed >= 0 else -0.5))
    if proposed_int == 0 and player_score != npc_score:
        proposed_int = 1 if player_score > npc_score else -1

    delta_result = apply_state_delta(
        {"momentum": state.momentum}, {"momentum": proposed_int}, {"momentum": defn}
    )
    new_momentum = delta_result.new_state["momentum"]
    actual = delta_result.actual_changes.get("momentum", 0)
    clamped = abs(proposed_int) > defn.max_delta_per_turn

    state.momentum = new_momentum
    state.round_number += 1

    outcome = RunOutcome.IN_PROGRESS.value
    if new_momentum >= bout.momentum_win:
        outcome = RunOutcome.MOMENTUM_WIN.value
    elif new_momentum <= (100 - bout.momentum_win):
        outcome = RunOutcome.MOMENTUM_LOSS.value
    elif state.round_number >= bout.rounds:
        if state.player_total > state.npc_total:
            outcome = RunOutcome.POINTS_WIN.value
        elif state.player_total < state.npc_total:
            outcome = RunOutcome.POINTS_LOSS.value
        elif state.sudden_death:
            # A sudden-death volley that ties again is an honest draw.
            outcome = RunOutcome.DRAW.value
        else:
            state.sudden_death = True

    state.outcome = outcome
    return ExchangeResult(
        momentum=new_momentum,
        momentum_delta=actual,
        proposed_delta=proposed,
        clamped=clamped,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Batting practice
# ---------------------------------------------------------------------------


def resolve_batting_practice(state: FlytingRunState, *, foul_ended: bool = False) -> str:
    """Return the run outcome after a batting-practice volley."""
    if foul_ended:
        state.outcome = RunOutcome.FOULED_OUT.value
        return state.outcome

    fmt = state.batting_format
    if fmt is BattingFormat.SET_10 and state.player_volleys >= SET_FORMAT_VOLLEYS:
        state.outcome = RunOutcome.SET_COMPLETE.value
    elif fmt is BattingFormat.TIMED_90 and state.elapsed_s >= TIMED_FORMAT_SECONDS:
        state.outcome = RunOutcome.TIME_UP.value
    elif fmt is BattingFormat.ENDLESS and state.whiffs >= ENDLESS_MAX_WHIFFS:
        state.outcome = RunOutcome.THREE_WHIFFS.value
    return state.outcome


def shot_clock_expired(state: FlytingRunState, elapsed_since_prompt_s: float) -> bool:
    """Whether a volley arrived after its shot clock ran out."""
    return elapsed_since_prompt_s > state.shot_clock_s


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------


@dataclass
class RunSummary:
    """Aggregates over the volleys of one run — pure functions of the volley log."""

    play_format: str
    batting_format: Optional[str]
    outcome: str
    total_score: int
    player_total: int
    npc_total: int
    volley_count: int
    best_volley_score: int
    best_volley_text: Optional[str]
    peak_heat: float
    final_momentum: Optional[int]
    whiffs: int
    fouls: Dict[str, int]
    theme_report: List[Dict[str, Any]]
    device_histogram: Dict[str, int]
    rarest_words: List[str]
    coaching_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "play_format": self.play_format,
            "batting_format": self.batting_format,
            "outcome": self.outcome,
            "total_score": self.total_score,
            "player_total": self.player_total,
            "npc_total": self.npc_total,
            "volley_count": self.volley_count,
            "best_volley_score": self.best_volley_score,
            "best_volley_text": self.best_volley_text,
            "peak_heat": round(self.peak_heat, 2),
            "final_momentum": self.final_momentum,
            "whiffs": self.whiffs,
            "fouls": dict(self.fouls),
            "theme_report": list(self.theme_report),
            "device_histogram": dict(self.device_histogram),
            "rarest_words": list(self.rarest_words),
            "coaching_notes": list(self.coaching_notes),
        }


def summarize_run(
    state: FlytingRunState,
    player_volleys: Sequence[VolleyScore],
    *,
    theme_decay: float = 0.75,
) -> RunSummary:
    """Build the debrief aggregates for a finished run."""
    best = max(player_volleys, key=lambda v: v.score, default=None)
    peak_heat = max((v.heat for v in player_volleys), default=HEAT_MIN)

    theme_counts: Dict[str, int] = {}
    devices: Dict[str, int] = {}
    rarest: List[str] = []
    for volley in player_volleys:
        if volley.judgment is not None:
            for theme in volley.judgment.themes:
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
            for device in volley.judgment.devices:
                devices[device] = devices.get(device, 0) + 1
        rarest.extend(volley.craft.rarest_words)

    theme_report = [
        {
            "theme": theme,
            "uses": count,
            # The value the *next* use of this theme would carry.
            "remaining_value": round(theme_decay ** count, 3),
        }
        for theme, count in sorted(theme_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return RunSummary(
        play_format=state.play_format.value,
        batting_format=state.batting_format.value if state.batting_format else None,
        outcome=state.outcome,
        total_score=state.banked_total,
        player_total=state.player_total,
        npc_total=state.npc_total,
        volley_count=len(player_volleys),
        best_volley_score=best.score if best else 0,
        best_volley_text=best.text if best else None,
        peak_heat=peak_heat,
        final_momentum=state.momentum if state.play_format is PlayFormat.BOUT else None,
        whiffs=state.whiffs,
        fouls=dict(state.foul_counts),
        theme_report=theme_report,
        device_histogram=devices,
        rarest_words=sorted(set(rarest))[:8],
        coaching_notes=coaching_notes(player_volleys, theme_report),
    )


def coaching_notes(
    player_volleys: Sequence[VolleyScore],
    theme_report: Sequence[Dict[str, Any]],
) -> List[str]:
    """Observations a player can act on, derived from the volley log alone."""
    notes: List[str] = []
    scored = [v for v in player_volleys if not v.gate.scores_zero]
    if not scored:
        return ["Nothing landed this run. Three words minimum, aimed at the target."]

    # Openers versus closers: do they start hot and pad?
    if len(scored) >= 4:
        half = len(scored) // 2
        opening = sum(v.score for v in scored[:half]) / half
        closing = sum(v.score for v in scored[-half:]) / half
        if opening >= closing * 1.5:
            notes.append(
                f"Your openers outscored your closers {opening:.0f} to {closing:.0f} — "
                "you start hot and then pad."
            )
        elif closing >= opening * 1.5:
            notes.append(
                f"You warmed up: {opening:.0f} early against {closing:.0f} late. "
                "Try opening with the line you found in round three."
            )

    over_used = [t for t in theme_report if t["uses"] >= 3]
    if over_used:
        worst = over_used[0]
        notes.append(
            f"You went to {worst['theme']} {worst['uses']} times; its value had decayed "
            f"to {int(worst['remaining_value'] * 100)}%. Variety is the meta."
        )

    unaimed = sum(1 for v in scored if "no_aim" in v.flags)
    if unaimed >= 2:
        notes.append(
            f"{unaimed} volleys never pointed at anyone. Sting needs a target in the sentence."
        )

    hooked = [v for v in scored if v.judgment is not None and v.judgment.hooks]
    if scored and len(hooked) <= len(scored) // 3:
        notes.append(
            "Most of your volleys landed on nothing in particular. Read the attack "
            "surface and aim at a named trait."
        )

    run_ons = sum(1 for v in scored if "run_on" in v.flags)
    if run_ons:
        notes.append(
            f"{run_ons} volleys ran past sixty words, where the topicality bonus stops "
            "and the decay starts. Cut and sharpen."
        )

    dropped = sum(
        len(v.judgment.dropped_hooks) for v in scored if v.judgment is not None
    )
    if dropped >= 3:
        notes.append(
            "Several claimed hits could not be verified against your own words — "
            "name the trait in the line, do not imply it."
        )

    return notes or ["Solid, varied, and aimed. Raise the difficulty."]
