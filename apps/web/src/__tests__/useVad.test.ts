// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../api/client', () => ({
  apiClient: {
    vadHealth: vi.fn().mockResolvedValue({ status: 'ready', worker_id: 'silero_vad', worker_name: 'Silero VAD', checked_at: '' }),
    vadCalibrate: vi.fn().mockResolvedValue({ recommended_threshold: 0.08, noise_floor: 0.02, worker_id: 'silero_vad', status: 'ok' }),
  },
}))

import { useVad } from '../hooks/useVad'
import { apiClient } from '../api/client'

function makeStream(): MediaStream {
  return {} as MediaStream
}

// AnalyserNode mock
function makeAnalyser(rmsValue: number): AnalyserNode {
  const frameLen = 512
  return {
    fftSize: frameLen,
    frequencyBinCount: frameLen / 2,
    smoothingTimeConstant: 0,
    connect: vi.fn(),
    getFloatTimeDomainData: (buf: Float32Array) => {
      // Fill buffer so RMS equals rmsValue
      const v = rmsValue
      buf.fill(v)
    },
  } as unknown as AnalyserNode
}

// Helpers to stub AudioContext
function stubAudioContext(rmsValue: number) {
  const analyser = makeAnalyser(rmsValue)
  const mockCtx = {
    createAnalyser: () => analyser,
    createMediaStreamSource: () => ({ connect: vi.fn() }),
    close: vi.fn().mockResolvedValue(undefined),
  }
  vi.stubGlobal('AudioContext', vi.fn(() => mockCtx))
  return { analyser, mockCtx }
}

// Stub AudioContext with a mutable RMS plus a manual requestAnimationFrame driver
// so tests can step the silence-detection loop one frame at a time.
function stubMutableAudio() {
  const audioState = { rms: 0 }
  const analyser = {
    fftSize: 512,
    frequencyBinCount: 256,
    smoothingTimeConstant: 0,
    connect: vi.fn(),
    getFloatTimeDomainData: (buf: Float32Array) => buf.fill(audioState.rms),
  } as unknown as AnalyserNode
  const mockCtx = {
    createAnalyser: () => analyser,
    createMediaStreamSource: () => ({ connect: vi.fn() }),
    close: vi.fn().mockResolvedValue(undefined),
  }
  vi.stubGlobal('AudioContext', vi.fn(() => mockCtx))

  const pending: FrameRequestCallback[] = []
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => pending.push(cb))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  const flushFrame = () => pending.splice(0).forEach((cb) => cb(0))

  return { audioState, flushFrame }
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// Settings persistence
// ---------------------------------------------------------------------------

describe('useVad — settings', () => {
  it('defaults to ptt mode', () => {
    const { result } = renderHook(() => useVad())
    expect(result.current.settings.mode).toBe('ptt')
  })

  it('setMode persists hands-free to localStorage', () => {
    const { result } = renderHook(() => useVad())
    act(() => result.current.setMode('hands-free'))
    expect(result.current.settings.mode).toBe('hands-free')
    const stored = JSON.parse(localStorage.getItem('convsim_vad_settings') ?? '{}')
    expect(stored.mode).toBe('hands-free')
  })

  it('setMode back to ptt persists', () => {
    const { result } = renderHook(() => useVad())
    act(() => result.current.setMode('hands-free'))
    act(() => result.current.setMode('ptt'))
    expect(result.current.settings.mode).toBe('ptt')
  })

  it('setThreshold updates settings and persists', () => {
    const { result } = renderHook(() => useVad())
    act(() => result.current.setThreshold(0.12))
    expect(result.current.settings.threshold).toBe(0.12)
    const stored = JSON.parse(localStorage.getItem('convsim_vad_settings') ?? '{}')
    expect(stored.threshold).toBe(0.12)
  })

  it('setSilenceDurationMs updates settings and persists', () => {
    const { result } = renderHook(() => useVad())
    act(() => result.current.setSilenceDurationMs(2000))
    expect(result.current.settings.silenceDurationMs).toBe(2000)
    const stored = JSON.parse(localStorage.getItem('convsim_vad_settings') ?? '{}')
    expect(stored.silenceDurationMs).toBe(2000)
  })

  it('loads persisted settings on mount', () => {
    localStorage.setItem(
      'convsim_vad_settings',
      JSON.stringify({ mode: 'hands-free', threshold: 0.07, silenceDurationMs: 2000, calibratedAt: '2025-01-01T00:00:00Z' }),
    )
    const { result } = renderHook(() => useVad())
    expect(result.current.settings.mode).toBe('hands-free')
    expect(result.current.settings.threshold).toBe(0.07)
    expect(result.current.settings.silenceDurationMs).toBe(2000)
    expect(result.current.settings.calibratedAt).toBe('2025-01-01T00:00:00Z')
  })
})

