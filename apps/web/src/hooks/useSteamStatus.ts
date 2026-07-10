// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SteamStatus {
  /** True only when the Steamworks SDK was successfully initialized. */
  is_steam_enabled: boolean
  /** True when the process was launched by the Steam client. */
  launched_by_steam: boolean
  /** Steam AppID if available from the SDK or environment. */
  app_id: number | null
  /** Display name of the current Steam user, or null outside Steam. */
  persona_name: string | null
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns the Steam integration status reported by the Tauri desktop shell.
 *
 * - In a browser context (no `window.__TAURI__`) returns `null` immediately.
 * - In the Tauri shell, queries the `get_steam_status` command once on mount.
 *   The returned status reflects whether the `steam` Cargo feature is enabled
 *   and whether Steam was running at app launch.
 */
export function useSteamStatus(): SteamStatus | null {
  const [status, setStatus] = useState<SteamStatus | null>(null)

  useEffect(() => {
    const tauri = (
      window as { __TAURI__?: { core?: { invoke<T>(cmd: string): Promise<T> } } }
    ).__TAURI__
    if (!tauri?.core) return

    tauri.core
      .invoke<SteamStatus>('get_steam_status')
      .then(setStatus)
      .catch(() => {})
  }, [])

  return status
}
