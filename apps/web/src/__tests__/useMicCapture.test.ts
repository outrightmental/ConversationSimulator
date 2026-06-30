// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useMicCapture, MAX_RECORDING_SECONDS } from '../hooks/useMicCapture'

// --- mock MediaStream ---

function makeMockStream(): MediaStream {
  return {
    getTracks: () => [{ stop: vi.fn() }],
  } as unknown as MediaStream
}

// --- mock MediaRecorder ---

class MockMediaRecorder {
  state: 'inactive' | 'recording' | 'paused' = 'inactive'
  mimeType: string
  stream: MediaStream
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null

  constructor(stream: MediaStream, options?: { mimeType?: string }) {
    this.stream = stream
    this.mimeType = options?.mimeType ?? 'audio/webm'
  }

  start(_timeslice?: number): void {
    this.state = 'recording'
  }

  stop(): void {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['chunk'], { type: this.mimeType }) })
    this.onstop?.()
  }

  static isTypeSupported(_type: string): boolean {
    return true
  }
}

// --- setup ---

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('MediaRecorder', MockMediaRecorder)

  const mockStream = makeMockStream()
  vi.stubGlobal('navigator', {
    ...navigator,
    mediaDevices: {
      getUserMedia: vi.fn().mockResolvedValue(mockStream),
    },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

// --- tests ---

describe('useMicCapture — initial state', () => {
  it('reports idle when browser is supported', () => {
    const { result } = renderHook(() => useMicCapture())
    expect(result.current.permission).toBe('idle')
    expect(result.current.isRecording).toBe(false)
    expect(result.current.recordingSeconds).toBe(0)
    expect(result.current.error).toBeNull()
  })

  it('reports unsupported when MediaRecorder is unavailable', () => {
    vi.stubGlobal('MediaRecorder', undefined)
    const { result } = renderHook(() => useMicCapture())
    expect(result.current.permission).toBe('unsupported')
  })
})

describe('useMicCapture — permission request', () => {
  it('transitions to granted when getUserMedia succeeds', async () => {
    const { result } = renderHook(() => useMicCapture())

    await act(async () => {
      await result.current.requestPermission()
    })

    expect(result.current.permission).toBe('granted')
    expect(result.current.error).toBeNull()
  })

  it('transitions to denied on NotAllowedError', async () => {
    const denied = Object.assign(new Error('Denied'), { name: 'NotAllowedError' })
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockRejectedValue(denied),
      },
    })

    const { result } = renderHook(() => useMicCapture())

    await act(async () => {
      await result.current.requestPermission()
    })

    expect(result.current.permission).toBe('denied')
    expect(result.current.error).toBe('Microphone access was denied.')
  })

  it('stays idle on non-permission errors', async () => {
    const err = Object.assign(new Error('Device not found'), { name: 'NotFoundError' })
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockRejectedValue(err),
      },
    })

    const { result } = renderHook(() => useMicCapture())

    await act(async () => {
      await result.current.requestPermission()
    })

    expect(result.current.permission).toBe('idle')
    expect(result.current.error).toBe('Could not access microphone.')
  })
})

describe('useMicCapture — recording', () => {
  it('toggles isRecording when startRecording and stopRecording are called', async () => {
    const { result } = renderHook(() => useMicCapture())

    await act(async () => {
      await result.current.requestPermission()
    })

    act(() => {
      result.current.startRecording()
    })
    expect(result.current.isRecording).toBe(true)

    act(() => {
      result.current.stopRecording()
    })
    expect(result.current.isRecording).toBe(false)
  })

  it('increments recordingSeconds while recording', async () => {
    const { result } = renderHook(() => useMicCapture())

    await act(async () => {
      await result.current.requestPermission()
    })

    act(() => {
      result.current.startRecording()
    })

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.recordingSeconds).toBe(3)

    act(() => {
      result.current.stopRecording()
    })
    expect(result.current.recordingSeconds).toBe(0)
  })

  it('does not start recording before permission is granted', () => {
    const { result } = renderHook(() => useMicCapture())

    act(() => {
      result.current.startRecording()
    })

    expect(result.current.isRecording).toBe(false)
  })

  it('calls onAudioReady with a Blob when recording stops', async () => {
    const onAudioReady = vi.fn()
    const { result } = renderHook(() => useMicCapture(onAudioReady))

    await act(async () => {
      await result.current.requestPermission()
    })

    act(() => {
      result.current.startRecording()
    })

    act(() => {
      result.current.stopRecording()
    })

    expect(onAudioReady).toHaveBeenCalledOnce()
    expect(onAudioReady.mock.calls[0][0]).toBeInstanceOf(Blob)
  })

  it('auto-stops after MAX_RECORDING_SECONDS', async () => {
    const { result } = renderHook(() => useMicCapture())

    await act(async () => {
      await result.current.requestPermission()
    })

    act(() => {
      result.current.startRecording()
    })
    expect(result.current.isRecording).toBe(true)

    act(() => {
      vi.advanceTimersByTime(MAX_RECORDING_SECONDS * 1000)
    })

    expect(result.current.isRecording).toBe(false)
  })
})
