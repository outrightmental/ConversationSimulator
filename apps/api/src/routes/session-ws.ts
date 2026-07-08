// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import type { WebSocket } from '@fastify/websocket';
import { getDb } from '../db.js';
import { registerConnection, removeConnection, nextSeq } from '../ws/session-events.js';
import type { WsEvent, WsEventType, SessionState, EndingType } from '@convsim/shared';

/** Maximum number of recent durable events replayed on reconnect. */
const REPLAY_LIMIT = 50;

interface SessionRow {
  state: string;
  state_vars_json: string;
  ending_type: string | null;
}

interface EventRow {
  event_id: number;
  event_type: string;
  payload_json: string;
  created_at: string;
}

/** Maps a persisted session_events row to a WS event type and payload, or null to skip. */
function mapDbEvent(
  eventType: string,
  payload: Record<string, unknown>,
): { type: WsEventType; payload: Record<string, unknown> } | null {
  switch (eventType) {
    case 'npc_opening':
      return {
        type: 'npc.final',
        payload: {
          content: payload['content'] ?? '',
          emotion: 'neutral',
          state_delta: {},
          event_flags: [],
        },
      };
    case 'npc_turn':
      return {
        type: 'npc.final',
        payload: {
          content: payload['content'] ?? '',
          emotion: payload['emotion'] ?? 'neutral',
          state_delta: payload['state_delta'] ?? {},
          event_flags: payload['event_flags'] ?? [],
        },
      };
    case 'session_ended':
      return {
        type: 'session.state',
        payload: { state: 'Ended', ending_type: payload['ending_type'] ?? null },
      };
    default:
      return null;
  }
}

function send(socket: WebSocket, event: WsEvent): void {
  try {
    socket.send(JSON.stringify(event));
  } catch {
    // ignore — connection may be closing
  }
}

export async function sessionWsRoutes(app: FastifyInstance): Promise<void> {
  app.get<{
    Params: { session_id: string };
    Querystring: { after_seq?: string };
  }>(
    '/ws/session/:session_id',
    { websocket: true },
    (socket: WebSocket, req) => {
      const { session_id } = req.params;

      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>(
          'SELECT state, state_vars_json, ending_type FROM sessions WHERE session_id = ?',
        )
        .get(session_id);

      if (!row) {
        send(socket, {
          seq: 1,
          session_id,
          type: 'error',
          ts: new Date().toISOString(),
          payload: { code: 'SESSION_NOT_FOUND', message: `Session '${session_id}' not found` },
        });
        socket.close(1008, 'Session not found');
        return;
      }

      registerConnection(session_id, socket);

      const stateVars = JSON.parse(row.state_vars_json || '{}') as Record<string, number>;

      // Always send the current session state on connect so the client can sync.
      send(socket, {
        seq: nextSeq(session_id),
        session_id,
        type: 'session.state',
        ts: new Date().toISOString(),
        payload: {
          state: row.state as SessionState,
          state_vars: stateVars,
          ending_type: (row.ending_type as EndingType | null) ?? null,
        },
      });

      // Replay durable events when the client passes after_seq=0.
      // Only after_seq=0 (replay all) is supported in this MVP. Non-zero values
      // are silently ignored because `after_seq` is intended to map to the WS
      // `seq` field, but the DB only has `event_id`, which is a different number
      // space. Proper seq-mapped replay requires storing the WS seq in
      // session_events and is deferred to a future issue.
      const rawAfterSeq = req.query?.['after_seq'];
      if (rawAfterSeq === '0') {
        const recentEvents = db
          .prepare<[string, number], EventRow>(
            'SELECT event_id, event_type, payload_json, created_at FROM session_events WHERE session_id = ? AND event_id > 0 ORDER BY event_id LIMIT ?',
          )
          .all(session_id, REPLAY_LIMIT);

        for (const evt of recentEvents) {
          const payload = JSON.parse(evt.payload_json) as Record<string, unknown>;
          const mapped = mapDbEvent(evt.event_type, payload);
          if (mapped) {
            send(socket, {
              seq: nextSeq(session_id),
              session_id,
              type: mapped.type,
              ts: evt.created_at,
              payload: mapped.payload,
            } as WsEvent);
          }
        }
      }

      socket.on('close', () => {
        removeConnection(session_id, socket);
      });

      socket.on('error', () => {
        removeConnection(session_id, socket);
      });
    },
  );
}
