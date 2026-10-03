# SPDX-License-Identifier: Apache-2.0
"""Stage 4 — composition.

    Q = Σ weight[dim] · judge[dim] / 10                 # 0 .. 1
    T = 1 + Σ hook_bonus[i] · theme_decay               # doubled for a discovery
    F = freshness                                       # 0.1 .. 1.0
    P = scenario difficulty multiplier                  # 0.8 .. 1.5
    D = run-on decay                                    # 1.0, or 0.9^k past 60 words

    S = round(100 · Q · T · F · P · D) + bonuses

    bonuses: riposte (bout only) · callback +10 · device rotation +5 · compound +5

Typical range 0-250: a 100 is a solid hit, 180+ is highlight-reel.

Two rules in here exist specifically to make padding worthless. Past the 60-word
soft cap the run-on decay applies *and* the topicality bonus stops accruing
(T collapses to 1), so a long volley cannot buy hooks with length. And a
plagiarized zinger is capped before bonuses, so a borrowed line plus a riposte
is still a borrowed line.

A foul is also resolved here, not only in Stage 0: the register fouls only a
reader of the scene can raise — overt rudeness in a ballroom, an anachronism
where the scenario forbids one — arrive with the judge's verdict. They are
promoted to a ``GateResult`` and zero the volley exactly as a Stage 0 foul
does, so the dimensions a drifting judge reported alongside a foul it raised
itself can never pay out.

Every number that went into the score is kept on the result, because the
scorecard showing its own arithmetic is what makes this a practice tool rather
than a slot machine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from convsim_prompt import JUDGE_DIMENSIONS, JudgeRubric, VolleyJudgment

from convsim_core.flyting.config import band_for_score
from convsim_core.flyting.craft import CraftMetrics
from convsim_core.flyting.gates import (
    ALWAYS_HONORED_JUDGE_FOULS,
    GateResult,
    judge_foul_result,
)
from convsim_core.flyting.novelty import FreshnessResult
from convsim_core.flyting.volley import NormalizedVolley

CALLBACK_BONUS = 10
DEVICE_ROTATION_BONUS = 5
COMPOUND_BONUS = 5

# A device counts as rotated in when it has not appeared in this many prior volleys.
DEVICE_ROTATION_WINDOW = 3

# Mechanical stand-ins used when the judge produced nothing usable. Deliberately
# modest: a player should not be punished for our outage, and should not be able
# to farm a high score from one either.
_MECHANICAL_AIMED_STING = 6
_MECHANICAL_UNAIMED_STING = 2
_MECHANICAL_FIDELITY = 5


@dataclass
class Bonus:
    id: str
    points: int
    evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "points": self.points, "evidence": self.evidence}


@dataclass
class VolleyScore:
    """A complete per-volley scorecard — see schemas/volley-score.schema.json."""

    volley_number: int
    speaker: str
    text: str
    score: int
    band: str
    gate: GateResult
    craft: CraftMetrics
    freshness: FreshnessResult
    judgment: Optional[VolleyJudgment] = None
    quality: float = 0.0
    topicality: float = 1.0
    difficulty: float = 1.0
    run_on_decay: float = 1.0
    base: int = 0
    bonuses: List[Bonus] = field(default_factory=list)
    heat: float = 1.0
    banked_score: int = 0
    momentum: Optional[int] = None
    flags: List[str] = field(default_factory=list)
    audience_reaction: Optional[str] = None

    @property
    def bonus_total(self) -> int:
        return sum(b.points for b in self.bonuses)

    @property
    def is_whiff(self) -> bool:
        """A whiff: a dud, a foul, or a shot clock that ran out."""
        return self.gate.scores_zero or "shot_clock_expired" in self.flags

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to volley-score.schema.json."""
        payload: Dict[str, Any] = {
            "volley_number": self.volley_number,
            "speaker": self.speaker,
            "score": self.score,
            "band": self.band,
            "gate": self.gate.to_dict(),
            "composition": {
                "quality": round(self.quality, 4),
                "topicality": round(self.topicality, 4),
                "freshness": round(self.freshness.value, 4),
                "difficulty": round(self.difficulty, 4),
                "run_on_decay": round(self.run_on_decay, 4),
                "base": self.base,
                "bonuses": [b.to_dict() for b in self.bonuses],
                "bonus_total": self.bonus_total,
            },
            "judge": self.judgment.to_dict() if self.judgment else None,
            "craft_metrics": self.craft.to_dict(),
            "freshness": self.freshness.to_dict(),
            "heat": round(self.heat, 2),
            "banked_score": self.banked_score,
            "flags": list(self.flags),
            "audience_reaction": self.audience_reaction,
        }
        if self.momentum is not None:
            payload["momentum"] = self.momentum
        return payload


