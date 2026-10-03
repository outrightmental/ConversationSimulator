// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach } from 'vitest'
import {
  DEFAULT_UI_LANGUAGE_LEVEL,
  UI_LANGUAGE_KEYS,
  hasSeenFamiliarityReask,
  humanizeEndingType,
  humanizeFlags,
  humanizeIdentifier,
  levelForFamiliarity,
  markFamiliarityReaskShown,
  plainFlowState,
  readLlmFamiliarity,
  readUiLanguageLevel,
  writeLlmFamiliarity,
  writeUiLanguageLevel,
} from '../lib/plainLanguage'

/** Issue #501 §2: the buffer between player-facing and technical language. */
beforeEach(() => {
  localStorage.clear()
})

describe('wording level', () => {
  it('defaults to plain for a player who was never asked', () => {
    // Plain is the safe direction: Settings is one click away, but a first
    // session reading `PlayerTurnListening` is not recoverable.
    expect(readUiLanguageLevel()).toBe('plain')
    expect(DEFAULT_UI_LANGUAGE_LEVEL).toBe('plain')
  })

  it('round-trips a chosen level', () => {
    writeUiLanguageLevel('technical')
    expect(readUiLanguageLevel()).toBe('technical')
    writeUiLanguageLevel('plain')
    expect(readUiLanguageLevel()).toBe('plain')
  })

  it('reads an unrecognised stored value as plain', () => {
    localStorage.setItem(UI_LANGUAGE_KEYS.level, 'expert-mode')
    expect(readUiLanguageLevel()).toBe('plain')
  })

  it('notifies this document so a mounted screen re-reads it', () => {
    // `storage` only fires in other documents, so flipping the switch in
    // Settings would never reach a Conversation mounted behind it.
    let fired = 0
    const listener = () => { fired += 1 }
    window.addEventListener('convsim:ui-language-level', listener)
    writeUiLanguageLevel('technical')
    window.removeEventListener('convsim:ui-language-level', listener)
    expect(fired).toBe(1)
  })
})

describe('familiarity answers', () => {
  it('only the player who works with language models gets the identifiers', () => {
    expect(levelForFamiliarity('new')).toBe('plain')
    expect(levelForFamiliarity('some')).toBe('plain')
    expect(levelForFamiliarity('expert')).toBe('technical')
  })

  it('an answer applies the level it implies', () => {
    writeLlmFamiliarity('expert')
    expect(readUiLanguageLevel()).toBe('technical')
    writeLlmFamiliarity('new')
    expect(readUiLanguageLevel()).toBe('plain')
  })

  it('remembers the answer so the re-ask can preselect it', () => {
    expect(readLlmFamiliarity()).toBeNull()
    writeLlmFamiliarity('some')
    expect(readLlmFamiliarity()).toBe('some')
  })

  it('tracks whether the post-tutorial re-ask has been shown', () => {
    expect(hasSeenFamiliarityReask()).toBe(false)
    markFamiliarityReaskShown()
    expect(hasSeenFamiliarityReask()).toBe(true)
  })
})

describe('humanizers', () => {
  it('turns a snake_case identifier into a sentence-cased label', () => {
    expect(humanizeIdentifier('objective_progress')).toBe('Objective progress')
    expect(humanizeIdentifier('trust')).toBe('Trust')
    expect(humanizeIdentifier('preparation-score')).toBe('Preparation score')
  })

  it('leaves an empty identifier alone rather than producing an empty label', () => {
    expect(humanizeIdentifier('')).toBe('')
  })

  it('joins several flags into one readable phrase', () => {
    expect(humanizeFlags(['honesty_demonstrated', 'player_demonstrates_knowledge'])).toBe(
      'Honesty demonstrated · Player demonstrates knowledge',
    )
  })

  it('says what the NPC is doing instead of naming the flow state', () => {
    expect(plainFlowState('PlayerTurnListening')).toBe('Your turn')
    expect(plainFlowState('NpcThinking')).toBe('Writing a reply')
    expect(plainFlowState('ScenarioEvent')).toBe('Something is changing')
    expect(plainFlowState('Ended')).toBe('Finished')
  })

  it('never prints an unmapped flow state raw at a player', () => {
    expect(plainFlowState('SomeFutureState')).toBe('In progress')
    expect(plainFlowState('SomeFutureState')).not.toContain('SomeFutureState')
  })

  it('reads an ending type as words', () => {
    expect(humanizeEndingType('player_exit')).toBe('player exit')
    expect(humanizeEndingType('safety_stop')).toBe('safety stop')
  })
})
