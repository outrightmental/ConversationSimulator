// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach } from 'vitest'
import {
  clearTurnSamples,
  estimateTurnMs,
  MAX_TURN_SAMPLES,
  readTurnSamples,
  recordTurnSample,
  UNKNOWN_MODEL_KEY,
} from '../lib/turnEstimate'

const MODEL = 'Qwen3 8B'
const STORAGE_KEY = 'convsim.turnTiming'

beforeEach(() => {
  clearTurnSamples()
})

describe('readTurnSamples', () => {
  it('has nothing to offer before a turn has been timed', () => {
    expect(readTurnSamples(MODEL)).toEqual([])
  })

  it('ignores samples measured on a different model', () => {
    // Swapping in a smaller model is the app's own advice for slow turns, so the
    // old model's minutes must not be quoted back on the new one.
    recordTurnSample(MODEL, 90_000)
    expect(readTurnSamples('Llama 3.2 3B')).toEqual([])
  })

  it('survives a hand-edited or half-written store', () => {
    localStorage.setItem(STORAGE_KEY, 'not json at all')
    expect(readTurnSamples(MODEL)).toEqual([])

    localStorage.setItem(STORAGE_KEY, JSON.stringify({ model: MODEL, samples: 'nope' }))
    expect(readTurnSamples(MODEL)).toEqual([])

    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ model: MODEL, samples: [12_000, null, 'slow', 18_000, Infinity] }),
    )
    expect(readTurnSamples(MODEL)).toEqual([12_000, 18_000])
  })
})

describe('recordTurnSample', () => {
  it('remembers a turn and hands back the window to estimate from', () => {
    expect(recordTurnSample(MODEL, 12_000)).toEqual([12_000])
    expect(recordTurnSample(MODEL, 18_000)).toEqual([12_000, 18_000])
    expect(readTurnSamples(MODEL)).toEqual([12_000, 18_000])
  })

  it('keeps only the most recent samples, so conditions can change', () => {
    for (let i = 1; i <= MAX_TURN_SAMPLES + 3; i++) recordTurnSample(MODEL, i * 1_000)
    const samples = readTurnSamples(MODEL)
    expect(samples).toHaveLength(MAX_TURN_SAMPLES)
    expect(samples[0]).toBe(4_000)
    expect(samples[samples.length - 1]).toBe((MAX_TURN_SAMPLES + 3) * 1_000)
  })

  it('drops a duration that measures something other than model work', () => {
    recordTurnSample(MODEL, 12_000)
    // A stubbed or cached reply, and a wait that outlived the screen's own
    // abandon ceiling: neither says anything true about the next turn.
    expect(recordTurnSample(MODEL, 40)).toEqual([12_000])
    expect(recordTurnSample(MODEL, 900_000)).toEqual([12_000])
    expect(recordTurnSample(MODEL, Number.NaN)).toEqual([12_000])
    expect(readTurnSamples(MODEL)).toEqual([12_000])
  })

  it('starts the window over when the model changes', () => {
    recordTurnSample(MODEL, 90_000)
    expect(recordTurnSample('Llama 3.2 3B', 9_000)).toEqual([9_000])
    expect(readTurnSamples(MODEL)).toEqual([])
  })

  it('still accumulates when the runtime has not named its model', () => {
    expect(recordTurnSample(UNKNOWN_MODEL_KEY, 7_000)).toEqual([7_000])
    expect(recordTurnSample(UNKNOWN_MODEL_KEY, 9_000)).toEqual([7_000, 9_000])
    expect(readTurnSamples(UNKNOWN_MODEL_KEY)).toEqual([7_000, 9_000])
  })

  it('will not spend a named model\'s samples on a turn it cannot name', () => {
    // /health answers after the screen mounts, so a turn can finish while the
    // model is still unnamed. There is one bucket, so filing that turn would
    // empty the named model's — and the estimate the player had built up over a
    // session would read as "nothing measured yet" the moment the name arrived.
    recordTurnSample(MODEL, 12_000)
    recordTurnSample(MODEL, 18_000)
    expect(recordTurnSample(UNKNOWN_MODEL_KEY, 9_000)).toEqual([])
    expect(readTurnSamples(MODEL)).toEqual([12_000, 18_000])
  })
})

describe('estimateTurnMs', () => {
  it('declines to guess with nothing measured', () => {
    expect(estimateTurnMs([])).toBeNull()
  })

  it('reports the single sample it has', () => {
    expect(estimateTurnMs([14_000])).toBe(14_000)
  })

  it('takes the median, so one stalled turn cannot carry the estimate', () => {
    // A mean of these is 32s; the player will not wait 32s again.
    expect(estimateTurnMs([10_000, 11_000, 12_000, 120_000])).toBe(11_500)
    expect(estimateTurnMs([10_000, 11_000, 120_000])).toBe(11_000)
  })

  it('does not care what order the samples arrived in', () => {
    expect(estimateTurnMs([30_000, 10_000, 20_000])).toBe(20_000)
  })
})

