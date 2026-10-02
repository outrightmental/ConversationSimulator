// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TauriWindow = {
  __TAURI__?: { core?: { invoke<T>(cmd: string, args?: unknown): Promise<T> } }
}

// ── API name constants ────────────────────────────────────────────────────────

/**
 * Achievement API names matching the Steamworks App Admin configuration.
 *
 * The set is deliberately a guided tour of the whole product (issue #494): a
 * player holding all of them has exercised onboarding, both input modes, the
 * debrief/logbook loop, the library and pack tooling, every privacy control,
 * and the creator workbench. `docs/steam-achievements-stats-rich-presence.md`
 * is the authoritative table (display name, condition, hidden flag) and must be
 * updated alongside this object.
 *
 * API names are a shipped contract: Steam keys a player's unlocked achievements
 * by API name, so renaming one silently discards their progress. Add new names;
 * never rename or reuse an existing one. The five marked "v1" shipped first
 * (#230) and are frozen.
 */
export const SteamAchievement = {
  // ── Onboarding, models, runtime, and support ───────────────────────────────
  SETUP_COMPLETE: 'ACH_SETUP_COMPLETE',
  BYO_MODEL: 'ACH_BYO_MODEL',
  BENCHMARKED: 'ACH_BENCHMARKED',
  RUNTIME_TUNED: 'ACH_RUNTIME_TUNED',
  SELF_TEST: 'ACH_SELF_TEST',
  DIAGNOSTICS: 'ACH_DIAGNOSTICS',

  // ── Conversation: text, voice, and the mic pipeline ────────────────────────
  FIRST_SCENARIO: 'ACH_FIRST_SCENARIO', // v1
  TEXT_TURN: 'ACH_TEXT_TURN',
  VOICE_TURN: 'ACH_VOICE_TURN',
  HANDS_FREE: 'ACH_HANDS_FREE',
  VAD_CALIBRATED: 'ACH_VAD_CALIBRATED',
  BARGE_IN: 'ACH_BARGE_IN',
  TRANSCRIPT_EDITED: 'ACH_TRANSCRIPT_EDITED',
  DEEP_CONVERSATION: 'ACH_DEEP_CONVERSATION',
  VOICE_TUNED: 'ACH_VOICE_TUNED',

  // ── Debrief, transcripts, logbook, and relationship memory ────────────────
  FIRST_DEBRIEF: 'ACH_FIRST_DEBRIEF', // v1
  TURNING_POINT: 'ACH_TURNING_POINT',
  TRANSCRIPT_EXPORT: 'ACH_TRANSCRIPT_EXPORT',
  REPLAY_VARIATION: 'ACH_REPLAY_VARIATION',
  PRACTICE_STREAK: 'ACH_PRACTICE_STREAK', // v1
  TEN_SCENARIOS: 'ACH_TEN_SCENARIOS',
  PERSONAL_BEST: 'ACH_PERSONAL_BEST',
  LOGBOOK_EXPORT: 'ACH_LOGBOOK_EXPORT',
  RELATIONSHIP_MEMORY: 'ACH_RELATIONSHIP_MEMORY',

  // ── Scenario library and pack management ──────────────────────────────────
  PACK_EXPLORER: 'ACH_PACK_EXPLORER', // v1
  PACK_CONNOISSEUR: 'ACH_PACK_CONNOISSEUR',
  LIBRARY_CURATOR: 'ACH_LIBRARY_CURATOR',
  PACK_IMPORTED: 'ACH_PACK_IMPORTED',
  PACKS_RESTORED: 'ACH_PACKS_RESTORED',

  // ── Privacy controls and personalisation ──────────────────────────────────
  PRIVACY_TUNED: 'ACH_PRIVACY_TUNED',
  MEMORY_FORGOTTEN: 'ACH_MEMORY_FORGOTTEN',
  POLYGLOT: 'ACH_POLYGLOT',
  DEV_MODE: 'ACH_DEV_MODE',

  // ── Creator workbench ─────────────────────────────────────────────────────
  CREATOR_FIRST_VALIDATE: 'ACH_CREATOR_FIRST_VALIDATE', // v1
  CREATOR_FORK: 'ACH_CREATOR_FORK',
  CREATOR_SAVE: 'ACH_CREATOR_SAVE',
  CREATOR_TEST: 'ACH_CREATOR_TEST',
  CREATOR_EXPORT: 'ACH_CREATOR_EXPORT',

  // ── Steam platform surfaces (optional content / optional hardware) ────────
  WORKSHOP_SUBSCRIBER: 'ACH_WORKSHOP_SUBSCRIBER',
  WORKSHOP_PUBLISHER: 'ACH_WORKSHOP_PUBLISHER',
  DLC_LIBRARY: 'ACH_DLC_LIBRARY',
  BIG_PICTURE: 'ACH_BIG_PICTURE',

  // ── Capstone ──────────────────────────────────────────────────────────────
  CERTIFIED_EXPERT: 'ACH_CERTIFIED_EXPERT',
} as const