def _mechanical_dimensions(craft: CraftMetrics) -> Dict[str, float]:
    """Judge-scale estimates from Stage 1 alone, for when the judge is unavailable.

    Aim is the one dimension mechanics can speak to honestly (second-person
    anchoring), wit is approximated from rarity and variety, craft uses the
    craft floor directly, and fidelity — which no deterministic metric can read
    — sits at the neutral midpoint rather than guessing.
    """
    return {
        "sting": _MECHANICAL_AIMED_STING if craft.second_person else _MECHANICAL_UNAIMED_STING,
        "wit": 10 * (0.6 * craft.rarity_reward + 0.4 * craft.variety_reward),
        "craft": craft.craft_floor,
        "fidelity": _MECHANICAL_FIDELITY,
    }


def compute_quality(
    judgment: Optional[VolleyJudgment],
    craft: CraftMetrics,
    rubric: JudgeRubric,
) -> float:
    """Q — the weighted judge dimensions, normalised to 0..1."""
    weights = rubric.normalized_weights()
    dims = (
        {k: float(v) for k, v in judgment.dimensions().items()}
        if judgment is not None
        else _mechanical_dimensions(craft)
    )
    total = sum(weights.get(dim, 0.0) * dims.get(dim, 0.0) for dim in JUDGE_DIMENSIONS)
    return max(0.0, min(1.0, total / 10.0))


def compute_topicality(
    judgment: Optional[VolleyJudgment],
    rubric: JudgeRubric,
    theme_decay: float,
    *,
    run_on: bool,
) -> float:
    """T — 1 plus the decayed hook bonuses, doubled for a trait discovered now.

    Returns a flat 1.0 for a run-on volley: past the soft cap the topicality
    bonus stops accruing, so padding a volley with more angles is worth nothing.
    """
    if judgment is None or run_on or not judgment.hooks:
        return 1.0
    bonus = 0.0
    for index, hook in enumerate(judgment.hooks[: len(rubric.hook_bonus)]):
        weight = rubric.hook_bonus[index]
        if hook.discovered:
            weight *= 2  # a discoverable trait is worth double on discovery
        bonus += weight * theme_decay
    return 1.0 + bonus


def _device_rotation_earned(
    devices: Sequence[str],
    recent_devices: Sequence[Sequence[str]],
) -> Optional[str]:
    """The first device in this volley unused across the last few volleys."""
    if not devices:
        return None
    window = set()
    for prior in list(recent_devices)[-DEVICE_ROTATION_WINDOW:]:
        window.update(prior)
    for device in devices:
        if device not in window:
            return device
    return None


def _compound_earned(
    volley: NormalizedVolley,
    judgment: Optional[VolleyJudgment],
) -> bool:
    """Two independent constructions that both land.

    Operationalised as: at least two substantial clauses, and at least two
    distinct devices or two verified hooks — so a single long sentence with one
    figure in it does not qualify, and neither does a pair of clauses that do
    nothing.
    """
    if judgment is None or len(volley.independent_clauses) < 2:
        return False
    return len(judgment.devices) >= 2 or len(judgment.hooks) >= 2


