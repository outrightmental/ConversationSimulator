// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

// ── DLC App ID registry ───────────────────────────────────────────────────────

/**
 * Parses the VITE_STEAM_DLC_APP_IDS build variable (set from the
 * STEAM_DLC_APP_IDS repository variable at build time) into a pack-id →
 * DLC App ID map.
 *
 * Format: comma-separated `pack_id:dlc_app_id` pairs, e.g.
 *   `official.premium_pack:2123456,official.other_pack:2123457`
 *
 * Returns an empty record when the variable is absent or empty, so the
 * open-source and browser builds treat every premium pack as not-owned.
 */
export function parseDlcRegistry(raw: string | undefined): Record<string, number> {
  if (!raw) return {}
  const registry: Record<string, number> = {}
  for (const entry of raw.split(',')) {
    const trimmed = entry.trim()
    if (!trimmed) continue
    const colon = trimmed.indexOf(':')
    if (colon < 1) continue
    const packId = trimmed.slice(0, colon).trim()
    const appId = parseInt(trimmed.slice(colon + 1).trim(), 10)
    if (packId && Number.isInteger(appId) && appId > 0) {
      registry[packId] = appId
    }
  }
  return registry
}

/**
 * Pack-id → DLC App ID map baked in at build time from VITE_STEAM_DLC_APP_IDS.
 *
 * Empty in open-source and browser builds (no STEAM_DLC_APP_IDS configured),
 * which means all premium packs are treated as not-owned.
 */
export const DLC_REGISTRY: Readonly<Record<string, number>> = parseDlcRegistry(
  import.meta.env.VITE_STEAM_DLC_APP_IDS as string | undefined,
)

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Provides callbacks for Steam DLC ownership checks.
 *
 * - In a browser context (no `window.__TAURI__`) all callbacks return
 *   `false` — every premium pack is treated as not-owned.
 * - In the Tauri shell, delegates to the `steam_is_dlc_installed` command,
 *   which is a no-op when Steam is absent or the `steam` Cargo feature is
 *   disabled.
 *
 * Usage — check whether a premium pack is owned:
 *   const { isDlcInstalled, isDlcInstalledForPack } = useSteamDlc()
 *   const owned = await isDlcInstalledForPack('official.premium_pack')
 */
export function useSteamDlc() {
  /**
   * Returns `true` when the DLC with the given Steam App ID is installed
   * (owned and downloaded) for the current user.
   *
   * Returns `false` in any non-Tauri context, when Steam is unavailable, or
   * when the `steam` Cargo feature is disabled.
   */
  const isDlcInstalled = useCallback(
    async (dlcAppId: number): Promise<boolean> => {
      const tauri = (window as TauriWindow).__TAURI__
      if (!tauri?.core) return false
      return tauri.core
        .invoke<boolean>('steam_is_dlc_installed', { dlc_app_id: dlcAppId })
        .catch(() => false)
    },
    [],
  )

  /**
   * Looks up the DLC App ID for `packId` in the build-time registry and
   * checks DLC ownership.
   *
   * Returns `false` when the pack has no DLC App ID registered (free pack,
   * or this build was compiled without `STEAM_DLC_APP_IDS`).
   */
  const isDlcInstalledForPack = useCallback(
    async (packId: string): Promise<boolean> => {
      const appId = DLC_REGISTRY[packId]
      if (appId === undefined) return false
      return isDlcInstalled(appId)
    },
    [isDlcInstalled],
  )

  return { isDlcInstalled, isDlcInstalledForPack }
}
