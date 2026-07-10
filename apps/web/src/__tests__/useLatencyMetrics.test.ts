// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLatencyMetrics } from '../hooks/useLatencyMetrics'

describe('useLatencyMetrics', () => {
  let nowValue = 0

  beforeEach(() => {
    nowValue = 0
    vi.spyOn(performance, 'now').mockImplementation(() => nowValue)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('mark and recordInterval', () => {
    it('records a latency measurement between two marks', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 100
        result.current.mark('start_event')
        nowValue = 600
        result.current.recordInterval('session_start_ms', 'start_event')
      })

      expect(result.current.snapshot.session_start_ms).toBe(500)
    })

    it('records latency to current time when endEvent is omitted', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 3000
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      expect(result.current.snapshot.first_token_ms).toBe(3000)
    })

    it('does nothing when startEvent has not been marked', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 5000
        result.current.recordInterval('first_token_ms', 'nonexistent_event')
      })

      expect(result.current.snapshot.first_token_ms).toBeUndefined()
    })

    it('accumulates multiple different measurements', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('session_start')
        nowValue = 2000
        result.current.recordInterval('session_start_ms', 'session_start')

        nowValue = 3000
        result.current.mark('turn_submit')
        nowValue = 3500
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      expect(result.current.snapshot.session_start_ms).toBe(2000)
      expect(result.current.snapshot.first_token_ms).toBe(500)
    })

    it('rounds fractional milliseconds', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('start')
        nowValue = 1000.7
        result.current.recordInterval('full_response_ms', 'start')
      })

      expect(result.current.snapshot.full_response_ms).toBe(1001)
    })
  })

  describe('recordValue', () => {
    it('records a directly-measured latency value (e.g. STT round-trip)', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('stt_final_ms', 1234)
      })

      expect(result.current.snapshot.stt_final_ms).toBe(1234)
    })

    it('rounds fractional values', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('tts_first_sentence_ms', 842.6)
      })

      expect(result.current.snapshot.tts_first_sentence_ms).toBe(843)
    })

    it('overwrites a prior value for the same field', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('stt_final_ms', 1000)
        result.current.recordValue('stt_final_ms', 2000)
      })

      expect(result.current.snapshot.stt_final_ms).toBe(2000)
    })
  })

  describe('reset', () => {
    it('clears the snapshot', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 1000
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      expect(result.current.snapshot.first_token_ms).toBe(1000)

      act(() => {
        result.current.reset()
      })

      expect(result.current.snapshot.first_token_ms).toBeUndefined()
    })

    it('allows marks to be re-recorded after reset', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 5000
        result.current.recordInterval('first_token_ms', 'turn_submit')
        result.current.reset()
        nowValue = 6000
        result.current.mark('turn_submit')
        nowValue = 6200
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      expect(result.current.snapshot.first_token_ms).toBe(200)
    })
  })

  describe('performance warnings', () => {
    it('returns no warnings when snapshot is empty', () => {
      const { result } = renderHook(() => useLatencyMetrics())
      expect(result.current.warnings).toHaveLength(0)
    })

    it('returns no warnings when latencies are below thresholds', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('session_start')
        nowValue = 1000
        result.current.recordInterval('session_start_ms', 'session_start')

        result.current.mark('turn_submit')
        nowValue = 1500
        result.current.recordInterval('first_token_ms', 'turn_submit')

        result.current.mark('turn_submit')
        nowValue = 6000
        result.current.recordInterval('full_response_ms', 'turn_submit')
      })

      expect(result.current.warnings).toHaveLength(0)
    })

    it('warns use_smaller_model when session_start_ms exceeds 10000ms', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('session_start')
        nowValue = 11000
        result.current.recordInterval('session_start_ms', 'session_start')
      })

      const w = result.current.warnings.find((w) => w.code === 'use_smaller_model')
      expect(w).toBeDefined()
      expect(w?.title).toMatch(/session startup/i)
    })

    it('warns use_smaller_model when first_token_ms exceeds 2500ms', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 2501
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      const w = result.current.warnings.find((w) => w.code === 'use_smaller_model')
      expect(w).toBeDefined()
      expect(w?.title).toMatch(/npc response/i)
    })

    it('warns reduce_context_length when full_response_ms exceeds 10000ms', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 10001
        result.current.recordInterval('full_response_ms', 'turn_submit')
      })

      const w = result.current.warnings.find((w) => w.code === 'reduce_context_length')
      expect(w).toBeDefined()
      expect(w?.title).toMatch(/very slow/i)
    })

    it('includes elapsed time in the warning detail', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 5000
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      const w = result.current.warnings[0]
      expect(w?.detail).toContain('5.0s')
    })

    it('does not warn when first_token_ms is exactly at threshold (2500ms)', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        nowValue = 0
        result.current.mark('turn_submit')
        nowValue = 2500
        result.current.recordInterval('first_token_ms', 'turn_submit')
      })

      expect(result.current.warnings).toHaveLength(0)
    })

    it('warns disable_tts when tts_first_sentence_ms exceeds 1500ms', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('tts_first_sentence_ms', 1501)
      })

      const w = result.current.warnings.find((w) => w.code === 'disable_tts')
      expect(w).toBeDefined()
      expect(w?.title).toMatch(/tts audio/i)
    })

    it('does not warn when tts_first_sentence_ms is exactly at threshold (1500ms)', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('tts_first_sentence_ms', 1500)
      })

      expect(result.current.warnings).toHaveLength(0)
    })

    it('warns switch_to_push_to_talk when stt_final_ms exceeds 2000ms', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('stt_final_ms', 2001)
      })

      const w = result.current.warnings.find((w) => w.code === 'switch_to_push_to_talk')
      expect(w).toBeDefined()
      expect(w?.title).toMatch(/speech recognition/i)
    })

    it('does not warn when stt_final_ms is exactly at threshold (2000ms)', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('stt_final_ms', 2000)
      })

      expect(result.current.warnings).toHaveLength(0)
    })

    it('includes elapsed time in tts warning detail', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('tts_first_sentence_ms', 2000)
      })

      const w = result.current.warnings.find((w) => w.code === 'disable_tts')
      expect(w?.detail).toContain('2.0s')
    })

    it('includes elapsed time in stt warning detail', () => {
      const { result } = renderHook(() => useLatencyMetrics())

      act(() => {
        result.current.recordValue('stt_final_ms', 3500)
      })

      const w = result.current.warnings.find((w) => w.code === 'switch_to_push_to_talk')
      expect(w?.detail).toContain('3.5s')
    })
  })
})
