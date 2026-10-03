// SPDX-License-Identifier: Apache-2.0
//
// The flyting (turn-scored) mode contract, mirroring what
// /api/flyting/* returns. Two documents are authoritative and these types
// follow them field for field:
//
//   schemas/volley-score.schema.json  — one scorecard per volley
//   services/convsim-core/convsim_core/routers/flyting.py — the route payloads
//
// Everything here is runtime output. Nothing in this file is pack-authored, so
// there are no optional-for-authoring fields: a value is optional only when the
// engine genuinely may not produce it (no judge, no scene audience, no bout).

export type PlayFormat = 'bout' | 'batting_practice';
export type BattingFormat = 'timed_90' | 'set_10' | 'endless';
export type VolleyBand = 'dud' | 'weak' | 'solid' | 'strong' | 'highlight';
export type GateOutcome = 'ok' | 'dud' | 'foul';
export type FreshnessMethod = 'embedding' | 'lexical';
export type BonusId = 'riposte' | 'callback' | 'device_rotation' | 'compound';

export type VolleyFoul =
  | 'below_the_belt'
  | 'out_of_fiction'
  | 'bribing_the_ref'
  | 'overt_rudeness'
  | 'anachronism';

export type VolleyFlag =
  | 'plagiarized_zinger'
  | 'run_on'
  | 'gibberish'
  | 'no_aim'
  | 'too_short'
  | 'judge_unavailable'
  | 'judge_foul'
  | 'shot_clock_expired'
  | 'whiff';

/** The four judged dimensions, in the order the scorecard shows them. */
export const JUDGE_DIMENSIONS = ['sting', 'wit', 'craft', 'fidelity'] as const;
export type JudgeDimension = (typeof JUDGE_DIMENSIONS)[number];

export interface VolleyGate {
  outcome: GateOutcome;
  foul?: VolleyFoul | null;
  reason?: string | null;
  /** In-character line shown when the gate fired. */
  umpire_mock?: string | null;
  ends_session?: boolean;
}

export interface VolleyBonus {
  id: BonusId;
  points: number;
  evidence?: string | null;
}

export interface VolleyComposition {
  /** Q — weighted judge dimensions, 0..1. */
  quality: number;
  /** T — 1 plus the decayed hook bonuses. */
  topicality: number;
  /** F — clamp(1 − s_max², 0.1, 1.0). */
  freshness: number;
  /** P — the scenario's difficulty multiplier. */
  difficulty: number;
  run_on_decay?: number;
  base: number;
  bonuses?: VolleyBonus[];
  bonus_total: number;
}

export interface VolleyHook {
  trait: string;
  evidence: string;
  /** True when this volley was the first to strike a discoverable trait. */
  discovered?: boolean;
}

export type DroppedHookReason =
  | 'unknown_trait'
  | 'evidence_not_in_volley'
  | 'duplicate_trait'
  /** Quoted the same words as a hook already accepted for this volley. */
  | 'overlapping_evidence'
  | 'over_hook_cap';

export interface DroppedHook {
  trait: string;
  evidence?: string | null;
  reason: DroppedHookReason;
}

export interface EvidenceClaim {
  evidence?: string | null;
}

export interface VolleyJudgment {
  sting: number;
  wit: number;
  craft: number;
  fidelity: number;
  hooks?: VolleyHook[];
  themes?: string[];
  devices?: string[];
  riposte?: EvidenceClaim & { is_riposte?: boolean };
  callback?: EvidenceClaim & { is_callback?: boolean };
  fouls?: string[];
  umpire_line?: string;
  /** Hook claims the engine refused — shown so the judge stays auditable. */
  dropped_hooks?: DroppedHook[];
}

export interface VolleyCraftMetrics {
  word_count: number;
  content_word_count?: number;
  type_token_ratio: number;
  mean_zipf: number;
  rarity_reward?: number;
  variety_reward?: number;
  sound_reward?: number;
  alliteration_runs?: number;
  assonance_runs?: number;
  rhyme_pairs?: number;
  scansion_regularity?: number;
  second_person: boolean;
  craft_floor?: number;
  rarest_words?: string[];
}

export interface VolleyFreshness {
  value: number;
  s_max: number;
  method: FreshnessMethod;
  nearest_source?: 'none' | 'session' | 'cliche';
  nearest_label?: string | null;
  theme_uses?: Record<string, number>;
  theme_decay?: number;
}

/** One volley's complete scorecard — schemas/volley-score.schema.json. */
export interface VolleyScorecard {
  volley_number: number;
  speaker: 'player' | 'npc';
  score: number;
  band: VolleyBand;
  gate: VolleyGate;
  composition: VolleyComposition;
  judge?: VolleyJudgment | null;
  craft_metrics: VolleyCraftMetrics;
  freshness: VolleyFreshness;
  heat?: number;
  banked_score?: number;
  momentum?: number;
  flags: VolleyFlag[];
  audience_reaction?: string | null;
}

