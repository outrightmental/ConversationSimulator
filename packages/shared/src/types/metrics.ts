// SPDX-License-Identifier: Apache-2.0

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
