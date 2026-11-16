// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { voiceJob, voicePlan, readyPlan } from './voiceFixtures'

vi.mock('../api/client', () => ({
  api: {
    getVoiceSetup: vi.fn(),
    startVoiceInstall: vi.fn(),
    getVoiceInstallJob: vi.fn(),
    cancelVoiceInstall: vi.fn(),
  },
}))

import { api } from '../api/client'
import { useVoiceInstall } from '../hooks/useVoiceInstall'

const mockApi = vi.mocked(api)
const ok = <T,>(data: T) => ({ ok: true as const, data })

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useVoiceInstall', () => {
  it('loads the plan without starting anything', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan()))
    const { result } = renderHook(() => useVoiceInstall())

    await waitFor(() => expect(result.current.status).not.toBeNull())
    expect(result.current.installing).toBe(false)
    expect(result.current.job).toBeNull()
    expect(mockApi.startVoiceInstall).not.toHaveBeenCalled()
  })

  it('installs, follows the job to the end, then reloads the plan and tells the caller', async () => {
    mockApi.getVoiceSetup.mockResolvedValueOnce(ok(voicePlan()))
    mockApi.startVoiceInstall.mockResolvedValue(ok(voiceJob({ status: 'running' })))
    mockApi.getVoiceInstallJob
      .mockResolvedValueOnce(ok(voiceJob({ status: 'running' })))
      .mockResolvedValue(ok(voiceJob({ status: 'complete' })))
    mockApi.getVoiceSetup.mockResolvedValue(ok(readyPlan()))
    const onChanged = vi.fn()

    const { result } = renderHook(() => useVoiceInstall(onChanged))
    await waitFor(() => expect(result.current.status).not.toBeNull())

    await act(async () => {
      await result.current.install()
    })
    expect(mockApi.startVoiceInstall).toHaveBeenCalledWith(undefined)
    expect(result.current.installing).toBe(true)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500)
    })

    await waitFor(() => expect(result.current.job?.status).toBe('complete'))
    expect(result.current.installing).toBe(false)
    expect(result.current.status?.components.every((c) => c.ready)).toBe(true)
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('reattaches to an install that was already running', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan({ job: voiceJob({ id: 7 }) })))
    mockApi.getVoiceInstallJob.mockResolvedValue(ok(voiceJob({ id: 7 })))

    const { result } = renderHook(() => useVoiceInstall())
    await waitFor(() => expect(result.current.installing).toBe(true))
    expect(result.current.job?.id).toBe(7)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800)
    })
    expect(mockApi.getVoiceInstallJob).toHaveBeenCalledWith(7)
    expect(mockApi.startVoiceInstall).not.toHaveBeenCalled()
  })

  it('shows the outcome of an install that just failed', async () => {
    const failed = voiceJob({ status: 'failed', error_code: 'NETWORK', error_message: 'Offline.' })
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan({ job: failed })))

    const { result } = renderHook(() => useVoiceInstall())
    await waitFor(() => expect(result.current.job?.status).toBe('failed'))
    expect(result.current.installing).toBe(false)
    expect(mockApi.getVoiceInstallJob).not.toHaveBeenCalled()
  })

  it('does not tell the caller anything changed when the job fails', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan()))
    mockApi.startVoiceInstall.mockResolvedValue(ok(voiceJob()))
    mockApi.getVoiceInstallJob.mockResolvedValue(
      ok(voiceJob({ status: 'failed', error_code: 'CHECKSUM', error_message: 'Mismatch.' })),
    )
    const onChanged = vi.fn()

    const { result } = renderHook(() => useVoiceInstall(onChanged))
    await waitFor(() => expect(result.current.status).not.toBeNull())
    await act(async () => {
      await result.current.install()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })

    await waitFor(() => expect(result.current.job?.status).toBe('failed'))
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('reports a refusal to start as an error, not as a job', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan()))
    mockApi.startVoiceInstall.mockResolvedValue({
      ok: false as const,
      error: { kind: 'http-error' as const, status: 409, message: 'Voice is not available here.' },
    })

    const { result } = renderHook(() => useVoiceInstall())
    await waitFor(() => expect(result.current.status).not.toBeNull())
    await act(async () => {
      await result.current.install()
    })

    expect(result.current.error?.message).toBe('Voice is not available here.')
    expect(result.current.installing).toBe(false)
  })

  it('cancels the running job', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan({ job: voiceJob({ id: 3 }) })))
    mockApi.getVoiceInstallJob.mockResolvedValue(ok(voiceJob({ id: 3 })))
    mockApi.cancelVoiceInstall.mockResolvedValue(ok(undefined))

    const { result } = renderHook(() => useVoiceInstall())
    await waitFor(() => expect(result.current.installing).toBe(true))
    await act(async () => {
      await result.current.cancel()
    })

    expect(mockApi.cancelVoiceInstall).toHaveBeenCalledWith(3)
    expect(result.current.error).toBeNull()
  })

  it('treats a cancel that lost the race with completion as no error', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan({ job: voiceJob({ id: 3 }) })))
    mockApi.getVoiceInstallJob.mockResolvedValue(ok(voiceJob({ id: 3 })))
    mockApi.cancelVoiceInstall.mockResolvedValue({
      ok: false as const,
      error: { kind: 'http-error' as const, status: 409, message: 'Already complete.' },
    })

    const { result } = renderHook(() => useVoiceInstall())
    await waitFor(() => expect(result.current.installing).toBe(true))
    await act(async () => {
      await result.current.cancel()
    })
    expect(result.current.error).toBeNull()
  })

  it('offers no installer when the engine has none', async () => {
    mockApi.getVoiceSetup.mockResolvedValue({
      ok: false as const,
      error: { kind: 'http-error' as const, status: 404, message: 'Not Found' },
    })
    const { result } = renderHook(() => useVoiceInstall())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    expect(result.current.status).toBeNull()
    expect(result.current.installing).toBe(false)
  })
})