describe('clearTurnSamples', () => {
  it('forgets everything', () => {
    recordTurnSample(MODEL, 12_000)
    clearTurnSamples()
    expect(readTurnSamples(MODEL)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// When the reply will start (issue #539)
// ---------------------------------------------------------------------------
import {
  estimateReplyStartMs,
  FIRST_SENTENCE_TOKENS,
  REPLY_START_THRESHOLD_MS,
  replyStartRange,
} from '../lib/turnEstimate'

describe('estimateReplyStartMs', () => {
  // A report that has just arrived, on a turn that has just gone out.
  const now = { sinceReportMs: 0, waitedMs: 0 }
  const speeds = { ...now, readingTps: 87, writingTps: 6.5, measuredFirstWordsMs: null }

  it('is longer for a turn that must read 2,000 tokens than for one that reads 200', () => {
    const cold = estimateReplyStartMs({ ...speeds, unreadPromptTokens: 2000 })
    const warm = estimateReplyStartMs({ ...speeds, unreadPromptTokens: 200 })
    expect(cold).not.toBeNull()
    expect(warm).not.toBeNull()
    expect(cold!).toBeGreaterThan(warm!)
    // 2000 / 87 s of reading plus one short sentence at 6.5 tokens/s.
    expect(cold).toBe(Math.round((2000 / 87) * 1000 + (FIRST_SENTENCE_TOKENS / 6.5) * 1000))
  })

  it('returns none with no speeds and no measured first words', () => {
    expect(estimateReplyStartMs({ ...now, unreadPromptTokens: 2000, readingTps: null, writingTps: null, measuredFirstWordsMs: null })).toBeNull()
    expect(estimateReplyStartMs({ ...now, unreadPromptTokens: null, readingTps: 87, writingTps: 6.5, measuredFirstWordsMs: null })).toBeNull()
  })

  it('uses this machine\'s measured time to first words before the engine reports progress', () => {
    expect(estimateReplyStartMs({ ...now, unreadPromptTokens: null, readingTps: 87, writingTps: 6.5, measuredFirstWordsMs: 12_400 })).toBe(12_400)
  })

  it('prefers the formula once a progress report says how much is left to read', () => {
    expect(estimateReplyStartMs({ ...now, unreadPromptTokens: 0, readingTps: 87, writingTps: 6.5, measuredFirstWordsMs: 12_400 })).toBe(
      Math.round((FIRST_SENTENCE_TOKENS / 6.5) * 1000),
    )
  })

  it('counts the measured time to first words down with the wait, since it is a whole-wait figure', () => {
    // The median runs from the moment the turn went out, so ten seconds in
    // there are ten seconds fewer to go, and past the median there is no
    // honest figure left to quote.
    const fallback = { unreadPromptTokens: null, readingTps: null, writingTps: null, measuredFirstWordsMs: 27_000, sinceReportMs: 0 }
    expect(estimateReplyStartMs({ ...fallback, waitedMs: 0 })).toBe(27_000)
    expect(estimateReplyStartMs({ ...fallback, waitedMs: 10_000 })).toBe(17_000)
    expect(estimateReplyStartMs({ ...fallback, waitedMs: 40_000 })).toBe(0)
  })

  it('counts the formula down from the report it was built from, not from the start of the wait', () => {
    const read = { unreadPromptTokens: 870, readingTps: 87, writingTps: 6, measuredFirstWordsMs: null }
    // 10 s of reading and 4 s of writing, as of the report.
    expect(estimateReplyStartMs({ ...read, sinceReportMs: 0, waitedMs: 30_000 })).toBe(14_000)
    expect(estimateReplyStartMs({ ...read, sinceReportMs: 5_000, waitedMs: 35_000 })).toBe(9_000)
    expect(estimateReplyStartMs({ ...read, sinceReportMs: 20_000, waitedMs: 50_000 })).toBe(0)
  })

  it('quotes a range around the point estimate, never a single second', () => {
    expect(replyStartRange(6_500)).toEqual({ lowMs: 5_000, highMs: 8_000 })
    expect(replyStartRange(1_200)).toEqual({ lowMs: 1_000, highMs: 2_000 })
  })

  it('has a threshold under which no estimate is shown', () => {
    expect(REPLY_START_THRESHOLD_MS).toBe(4_000)
  })
})
