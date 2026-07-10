// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import {
  useSteamAchievements,
  SteamAchievement,
  SteamStat,
} from '../hooks/useSteamAchievements'

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

describe('useSteamAchievements — non-Tauri context', () => {
  it('unlock returns false immediately when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamAchievements())
    const ok = await result.current.unlock(SteamAchievement.FIRST_SCENARIO)
    expect(ok).toBe(false)
  })

  it('incrementStat returns false immediately when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamAchievements())
    const ok = await result.current.incrementStat(SteamStat.SCENARIOS_COMPLETED)
    expect(ok).toBe(false)
  })

  it('returns false when __TAURI__ has no core.invoke', async () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }

    const { result } = renderHook(() => useSteamAchievements())
    const ok = await result.current.unlock(SteamAchievement.FIRST_DEBRIEF)
    expect(ok).toBe(false)
  })
})

// ── Achievement unlock ────────────────────────────────────────────────────────

describe('useSteamAchievements — unlock', () => {
  it('invokes steam_unlock_achievement with the correct name', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamAchievements())

    let ok: boolean = false
    await act(async () => {
      ok = await result.current.unlock(SteamAchievement.FIRST_SCENARIO)
    })

    expect(ok).toBe(true)
    expect(invoke).toHaveBeenCalledOnce()
    expect(invoke).toHaveBeenCalledWith('steam_unlock_achievement', {
      name: SteamAchievement.FIRST_SCENARIO,
    })
  })

  it('returns false when invoke returns false (already unlocked or Steam absent)', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamAchievements())

    let ok = true
    await act(async () => {
      ok = await result.current.unlock(SteamAchievement.FIRST_DEBRIEF)
    })

    expect(ok).toBe(false)
  })

  it('returns false and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('Steam unavailable'))
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamAchievements())

    let ok = true
    await act(async () => {
      ok = await result.current.unlock(SteamAchievement.PRACTICE_STREAK)
    })

    expect(ok).toBe(false)
  })

  it('passes all achievement API names through to invoke', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamAchievements())

    const names = Object.values(SteamAchievement)
    for (const name of names) {
      await act(async () => {
        await result.current.unlock(name)
      })
    }

    expect(invoke).toHaveBeenCalledTimes(names.length)
    for (const name of names) {
      expect(invoke).toHaveBeenCalledWith('steam_unlock_achievement', { name })
    }
  })
})

// ── Stat increment ────────────────────────────────────────────────────────────

describe('useSteamAchievements — incrementStat', () => {
  it('invokes steam_increment_stat with the correct name', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamAchievements())

    let ok = false
    await act(async () => {
      ok = await result.current.incrementStat(SteamStat.SCENARIOS_COMPLETED)
    })

    expect(ok).toBe(true)
    expect(invoke).toHaveBeenCalledWith('steam_increment_stat', {
      name: SteamStat.SCENARIOS_COMPLETED,
    })
  })

  it('returns false when invoke returns false', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamAchievements())

    let ok = true
    await act(async () => {
      ok = await result.current.incrementStat(SteamStat.DEBRIEFS_GENERATED)
    })
    expect(ok).toBe(false)
  })

  it('returns false and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('IPC error'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamAchievements())

    let ok = true
    await act(async () => {
      ok = await result.current.incrementStat(SteamStat.TEXT_MODE_SESSIONS)
    })
    expect(ok).toBe(false)
  })

  it('passes all stat API names through to invoke', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamAchievements())

    const names = Object.values(SteamStat)
    for (const name of names) {
      await act(async () => {
        await result.current.incrementStat(name)
      })
    }

    expect(invoke).toHaveBeenCalledTimes(names.length)
    for (const name of names) {
      expect(invoke).toHaveBeenCalledWith('steam_increment_stat', { name })
    }
  })
})

// ── API name constant shapes ──────────────────────────────────────────────────

describe('SteamAchievement constants', () => {
  it('all have the ACH_ prefix', () => {
    for (const v of Object.values(SteamAchievement)) {
      expect(v).toMatch(/^ACH_/)
    }
  })

  it('contains the five v1 achievements', () => {
    expect(SteamAchievement.FIRST_SCENARIO).toBe('ACH_FIRST_SCENARIO')
    expect(SteamAchievement.FIRST_DEBRIEF).toBe('ACH_FIRST_DEBRIEF')
    expect(SteamAchievement.PRACTICE_STREAK).toBe('ACH_PRACTICE_STREAK')
    expect(SteamAchievement.PACK_EXPLORER).toBe('ACH_PACK_EXPLORER')
    expect(SteamAchievement.CREATOR_FIRST_VALIDATE).toBe(
      'ACH_CREATOR_FIRST_VALIDATE',
    )
  })
})

describe('SteamStat constants', () => {
  it('all have the STAT_ prefix', () => {
    for (const v of Object.values(SteamStat)) {
      expect(v).toMatch(/^STAT_/)
    }
  })

  it('contains the five v1 stats', () => {
    expect(SteamStat.SCENARIOS_COMPLETED).toBe('STAT_SCENARIOS_COMPLETED')
    expect(SteamStat.DEBRIEFS_GENERATED).toBe('STAT_DEBRIEFS_GENERATED')
    expect(SteamStat.PACKS_VALIDATED).toBe('STAT_PACKS_VALIDATED')
    expect(SteamStat.TEXT_MODE_SESSIONS).toBe('STAT_TEXT_MODE_SESSIONS')
    expect(SteamStat.VOICE_MODE_SESSIONS).toBe('STAT_VOICE_MODE_SESSIONS')
  })
})
