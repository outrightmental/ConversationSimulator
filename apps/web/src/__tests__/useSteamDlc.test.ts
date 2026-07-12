// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useSteamDlc / useSteamDlcOwned.
 *
 * These verify the premium-DLC ownership gate (see docs/DLC_MODEL.md):
 *  - In a browser context (window.__TAURI__ absent) every premium pack is
 *    treated as not-owned, without attempting a Tauri invocation.
 *  - Under Tauri the hooks call `steam_is_dlc_installed` with the DLC App ID and
 *    reflect its boolean result (coercing anything non-`true` to `false`).
 *  - The command argument is the camelCase key `dlcAppId`, which is how Tauri v2
 *    maps to the Rust `dlc_app_id` parameter of a plain `#[tauri::command]`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useSteamDlc, useSteamDlcOwned } from '../hooks/useSteamDlc'

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

const SAMPLE_DLC_APP_ID = 3210000

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  clearTauri()
})

afterEach(() => {
  vi.restoreAllMocks()
  clearTauri()
})

// ── useSteamDlcOwned — non-Tauri (browser) context ────────────────────────────

describe('useSteamDlcOwned — non-Tauri context', () => {
  it('reports not-owned when __TAURI__ is absent', () => {
    const { result } = renderHook(() => useSteamDlcOwned(SAMPLE_DLC_APP_ID))
    expect(result.current).toBe(false)
  })

  it('reports not-owned when __TAURI__ has no core.invoke', () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }

    const { result } = renderHook(() => useSteamDlcOwned(SAMPLE_DLC_APP_ID))
    expect(result.current).toBe(false)
  })
})

// ── useSteamDlcOwned — Tauri context ──────────────────────────────────────────

describe('useSteamDlcOwned — Tauri context', () => {
  it('invokes steam_is_dlc_installed with the camelCase dlcAppId and reflects true', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlcOwned(SAMPLE_DLC_APP_ID))

    await waitFor(() => expect(result.current).toBe(true))
    expect(invoke).toHaveBeenCalledWith('steam_is_dlc_installed', {
      dlcAppId: SAMPLE_DLC_APP_ID,
    })
  })

  it('reports not-owned when the command resolves false', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlcOwned(SAMPLE_DLC_APP_ID))

    // Give the effect a chance to run; ownership must remain false.
    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current).toBe(false)
  })

  it('coerces a non-boolean result to false', async () => {
    const invoke = vi.fn().mockResolvedValue('yes' as unknown as boolean)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlcOwned(SAMPLE_DLC_APP_ID))

    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current).toBe(false)
  })

  it('reports not-owned when the command rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('steam feature off'))
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlcOwned(SAMPLE_DLC_APP_ID))

    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current).toBe(false)
  })

  it('skips the check and stays not-owned when dlcAppId is null', () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlcOwned(null))
    expect(result.current).toBe(false)
    expect(invoke).not.toHaveBeenCalled()
  })
})

// ── useSteamDlc — imperative variant ──────────────────────────────────────────

describe('useSteamDlc — imperative isDlcOwned', () => {
  it('resolves false when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamDlc())
    const owned = await result.current.isDlcOwned(SAMPLE_DLC_APP_ID)
    expect(owned).toBe(false)
  })

  it('invokes steam_is_dlc_installed with the camelCase dlcAppId and returns its result', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())

    let owned = false
    await act(async () => {
      owned = await result.current.isDlcOwned(SAMPLE_DLC_APP_ID)
    })

    expect(owned).toBe(true)
    expect(invoke).toHaveBeenCalledWith('steam_is_dlc_installed', {
      dlcAppId: SAMPLE_DLC_APP_ID,
    })
  })

  it('resolves false when the command rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('not running under Steam'))
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamDlc())

    let owned = true
    await act(async () => {
      owned = await result.current.isDlcOwned(SAMPLE_DLC_APP_ID)
    })
    expect(owned).toBe(false)
  })
})
