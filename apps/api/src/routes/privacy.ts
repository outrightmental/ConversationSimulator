// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import { getDb } from '../db.js';

let _dataFolderPath = ':memory:';

export function setDataFolderPath(p: string): void {
  _dataFolderPath = p;
}

export function getDataFolderPath(): string {
  return _dataFolderPath;
}

interface SessionRow {
  session_id: string;
  scenario_id: string;
  state: string;
  ending_type: string | null;
  created_at: string;
  setup_json: string;
  state_vars_json: string;
  turn_count: number;
}

interface EventRow {
  event_id: number;
  session_id: string;
  event_type: string;
  payload_json: string;
  created_at: string;
}

export async function privacyRoutes(app: FastifyInstance) {
  // GET /api/privacy/data-folder
  app.get('/api/privacy/data-folder', async (): Promise<{ path: string }> => {
    return { path: _dataFolderPath };
  });

  // POST /api/privacy/clear
  // Deletes all sessions and their events from the database.
  app.post('/api/privacy/clear', async (): Promise<{ deleted_sessions: number }> => {
    const db = getDb();
    const count = (
      db.prepare<[], { n: number }>('SELECT COUNT(*) AS n FROM sessions').get()
    )?.n ?? 0;
    db.transaction(() => {
      db.prepare('DELETE FROM session_events').run();
      db.prepare('DELETE FROM sessions').run();
    })();
    return { deleted_sessions: count };
  });

  // GET /api/sessions/:session_id/export
  // Returns a full JSON export of the session and all its events.
  app.get<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id/export',
    async (req, reply): Promise<{
      session: {
        session_id: string;
        scenario_id: string;
        state: string;
        ending_type: string | null;
        created_at: string;
        turn_count: number;
        setup: unknown;
        state_vars: unknown;
      };
      events: Array<{ event_id: number; session_id: string; event_type: string; payload: unknown; created_at: string }>;
    }> => {
      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>('SELECT * FROM sessions WHERE session_id = ?')
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      const events = db
        .prepare<[string], EventRow>(
          'SELECT * FROM session_events WHERE session_id = ? ORDER BY event_id',
        )
        .all(req.params.session_id);

      return {
        session: {
          session_id: row.session_id,
          scenario_id: row.scenario_id,
          state: row.state,
          ending_type: row.ending_type,
          created_at: row.created_at,
          turn_count: row.turn_count,
          setup: JSON.parse(row.setup_json) as unknown,
          state_vars: JSON.parse(row.state_vars_json) as unknown,
        },
        events: events.map((e) => ({
          event_id: e.event_id,
          session_id: e.session_id,
          event_type: e.event_type,
          payload: JSON.parse(e.payload_json) as unknown,
          created_at: e.created_at,
        })),
      };
    },
  );
}