// ---------------------------------------------------------------------------
// Backend availability check
// ---------------------------------------------------------------------------

describe('useVad — backend availability', () => {
  it('calls vadHealth on mount and sets backendAvailable=true on success', async () => {
    const { result } = renderHook(() => useVad())
    expect(result.current.backendAvailable).toBeNull()
    await act(async () => { await vi.runAllTimersAsync() })
    expect(vi.mocked(apiClient.vadHealth)).toHaveBeenCalledOnce()
    expect(result.current.backendAvailable).toBe(true)
  })

  it('sets backendAvailable=false when vadHealth rejects', async () => {
    vi.mocked(apiClient.vadHealth).mockRejectedValueOnce(new Error('network'))
    const { result } = renderHook(() => useVad())
    await act(async () => { await vi.runAllTimersAsync() })
    expect(result.current.backendAvailable).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// calibrate()
// ---------------------------------------------------------------------------

describe('useVad — calibrate', () => {
  it('calls vadCalibrate with the blob and updates threshold', async () => {
    const { result } = renderHook(() => useVad())
    const blob = new Blob(['audio'], { type: 'audio/webm' })

    await act(async () => { await result.current.calibrate(blob) })

    expect(vi.mocked(apiClient.vadCalibrate)).toHaveBeenCalledWith(blob)
    expect(result.current.settings.threshold).toBe(0.08)
  })

  it('sets calibratedAt after successful calibration', async () => {
    const { result } = renderHook(() => useVad())
    expect(result.current.settings.calibratedAt).toBeNull()
    await act(async () => { await result.current.calibrate(new Blob()) })
    expect(result.current.settings.calibratedAt).not.toBeNull()
  })

  it('sets isCalibrating=true while in progress', async () => {
    let resolve: () => void
    vi.mocked(apiClient.vadCalibrate).mockReturnValueOnce(
      new Promise((r) => { resolve = () => r({ recommended_threshold: 0.05, noise_floor: 0.01, worker_id: 'silero_vad', status: 'ok' }) })
    )
    const { result } = renderHook(() => useVad())
    act(() => { void result.current.calibrate(new Blob()) })
    expect(result.current.isCalibrating).toBe(true)
    await act(async () => { resolve!() })
    expect(result.current.isCalibrating).toBe(false)
  })

  it('sets backendAvailable=false when vadCalibrate throws', async () => {
    vi.mocked(apiClient.vadCalibrate).mockRejectedValueOnce(new Error('fail'))
    const { result } = renderHook(() => useVad())
    await act(async () => {
      await expect(result.current.calibrate(new Blob())).rejects.toThrow('fail')
    })
    expect(result.current.backendAvailable).toBe(false)
  })

  it('propagates the error to the caller when vadCalibrate throws', async () => {
    vi.mocked(apiClient.vadCalibrate).mockRejectedValueOnce(new Error('network'))
    const { result } = renderHook(() => useVad())
    await act(async () => {
      await expect(result.current.calibrate(new Blob())).rejects.toThrow('network')
    })
  })
})

// ---------------------------------------------------------------------------
// Silence detection visual states
// ---------------------------------------------------------------------------

describe('useVad — startSilenceDetection VAD states', () => {
  it('starts in idle state', () => {
    const { result } = renderHook(() => useVad())
    expect(result.current.vadState).toBe('idle')
  })

  it('transitions to listening when startSilenceDetection is called', () => {
    stubAudioContext(0.01) // quiet audio
    const { result } = renderHook(() => useVad())
    act(() => result.current.setThreshold(0.05))

    act(() => result.current.startSilenceDetection(makeStream(), vi.fn()))

    // requestAnimationFrame is not fired in fake timers without explicit advance
    expect(result.current.vadState).toBe('listening')
  })

  it('stopSilenceDetection resets to idle', () => {
    stubAudioContext(0.01)
    const { result } = renderHook(() => useVad())
    act(() => result.current.startSilenceDetection(makeStream(), vi.fn()))
    act(() => result.current.stopSilenceDetection())
    expect(result.current.vadState).toBe('idle')
  })

  it('stopSilenceDetection is safe to call without prior start', () => {
    const { result } = renderHook(() => useVad())
    expect(() => act(() => result.current.stopSilenceDetection())).not.toThrow()
    expect(result.current.vadState).toBe('idle')
  })
})

// ---------------------------------------------------------------------------
// Auto-stop only arms after speech (regression: an initial pause before the
// user speaks must not trigger a premature auto-stop).
// ---------------------------------------------------------------------------

describe('useVad — auto-stop arms only after speech', () => {
  it('does not fire onSilence while quiet before any speech is detected', () => {
    const { audioState, flushFrame } = stubMutableAudio()
    const { result } = renderHook(() => useVad())
    act(() => result.current.setThreshold(0.05))
    const onSilence = vi.fn()

    audioState.rms = 0.001 // below threshold from the very start
    act(() => result.current.startSilenceDetection(makeStream(), onSilence))

    // Step several frames while silent, then advance well past silenceDurationMs.
    act(() => { for (let i = 0; i < 5; i++) flushFrame() })
    act(() => { vi.advanceTimersByTime(5000) })

    expect(onSilence).not.toHaveBeenCalled()
    expect(result.current.vadState).toBe('listening')
  })

  it('fires onSilence after speech is followed by sustained silence', () => {
    const { audioState, flushFrame } = stubMutableAudio()
    const { result } = renderHook(() => useVad())
    act(() => {
      result.current.setThreshold(0.05)
      result.current.setSilenceDurationMs(1000)
    })
    const onSilence = vi.fn()
    act(() => result.current.startSilenceDetection(makeStream(), onSilence))

    // Speech frame.
    audioState.rms = 0.2
    act(() => flushFrame())
    expect(result.current.vadState).toBe('speech')

    // Silence begins — timer arms but has not yet elapsed.
    audioState.rms = 0.001
    act(() => flushFrame())
    expect(result.current.vadState).toBe('silence')
    expect(onSilence).not.toHaveBeenCalled()

    // Silence persists past the configured duration → auto-stop.
    act(() => { vi.advanceTimersByTime(1000) })
    expect(onSilence).toHaveBeenCalledOnce()
    expect(result.current.vadState).toBe('stopping')
  })
})

// ---------------------------------------------------------------------------
// Threshold configuration
// ---------------------------------------------------------------------------

describe('useVad — threshold range', () => {
  it('default threshold is between 0 and 1', () => {
    const { result } = renderHook(() => useVad())
    expect(result.current.settings.threshold).toBeGreaterThan(0)
    expect(result.current.settings.threshold).toBeLessThan(1)
  })

  it('setThreshold to 0 is accepted', () => {
    const { result } = renderHook(() => useVad())
    act(() => result.current.setThreshold(0))
    expect(result.current.settings.threshold).toBe(0)
  })

  it('setThreshold to 1 is accepted', () => {
    const { result } = renderHook(() => useVad())
    act(() => result.current.setThreshold(1))
    expect(result.current.settings.threshold).toBe(1)
  })
})
