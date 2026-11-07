// SPDX-License-Identifier: Apache-2.0

/**
 * Latency budgets that define "fast enough" on the mid-spec reference machine.
 * All values in milliseconds. These are targets, not measurements; #522 moves
 * them into one shared definition.
 *
 * Reference machine: Apple M2 / NVIDIA RTX 3060 equivalent — the mid-spec
 * "Fast" tier documented in docs/performance.md. Nightly CI smoke tests fail
 * when any measured value exceeds the budget by more than 20 %.
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

// ---------------------------------------------------------------------------
// What each NPC turn actually cost (issue #519).
// Mirrors `TurnTiming` in services/convsim-core/convsim_core/services/turn_timing.py;
// keep the two in step. Every millisecond is measured, never estimated; a field
// the engine or the pipeline could not supply is null.
// ---------------------------------------------------------------------------

/** The six stages of an NPC turn, in order. Defined once here and in the core. */
export const TURN_STAGES = ['waiting', 'reading', 'writing', 'finishing', 'checking', 'voice'] as const
export type TurnStage = (typeof TURN_STAGES)[number]

export type TurnFinishReason = 'stop' | 'length' | 'cancelled'

export interface TurnExtraCall {
  kind: 'repair' | 'safety_retry'
  ms: number
  tokens: number | null
}

export interface TurnTimingContext {
  /** The model as the engine named it. */
  model_id: string
  /** The registry id of the active model when the app knew one. */
  registry_model_id: string | null
  runtime_id: string
  engine_variant: string | null
  n_ctx: number | null
  n_batch: number | null
  threads: number | null
  /** True when fewer than half the prompt tokens came from the engine's cache; null when the engine did not report cache use. */
  cold: boolean | null
}

export interface TurnTiming {
  total_ms: number
  waiting_ms: number | null
  reading_ms: number | null
  /** Request received → first generated token. */
  first_token_ms: number | null
  /** Request received → first reply text released to the player. Null until words stream (#538). */
  first_words_ms: number | null
  /** Request received → spoken line complete. Null until words stream (#538). */
  reply_done_ms: number | null
  writing_ms: number | null
  /** Compose + parse + persist. */
  other_ms: number
  extra_calls: TurnExtraCall[]
  salvaged: boolean
  fallback: boolean
  stopped: boolean
  finish_reason: TurnFinishReason | null
  voice: { synth_ms: number | null; first_audio_ms: number | null } | null
  tokens: {
    prompt: number | null
    cached: number | null
    evaluated: number | null
    output: number | null
    spoken: number | null
  }
  rates: { reading_tps: number | null; writing_tps: number | null }
  context: TurnTimingContext
}

/** `GET /api/performance/rolling`: this machine's recent medians for one model and engine configuration. */
export interface RollingSpeeds {
  runtime_id: string | null
  model_id: string | null
  /** Recorded turns the medians were taken over; 0 means every figure is null. */
  samples: number
  reading_tps: number | null
  writing_tps: number | null
  first_token_ms: number | null
  first_words_ms: number | null
  total_ms: number | null
}
