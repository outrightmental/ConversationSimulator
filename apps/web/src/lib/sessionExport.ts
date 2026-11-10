// SPDX-License-Identifier: Apache-2.0
import type { SessionCreateRequest } from '@convsim/shared'

export type TranscriptEvent = {
  event_id: number
  event_type: string
  payload: Record<string, unknown>
}

// One entry of the export's event log. Its payload is whatever the event
// stored: an object for most events, but a list for `rubric_observations`.
type ExportedEvent = Omit<TranscriptEvent, 'payload'> & { payload: unknown }

const TRANSCRIPT_EVENT_TYPES = new Set(['player_turn', 'npc_turn', 'npc_opening'])

export function transcriptEventsOf(events: ExportedEvent[] | undefined): TranscriptEvent[] {
  return (events ?? []).filter(
    (e): e is TranscriptEvent =>
      TRANSCRIPT_EVENT_TYPES.has(e.event_type) &&
      typeof e.payload === 'object' &&
      e.payload !== null &&
      !Array.isArray(e.payload),
  )
}

// What the debrief reads from GET /api/sessions/{id}/export. convsim-core's
// export (SessionExportResponse in routers/sessions.py) carries the setup at
// the top level, the scenario as `scenario.id`, and the transcript as `turns`;
// it stores no player_turn / npc_turn / npc_opening events. The legacy apps/api
// export nested `session.setup` and kept the transcript as those events. Reading
// only the legacy shape left the real app's debrief with no transcript and sent
// "Replay same setup" to the variation flow every time, so both are read.
type ExportShape = {
  setup?: SessionCreateRequest
  scenario?: { id?: string }
  turns?: Array<{ turn_number: number; role: string; content: string; emotion?: string | null }>
  session?: { setup?: SessionCreateRequest; scenario_id?: string }
  events?: ExportedEvent[]
}

const TURN_ROLE_EVENT_TYPE: Record<string, string> = {
  npc_opening: 'npc_opening',
  player: 'player_turn',
  npc: 'npc_turn',
}

export function readExport(data: unknown): {
  setup: SessionCreateRequest | undefined
  scenarioId: string | undefined
  transcript: TranscriptEvent[]
} {
  const d = (data ?? {}) as ExportShape
  const transcript =
    Array.isArray(d.turns) && d.turns.length > 0
      ? d.turns
          .filter((turn) => turn.role in TURN_ROLE_EVENT_TYPE)
          // Turns carry no event id; a non-positive id keys the row by position.
          .map((turn, i) => ({
            event_id: -(i + 1),
            event_type: TURN_ROLE_EVENT_TYPE[turn.role],
            payload: { content: turn.content, emotion: turn.emotion ?? undefined },
          }))
      : transcriptEventsOf(d.events)
  return {
    setup: d.setup ?? d.session?.setup,
    scenarioId: d.scenario?.id ?? d.session?.scenario_id,
    transcript,
  }
}
