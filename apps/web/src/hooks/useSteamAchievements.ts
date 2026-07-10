// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

// ── API name constants ────────────────────────────────────────────────────────

/** Achievement API names matching the Steamworks App Admin configuration. */
export const SteamAchievement = {
  FIRST_SCENARIO: 'ACH_FIRST_SCENARIO',
  FIRST_DEBRIEF: 'ACH_FIRST_DEBRIEF',
  PRACTICE_STREAK: 'ACH_PRACTICE_STREAK',
  PACK_EXPLORER: 'ACH_PACK_EXPLORER',
  CREATOR_FIRST_VALIDATE: 'ACH_CREATOR_FIRST_VALIDATE',
} as const

/** Stat API names matching the Steamworks App Admin configuration. */
export const SteamStat = {
  SCENARIOS_COMPLETED: 'STAT_SCENARIOS_COMPLETED',
  DEBRIEFS_GENERATED: 'STAT_DEBRIEFS_GENERATED',
  PACKS_VALIDATED: 'STAT_PACKS_VALIDATED',
  TEXT_MODE_SESSIONS: 'STAT_TEXT_MODE_SESSIONS',
  VOICE_MODE_SESSIONS: 'STAT_VOICE_MODE_SESSIONS',
} as const

export type SteamAchievementName =
  (typeof SteamAchievement)[keyof typeof SteamAchievement]
export type SteamStatName = (typeof SteamStat)[keyof typeof SteamStat]

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns callbacks for unlocking Steam achievements and incrementing stats.
 *
 * - In a browser context (no `window.__TAURI__`) both callbacks return
 *   `false` immediately without throwing.
 * - In the Tauri shell, delegates to the `steam_unlock_achievement` and
 *   `steam_increment_stat` commands, which are no-ops when Steam is absent
 *   or the `steam` Cargo feature is disabled.
 */
export function useSteamAchievements() {
  const unlock = useCallback(
    async (achievementName: SteamAchievementName): Promise<boolean> => {
      const tauri = (window as TauriWindow).__TAURI__
      if (!tauri?.core) return false
      return tauri.core
        .invoke<boolean>('steam_unlock_achievement', { name: achievementName })
        .catch(() => false)
    },
    [],
  )

  const incrementStat = useCallback(
    async (statName: SteamStatName): Promise<boolean> => {
      const tauri = (window as TauriWindow).__TAURI__
      if (!tauri?.core) return false
      return tauri.core
        .invoke<boolean>('steam_increment_stat', { name: statName })
        .catch(() => false)
    },
    [],
  )

  return { unlock, incrementStat }
}