/** Stat API names matching the Steamworks App Admin configuration. */
export const SteamStat = {
  SCENARIOS_COMPLETED: 'STAT_SCENARIOS_COMPLETED',
  DEBRIEFS_GENERATED: 'STAT_DEBRIEFS_GENERATED',
  PACKS_VALIDATED: 'STAT_PACKS_VALIDATED',
  TEXT_MODE_SESSIONS: 'STAT_TEXT_MODE_SESSIONS',
  VOICE_MODE_SESSIONS: 'STAT_VOICE_MODE_SESSIONS',
  VOICE_TURNS: 'STAT_VOICE_TURNS',
  PACKS_IMPORTED: 'STAT_PACKS_IMPORTED',
  PACKS_EXPORTED: 'STAT_PACKS_EXPORTED',
  TRANSCRIPTS_EXPORTED: 'STAT_TRANSCRIPTS_EXPORTED',
} as const

export type SteamAchievementName =
  (typeof SteamAchievement)[keyof typeof SteamAchievement]
export type SteamStatName = (typeof SteamStat)[keyof typeof SteamStat]

// ── Unlock thresholds ─────────────────────────────────────────────────────────
//
// Centralised so the unlock sites and the documented conditions cannot drift.

/** Distinct packs played for `ACH_PACK_EXPLORER`. */
export const PACK_EXPLORER_PACKS = 3
/**
 * Distinct packs played for `ACH_PACK_CONNOISSEUR`. The base game ships five
 * `official.*` packs plus the tutorial pack, so this is reachable without any
 * DLC, Workshop subscription, or imported pack.
 */
export const PACK_CONNOISSEUR_PACKS = 5
/** Consecutive practice days for `ACH_PRACTICE_STREAK`. */
export const PRACTICE_STREAK_DAYS = 3
/** Completed scenarios for `ACH_TEN_SCENARIOS`. */
export const SEASONED_SCENARIOS = 10
/**
 * Player turns within one session for `ACH_DEEP_CONVERSATION`. Scenario
 * `max_turns` counts player turns, and most shipped scenarios allow 14–20, so
 * this is reachable in nearly every one. Two shipped scenarios are shorter by
 * design (`first_words_tutorial` at 8, `graceful_exit` at 10) and cannot grant
 * it — raising the threshold above 12 would start excluding the 14-turn
 * scenarios too.
 */
export const DEEP_CONVERSATION_TURNS = 12

// ── Capstone composition ──────────────────────────────────────────────────────

/**
 * Achievements deliberately left out of the `ACH_CERTIFIED_EXPERT` requirement
 * because they depend on content or hardware a player may legitimately not
 * have. Excluding them keeps the capstone — and therefore "every feature of the
 * base game" — reachable for every player.
 */
export const OPTIONAL_ACHIEVEMENTS: readonly SteamAchievementName[] = [
  SteamAchievement.BYO_MODEL, // needs an Ollama install or a .gguf on disk
  SteamAchievement.BENCHMARKED, // only reachable through those advanced paths
  SteamAchievement.WORKSHOP_SUBSCRIBER, // needs a Workshop subscription
  SteamAchievement.WORKSHOP_PUBLISHER, // needs a Workshop upload
  SteamAchievement.DLC_LIBRARY, // needs a DLC purchase
  SteamAchievement.BIG_PICTURE, // needs a game controller
]

/**
 * Every achievement the capstone requires: all of them except the optional-
 * content ones above and the capstone itself. A microphone IS required — voice
 * practice is the product, and the store page lists a mic as the requirement
 * for voice mode.
 *
 * Adding a new achievement adds it to this list by default, which is the safe
 * direction: a genuinely optional one must be declared in
 * `OPTIONAL_ACHIEVEMENTS` to be excluded.
 */
export const CAPSTONE_ACHIEVEMENTS: readonly SteamAchievementName[] =
  Object.values(SteamAchievement).filter(
    (name) =>
      name !== SteamAchievement.CERTIFIED_EXPERT &&
      !OPTIONAL_ACHIEVEMENTS.includes(name),
  )

// ── Local progress ledger ─────────────────────────────────────────────────────
//
// Steamworks exposes no read-back command in this bridge, so the capstone needs
// a local record of what has already been unlocked. Only achievement API names
// and pack IDs are stored, on this device only — never transcript text, session
// IDs, or anything else about a conversation. Nothing here is sent anywhere;
// Steam only ever receives the unlock calls it would have received anyway.

