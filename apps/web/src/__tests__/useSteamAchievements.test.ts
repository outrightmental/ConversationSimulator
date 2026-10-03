// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import {
  useSteamAchievements,
  SteamAchievement,
  SteamStat,
  CAPSTONE_ACHIEVEMENTS,
  OPTIONAL_ACHIEVEMENTS,
  isCapstoneComplete,
  readUnlockedAchievements,
  recordUnlockedAchievement,
  readPacksPlayed,
  recordPackPlayed,
} from '../hooks/useSteamAchievements'

// ── Helpers ───────────────────────────────────────────────────────────────────

type InvokeFn = (cmd: string, args?: unknown) => Promise<unknown>

function stubTauriInvoke(invoke: InvokeFn) {
  const win = window as { __TAURI__?: unknown }
  win.__TAURI__ = { core: { invoke } }
}

/**
 * Stubs the bridge with a mock that answers both commands sensibly: unlocks
 * succeed, and `steam_unlocked_achievements` reports `unlockedOnSteam` (nothing
 * by default). Needed because a single `mockResolvedValue` cannot answer a
 * boolean command and a list command at the same time.
 */
function stubSteam(
  opts: { unlock?: boolean; unlockedOnSteam?: readonly string[] } = {},
) {
  const { unlock = true, unlockedOnSteam = [] } = opts
  const invoke = vi.fn((cmd: string, args?: unknown) => {
    if (cmd === 'steam_unlocked_achievements') {
      const asked = (args as { names: string[] }).names
      return Promise.resolve(asked.filter((n) => unlockedOnSteam.includes(n)))
    }
    return Promise.resolve(unlock)
  })
  stubTauriInvoke(invoke)
  return invoke
}

/** The achievement names passed to `steam_unlock_achievement`, in order. */
function unlockedNames(invoke: ReturnType<typeof vi.fn>): string[] {
  return invoke.mock.calls
    .filter(([cmd]) => cmd === 'steam_unlock_achievement')
    .map(([, args]) => (args as { name: string }).name)
}

function clearTauri() {
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
}

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  clearTauri()
  // `unlock` keeps a local ledger of confirmed unlocks in localStorage to drive
  // the capstone, and setupTests backs localStorage with one in-memory store for
  // the whole file. Clear it so a ledger left by an earlier test cannot change
  // whether the capstone fires in a later one.
  localStorage.clear()
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
    const invoke = stubSteam()

    const { result } = renderHook(() => useSteamAchievements())

    let ok: boolean = false
    await act(async () => {
      ok = await result.current.unlock(SteamAchievement.FIRST_SCENARIO)
    })

    expect(ok).toBe(true)
    expect(unlockedNames(invoke)).toEqual([SteamAchievement.FIRST_SCENARIO])
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
    const invoke = stubSteam()
    const { result } = renderHook(() => useSteamAchievements())

    const names = Object.values(SteamAchievement)
    for (const name of names) {
      // Reset the ledger between names. Unlocking every achievement in one
      // ledger would complete the capstone partway through the loop and add an
      // ACH_CERTIFIED_EXPERT call, which is covered by its own tests below.
      localStorage.clear()
      await act(async () => {
        await result.current.unlock(name)
      })
    }

    expect(unlockedNames(invoke)).toEqual([...names])
  })
})

// ── Capstone ──────────────────────────────────────────────────────────────────

