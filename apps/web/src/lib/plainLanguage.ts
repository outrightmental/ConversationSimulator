// SPDX-License-Identifier: Apache-2.0
/**
 * The buffer between player-facing and technical language (issue #501 §2).
 *
 * Playtest feedback: the app "feels both too sparse and too technical in the
 * first few sessions", and named the words that landed badly — "runtime",
 * "event", "state", "flag". The ask was a customizable buffer, chosen by an
 * initial question about how familiar the player is with AI language models.
 *
 * There are two levels, not a scale. A third intermediate level would have to
 * pick a different word for every string without a rule saying which words
 * belong to it, which is how copy drifts; two levels have a clear rule:
 *
 *   plain      — the default. No identifiers, no engine vocabulary, no raw
 *                state names. Everything on screen is a sentence a player can
 *                read without knowing how the app is built.
 *   technical  — adds the identifiers back: session ids, flow-state names,
 *                event flags, raw variable keys. Chosen by players who work
 *                with language models, and by anyone who goes looking for it
 *                in Settings.
 *
 * `plain` is the default for a never-asked player: being under-informed about
 * internals is recoverable (Settings is one click away), being confronted with
 * `PlayerTurnListening` on your first session is what this issue is about.
 */

export type UiLanguageLevel = 'plain' | 'technical'

/** The three answers the familiarity question offers, in order. */
export type LlmFamiliarity = 'new' | 'some' | 'expert'

export const UI_LANGUAGE_KEYS = {
  /** The active level. Absent means "never chosen" → `plain`. */
  level: 'convsim.ui.languageLevel',
  /** The answer that produced the level, kept so the re-ask can preselect it. */
  familiarity: 'convsim.ui.llmFamiliarity',
  /** Set once the post-tutorial re-ask has been shown, so it appears once. */
  reaskShown: 'convsim.ui.llmFamiliarityReasked',
} as const

export const DEFAULT_UI_LANGUAGE_LEVEL: UiLanguageLevel = 'plain'

/** Only the player who says they work with language models gets the identifiers. */
export function levelForFamiliarity(answer: LlmFamiliarity): UiLanguageLevel {
  return answer === 'expert' ? 'technical' : 'plain'
}

export function readUiLanguageLevel(): UiLanguageLevel {
  if (typeof localStorage === 'undefined') return DEFAULT_UI_LANGUAGE_LEVEL
  try {
    return localStorage.getItem(UI_LANGUAGE_KEYS.level) === 'technical'
      ? 'technical'
      : DEFAULT_UI_LANGUAGE_LEVEL
  } catch {
    return DEFAULT_UI_LANGUAGE_LEVEL
  }
}

export function writeUiLanguageLevel(level: UiLanguageLevel): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(UI_LANGUAGE_KEYS.level, level)
    // Screens read the level at render, so a change made in Settings has to
    // reach a Conversation mounted in the same session. `storage` only fires in
    // *other* documents, so dispatch our own event for this one.
    window.dispatchEvent(new Event(UI_LANGUAGE_CHANGE_EVENT))
  } catch {
    /* ignore storage errors */
  }
}

export const UI_LANGUAGE_CHANGE_EVENT = 'convsim:ui-language-level'

export function readLlmFamiliarity(): LlmFamiliarity | null {
  if (typeof localStorage === 'undefined') return null
  try {
    const v = localStorage.getItem(UI_LANGUAGE_KEYS.familiarity)
    return v === 'new' || v === 'some' || v === 'expert' ? v : null
  } catch {
    return null
  }
}

/** Record a familiarity answer and apply the level it implies. */
export function writeLlmFamiliarity(answer: LlmFamiliarity): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(UI_LANGUAGE_KEYS.familiarity, answer)
  } catch {
    /* ignore storage errors */
  }
  writeUiLanguageLevel(levelForFamiliarity(answer))
}

export function hasSeenFamiliarityReask(): boolean {
  if (typeof localStorage === 'undefined') return false
  try {
    return localStorage.getItem(UI_LANGUAGE_KEYS.reaskShown) === 'true'
  } catch {
    return false
  }
}

export function markFamiliarityReaskShown(): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(UI_LANGUAGE_KEYS.reaskShown, 'true')
  } catch {
    /* ignore storage errors */
  }
}

// ── Humanizers ───────────────────────────────────────────────────────────────

/**
 * "objective_progress" → "Objective progress".
 *
 * Scenario packs name their state variables in snake_case because they are
 * keys in a YAML file; the player never agreed to read keys.
 */
export function humanizeIdentifier(raw: string): string {
  const words = raw.replace(/[_-]+/g, ' ').trim()
  if (words.length === 0) return raw
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** "player_demonstrates_knowledge" → "Player demonstrates knowledge". */
export const humanizeFlag = humanizeIdentifier

/** Join several flags into one readable phrase. */
export function humanizeFlags(flags: readonly string[]): string {
  return flags.map(humanizeFlag).join(' · ')
}

/**
 * Plain-language label per flow state, in English.
 *
 * The keys double as locale keys under `sessionStates.` in the i18n catalogs,
 * so a screen that has been migrated to `t()` can translate the same label this
 * table spells in English — see `flowStateLabelKey`. `unknown` is the label for
 * a state this build does not know; an unmapped state is a bug, not a thing to
 * print raw at a player.
 */
export const FLOW_STATE_LABELS: Record<string, string> = {
  NotStarted: 'Not started yet',
  LoadingModel: 'Getting ready',
  LoadingScenario: 'Getting ready',
  Briefing: 'Briefing',
  NpcOpening: 'Opening the conversation',
  PlayerTurnListening: 'Your turn',
  PlayerTurnReview: 'Check your message',
  NpcThinking: 'Writing a reply',
  NpcSpeaking: 'Speaking',
  ScenarioEvent: 'Something is changing',
  DebriefGenerating: 'Preparing your debrief',
  DebriefReady: 'Debrief ready',
  Ended: 'Finished',
  Error: 'Something went wrong',
  unknown: 'In progress',
}

const UNKNOWN_FLOW_STATE = 'unknown'

/**
 * What the NPC is doing, in words rather than flow-state identifiers.
 *
 * The header used to print the raw identifier (`State: PlayerTurnListening`).
 * At `technical` the caller still shows the identifier alongside this.
 *
 * English only — for the screens that have not been migrated to `t()` yet.
 * A migrated screen must use `flowStateLabelKey` instead, or a German player
 * reads "Your turn" in an otherwise German UI.
 */
export function plainFlowState(state: string): string {
  return (
    (state === UNKNOWN_FLOW_STATE ? undefined : FLOW_STATE_LABELS[state]) ??
    FLOW_STATE_LABELS[UNKNOWN_FLOW_STATE]
  )
}

/** The locale key for a flow state's plain-language label. */
export function flowStateLabelKey(state: string): string {
  const known = state !== UNKNOWN_FLOW_STATE && state in FLOW_STATE_LABELS
  return `sessionStates.${known ? state : UNKNOWN_FLOW_STATE}`
}

/** "player_exit" → "player exit"; used in the "Outcome: …" lines. */
export function humanizeEndingType(endingType: string): string {
  return endingType.replace(/_/g, ' ')
}
