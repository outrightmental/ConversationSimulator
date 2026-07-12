// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamDlc } from '../hooks/useSteamDlc'

// ── Helpers ───────────────────────────────────────────────────────────────────

type InvokeFn = (cmd: string, args?: unknown) => Promise<unknown>

function stubTauriInvoke(invoke: InvokeFn) {
  const win = window as { __TAURI__?: unknown }
  win.__TAURI__ = { core: { invoke } }
}

function clearTauri() {
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
}

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  clearTauri()
})

afterEach(() => {
  vi.restoreAllMocks()
  clearTauri()
})

// ── Non-Tauri (browser) context ───────────────────────────────────────────────

describe('useSteamDlc — non-Tauri context', () => {
  it('isDlcInstalled returns false when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamDlc())
    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalled(1234567)
    })
    expect(owned).toBe(false)
  })

  it('returns false when __TAURI__ has no core.invoke', async () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }

    const { result } = renderHook(() => useSteamDlc())
    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalled(1234567)
    })
    expect(owned).toBe(false)
  })
})

// ── isDlcInstalled ────────────────────────────────────────────────────────────

describe('useSteamDlc — isDlcInstalled', () => {
  it('invokes steam_is_dlc_installed with the dlc_app_id', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    let owned = false
    await act(async () => {
      owned = await result.current.isDlcInstalled(1234567)
    })

    expect(owned).toBe(true)
    expect(invoke).toHaveBeenCalledWith('steam_is_dlc_installed', {
      dlc_app_id: 1234567,
    })
  })

  it('returns false when the user does not own the DLC', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalled(1234567)
    })
    expect(owned).toBe(false)
  })

  it('returns false and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('Steam not running'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalled(1234567)
    })
    expect(owned).toBe(false)
  })

  it('returns false for a DLC App ID of 0', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalled(0)
    })
    expect(owned).toBe(false)
    expect(invoke).toHaveBeenCalledWith('steam_is_dlc_installed', {
      dlc_app_id: 0,
    })
  })

  it('handles multiple DLC App IDs independently', async () => {
    const invoke = vi.fn().mockImplementation((_cmd, args) => {
      const { dlc_app_id } = args as { dlc_app_id: number }
      return Promise.resolve(dlc_app_id === 1111111)
    })
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    let owned1 = false
    let owned2 = true
    await act(async () => {
      owned1 = await result.current.isDlcInstalled(1111111)
      owned2 = await result.current.isDlcInstalled(2222222)
    })
    expect(owned1).toBe(true)
    expect(owned2).toBe(false)
  })
})