describe('useSteamAchievements — capstone', () => {
  /** Seeds the ledger with every required achievement except `omit`. */
  function seedAllRequiredExcept(omit: string) {
    for (const name of CAPSTONE_ACHIEVEMENTS) {
      if (name !== omit) recordUnlockedAchievement(name)
    }
  }

  it('unlocks ACH_CERTIFIED_EXPERT once the last required achievement lands', async () => {
    const last = CAPSTONE_ACHIEVEMENTS[CAPSTONE_ACHIEVEMENTS.length - 1]
    seedAllRequiredExcept(last)

    const invoke = stubSteam()
    const { result } = renderHook(() => useSteamAchievements())

    await act(async () => {
      await result.current.unlock(last)
    })

    expect(unlockedNames(invoke)).toEqual([
      last,
      SteamAchievement.CERTIFIED_EXPERT,
    ])
    expect(readUnlockedAchievements()).toContain(
      SteamAchievement.CERTIFIED_EXPERT,
    )
    // The ledger already vouched for everything else, so there was nothing to
    // ask Steam about.
    expect(invoke).not.toHaveBeenCalledWith(
      'steam_unlocked_achievements',
      expect.anything(),
    )
  })

  it('does not unlock the capstone while a required achievement is missing', async () => {
    const last = CAPSTONE_ACHIEVEMENTS[CAPSTONE_ACHIEVEMENTS.length - 1]
    const alsoMissing = CAPSTONE_ACHIEVEMENTS[0]
    for (const name of CAPSTONE_ACHIEVEMENTS) {
      if (name !== last && name !== alsoMissing) recordUnlockedAchievement(name)
    }

    const invoke = stubSteam()
    const { result } = renderHook(() => useSteamAchievements())

    await act(async () => {
      await result.current.unlock(last)
    })

    expect(unlockedNames(invoke)).toEqual([last])
    expect(readUnlockedAchievements()).not.toContain(
      SteamAchievement.CERTIFIED_EXPERT,
    )
  })

  it('does not re-unlock the capstone once it is recorded', async () => {
    for (const name of CAPSTONE_ACHIEVEMENTS) recordUnlockedAchievement(name)
    recordUnlockedAchievement(SteamAchievement.CERTIFIED_EXPERT)

    const invoke = stubSteam()
    const { result } = renderHook(() => useSteamAchievements())

    await act(async () => {
      await result.current.unlock(SteamAchievement.DLC_LIBRARY)
    })

    expect(unlockedNames(invoke)).toEqual([SteamAchievement.DLC_LIBRARY])
  })

  it('does not recurse when the capstone itself is unlocked', async () => {
    for (const name of CAPSTONE_ACHIEVEMENTS) recordUnlockedAchievement(name)

    const invoke = stubSteam()
    const { result } = renderHook(() => useSteamAchievements())

    await act(async () => {
      await result.current.unlock(SteamAchievement.CERTIFIED_EXPERT)
    })

    expect(unlockedNames(invoke)).toEqual([SteamAchievement.CERTIFIED_EXPERT])
  })

  it('does not record an unlock Steam did not confirm', async () => {
    const invoke = stubSteam({ unlock: false })
    const { result } = renderHook(() => useSteamAchievements())

    await act(async () => {
      await result.current.unlock(SteamAchievement.FIRST_SCENARIO)
    })

    expect(invoke).toHaveBeenCalledOnce()
    expect(readUnlockedAchievements()).toEqual([])
  })

  // ── Reconciliation against the Steam account ───────────────────────────────
  //
  // The ledger is device-local, so it starts empty on a second machine, after a
  // reinstall, and after the player clears app data. Steam is the authority on
  // what the account has earned, so the capstone check must ask it rather than
  // stranding such a player at 42/43.

  it('earns the capstone from Steam when the local ledger is empty', async () => {
    const earnedElsewhere = CAPSTONE_ACHIEVEMENTS.slice(0, -1)
    const last = CAPSTONE_ACHIEVEMENTS[CAPSTONE_ACHIEVEMENTS.length - 1]
    const invoke = stubSteam({ unlockedOnSteam: earnedElsewhere })

    const { result } = renderHook(() => useSteamAchievements())
    await act(async () => {
      await result.current.unlock(last)
    })

    expect(invoke).toHaveBeenCalledWith('steam_unlocked_achievements', {
      names: [...earnedElsewhere],
    })
    expect(unlockedNames(invoke)).toEqual([
      last,
      SteamAchievement.CERTIFIED_EXPERT,
    ])
  })

  it('folds the names Steam confirms back into the ledger', async () => {
    const earnedElsewhere = CAPSTONE_ACHIEVEMENTS.slice(0, 3)
    const invoke = stubSteam({ unlockedOnSteam: earnedElsewhere })

    const { result } = renderHook(() => useSteamAchievements())
    await act(async () => {
      await result.current.unlock(SteamAchievement.BARGE_IN)
    })

    // Not enough for the capstone, but the ledger must still have learned them
    // so the next unlock does not have to ask again.
    expect(unlockedNames(invoke)).toEqual([SteamAchievement.BARGE_IN])
    for (const name of earnedElsewhere) {
      expect(readUnlockedAchievements()).toContain(name)
    }
  })

  it('does not fire the capstone when Steam confirms nothing', async () => {
    const invoke = stubSteam({ unlockedOnSteam: [] })

    const { result } = renderHook(() => useSteamAchievements())
    await act(async () => {
      await result.current.unlock(SteamAchievement.BARGE_IN)
    })

    expect(unlockedNames(invoke)).toEqual([SteamAchievement.BARGE_IN])
  })

  it('does not fire the capstone when the read-back command is unavailable', async () => {
    // An older shell without `steam_unlocked_achievements` rejects the call.
    const invoke = vi.fn((cmd: string) =>
      cmd === 'steam_unlocked_achievements'
        ? Promise.reject(new Error('command not found'))
        : Promise.resolve(true),
    )
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamAchievements())
    let ok = false
    await act(async () => {
      ok = await result.current.unlock(SteamAchievement.BARGE_IN)
    })

    expect(ok).toBe(true)
    expect(unlockedNames(invoke)).toEqual([SteamAchievement.BARGE_IN])
  })

  it('ignores a non-array answer from the read-back command', async () => {
    const invoke = vi.fn(() => Promise.resolve(true))
    stubTauriInvoke(invoke)

    const { result } = renderHook(() => useSteamAchievements())
    await act(async () => {
      await result.current.unlock(SteamAchievement.BARGE_IN)
    })

    expect(unlockedNames(invoke)).toEqual([SteamAchievement.BARGE_IN])
  })

  it('leaves the optional achievements out of the requirement', () => {
    for (const name of OPTIONAL_ACHIEVEMENTS) {
      expect(CAPSTONE_ACHIEVEMENTS).not.toContain(name)
    }
    // The capstone must not require itself, or it could never be earned.
    expect(CAPSTONE_ACHIEVEMENTS).not.toContain(
      SteamAchievement.CERTIFIED_EXPERT,
    )
  })

  it('treats the required set as complete and a short set as incomplete', () => {
    expect(isCapstoneComplete(CAPSTONE_ACHIEVEMENTS)).toBe(true)
    expect(isCapstoneComplete(CAPSTONE_ACHIEVEMENTS.slice(1))).toBe(false)
    expect(isCapstoneComplete([])).toBe(false)
  })
})

