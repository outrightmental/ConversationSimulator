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
    expect(readTurnSamples(UNKNOWN_MODEL_KEY)).toEqual([7_000])
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
