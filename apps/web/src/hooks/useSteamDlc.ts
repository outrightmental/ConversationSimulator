// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Ownership gate for premium Steam DLC packs.
 *
 * Calls the `steam_is_dlc_installed` Tauri command, which uses the Steamworks
 * SDK to confirm that the local Steam user owns and has installed the DLC with
 * the given App ID.
 *
 * Degrades gracefully to `false` in a browser context or when the `steam`
 * Cargo feature is disabled — callers do not need to guard on
 * `SteamStatus.is_steam_enabled` before calling.
 *
 * Usage:
 *   const { isDlcInstalled } = useSteamDlc()
 *   const owned = await isDlcInstalled(1234567)
 *
 * A pack whose `manifest.yaml` carries a non-zero `dlc_app_id` should be
 * passed through this check before allowing a scenario launch. Packs without
 * `dlc_app_id` are always playable and do not need this check.
 *
 * See docs/DLC_MODEL.md for the full ownership-gate contract.
 */
export function useSteamDlc() {
  /**
   * Return `true` when the local Steam user owns and has installed the DLC
   * identified by `dlcAppId`. Returns `false` when Steam is unavailable,
   * the user does not own the DLC, or the DLC is not yet installed.
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

  return { isDlcInstalled }
}
