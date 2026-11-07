// SPDX-License-Identifier: Apache-2.0
//
// How long an NPC turn takes on *this* machine, learned from the turns this
// machine has already finished (issue #488).
//
// Nothing here models the model. The same scenario answers in two seconds on a
// GPU laptop and in three minutes on a CPU-only desktop (docs/performance.md),
// and the benchmark the installer runs measures generation speed only — it says
// nothing about the prompt eval that dominates a slow turn. So the app simply
// remembers how long recent turns took and reports the middle one back.
//
// Timings are kept per model, because the first thing a player does about a slow
// model is swap it for a smaller one, and samples from the old model would then
// overstate every estimate until they aged out. Only the bucket for the model in
// use is kept: switching models starts the estimate over rather than carrying a
// cache per model, a cheap trade for a number that is rebuilt within two turns.

const STORAGE_KEY = 'convsim.turnTiming'

/** Identifies the samples when the runtime has not named its model (health not
 *  back yet, or a runtime that reports none). Estimates still accumulate — they
 *  are just not protected against a model swap — but a turn filed under this key
 *  will not displace samples that do have a model's name on them. */
export const UNKNOWN_MODEL_KEY = 'unknown'

/** Enough samples for a median that one odd turn cannot move, few enough that
 *  the estimate still follows a real change in conditions. */
export const MAX_TURN_SAMPLES = 8

// A turn faster than this is a stubbed or cached reply, not model work; one
// longer than this outlived the screen's own abandon ceiling, so it measures a
// wedged request rather than a turn. Neither tells the player anything true.
const MIN_SAMPLE_MS = 100
const MAX_SAMPLE_MS = 600_000

interface StoredTimings {
  /** The model the samples were measured on. */
  model: string
  /** Round-trip milliseconds, oldest first. */
  samples: number[]
}

function readStore(): StoredTimings | null {
  if (typeof localStorage === 'undefined') return null
  let raw: string | null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    const { model, samples } = parsed as { model?: unknown; samples?: unknown }
    if (typeof model !== 'string' || !Array.isArray(samples)) return null
    // Drop anything that is not a usable number: the store is on the player's
    // disk, so a hand-edited or half-written value must not reach the estimate.
    const clean = (samples as unknown[]).filter(
      (s): s is number => typeof s === 'number' && Number.isFinite(s) && isUsableSample(s),
    )
    return { model, samples: clean.slice(-MAX_TURN_SAMPLES) }
  } catch {
    return null
  }
}

function writeStore(store: StoredTimings): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    // A full or blocked disk quota costs the player an estimate, nothing more.
  }
}

function isUsableSample(ms: number): boolean {
  return ms >= MIN_SAMPLE_MS && ms <= MAX_SAMPLE_MS
}

/** Recent turn durations measured for `model`, oldest first; empty when the
 *  stored samples belong to a different model. */
export function readTurnSamples(model: string): number[] {
  const store = readStore()
  if (!store || store.model !== model) return []
  return store.samples
}

/**
 * Remember how long a turn took, and hand back the samples to estimate from.
 *
 * Samples measured on another model are discarded rather than averaged in. A
 * duration outside the usable range is ignored, but the existing samples are
 * still returned so one odd turn never costs the player their estimate — and
 * neither does a turn that finished before the runtime named its model.
 */
export function recordTurnSample(model: string, ms: number): number[] {
  const store = readStore()
  const existing = store && store.model === model ? store.samples : []
  if (!Number.isFinite(ms) || !isUsableSample(ms)) return existing
  // A turn finished while the model is still unnamed cannot be filed against
  // one, and there is only the single bucket to file it in: writing it would
  // throw away everything a named model had accumulated, and the estimate would
  // drop back to "nothing measured yet" the moment /health answered with the
  // real name. Losing the one sample is much the cheaper loss.
  if (model === UNKNOWN_MODEL_KEY && store !== null && store.model !== UNKNOWN_MODEL_KEY) {
    return existing
  }
  const samples = [...existing, Math.round(ms)].slice(-MAX_TURN_SAMPLES)
  writeStore({ model, samples })
  return samples
}

