// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriInvoke = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> } }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Reports whether a premium scenario-pack DLC is owned and installed, by its
 * Steam **DLC App ID**.
 *
 * Premium expansion packs ship as Steam DLC (see `docs/DLC_MODEL.md`). Ownership
 * is the only gate — the same open-source binary ships to everyone, and unowned
 * premium packs are surfaced as available-to-buy rather than hidden.
 *
 * - In a browser context (no `window.__TAURI__`) always resolves to `false`, so
 *   the open-source/browser build treats every premium pack as not-owned.
 * - In the Tauri shell, queries the `steam_is_dlc_installed` command. Returns
 *   `false` when the `steam` feature is off, Steam is not running, or the player
 *   does not own the DLC.
 *
 * @param dlcAppId Steam DLC App ID, or `null`/`undefined` to skip the check.
 * @returns `true` only when the DLC is confirmed owned and installed.
 */
export function useSteamDlcOwned(dlcAppId: number | null | undefined): boolean {
  const [owned, setOwned] = useState(false)

  useEffect(() => {
    let cancelled = false
    setOwned(false)
    if (dlcAppId == null) return

    const tauri = (window as TauriInvoke).__TAURI__
    if (!tauri?.core) return

    tauri.core
      .invoke<boolean>('steam_is_dlc_installed', { dlcAppId })
      .then((result) => {
        if (!cancelled) setOwned(result === true)
      })
      .catch(() => {
        if (!cancelled) setOwned(false)
      })

    return () => {
      cancelled = true
    }
  }, [dlcAppId])

  return owned
}

/**
 * Imperative variant: returns a function that checks DLC ownership on demand.
 * Resolves to `false` outside the Tauri/Steam context.
 */
export function useSteamDlc(): { isDlcOwned: (dlcAppId: number) => Promise<boolean> } {
  const isDlcOwned = useCallback(async (dlcAppId: number): Promise<boolean> => {
    const tauri = (window as TauriInvoke).__TAURI__
    if (!tauri?.core) return false
    try {
      return (await tauri.core.invoke<boolean>('steam_is_dlc_installed', { dlcAppId })) === true
    } catch {
      return false
    }
  }, [])

  return { isDlcOwned }
}
