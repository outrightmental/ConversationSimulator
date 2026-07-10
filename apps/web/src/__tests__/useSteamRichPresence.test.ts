// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import {
  useSteamRichPresence,
  SteamActivity,
} from '../hooks/useSteamRichPresence'

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

describe('useSteamRichPresence — non-Tauri context', () => {
  it('setPresence returns false immediately when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamRichPresence())
    const ok = await result.current.setPresence(SteamActivity.IN_SCENARIO)
    expect(ok).toBe(false)
  })

  it('returns false when __TAURI__ has no core.invoke', async () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }

    const { result } = renderHook(() => useSteamRichPresence())
    const ok = await result.current.setPresence(SteamActivity.AT_MAIN_MENU)
    expect(ok).toBe(false)
  })
})

// ── Rich presence updates ─────────────────────────────────────────────────────

describe('useSteamRichPresence — setPresence', () => {
  it('invokes steam_set_rich_presence with the IN_SCENARIO token', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamRichPresence())

    let ok = false
    await act(async () => {
      ok = await result.current.setPresence(SteamActivity.IN_SCENARIO)
    })

    expect(ok).toBe(true)
    expect(invoke).toHaveBeenCalledOnce()
    expect(invoke).toHaveBeenCalledWith('steam_set_rich_presence', {
      value: SteamActivity.IN_SCENARIO,
    })
  })

  it('invokes steam_set_rich_presence with the REVIEWING_DEBRIEF token', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamRichPresence())

    await act(async () => {
      await result.current.setPresence(SteamActivity.REVIEWING_DEBRIEF)
    })

    expect(invoke).toHaveBeenCalledWith('steam_set_rich_presence', {
      value: SteamActivity.REVIEWING_DEBRIEF,
    })
  })

  it('invokes steam_set_rich_presence with the EDITING_PACK token', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamRichPresence())

    await act(async () => {
      await result.current.setPresence(SteamActivity.EDITING_PACK)
    })

    expect(invoke).toHaveBeenCalledWith('steam_set_rich_presence', {
      value: SteamActivity.EDITING_PACK,
    })
  })

  it('invokes steam_set_rich_presence with the AT_MAIN_MENU token', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamRichPresence())

    await act(async () => {
      await result.current.setPresence(SteamActivity.AT_MAIN_MENU)
    })

    expect(invoke).toHaveBeenCalledWith('steam_set_rich_presence', {
      value: SteamActivity.AT_MAIN_MENU,
    })
  })

  it('passes each activity token correctly', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamRichPresence())

    const tokens = Object.values(SteamActivity)
    for (const token of tokens) {
      await act(async () => {
        await result.current.setPresence(token)
      })
    }

    expect(invoke).toHaveBeenCalledTimes(tokens.length)
    for (const token of tokens) {
      expect(invoke).toHaveBeenCalledWith('steam_set_rich_presence', {
        value: token,
      })
    }
  })

  it('returns false when Steam is absent (invoke returns false)', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamRichPresence())

    let ok = true
    await act(async () => {
      ok = await result.current.setPresence(SteamActivity.IN_SCENARIO)
    })
    expect(ok).toBe(false)
  })

  it('returns false and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('IPC error'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamRichPresence())

    let ok = true
    await act(async () => {
      ok = await result.current.setPresence(SteamActivity.REVIEWING_DEBRIEF)
    })
    expect(ok).toBe(false)
  })
})

// ── SteamActivity constant shapes ─────────────────────────────────────────────

describe('SteamActivity constants', () => {
  it('all tokens start with #', () => {
    for (const v of Object.values(SteamActivity)) {
      expect(v).toMatch(/^#/)
    }
  })

  it('contains all four v1 activity states', () => {
    expect(SteamActivity.IN_SCENARIO).toBe('#InScenario')
    expect(SteamActivity.REVIEWING_DEBRIEF).toBe('#ReviewingDebrief')
    expect(SteamActivity.EDITING_PACK).toBe('#EditingPack')
    expect(SteamActivity.AT_MAIN_MENU).toBe('#AtMainMenu')
  })
})
