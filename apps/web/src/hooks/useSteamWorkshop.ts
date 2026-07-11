// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

/**
 * A Steam Workshop item the local user is subscribed to.
 *
 * Fields are populated by the Tauri bridge from synchronous UGC API calls.
 * `install_path` is empty while Steam is still downloading the item.
 */
export interface WorkshopItem {
  /** Workshop item ID as a decimal string (avoids JS precision loss on u64). */
  item_id: string
  /** Absolute path to the locally installed item content directory. */
  install_path: string
  /** Whether the local version is behind the current Workshop version. */
  needs_update: boolean
  /** Unix timestamp (seconds) of the last Workshop update. */
  updated_at: number
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Provides callbacks for Steam Workshop UGC operations.
 *
 * All callbacks degrade gracefully to no-ops in a browser context or when the
 * `steam` Cargo feature is disabled — callers do not need to guard on
 * `SteamStatus.is_steam_enabled` before calling.
 *
 * Typical subscribe-sync flow:
 *   1. Call `getSubscribedItems()` to list subscribed items with install paths.
 *   2. Pass the list to `POST /api/workshop/sync` to validate and import.
 *   3. The library auto-refreshes to show newly imported Workshop packs.
 *
 * Publish flow (Creator Workbench):
 *   1. Validate the pack (must be error-free).
 *   2. Call `publishPack(packPath)` to open the Steam overlay for consent.
 *   3. The creator reviews and submits from within the Steam overlay.
 */
export function useSteamWorkshop() {
  /**
   * Return all Workshop items the user is currently subscribed to.
   *
   * Items with an empty `install_path` are still downloading and should be
   * skipped during sync. Items with `needs_update: true` should be re-synced.
   */
  const getSubscribedItems = useCallback(async (): Promise<WorkshopItem[]> => {
    const tauri = (window as TauriWindow).__TAURI__
    if (!tauri?.core) return []
    return tauri.core
      .invoke<WorkshopItem[]>('steam_workshop_get_subscribed_items')
      .catch(() => [])
  }, [])

  /**
   * Open the Steam overlay to the Workshop submission flow for the given
   * pack directory. Returns `true` when Steam opened the overlay.
   *
   * The `packPath` must point to a directory that has already passed pack
   * validation — callers are responsible for running validation first.
   */
  const publishPack = useCallback(
    async (packPath: string): Promise<boolean> => {
      const tauri = (window as TauriWindow).__TAURI__
      if (!tauri?.core) return false
      return tauri.core
        .invoke<boolean>('steam_workshop_publish_pack', { pack_path: packPath })
        .catch(() => false)
    },
    [],
  )

  /**
   * Unsubscribe from a Workshop item by its numeric item ID string.
   *
   * Returns `true` when the unsubscribe request was submitted to Steam.
   * After calling this, invoke `DELETE /api/workshop/:pack_id` to remove the
   * pack from the local index.
   */
  const unsubscribeItem = useCallback(
    async (itemId: string): Promise<boolean> => {
      const tauri = (window as TauriWindow).__TAURI__
      if (!tauri?.core) return false
      return tauri.core
        .invoke<boolean>('steam_workshop_unsubscribe', { item_id: itemId })
        .catch(() => false)
    },
    [],
  )

  return { getSubscribedItems, publishPack, unsubscribeItem }
}
