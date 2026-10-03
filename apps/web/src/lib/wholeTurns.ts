// SPDX-License-Identifier: Apache-2.0
/**
 * Whole-turn numbering for a transcript (issue #501 §4).
 *
 * "In the conversational LLM space, the term 'turn' would indicate one message
 * from the user and one reply from the model. Currently, each response from the
 * user *and* the model is counted as a turn, when they should constitute halves
 * of one whole turn."
 *
 * One turn is the player's message plus the NPC's reply to it; the NPC's
 * opening line belongs to neither and is turn 0, labelled rather than numbered.
 *
 * This is also the number convsim-core already counts: `turn_count` increments
 * once per exchange, `duration.max_turns` is measured in it, and the debrief's
 * key moments point at it. Only the transcript labels disagreed, so "Turn 3" in
 * a debrief's key moments and "Turn 3" in the transcript below it were
 * different moments.
 */

type TurnRole = 'npc_opening' | 'player' | 'npc'

/** Infer the role of one transcript row from an event type or a role field. */
function roleOf(entry: { event_type?: string; role?: string }): TurnRole {
  const raw = entry.event_type ?? entry.role ?? ''
  if (raw === 'npc_opening') return 'npc_opening'
  if (raw === 'player_turn' || raw === 'player') return 'player'
  return 'npc'
}

/**
 * Whole-turn number per row, aligned with the input array.
 *
 * Derived from the sequence rather than from a stored index so it works for
 * both shapes the UI has to label: `npc_opening` / `player_turn` / `npc_turn`
 * event rows from the session export, and `npc_opening` / `player` / `npc`
 * transcript rows. A player message opens a turn; an NPC reply closes the one
 * that is open, or — if none is (a transcript that somehow starts with a reply)
 * — opens and closes its own.
 */
export function wholeTurnNumbersFor(
  rows: ReadonlyArray<{ event_type?: string; role?: string }>,
): number[] {
  let current = 0
  let openTurnClosed = true
  return rows.map((row) => {
    const role = roleOf(row)
    if (role === 'npc_opening') return 0
    if (role === 'player') {
      current += 1
      openTurnClosed = false
      return current
    }
    if (openTurnClosed) current += 1
    openTurnClosed = true
    return current
  })
}
