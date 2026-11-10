// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { readExport } from '../lib/sessionExport'

describe('readExport', () => {
  it("reads convsim-core's export: top-level setup, scenario.id and turns", () => {
    const out = readExport({
      scenario: { id: 'used_car_negotiation', name: 'The Used Car Deal' },
      setup: { scenario_id: 'used_car_negotiation', difficulty: 'standard', player_role_name: 'Sam' },
      turns: [
        { turn_number: 0, role: 'npc_opening', content: 'Hey there.' },
        { turn_number: 1, role: 'player', content: 'Hi.' },
        { turn_number: 2, role: 'npc', content: 'Welcome.', emotion: 'warm' },
      ],
      events: [{ id: 1, event_type: 'rubric_observations', payload: [{ rubric_id: 'a' }] }],
    })
    expect(out.scenarioId).toBe('used_car_negotiation')
    expect(out.setup?.scenario_id).toBe('used_car_negotiation')
    expect(out.transcript.map((e) => e.event_type)).toEqual(['npc_opening', 'player_turn', 'npc_turn'])
    expect(out.transcript[2].payload).toEqual({ content: 'Welcome.', emotion: 'warm' })
    // Rows carry no event id; a non-positive id keys them by position.
    expect(out.transcript.every((e) => e.event_id <= 0)).toBe(true)
  })

  it('still reads the legacy shape: session.setup and transcript events', () => {
    const out = readExport({
      session: { setup: { scenario_id: 'legacy', difficulty: 'standard', player_role_name: 'Sam' }, scenario_id: 'legacy' },
      events: [
        { event_id: 1, event_type: 'npc_opening', payload: { content: 'Hello.' } },
        { event_id: 2, event_type: 'rubric_observations', payload: [{ rubric_id: 'a' }] },
        { event_id: 3, event_type: 'player_turn', payload: { content: 'Hi.' } },
      ],
    })
    expect(out.scenarioId).toBe('legacy')
    expect(out.setup?.scenario_id).toBe('legacy')
    expect(out.transcript.map((e) => e.event_id)).toEqual([1, 3])
  })

  it('returns an empty transcript for a missing or empty export', () => {
    expect(readExport(undefined).transcript).toEqual([])
    expect(readExport({ turns: [] }).transcript).toEqual([])
  })
})
