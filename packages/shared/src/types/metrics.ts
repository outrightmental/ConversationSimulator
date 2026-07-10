// SPDX-License-Identifier: Apache-2.0

/**
 * Latency budgets that define "fast enough" on the mid-spec reference machine.
 * All values in milliseconds. PerformanceWarning thresholds are derived from
 * these constants rather than scattered ad-hoc numbers.
 *
 * Reference machine: Apple M2 / NVIDIA RTX 3060 equivalent (the "Comfortable"
 * hardware tier). Nightly CI smoke tests fail when any measured value exceeds
 * the budget by more than 20 %.
 */
export const LATENCY_BUDGETS = {
  /** Cold start → interactive Home. */
  COLD_START_MS: 10_000,
  /** Time-to-first-token on the starter model / recommended tier. */
  TTFT_MS: 2_500,
  /** TTS first-audio chunk ready. */
  TTS_FIRST_AUDIO_MS: 1_500,
  /** STT round-trip for a 10-word utterance. */
  STT_ROUND_TRIP_MS: 2_000,
  /** Maximum full NPC response time before recommending context reduction. */
  FULL_RESPONSE_MS: 10_000,
} as const

/** Latency measurements captured during a conversation session. All values in milliseconds. */
export interface LatencySnapshot {
  /** Time from session start request to first NPC opening event. */
  session_start_ms?: number;
  /** Time from turn submit to first npc.token streaming event. */
  first_token_ms?: number;
  /** Time from turn submit to npc.final (complete response). */
  full_response_ms?: number;
  /** Time for debrief generation to complete. */
  debrief_ms?: number;
  /** Time for STT to return a final transcript. */
  stt_final_ms?: number;
  /** Time for TTS to produce the first audio chunk. */
  tts_first_sentence_ms?: number;
}

/** Machine-readable codes for performance degradation suggestions. */
export type PerformanceSuggestionCode =
  | 'use_smaller_model'
  | 'reduce_context_length'
  | 'switch_to_push_to_talk'
  | 'disable_tts'
  | 'enable_transcript_summarization';

/** A user-visible performance warning with an actionable suggestion. */
export interface PerformanceWarning {
  /** Machine-readable code, stable across releases. */
  code: PerformanceSuggestionCode;
  /** Short headline for the warning (shown in bold). */
  title: string;
  /** Detailed explanation with a specific suggested fix. */
  detail: string;
}
