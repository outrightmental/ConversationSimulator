// SPDX-License-Identifier: Apache-2.0
//
// ACH_VAD_CALIBRATED is required for the ACH_CERTIFIED_EXPERT capstone, and the
// VAD calibration panel had no test file at all. The unlock sits inside the
// recorder's `onstop` handler, after `vad.calibrate()` resolves — so it is a
// success-only grant that no call-site guard can distinguish from one hoisted
// above the `try`, which would hand the achievement to a player whose
// calibration failed.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import type { UseVadReturn } from '../hooks/useVad'

// Typed with an explicit signature (rather than letting the no-arg
// implementation infer one) so `mock.calls` destructures the name argument
// instead of inferring an empty tuple.
const mockUnlock = vi.fn<(name: string) => Promise<boolean>>(() => Promise.resolve(false))
const mockIncrementStat = vi.fn<(name: string) => Promise<boolean>>(() => Promise.resolve(false))
// Only the hook itself is stubbed; importOriginal keeps the real name maps, so
// these assertions cannot drift from the shipped API names.
vi.mock('../hooks/useSteamAchievements', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useSteamAchievements')>()),
  useSteamAchievements: () => ({ unlock: mockUnlock, incrementStat: mockIncrementStat }),
}))

import VadCalibration from '../components/VadCalibration'

const CALIBRATION_SECONDS = 3

class MockMediaRecorder {
  state: 'inactive' | 'recording' | 'paused' = 'inactive'
  mimeType: string
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null

  constructor(_stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? 'audio/webm'
  }

  start(): void {
    this.state = 'recording'
  }

  stop(): void {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['chunk'], { type: this.mimeType }) })
    this.onstop?.()
  }

  static isTypeSupported(): boolean {
    return true
  }
}

function makeVad(overrides: Partial<UseVadReturn> = {}): UseVadReturn {
  return {
    settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
    vadState: 'idle',
    isCalibrating: false,
    backendAvailable: true,
    setMode: vi.fn(),
    setThreshold: vi.fn(),
    setSilenceDurationMs: vi.fn(),
    startSilenceDetection: vi.fn(),
    stopSilenceDetection: vi.fn(),
    calibrate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

const mockStream = { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream

/** Clicks Start and runs the countdown and the recording window to completion. */
async function runCalibration() {
  fireEvent.click(screen.getByRole('button', { name: /start 3-second calibration/i }))
  // Countdown ticks once a second, then the recorder runs for the same window.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(CALIBRATION_SECONDS * 1000)
  })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(CALIBRATION_SECONDS * 1000)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.stubGlobal('MediaRecorder', MockMediaRecorder)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('VadCalibration — ACH_VAD_CALIBRATED', () => {
  it('grants it once calibration completes', async () => {
    const vad = makeVad()
    render(<VadCalibration vad={vad} stream={mockStream} onDone={vi.fn()} />)
    expect(mockUnlock).not.toHaveBeenCalled()

    await runCalibration()

    expect(vad.calibrate).toHaveBeenCalled()
    expect(screen.getByText(/calibration complete/i)).toBeInTheDocument()
    expect(mockUnlock).toHaveBeenCalledWith('ACH_VAD_CALIBRATED')
  })

  it('does not grant it when calibration fails', async () => {
    // The player's microphone pipeline is not calibrated, so the achievement
    // that says it is must not be granted.
    const vad = makeVad({ calibrate: vi.fn().mockRejectedValue(new Error('vad worker down')) })
    render(<VadCalibration vad={vad} stream={mockStream} onDone={vi.fn()} />)

    await runCalibration()

    expect(screen.getByText(/calibration failed/i)).toBeInTheDocument()
    expect(mockUnlock).not.toHaveBeenCalledWith('ACH_VAD_CALIBRATED')
  })

  it('does not grant it for merely opening the panel', async () => {
    render(<VadCalibration vad={makeVad()} stream={mockStream} onDone={vi.fn()} />)
    expect(mockUnlock).not.toHaveBeenCalled()
  })

  it('does not grant it from the threshold sliders, which calibrate nothing', async () => {
    // Nudging the threshold by hand is not calibration — it is the fallback for
    // when calibration is unavailable.
    const vad = makeVad()
    render(<VadCalibration vad={vad} stream={mockStream} onDone={vi.fn()} />)
    fireEvent.change(screen.getByRole('slider', { name: /silence threshold/i }), {
      target: { value: '0.09' },
    })
    expect(vad.setThreshold).toHaveBeenCalled()
    expect(mockUnlock).not.toHaveBeenCalledWith('ACH_VAD_CALIBRATED')
  })

  it('increments no stat — a calibration run is not a counted event', async () => {
    render(<VadCalibration vad={makeVad()} stream={mockStream} onDone={vi.fn()} />)
    await runCalibration()
    expect(mockIncrementStat).not.toHaveBeenCalled()
  })
})
