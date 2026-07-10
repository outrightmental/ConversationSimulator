// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

// ── Activity token constants ──────────────────────────────────────────────────

/**
 * Generic activity tokens for Steam rich presence.
 *
 * These tokens are looked up in the Steamworks rich presence localization file
 * and rendered as human-readable strings in the Steam friends list. They reveal
 * only the category of activity — never session details, scenario names,
 * transcript excerpts, or NPC identifiers.
 */
export const SteamActivity = {
  IN_SCENARIO: '#InScenario',
  REVIEWING_DEBRIEF: '#ReviewingDebrief',
  EDITING_PACK: '#EditingPack',
  AT_MAIN_MENU: '#AtMainMenu',
} as const

export type SteamActivityValue = (typeof SteamActivity)[keyof typeof SteamActivity]

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns a `setPresence` callback that updates the player's Steam rich
 * presence to a generic activity token.
 *
 * - In a browser context (no `window.__TAURI__`) returns `false` immediately
 *   without throwing.
 * - In the Tauri shell, delegates to the `steam_set_rich_presence` command,
 *   which is a no-op when Steam is absent or the `steam` Cargo feature is off.
 *
 * Call this when the player navigates to a new major screen. Do NOT include
 * session-specific content (scenario title, NPC name, turn count, etc.).
 */
export function useSteamRichPresence() {
  const setPresence = useCallback(
    async (activity: SteamActivityValue): Promise<boolean> => {
      const tauri = (window as TauriWindow).__TAURI__
      if (!tauri?.core) return false
      return tauri.core
        .invoke<boolean>('steam_set_rich_presence', { value: activity })
        .catch(() => false)
    },
    [],
  )

  return { setPresence }
}