export const STEAM_PROGRESS_KEYS = {
  /** JSON array of achievement API names Steam has confirmed unlocked. */
  unlocked: 'convsim.steam.unlocked',
  /** JSON array of pack IDs the player has completed a scenario from. */
  packsPlayed: 'convsim.steam.packsPlayed',
} as const

function readStringArray(key: string): string[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((v): v is string => typeof v === 'string')
  } catch {
    return []
  }
}

function appendUnique(key: string, value: string): string[] {
  const current = readStringArray(key)
  if (current.includes(value)) return current
  const next = [...current, value]
  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(key, JSON.stringify(next))
    } catch {
      /* quota or private-mode failures must never break a conversation */
    }
  }
  return next
}

/** Achievement API names this device has seen Steam confirm. */
export function readUnlockedAchievements(): string[] {
  return readStringArray(STEAM_PROGRESS_KEYS.unlocked)
}

/** Records a confirmed unlock and returns the full ledger. */
export function recordUnlockedAchievement(name: string): string[] {
  return appendUnique(STEAM_PROGRESS_KEYS.unlocked, name)
}

/** Pack IDs the player has completed a scenario from. */
export function readPacksPlayed(): string[] {
  return readStringArray(STEAM_PROGRESS_KEYS.packsPlayed)
}

/**
 * Records that a scenario from `packId` was completed and returns the full set
 * of distinct packs played. Drives `ACH_PACK_EXPLORER` and
 * `ACH_PACK_CONNOISSEUR` without a server round-trip, so it keeps working when
 * transcript saving is disabled and sessions are never persisted — at the cost
 * of starting empty, so packs played before this release do not count toward
 * either threshold.
 */
export function recordPackPlayed(packId: string): string[] {
  if (!packId) return readPacksPlayed()
  return appendUnique(STEAM_PROGRESS_KEYS.packsPlayed, packId)
}

/** True when every capstone-required achievement is present in `unlocked`. */
export function isCapstoneComplete(unlocked: readonly string[]): boolean {
  const have = new Set(unlocked)
  return CAPSTONE_ACHIEVEMENTS.every((name) => have.has(name))
}

// ── Hook ──────────────────────────────────────────────────────────────────────

function invokeSteam(cmd: string, name: string): Promise<boolean> {
  const tauri = (window as TauriWindow).__TAURI__
  if (!tauri?.core) return Promise.resolve(false)
  return tauri.core.invoke<boolean>(cmd, { name }).catch(() => false)
}

/**
 * Returns callbacks for unlocking Steam achievements and incrementing stats.
 *
 * - In a browser context (no `window.__TAURI__`) both callbacks return
 *   `false` immediately without throwing.
 * - In the Tauri shell, delegates to the `steam_unlock_achievement` and
 *   `steam_increment_stat` commands, which are no-ops when Steam is absent
 *   or the `steam` Cargo feature is disabled.
 *
 * Unlocking is idempotent, so call sites are free to re-check a condition on
 * every visit to a screen. That is what makes the set retroactive wherever the
 * condition is derived from durable state the app already keeps: a player who
 * already has a practice streak, ten sessions, a personal record, a relationship
 * recap, a subscribed Workshop pack, or a completed setup earns those
 * achievements the next time they open the relevant screen. Conditions that can
 * only be observed as they happen — a spoken turn, a barge-in, an export, and
 * the pack tally in `recordPackPlayed` below, whose ledger starts empty — count
 * from this release forward only. Stats are NOT idempotent and must only be
 * incremented at the moment the counted event happens.
 */
export function useSteamAchievements() {
  const unlock = useCallback(
    async (achievementName: SteamAchievementName): Promise<boolean> => {
      const ok = await invokeSteam('steam_unlock_achievement', achievementName)
      if (!ok) return false

      // Steam confirmed it, so fold it into the local ledger and check whether
      // that completed the capstone. Guarded against recursing on the capstone
      // itself, and skipped once the capstone is already recorded.
      if (achievementName === SteamAchievement.CERTIFIED_EXPERT) {
        recordUnlockedAchievement(achievementName)
        return true
      }
      const unlocked = recordUnlockedAchievement(achievementName)
      if (
        !unlocked.includes(SteamAchievement.CERTIFIED_EXPERT) &&
        isCapstoneComplete(unlocked)
      ) {
        const capstoneOk = await invokeSteam(
          'steam_unlock_achievement',
          SteamAchievement.CERTIFIED_EXPERT,
        )
        if (capstoneOk) {
          recordUnlockedAchievement(SteamAchievement.CERTIFIED_EXPERT)
        }
      }
      return true
    },
    [],
  )

  const incrementStat = useCallback(
    async (statName: SteamStatName): Promise<boolean> =>
      invokeSteam('steam_increment_stat', statName),
    [],
  )

  return { unlock, incrementStat }
}