def compose_volley_score(
    *,
    volley_number: int,
    speaker: str,
    volley: NormalizedVolley,
    gate: GateResult,
    craft: CraftMetrics,
    freshness: FreshnessResult,
    judgment: Optional[VolleyJudgment],
    rubric: JudgeRubric,
    difficulty_multiplier: float = 1.0,
    riposte_bonus: int = 0,
    recent_devices: Sequence[Sequence[str]] = (),
    heat: float = 1.0,
    momentum: Optional[int] = None,
    audience_reaction: Optional[str] = None,
    extra_flags: Sequence[str] = (),
    honored_judge_fouls: Sequence[str] = ALWAYS_HONORED_JUDGE_FOULS,
    prior_below_the_belt: int = 0,
) -> VolleyScore:
    """Compose one volley's final score from the four stages' outputs."""
    # Flags come from three places: the volley's own bounds (too_short, run_on),
    # the gates (gibberish, plagiarized_zinger), and the caller (shot_clock).
    flags: List[str] = list(dict.fromkeys([*volley.flags, *gate.flags, *extra_flags]))
    if judgment is None and not gate.scores_zero:
        flags.append("judge_unavailable")
    if not craft.second_person and not gate.scores_zero and "no_aim" not in flags:
        flags.append("no_aim")

    # A foul the judge raised is a verdict, not a scoring opinion: the dimensions
    # it also reported are beside the point. Promote it to a gate result so the
    # volley is zeroed, the foul is recorded, the heat resets, and the player
    # sees a foul tag — the same treatment a Stage 0 foul gets. Only the fouls
    # this scenario asked for count; see gates.judge_foul_result.
    if not gate.scores_zero and judgment is not None and judgment.fouls:
        judged_gate = judge_foul_result(
            judgment.fouls,
            honored=honored_judge_fouls,
            prior_below_the_belt=prior_below_the_belt,
        )
        if judged_gate is not None:
            gate = judged_gate
            flags.extend(f for f in judged_gate.flags if f not in flags)

    # A gate that fired scores zero: no quality, no topicality, no bonuses.
    if gate.scores_zero:
        result = VolleyScore(
            volley_number=volley_number,
            speaker=speaker,
            text=volley.text,
            score=0,
            band=band_for_score(0),
            gate=gate,
            craft=craft,
            freshness=freshness,
            judgment=judgment,
            quality=0.0,
            topicality=1.0,
            difficulty=difficulty_multiplier,
            run_on_decay=volley.decay,
            base=0,
            heat=heat,
            banked_score=0,
            momentum=momentum,
            flags=flags,
            audience_reaction=None,
        )
        return result

    quality = compute_quality(judgment, craft, rubric)
    theme_decay = freshness.theme_decay
    topicality = compute_topicality(judgment, rubric, theme_decay, run_on=volley.is_run_on)
    decay = volley.decay

    base = round(100 * quality * topicality * freshness.value * difficulty_multiplier * decay)

    bonuses: List[Bonus] = []
    capped = gate.score_cap is not None
    if capped:
        # Borrowed material is capped before bonuses, so a famous line with a
        # riposte attached is still just a famous line.
        base = min(base, int(gate.score_cap or 0))
    else:
        if judgment is not None:
            if judgment.riposte.claimed and riposte_bonus > 0:
                bonuses.append(Bonus("riposte", riposte_bonus, judgment.riposte.evidence))
            if judgment.callback.claimed:
                bonuses.append(Bonus("callback", CALLBACK_BONUS, judgment.callback.evidence))
            rotated = _device_rotation_earned(judgment.devices, recent_devices)
            if rotated is not None:
                bonuses.append(Bonus("device_rotation", DEVICE_ROTATION_BONUS, rotated))
            if _compound_earned(volley, judgment):
                bonuses.append(Bonus("compound", COMPOUND_BONUS))

    score = max(0, base + sum(b.points for b in bonuses))

    return VolleyScore(
        volley_number=volley_number,
        speaker=speaker,
        text=volley.text,
        score=score,
        band=band_for_score(score),
        gate=gate,
        craft=craft,
        freshness=freshness,
        judgment=judgment,
        quality=quality,
        topicality=topicality,
        difficulty=difficulty_multiplier,
        run_on_decay=decay,
        base=base,
        bonuses=bonuses,
        heat=heat,
        banked_score=round(score * heat),
        momentum=momentum,
        flags=flags,
        audience_reaction=audience_reaction,
    )