/**
 * The turn length to expect from a set of samples, or null with nothing to go on.
 *
 * The median, not the mean: one turn that stalled on a cold cache or a
 * backgrounded machine would drag a mean far past anything the player is likely
 * to wait again.
 */
export function estimateTurnMs(samples: number[]): number | null {
  if (samples.length === 0) return null
  const sorted = [...samples].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
  return Math.round(median)
}

/** Forget every sample. Settings' "Clear all local data" calls this: the
 *  samples sit in this browser rather than in the data folder the API clears,
 *  and a record of how slow this machine is counts as cached data. */
export function clearTurnSamples(): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing to do: a store we cannot clear is a store we cannot read either.
  }
}

// ---------------------------------------------------------------------------
// When the reply will *start* (issue #539).
//
// Once words stream (#538) the wait the player feels ends when the first
// sentence lands, not when the turn ends. The panel therefore estimates the
// start of the reply, from this machine's measured speeds (#519's rolling
// medians) and how much of the prompt the engine still has to read (the core's
// turn.progress reports). Nothing here models the model: both inputs are
// measurements, and with neither there is no estimate.
// ---------------------------------------------------------------------------

/** Below this expected wait no estimate is shown: a number for a 2 s pause is noise. */
export const REPLY_START_THRESHOLD_MS = 4_000

/** How long the first sentence usually is, in tokens, when the engine has not
 *  started writing yet. A short sentence of a spoken line; deliberately modest
 *  so the estimate errs early rather than late. */
export const FIRST_SENTENCE_TOKENS = 24

export interface ReplyStartInputs {
  /** Prompt tokens the engine has still to read, from the latest progress report; null before the first. */
  unreadPromptTokens: number | null
  /** How long ago that progress report arrived, in milliseconds. */
  sinceReportMs: number
  /** How long the player has been waiting on this turn, in milliseconds. */
  waitedMs: number
  /** This machine's median reading speed, tokens per second, or null. */
  readingTps: number | null
  /** This machine's median writing speed, tokens per second, or null. */
  writingTps: number | null
  /** This machine's median time to first words, from recorded turns, or null. */
  measuredFirstWordsMs: number | null
}

/**
 * The expected milliseconds from now until the reply starts, or null with
 * nothing to go on.
 *
 * With a progress report and both speeds: the unread prompt at the reading
 * speed, plus one short sentence at the writing speed, less the time since
 * that report arrived. Otherwise the measured time to first words on this
 * machine, when any turn has been recorded, less the time already waited:
 * that median counts from the moment the turn went out, so quoting it
 * unchanged would promise the whole wait again on every tick of the clock.
 * Never below zero, and never a figure from the docs or a model size.
 */
export function estimateReplyStartMs(inputs: ReplyStartInputs): number | null {
  const { unreadPromptTokens, sinceReportMs, waitedMs, readingTps, writingTps, measuredFirstWordsMs } = inputs
  if (
    unreadPromptTokens !== null &&
    Number.isFinite(unreadPromptTokens) &&
    readingTps !== null &&
    readingTps > 0 &&
    writingTps !== null &&
    writingTps > 0
  ) {
    const readMs = (Math.max(0, unreadPromptTokens) / readingTps) * 1000
    const writeMs = (FIRST_SENTENCE_TOKENS / writingTps) * 1000
    return remaining(readMs + writeMs, sinceReportMs)
  }
  if (measuredFirstWordsMs !== null && Number.isFinite(measuredFirstWordsMs) && measuredFirstWordsMs > 0) {
    return remaining(measuredFirstWordsMs, waitedMs)
  }
  return null
}

function remaining(totalMs: number, passedMs: number): number {
  const passed = Number.isFinite(passedMs) ? Math.max(0, passedMs) : 0
  return Math.max(0, Math.round(totalMs - passed))
}

/** The range quoted to the player around a point estimate: a median is not a promise. */
export function replyStartRange(ms: number): { lowMs: number; highMs: number } {
  const low = roundToSecond(ms * 0.8)
  const high = Math.max(low + 1_000, roundToSecond(ms * 1.25))
  return { lowMs: low, highMs: high }
}

function roundToSecond(ms: number): number {
  return Math.max(1_000, Math.round(ms / 1_000) * 1_000)
}
