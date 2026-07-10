// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamStatus } from '../hooks/useSteamStatus'
import type { SteamStatus } from '../hooks/useSteamStatus'

// ── Helpers ───────────────────────────────────────────────────────────────────

type InvokeFn = (cmd: string) => Promise<unknown>

function stubTauriInvoke(invoke: InvokeFn) {
  const win = window as { __TAURI__?: unknown }
  win.__TAURI__ = { core: { invoke } }
}

function clearTauri() {
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
}

const DISABLED_STATUS: SteamStatus = {
  is_steam_enabled: false,
  launched_by_steam: false,
  app_id: null,
  persona_name: null,
}

const STEAM_RUNNING_STATUS: SteamStatus = {
  is_steam_enabled: false,
  launched_by_steam: true,
  app_id: 480,
  persona_name: null,
}

const STEAM_ENABLED_STATUS: SteamStatus = {
  is_steam_enabled: true,
  launched_by_steam: true,
  app_id: 480,
  persona_name: 'TestPlayer',
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

describe('useSteamStatus — non-Tauri context', () => {
  it('returns null immediately when __TAURI__ is absent', () => {
    const { result } = renderHook(() => useSteamStatus())
    expect(result.current).toBeNull()
  })

  it('returns null when __TAURI__ has no core.invoke', () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }
    const { result } = renderHook(() => useSteamStatus())
    expect(result.current).toBeNull()
  })
})

// ── Steam absent ──────────────────────────────────────────────────────────────

describe('useSteamStatus — Steam absent', () => {
  it('returns disabled status when get_steam_status reports steam absent', async () => {
    const invoke = vi.fn().mockResolvedValue(DISABLED_STATUS)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamStatus())

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current).toEqual(DISABLED_STATUS)
    expect(result.current?.is_steam_enabled).toBe(false)
    expect(result.current?.launched_by_steam).toBe(false)
    expect(result.current?.app_id).toBeNull()
    expect(result.current?.persona_name).toBeNull()
  })

  it('invokes get_steam_status exactly once on mount', async () => {
    const invoke = vi.fn().mockResolvedValue(DISABLED_STATUS)
    stubTauriInvoke(invoke)

    renderHook(() => useSteamStatus())

    await act(async () => {
      await Promise.resolve()
    })

    expect(invoke).toHaveBeenCalledOnce()
    expect(invoke).toHaveBeenCalledWith('get_steam_status')
  })
})

// ── Steam running (launched by Steam, SDK not initialized) ────────────────────

describe('useSteamStatus — Steam running without SDK feature', () => {
  it('reports launched_by_steam true and app_id when env-var detection fires', async () => {
    const invoke = vi.fn().mockResolvedValue(STEAM_RUNNING_STATUS)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamStatus())

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current?.launched_by_steam).toBe(true)
    expect(result.current?.app_id).toBe(480)
    expect(result.current?.is_steam_enabled).toBe(false)
    expect(result.current?.persona_name).toBeNull()
  })
})

// ── Packaged Steam launch (SDK feature enabled and initialized) ───────────────

describe('useSteamStatus — packaged Steam launch with SDK', () => {
  it('reports is_steam_enabled true with persona_name and app_id', async () => {
    const invoke = vi.fn().mockResolvedValue(STEAM_ENABLED_STATUS)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamStatus())

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current?.is_steam_enabled).toBe(true)
    expect(result.current?.launched_by_steam).toBe(true)
    expect(result.current?.app_id).toBe(480)
    expect(result.current?.persona_name).toBe('TestPlayer')
  })
})

// ── Error resilience ──────────────────────────────────────────────────────────

describe('useSteamStatus — invoke error handling', () => {
  it('stays null when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('invoke failed'))
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamStatus())

    await act(async () => {
      await Promise.resolve()
    })

    // Should not throw and should remain null after the rejection.
    expect(result.current).toBeNull()
  })
})
