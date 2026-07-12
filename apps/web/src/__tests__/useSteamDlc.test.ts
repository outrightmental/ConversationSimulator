// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import {
  useSteamDlc,
  useSteamDlcOwned,
  useSteamDlcStore,
  DLC_CATALOG,
} from '../hooks/useSteamDlc'
import type { DlcEntry } from '../hooks/useSteamDlc'

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

// ── DLC_CATALOG shape ─────────────────────────────────────────────────────────

describe('DLC_CATALOG', () => {
  it('exports a non-empty array', () => {
    expect(Array.isArray(DLC_CATALOG)).toBe(true)
    expect(DLC_CATALOG.length).toBeGreaterThan(0)
  })

  it('every entry has required fields', () => {
    for (const entry of DLC_CATALOG) {
      expect(typeof entry.pack_id).toBe('string')
      expect(entry.pack_id.length).toBeGreaterThan(0)
      expect(typeof entry.name).toBe('string')
      expect(entry.name.length).toBeGreaterThan(0)
      expect(typeof entry.description).toBe('string')
      expect(entry.description.length).toBeGreaterThan(0)
      expect(typeof entry.steam_dlc_app_id).toBe('number')
      expect(entry.steam_dlc_app_id).toBeGreaterThan(0)
      expect(typeof entry.store_url).toBe('string')
      expect(entry.store_url).toMatch(/^https:\/\/store\.steampowered\.com\/app\//)
    }
  })

  it('every pack_id starts with "premium."', () => {
    for (const entry of DLC_CATALOG) {
      expect(entry.pack_id).toMatch(/^premium\./)
    }
  })

  it('steam_dlc_app_ids are unique', () => {
    const ids = DLC_CATALOG.map((e) => e.steam_dlc_app_id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('pack_ids are unique', () => {
    const ids = DLC_CATALOG.map((e) => e.pack_id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

// ── useSteamDlcOwned — non-Tauri context ─────────────────────────────────────

describe('useSteamDlcOwned — non-Tauri context', () => {
  it('returns false immediately when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamDlcOwned(3000001))
    await waitFor(() => expect(result.current).toBe(false))
  })

  it('starts as null then resolves to false without Tauri', async () => {
    const { result } = renderHook(() => useSteamDlcOwned(3000001))
    // After mount, should resolve to false
    await waitFor(() => expect(result.current).not.toBeNull())
    expect(result.current).toBe(false)
  })

  it('returns false when __TAURI__ has no core', async () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }
    const { result } = renderHook(() => useSteamDlcOwned(3000001))
    await waitFor(() => expect(result.current).toBe(false))
  })
})

// ── useSteamDlcOwned — Tauri context ─────────────────────────────────────────

describe('useSteamDlcOwned — Tauri context', () => {
  it('returns true when steam_is_dlc_installed resolves true', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlcOwned(3000001))
    await waitFor(() => expect(result.current).toBe(true))
    expect(invoke).toHaveBeenCalledWith('steam_is_dlc_installed', { app_id: 3000001 })
  })

  it('returns false when steam_is_dlc_installed resolves false', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlcOwned(3000002))
    await waitFor(() => expect(result.current).toBe(false))
  })

  it('returns false when the Tauri command rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('IPC error'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlcOwned(3000001))
    await waitFor(() => expect(result.current).toBe(false))
  })

  it('starts as null while the check is in progress', async () => {
    let resolve: (v: boolean) => void
    const invoke = vi.fn().mockReturnValue(new Promise<boolean>((r) => { resolve = r }))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamDlcOwned(3000001))
    expect(result.current).toBeNull()
    await act(async () => { resolve!(true) })
    await waitFor(() => expect(result.current).toBe(true))
  })
})

// ── useSteamDlc — non-Tauri context ──────────────────────────────────────────

describe('useSteamDlc — non-Tauri context', () => {
  it('resolves immediately with empty ownedPackIds and isLoaded true', async () => {
    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.ownedPackIds.size).toBe(0)
  })

  it('ownedPackIds is a Set', async () => {
    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.ownedPackIds).toBeInstanceOf(Set)
  })
})

// ── useSteamDlc — Tauri context ───────────────────────────────────────────────

describe('useSteamDlc — Tauri context', () => {
  it('includes owned pack_ids in ownedPackIds', async () => {
    const firstEntry = DLC_CATALOG[0]!
    const invoke = vi.fn().mockImplementation((_cmd: string, args?: unknown) => {
      const { app_id } = args as { app_id: number }
      return Promise.resolve(app_id === firstEntry.steam_dlc_app_id)
    })
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.ownedPackIds.has(firstEntry.pack_id)).toBe(true)
  })

  it('excludes unowned pack_ids from ownedPackIds', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.ownedPackIds.size).toBe(0)
  })

  it('calls steam_is_dlc_installed for each catalog entry', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    const dlcCalls = invoke.mock.calls.filter(([cmd]) => cmd === 'steam_is_dlc_installed')
    expect(dlcCalls).toHaveLength(DLC_CATALOG.length)
  })

  it('handles rejected invoke calls gracefully (treats as unowned)', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('Steam error'))
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.ownedPackIds.size).toBe(0)
  })

  it('loads all owned DLC when all entries are owned', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.ownedPackIds.size).toBe(DLC_CATALOG.length)
    for (const entry of DLC_CATALOG) {
      expect(result.current.ownedPackIds.has(entry.pack_id)).toBe(true)
    }
  })
})

// ── useSteamDlcStore — non-Tauri context ─────────────────────────────────────

describe('useSteamDlcStore — non-Tauri context', () => {
  it('falls back to window.open when __TAURI__ is absent', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const { result } = renderHook(() => useSteamDlcStore())
    const entry: DlcEntry = DLC_CATALOG[0]!

    await act(async () => {
      await result.current.openStorePage(entry)
    })

    expect(openSpy).toHaveBeenCalledWith(entry.store_url, '_blank', 'noopener,noreferrer')
  })
})

// ── useSteamDlcStore — Tauri context ─────────────────────────────────────────

describe('useSteamDlcStore — Tauri context', () => {
  it('invokes steam_open_dlc_store_overlay and does not open browser when overlay succeeds', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const { result } = renderHook(() => useSteamDlcStore())
    const entry: DlcEntry = DLC_CATALOG[0]!

    await act(async () => {
      await result.current.openStorePage(entry)
    })

    expect(invoke).toHaveBeenCalledWith('steam_open_dlc_store_overlay', {
      app_id: entry.steam_dlc_app_id,
    })
    expect(openSpy).not.toHaveBeenCalled()
  })

  it('falls back to window.open when overlay command returns false', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const { result } = renderHook(() => useSteamDlcStore())
    const entry: DlcEntry = DLC_CATALOG[0]!

    await act(async () => {
      await result.current.openStorePage(entry)
    })

    expect(openSpy).toHaveBeenCalledWith(entry.store_url, '_blank', 'noopener,noreferrer')
  })

  it('falls back to window.open when overlay command rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('overlay error'))
    stubTauriInvoke(invoke)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const { result } = renderHook(() => useSteamDlcStore())
    const entry: DlcEntry = DLC_CATALOG[0]!

    await act(async () => {
      await result.current.openStorePage(entry)
    })

    expect(openSpy).toHaveBeenCalledWith(entry.store_url, '_blank', 'noopener,noreferrer')
  })
})