/** A stored volley: the text plus its scorecard, as the volley log returns it. */
export interface FlytingVolleyLogEntry {
  speaker: 'player' | 'npc';
  text: string;
  score: number;
  band: VolleyBand;
  heat: number;
  banked_score: number;
  momentum: number | null;
  scorecard: VolleyScorecard;
  created_at: string;
}

export interface FlytingRunState {
  play_format: PlayFormat;
  batting_format: BattingFormat | null;
  shot_clock_s: number;
  momentum: number;
  heat: number;
  whiffs: number;
  player_total: number;
  npc_total: number;
  banked_total: number;
  round_number: number;
  player_volleys: number;
  npc_volleys: number;
  best_volley_score: number;
  sudden_death: boolean;
  theme_uses: Record<string, number>;
  /** The opponent's own theme record, kept apart so each side's repeats decay
   *  only that side's topicality. */
  npc_theme_uses: Record<string, number>;
  recent_devices: string[][];
  discovered_traits: string[];
  foul_counts: Record<string, number>;
  elapsed_s: number;
  daily_seed: number | null;
  outcome: string | null;
}

export interface AttackSurfaceTraitBrief {
  id: string;
  brief: string;
}

/** The setup payload: everything the format picker and the brief need. */
export interface FlytingScenarioSetup {
  scenario_id: string;
  pack_id: string | null;
  title: string;
  summary: string;
  mode: 'flyting';
  content_rating: string;
  player_role: { label: string; brief: string };
  target: {
    npc_id: string;
    display_name: string;
    /** Only the visible half of the surface; discoverables are counted, not named. */
    attack_surface: AttackSurfaceTraitBrief[];
    discoverable_count: number;
  };
  formats: PlayFormat[];
  batting_formats: BattingFormat[];
  shot_clock_s: number;
  bout: {
    rounds: number;
    momentum_win: number;
    riposte_bonus: number;
    npc_tier: string;
    npc_tier_label: string;
  };
  difficulty_multiplier: number;
  verse_required: boolean;
  requires_surface_politeness: boolean;
  lexicon_hints: string[];
  judge_flavor: string;
  audience: { label: string } | null;
  personal_bests: Record<string, number | null>;
  goals: string[];
  limits: {
    max_volley_chars: number;
    set_volleys: number;
    timed_seconds: number;
    endless_whiffs: number;
  };
}

export interface FlytingRunCreateRequest {
  scenario_id: string;
  play_format: PlayFormat;
  batting_format?: BattingFormat | null;
  use_daily_seed?: boolean;
  save_transcript?: boolean;
}

export interface FlytingRunCreateResponse {
  session_id: string;
  scenario_id: string;
  state: string;
  run: FlytingRunState;
  created_at: string;
}

export interface FlytingExchange {
  momentum: number;
  momentum_delta: number;
  clamped: boolean;
}

export interface FlytingVolleyResponse {
  session_id: string;
  state: string;
  player_volley: VolleyScorecard;
  npc_line: string | null;
  npc_volley: VolleyScorecard | null;
  exchange: FlytingExchange | null;
  run: FlytingRunState;
  run_outcome: string | null;
  /** Null where the format is not bounded that way (a bout has no volley cap). */
  volleys_remaining: number | null;
  seconds_remaining: number | null;
  whiffs_remaining: number | null;
}

export interface FlytingRunDetail {
  session_id: string;
  scenario_id: string;
  state: string;
  run: FlytingRunState;
  volleys: FlytingVolleyLogEntry[];
  volleys_remaining: number | null;
  seconds_remaining: number | null;
  whiffs_remaining: number | null;
}

export interface FlytingThemeReportEntry {
  theme: string;
  uses: number;
  /** The value the *next* use of this theme would carry, 0..1. */
  remaining_value: number;
}

export interface FlytingRunSummary {
  play_format: PlayFormat;
  batting_format: BattingFormat | null;
  outcome: string;
  total_score: number;
  player_total: number;
  npc_total: number;
  volley_count: number;
  best_volley_score: number;
  best_volley_text: string | null;
  peak_heat: number;
  final_momentum: number | null;
  whiffs: number;
  fouls: Record<string, number>;
  theme_report: FlytingThemeReportEntry[];
  device_histogram: Record<string, number>;
  rarest_words: string[];
  coaching_notes: string[];
}

export interface FlytingRunSummaryResponse {
  session_id: string;
  scenario_id: string;
  summary: FlytingRunSummary;
  volleys: FlytingVolleyLogEntry[];
  high_score_rank: number | null;
  personal_best: number | null;
}

export interface FlytingHighScore {
  scenario_id: string;
  pack_id: string | null;
  play_format: PlayFormat;
  batting_format: BattingFormat | null;
  session_id: string | null;
  outcome: string | null;
  total_score: number;
  volley_count: number;
  best_volley_score: number;
  peak_heat: number;
  daily_seed: number | null;
  achieved_at: string;
}

export interface FlytingHighScoresResponse {
  scenario_id: string;
  play_format: PlayFormat | null;
  batting_format: BattingFormat | null;
  entries: FlytingHighScore[];
}

export interface FlytingPreviewResponse {
  scenario_id: string;
  volley: VolleyScorecard;
  judge_input: { system_prompt_preview: string };
}
