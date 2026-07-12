// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamDlc, parseDlcRegistry, DLC_REGISTRY } from '../hooks/useSteamDlc'

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

// ── parseDlcRegistry ──────────────────────────────────────────────────────────

describe('parseDlcRegistry', () => {
  it('returns empty record for undefined input', () => {
    expect(parseDlcRegistry(undefined)).toEqual({})
  })

  it('returns empty record for empty string', () => {
    expect(parseDlcRegistry('')).toEqual({})
  })

  it('parses a single pack_id:app_id entry', () => {
    expect(parseDlcRegistry('official.premium_pack:2123456')).toEqual({
      'official.premium_pack': 2123456,
    })
  })

  it('parses multiple comma-separated entries', () => {
    const result = parseDlcRegistry('official.pack_a:2000001,official.pack_b:2000002')
    expect(result).toEqual({
      'official.pack_a': 2000001,
      'official.pack_b': 2000002,
    })
  })

  it('trims whitespace around pack IDs and app IDs', () => {
    const result = parseDlcRegistry(' official.pack : 2000001 ')
    expect(result).toEqual({ 'official.pack': 2000001 })
  })

  it('skips entries with no colon separator', () => {
    const result = parseDlcRegistry('official.good:2000001,bad-no-colon,official.also_good:2000002')
    expect(result).toEqual({
      'official.good': 2000001,
      'official.also_good': 2000002,
    })
  })

  it('skips entries with non-numeric app IDs', () => {
    const result = parseDlcRegistry('official.bad:not_a_number,official.good:2000001')
    expect(result).toEqual({ 'official.good': 2000001 })
  })

  it('skips entries with zero or negative app IDs', () => {
    const result = parseDlcRegistry('official.zero:0,official.neg:-1,official.good:2000001')
    expect(result).toEqual({ 'official.good': 2000001 })
  })

  it('skips entries with empty pack IDs', () => {
    const result = parseDlcRegistry(':2000001,official.good:2000002')
    expect(result).toEqual({ 'official.good': 2000002 })
  })

  it('skips empty comma-separated slots', () => {
    const result = parseDlcRegistry('official.good:2000001,,official.other:2000002')
    expect(result).toEqual({
      'official.good': 2000001,
      'official.other': 2000002,
    })
  })
})

// ── DLC_REGISTRY ──────────────────────────────────────────────────────────────

describe('DLC_REGISTRY', () => {
  it('is an object (empty in test environment without VITE_STEAM_DLC_APP_IDS)', () => {
    expect(typeof DLC_REGISTRY).toBe('object')
    expect(DLC_REGISTRY).not.toBeNull()
  })
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

  it('isDlcInstalledForPack returns false when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamDlc())
    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalledForPack('official.some_pack')
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

// ── isDlcInstalledForPack ─────────────────────────────────────────────────────

describe('useSteamDlc — isDlcInstalledForPack', () => {
  it('returns false for a pack with no DLC App ID in the registry', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    let owned = true
    await act(async () => {
      owned = await result.current.isDlcInstalledForPack('official.free_pack')
    })

    expect(owned).toBe(false)
    expect(invoke).not.toHaveBeenCalled()
  })

  it('does not call Tauri when the pack has no registered DLC App ID', async () => {
    const invoke = vi.fn()
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlc())

    await act(async () => {
      await result.current.isDlcInstalledForPack('unknown.pack')
    })
    expect(invoke).not.toHaveBeenCalled()
  })
})
