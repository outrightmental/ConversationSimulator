# SPDX-License-Identifier: Apache-2.0
"""Flyting — the turn-scored game mode.

A flyting scenario scores every player turn as a *volley* instead of scoring
once at the debrief. The pipeline is five stages, four of which never call a
model:

  Stage 0  gates        deterministic safety, fiction, and plagiarism checks
  Stage 1  craft        lexical rarity, internal variety, sound play, aim
  Stage 2  novelty      freshness against the session and the cliché corpus
  Stage 3  judge        one grammar-constrained local model call per volley
  Stage 4  composition  S = round(100 · Q · T · F · P · D) + bonuses

``service.VolleyScoringService`` owns Stages 0-2 and 4; Stage 3 lives in
``convsim_prompt.flyting_judge`` with the rest of the prompt machinery, and the
single model call is made by ``pipeline.process_volley``.

Nothing here reaches the network. With no embedding model installed, novelty
falls back to a deterministic lexical comparison; with no judge available, a
volley is scored from its mechanics and flagged.
"""
from convsim_core.flyting.config import (
    BAND_THRESHOLDS,
    BattingFormat,
    BoutConfig,
    BattingPracticeConfig,
    AudienceConfig,
    AudienceReaction,
    ENDLESS_MAX_WHIFFS,
    FlytingConfig,
    HEAT_THRESHOLD,
    LexiconConfig,
    NpcTier,
    PlayFormat,
    RegisterConfig,
    SET_FORMAT_VOLLEYS,
    TIER_PROFILES,
    TIMED_FORMAT_SECONDS,
    TierProfile,
    VerseConfig,
    band_for_score,
    daily_seed,
    parse_attack_surface,
    parse_judge_rubric,
    visible_attack_surface,
)
from convsim_core.flyting.craft import CraftMetrics, compute_craft_metrics
from convsim_core.flyting.gates import (
    Foul,
    GateOutcome,
    GateResult,
    PLAGIARISM_SCORE_CAP,
    detect_plagiarism,
    evaluate_gates,
)
from convsim_core.flyting.novelty import (
    EmbeddingProvider,
    FreshnessResult,
    compute_freshness,
    freshness_from_similarity,
    lexical_similarity,
    theme_decay_factor,
)
from convsim_core.flyting.scoring import (
    Bonus,
    VolleyScore,
    compose_volley_score,
    compute_quality,
    compute_topicality,
)
from convsim_core.flyting.service import (
    PreparedVolley,
    ScoringContext,
    VolleyScoringService,
)
from convsim_core.flyting.session import (
    ExchangeResult,
    FLYTING_VARIABLE_DEFAULTS,
    FlytingRunState,
    HEAT_MAX,
    HEAT_MIN,
    HEAT_STEP,
    MOMENTUM_START,
    RunOutcome,
    RunSummary,
    coaching_notes,
    next_heat,
    record_npc_volley,
    record_player_volley,
    resolve_batting_practice,
    resolve_exchange,
    shot_clock_expired,
    summarize_run,
)
from convsim_core.flyting.volley import (
    MAX_VOLLEY_CHARS,
    MIN_VOLLEY_WORDS,
    NormalizedVolley,
    SOFT_WORD_CAP,
    VolleyInputError,
    analyze_volley,
    normalize_volley_text,
    run_on_decay,
)

__all__ = [
    # config
    "AudienceConfig", "AudienceReaction", "BAND_THRESHOLDS", "BattingFormat",
    "BattingPracticeConfig", "BoutConfig", "ENDLESS_MAX_WHIFFS", "FlytingConfig",
    "HEAT_THRESHOLD", "LexiconConfig", "NpcTier", "PlayFormat", "RegisterConfig",
    "SET_FORMAT_VOLLEYS", "TIER_PROFILES", "TIMED_FORMAT_SECONDS", "TierProfile",
    "VerseConfig", "band_for_score", "daily_seed", "parse_attack_surface",
    "parse_judge_rubric", "visible_attack_surface",
    # volley
    "MAX_VOLLEY_CHARS", "MIN_VOLLEY_WORDS", "NormalizedVolley", "SOFT_WORD_CAP",
    "VolleyInputError", "analyze_volley", "normalize_volley_text", "run_on_decay",
    # stages
    "CraftMetrics", "compute_craft_metrics",
    "Foul", "GateOutcome", "GateResult", "PLAGIARISM_SCORE_CAP",
    "detect_plagiarism", "evaluate_gates",
    "EmbeddingProvider", "FreshnessResult", "compute_freshness",
    "freshness_from_similarity", "lexical_similarity", "theme_decay_factor",
    "Bonus", "VolleyScore", "compose_volley_score", "compute_quality",
    "compute_topicality",
    # service
    "PreparedVolley", "ScoringContext", "VolleyScoringService",
    # session
    "ExchangeResult", "FLYTING_VARIABLE_DEFAULTS", "FlytingRunState", "HEAT_MAX",
    "HEAT_MIN", "HEAT_STEP", "MOMENTUM_START", "RunOutcome", "RunSummary",
    "coaching_notes", "next_heat", "record_npc_volley", "record_player_volley",
    "resolve_batting_practice", "resolve_exchange", "shot_clock_expired",
    "summarize_run",
]
