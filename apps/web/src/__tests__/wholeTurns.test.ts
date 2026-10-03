// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { wholeTurnNumbersFor } from '../lib/wholeTurns'

/**
 * Issue #501 §4: one turn is the player's message plus the reply to it. The
 * transcript used to number half-turns, so a debrief key moment at "turn 3"
 * and the transcript's "Turn 3" pointed at different moments.
 */
describe('wholeTurnNumbersFor', () => {
  it('returns nothing for an empty transcript', () => {
    expect(wholeTurnNumbersFor([])).toEqual([])
  })

  it('gives the opening turn 0', () => {
    expect(wholeTurnNumbersFor([{ event_type: 'npc_opening' }])).toEqual([0])
  })

  it('numbers a player message and the reply to it as one turn', () => {
    expect(
      wholeTurnNumbersFor([
        { event_type: 'npc_opening' },
        { event_type: 'player_turn' },
        { event_type: 'npc_turn' },
      ]),
    ).toEqual([0, 1, 1])
  })

  it('counts successive exchanges', () => {
    expect(
      wholeTurnNumbersFor([
        { event_type: 'npc_opening' },
        { event_type: 'player_turn' },
        { event_type: 'npc_turn' },
        { event_type: 'player_turn' },
        { event_type: 'npc_turn' },
        { event_type: 'player_turn' },
        { event_type: 'npc_turn' },
      ]),
    ).toEqual([0, 1, 1, 2, 2, 3, 3])
  })

  it('numbers a turn still awaiting its reply', () => {
    expect(
      wholeTurnNumbersFor([
        { event_type: 'npc_opening' },
        { event_type: 'player_turn' },
        { event_type: 'npc_turn' },
        { event_type: 'player_turn' },
      ]),
    ).toEqual([0, 1, 1, 2])
  })

  it('reads transcript rows as well as export events', () => {
    // GET /sessions/{id}/transcript says role; the session export says
    // event_type. Both have to label the same way.
    expect(
      wholeTurnNumbersFor([
        { role: 'npc_opening' },
        { role: 'player' },
        { role: 'npc' },
        { role: 'player' },
        { role: 'npc' },
      ]),
    ).toEqual([0, 1, 1, 2, 2])
  })

  it('does not merge two replies into one turn', () => {
    // Two NPC rows in a row must stay distinguishable: they are separate
    // moments, and a key moment pointing at either has to land on the right one.
    expect(
      wholeTurnNumbersFor([
        { event_type: 'player_turn' },
        { event_type: 'npc_turn' },
        { event_type: 'npc_turn' },
      ]),
    ).toEqual([1, 1, 2])
  })

  it('counts a transcript with no opening from turn 1', () => {
    expect(
      wholeTurnNumbersFor([{ event_type: 'player_turn' }, { event_type: 'npc_turn' }]),
    ).toEqual([1, 1])
  })
})
