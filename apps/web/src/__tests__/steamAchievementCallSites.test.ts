// SPDX-License-Identifier: Apache-2.0
//
// Guards the half of the achievement contract that the name-registry tests in
// useSteamAchievements.test.ts cannot see: a name can be defined in the hook,
// mirrored into steam.rs, and written up in the Steamworks configuration table
// while nothing in the app ever unlocks it. Steam would then show the player an
// achievement that is impossible to earn — and because the capstone requires
// every non-optional name, one unwired achievement makes ACH_CERTIFIED_EXPERT
// unreachable for everyone. Adding an achievement without a call site fails
// here (issue #494: "every new achievement has an unlock call site").
import { describe, it, expect } from 'vitest'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import {
  SteamAchievement,
  SteamStat,
} from '../hooks/useSteamAchievements'

/**
 * Walks up from the working directory to the workspace root, so the paths below
 * resolve whether vitest is started in `apps/web` or at the repo root.
 * `import.meta.url` is not a file URL under the jsdom environment, so it cannot
 * stand in for this.
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

const SRC_ROOT = join(findRepoRoot(), 'apps', 'web', 'src')
const HOOK_RELATIVE = join('hooks', 'useSteamAchievements.ts')

/** Every .ts/.tsx file under src, minus test files and the hook itself. */
function appSources(): string[] {
  const out: string[] = []
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry)
      if (statSync(full).isDirectory()) {
        if (entry === '__tests__') continue
        walk(full)
        continue
      }
      if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue
      if (full.endsWith(HOOK_RELATIVE)) continue
      out.push(full)
    }
  }
  walk(SRC_ROOT)
  return out
}

/** Constant member expressions (`SteamAchievement.FOO`) used across the app. */
function referencedKeys(object: 'SteamAchievement' | 'SteamStat'): Set<string> {
  const pattern = new RegExp(`\\b${object}\\.([A-Z0-9_]+)\\b`, 'g')
  const keys = new Set<string>()
  for (const file of appSources()) {
    for (const m of readFileSync(file, 'utf8').matchAll(pattern)) {
      keys.add(m[1])
    }
  }
  return keys
}

describe('Steam achievement call sites', () => {
  it('every achievement except the capstone is unlocked somewhere in the app', () => {
    const referenced = referencedKeys('SteamAchievement')
    for (const key of Object.keys(SteamAchievement)) {
      // The capstone is fired by the hook itself once the others land, so it
      // has no screen-level call site by design.
      if (key === 'CERTIFIED_EXPERT') continue
      expect(
        referenced,
        `SteamAchievement.${key} is defined but never unlocked in apps/web/src`,
      ).toContain(key)
    }
  })

  it('the capstone is unlocked by the hook', () => {
    const hook = readFileSync(join(SRC_ROOT, HOOK_RELATIVE), 'utf8')
    expect(hook).toContain('CERTIFIED_EXPERT')
  })

  it('every stat is incremented somewhere in the app', () => {
    const referenced = referencedKeys('SteamStat')
    for (const key of Object.keys(SteamStat)) {
      expect(
        referenced,
        `SteamStat.${key} is defined but never incremented in apps/web/src`,
      ).toContain(key)
    }
  })
})
