// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

/**
 * A premium DLC pack known to the app. Each entry maps a `pack_id` (as served
 * by `/api/scenarios`) to the Steam DLC that unlocks it.
 *
 * Content is installed by Steam at `dlc/<steam_dlc_app_id>/` relative to the
 * DLC install root. The backend discovers scenarios at this path automatically
 * once the DLC is purchased and installed.
 *
 * See `docs/DLC_MODEL.md` for the full ownership model.
 */
export interface DlcEntry {
  /** Stable pack identifier matching the pack manifest (`pack_id` field). */
  pack_id: string
  /** Display name shown in the Scenario Library. */
  name: string
  /** Short description shown on the "Available on Steam" card. */
  description: string
  /** Steam AppID of this DLC (distinct from the base-game AppID). */
  steam_dlc_app_id: number
  /** Steam store page URL used as a browser fallback outside of Steam. */
  store_url: string
}

// ── DLC catalog ───────────────────────────────────────────────────────────────

/**
 * Authoritative list of premium DLC packs.
 *
 * Ownership is checked via `steam_is_dlc_installed` for each entry. Packs
 * not present in the installed scenarios list (unowned or not yet installed)
 * are shown as "Available on Steam" cards in the Scenario Library.
 *
 * Steam DLC AppIDs are pending registration in the Steamworks partner portal;
 * placeholder IDs (3000001+) are used until registration is complete.
 */
export const DLC_CATALOG: DlcEntry[] = [
  {
    pack_id: 'premium.dating_confidence',
    name: 'Dating Confidence',
    description:
      'Practice asking someone out, navigating first-date conversation, and setting respectful boundaries in romantic social contexts.',
    steam_dlc_app_id: 3000001,
    store_url: 'https://store.steampowered.com/app/3000001/',
  },
  {
    pack_id: 'premium.public_speaking',
    name: 'Public Speaking',
    description:
      'Build confidence for presentations, pitches, and keynote talks — from small team stand-ups to auditorium-scale speeches.',
    steam_dlc_app_id: 3000002,
    store_url: 'https://store.steampowered.com/app/3000002/',
  },
]

// ── useSteamDlcOwned ─────────────────────────────────────────────────────────

/**
 * Check ownership of a single Steam DLC by its AppID.
 *
 * - Returns `null` while the asynchronous check is in progress.
 * - Returns `true` when the DLC is owned and installed (`BIsDlcInstalled`).
 * - Returns `false` in a non-Tauri context or when the DLC is not owned.
 *
 * Callers should treat `false` as "available to buy" rather than hiding the
 * pack — per the DLC model, premium packs are never hidden.
 */
export function useSteamDlcOwned(steamDlcAppId: number): boolean | null {
  const [owned, setOwned] = useState<boolean | null>(null)

  useEffect(() => {
    const tauri = (window as TauriWindow).__TAURI__
    if (!tauri?.core) {
      setOwned(false)
      return
    }
    tauri.core
      .invoke<boolean>('steam_is_dlc_installed', { app_id: steamDlcAppId })
      .then(setOwned)
      .catch(() => setOwned(false))
  }, [steamDlcAppId])

  return owned
}

// ── useSteamDlc ──────────────────────────────────────────────────────────────

/**
 * Returns DLC ownership state for all entries in `DLC_CATALOG`.
 *
 * `ownedPackIds` is a `Set<string>` of `pack_id` values the current Steam
 * user owns. `isLoaded` is `false` until all ownership checks have resolved.
 *
 * In a non-Tauri context (browser / non-Steam build), resolves immediately
 * with an empty `ownedPackIds` and `isLoaded: true`. Callers should treat
 * installed packs as playable when Steam is unavailable — the check returning
 * empty does not mean "unowned", it means "cannot verify".
 */
export function useSteamDlc(): { ownedPackIds: Set<string>; isLoaded: boolean } {
  const [ownedPackIds, setOwnedPackIds] = useState<Set<string>>(new Set())
  const [isLoaded, setIsLoaded] = useState(false)

  useEffect(() => {
    const tauri = (window as TauriWindow).__TAURI__
    if (!tauri?.core || DLC_CATALOG.length === 0) {
      setIsLoaded(true)
      return
    }

    let cancelled = false

    const checks = DLC_CATALOG.map((entry) =>
      tauri.core!
        .invoke<boolean>('steam_is_dlc_installed', { app_id: entry.steam_dlc_app_id })
        .then((owned): string | null => (owned ? entry.pack_id : null))
        .catch((): null => null),
    )

    void Promise.all(checks).then((results) => {
      if (cancelled) return
      const owned = new Set(results.filter((id): id is string => id !== null))
      setOwnedPackIds(owned)
      setIsLoaded(true)
    })

    return () => {
      cancelled = true
    }
  }, [])

  return { ownedPackIds, isLoaded }
}

// ── useSteamDlcStore ─────────────────────────────────────────────────────────

/**
 * Returns a callback that opens the Steam store page for a DLC entry.
 *
 * Under Steam (Tauri + `steam_open_dlc_store_overlay`), the store page opens
 * inside the Steam overlay without leaving the app. When Steam is unavailable
 * or the overlay fails, the store URL opens in the system browser instead.
 */
export function useSteamDlcStore() {
  const openStorePage = useCallback(async (entry: DlcEntry): Promise<void> => {
    const tauri = (window as TauriWindow).__TAURI__
    if (tauri?.core) {
      const opened = await tauri.core
        .invoke<boolean>('steam_open_dlc_store_overlay', { app_id: entry.steam_dlc_app_id })
        .catch(() => false)
      if (opened) return
    }
    window.open(entry.store_url, '_blank', 'noopener,noreferrer')
  }, [])

  return { openStorePage }
}