// ── Pack ledger ───────────────────────────────────────────────────────────────

describe('recordPackPlayed', () => {
  it('records distinct pack IDs and ignores repeats', () => {
    recordPackPlayed('official.workplace')
    recordPackPlayed('official.dating')
    expect(recordPackPlayed('official.workplace')).toEqual([
      'official.workplace',
      'official.dating',
    ])
    expect(readPacksPlayed()).toHaveLength(2)
  })

  it('ignores an empty pack ID without recording it', () => {
    recordPackPlayed('official.workplace')
    expect(recordPackPlayed('')).toEqual(['official.workplace'])
    expect(readPacksPlayed()).toEqual(['official.workplace'])
  })

  it('starts empty', () => {
    expect(readPacksPlayed()).toEqual([])
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

// ── Cross-source name registry ────────────────────────────────────────────────
//
// The same API names are spelled out in three places that Steam ties together:
// this hook, the Tauri `steam.rs` constants, and the Steamworks configuration
// table in docs/steam-achievements-stats-rich-presence.md (mirrored into the
// docs site). Nothing but these tests stops the three from drifting — and a
// name missing from the docs table is a name nobody creates in App Admin, so
// the unlock silently no-ops for every player.

/**
 * Walks up from the working directory to the workspace root, so the paths below
 * resolve whether vitest is started in `apps/web` or at the repo root.
 */
function findRepoRoot(): string {
  let dir = process.cwd()
  for (;;) {
    if (existsSync(join(dir, 'pnpm-workspace.yaml'))) return dir
    const parent = dirname(dir)
    if (parent === dir) throw new Error('workspace root not found above ' + process.cwd())
    dir = parent
  }
}

const REPO_ROOT = findRepoRoot()

function namesIn(relativePath: string, prefix: 'ACH_' | 'STAT_'): Set<string> {
  const text = readFileSync(join(REPO_ROOT, relativePath), 'utf8')
  return new Set(text.match(new RegExp(`\\b${prefix}[A-Z0-9_]+\\b`, 'g')) ?? [])
}

const RUST_SOURCE = 'apps/desktop/src-tauri/src/steam.rs'
const CONFIG_DOC = 'docs/steam-achievements-stats-rich-presence.md'
const DOCS_SITE_MIRROR = 'docs-site/src/content/docs/dev/steam-achievements.md'

describe('API name registry', () => {
  it('the Tauri constants cover exactly the front-end achievement names', () => {
    const rust = namesIn(RUST_SOURCE, 'ACH_')
    expect([...rust].sort()).toEqual(
      [...Object.values(SteamAchievement)].sort(),
    )
  })

  it('the Tauri constants cover exactly the front-end stat names', () => {
    const rust = namesIn(RUST_SOURCE, 'STAT_')
    expect([...rust].sort()).toEqual([...Object.values(SteamStat)].sort())
  })

  for (const doc of [CONFIG_DOC, DOCS_SITE_MIRROR]) {
    it(`${doc} documents every achievement and stat`, () => {
      const documentedAchievements = namesIn(doc, 'ACH_')
      for (const name of Object.values(SteamAchievement)) {
        expect(documentedAchievements, `${name} is undocumented`).toContain(name)
      }
      const documentedStats = namesIn(doc, 'STAT_')
      for (const name of Object.values(SteamStat)) {
        expect(documentedStats, `${name} is undocumented`).toContain(name)
      }
    })

    it(`${doc} documents no achievement or stat that does not exist`, () => {
      const achievements = new Set<string>(Object.values(SteamAchievement))
      for (const name of namesIn(doc, 'ACH_')) {
        expect(achievements, `${name} is documented but not defined`).toContain(
          name,
        )
      }
      const statNames = new Set<string>(Object.values(SteamStat))
      for (const name of namesIn(doc, 'STAT_')) {
        expect(statNames, `${name} is documented but not defined`).toContain(
          name,
        )
      }
    })
  }
})
