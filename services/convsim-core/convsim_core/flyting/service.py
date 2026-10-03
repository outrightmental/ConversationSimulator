# SPDX-License-Identifier: Apache-2.0
"""The volley scoring service: Stages 0-4, assembled.

The model call is not in here. ``prepare()`` runs the deterministic stages
(gates, craft, novelty) and ``compose()`` runs the arithmetic; between them the
caller makes exactly one judge call with the prompt from ``judge_input()``. That
split is what lets the whole pipeline be tested, and the whole scorecard be
reproduced, without a model — which is also how the calibration suite runs in
CI and how the engine degrades when no judge is available.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

from convsim_prompt import (
    AttackSurfaceTrait,
    JudgeRubric,
    VolleyJudgeInput,
    VolleyJudgment,
)

from convsim_core.flyting.config import AudienceConfig, FlytingConfig
from convsim_core.flyting.corpus import cliche_insults
from convsim_core.flyting.craft import CraftMetrics, compute_craft_metrics
from convsim_core.flyting.gates import (
    ALWAYS_HONORED_JUDGE_FOULS,
    GateResult,
    evaluate_gates,
)
from convsim_core.flyting.novelty import (
    EmbeddingProvider,
    FreshnessResult,
    compute_freshness,
    theme_decay_factor,
)
from convsim_core.flyting.scoring import VolleyScore, compose_volley_score
from convsim_core.flyting.volley import NormalizedVolley, analyze_volley
from convsim_core.input_router import SafetyPolicyConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoringContext:
    """Everything about a scenario that the scorer needs, resolved once."""

    scenario_id: str
    scenario_title: str
    flyting: FlytingConfig
    safety_policy: SafetyPolicyConfig
    rubric: JudgeRubric = field(default_factory=JudgeRubric)
    attack_surface: Tuple[AttackSurfaceTrait, ...] = ()
    target_name: str = "the target"
    setting_brief: str = ""
    audience: Optional[AudienceConfig] = None
    content_rating: str = "PG-13"


@dataclass
class PreparedVolley:
    """A volley through Stages 0-2, ready for the judge and then composition."""

    volley: NormalizedVolley
    gate: GateResult
    craft: CraftMetrics
    freshness: FreshnessResult

    @property
    def needs_judge(self) -> bool:
        """A volley the gates already zeroed is not worth a model call."""
        return not self.gate.scores_zero


class VolleyScoringService:
    """Scores volleys for one scenario, one session at a time."""

    def __init__(
        self,
        context: ScoringContext,
        *,
        embedding_provider: Optional[EmbeddingProvider] = None,
        cliches: Optional[Sequence[str]] = None,
    ) -> None:
        self.context = context
        self._embedding_provider = embedding_provider
        self._cliches = tuple(cliches) if cliches is not None else cliche_insults()

    @property
    def honored_judge_fouls(self) -> Tuple[str, ...]:
        """The judge fouls this scenario asked for, and so will act on.

        Safety and out-of-fiction are never a pack's choice. The other two are
        exactly the ones the judge prompt only requests under a policy: overt
        rudeness where the register makes it a foul rather than a fidelity cost,
        and anachronism where the lexicon policy is ``forbid`` rather than
        ``penalize``. Acting on a foul the judge was never asked to raise would
        void volleys in scenarios whose authors chose a penalty instead.
        """
        flyting = self.context.flyting
        honored = list(ALWAYS_HONORED_JUDGE_FOULS)
        if flyting.register.overt_rudeness_is_foul:
            honored.append("overt_rudeness")
        if flyting.lexicon.anachronism_policy == "forbid":
            honored.append("anachronism")
        return tuple(honored)

    # ── Stages 0-2 ───────────────────────────────────────────────────────────

    def prepare(
        self,
        raw_text: str,
        *,
        prior_volleys: Sequence[str] = (),
        prior_below_the_belt: int = 0,
    ) -> PreparedVolley:
        """Normalise, gate, measure, and compare one volley. No model involved.

        Raises ``VolleyInputError`` when the text exceeds the hard character cap.
        """
        volley = analyze_volley(raw_text)
        craft = compute_craft_metrics(
            volley,
            verse=self.context.flyting.verse.required,
            min_alliteration_run=self.context.flyting.verse.min_alliteration_run,
        )
        gate = evaluate_gates(
            volley,
            craft,
            safety_policy=self.context.safety_policy,
            lexicon=self.context.flyting.lexicon,
            prior_below_the_belt=prior_below_the_belt,
        )
        if gate.scores_zero:
            # Novelty of a zero is meaningless, and comparing it against the
            # session would let a dud poison later volleys' freshness.
            freshness = FreshnessResult(value=1.0, s_max=0.0, method="lexical")
        else:
            freshness = compute_freshness(
                volley.text,
                prior_volleys=prior_volleys,
                cliches=self._cliches,
                provider=self._embedding_provider,
            )
        return PreparedVolley(volley=volley, gate=gate, craft=craft, freshness=freshness)

    # ── Stage 3 input ────────────────────────────────────────────────────────

    def judge_input(
        self,
        prepared: PreparedVolley,
        *,
        speaker: str = "player",
        opponent_last_line: Optional[str] = None,
        earlier_exchanges: Sequence[str] = (),
        theme_uses: Optional[Dict[str, int]] = None,
    ) -> VolleyJudgeInput:
        """Build the judge prompt input for a prepared volley."""
        ctx = self.context
        flyting = ctx.flyting
        return VolleyJudgeInput(
            volley_text=prepared.volley.text,
            scenario_title=ctx.scenario_title,
            setting_brief=ctx.setting_brief,
            target_name=ctx.target_name,
            attack_surface=ctx.attack_surface,
            judge_flavor=flyting.judge_flavor,
            rubric=ctx.rubric,
            require_surface_politeness=flyting.register.require_surface_politeness,
            overt_rudeness_is_foul=flyting.register.overt_rudeness_is_foul,
            register_notes=flyting.register.notes,
            encouraged_lexicon=flyting.lexicon.encouraged,
            discouraged_lexicon=flyting.lexicon.discouraged,
            anachronism_policy=flyting.lexicon.anachronism_policy,
            verse_required=flyting.verse.required,
            content_rating=ctx.content_rating,
            speaker=speaker,
            opponent_last_line=opponent_last_line,
            earlier_exchanges=earlier_exchanges,
            theme_uses=theme_uses,
        )

    # ── Stage 4 ──────────────────────────────────────────────────────────────

    def compose(
        self,
        prepared: PreparedVolley,
        judgment: Optional[VolleyJudgment],
        *,
        volley_number: int,
        speaker: str = "player",
        theme_uses: Optional[Dict[str, int]] = None,
        recent_devices: Sequence[Sequence[str]] = (),
        heat: float = 1.0,
        momentum: Optional[int] = None,
        riposte_bonus: int = 0,
        extra_flags: Sequence[str] = (),
        prior_below_the_belt: int = 0,
    ) -> VolleyScore:
        """Compose the final scorecard for a prepared, judged volley."""
        uses = dict(theme_uses or {})
        themes = judgment.themes if judgment is not None else []
        prepared.freshness.theme_uses = {
            theme: uses.get(theme, 0) for theme in themes
        }
        prepared.freshness.theme_decay = theme_decay_factor(
            themes, uses, self.context.rubric.theme_decay
        )

        score = compose_volley_score(
            volley_number=volley_number,
            speaker=speaker,
            volley=prepared.volley,
            gate=prepared.gate,
            craft=prepared.craft,
            freshness=prepared.freshness,
            judgment=judgment,
            rubric=self.context.rubric,
            difficulty_multiplier=self.context.flyting.difficulty_multiplier,
            riposte_bonus=riposte_bonus,
            recent_devices=recent_devices,
            heat=heat,
            momentum=momentum,
            extra_flags=extra_flags,
            honored_judge_fouls=self.honored_judge_fouls,
            prior_below_the_belt=prior_below_the_belt,
        )

        audience = self.context.audience
        # ``score.gate``, not ``prepared.gate``: a foul the judge raised is
        # resolved during composition, and a fouled volley draws no cheer.
        if audience is not None and not score.gate.scores_zero:
            reaction = audience.reaction_for(score.score)
            if reaction is not None:
                score.audience_reaction = reaction.line

        return score

    # ── Convenience ──────────────────────────────────────────────────────────

    def score_mechanically(
        self,
        raw_text: str,
        *,
        volley_number: int = 1,
        speaker: str = "player",
        prior_volleys: Sequence[str] = (),
        prior_below_the_belt: int = 0,
    ) -> VolleyScore:
        """Score a volley with no judge at all — deterministic end to end.

        This is the path the calibration suite takes in CI, and the path a
        session takes when no model is available.
        """
        prepared = self.prepare(
            raw_text,
            prior_volleys=prior_volleys,
            prior_below_the_belt=prior_below_the_belt,
        )
        return self.compose(
            prepared, None, volley_number=volley_number, speaker=speaker
        )
