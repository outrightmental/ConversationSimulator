import type { FastifyInstance } from 'fastify';
import type {
  SessionCreateRequest,
  SessionCreateResponse,
  SessionState,
  SessionStartResponse,
  TurnRequest,
  TurnResponse,
  SessionEndResponse,
  SessionDebriefResponse,
  EndingType,
} from '@convsim/shared';
import { SCENARIOS } from '../data/scenarios.js';
import { getDb } from '../db.js';

const MAX_TURN_CONTENT_LENGTH = 2000;

// Baseline state variable defaults (mirrors convsim_core/scenario_state.py).
const BASELINE_STATE_VARS: Record<string, number> = {
  trust: 50,
  patience: 75,
  pressure: 25,
  rapport: 50,
  openness: 50,
  objective_progress: 0,
};

// Fake structured NPC response (mirrors fake.py _STRUCTURED_RESPONSE).
const FAKE_NPC_RESPONSE = {
  npc_utterance: 'Hello there. I am a simulated NPC.',
  npc_emotion: 'neutral',
  state_delta: {} as Record<string, number>,
  event_flags: [] as string[],
  safety: { status: 'ok' as 'ok' | 'redirect' | 'stop' },
  session_control: { continue_session: true },
};

function generateSessionId(): string {
  const bytes = Array.from({ length: 8 }, () =>
    Math.floor(Math.random() * 256)
      .toString(16)
      .padStart(2, '0'),
  );
  return `sess-${bytes.join('')}`;
}

type Action = 'start' | 'turn' | 'end' | 'debrief';

// Returns true when the action is a legal next step from the given state.
function canTransition(state: SessionState, action: Action): boolean {
  if (state === 'Ended') return false;
  if (state === 'Error') return action === 'end';
  if (action === 'end') return true;
  if (action === 'start') return state === 'NotStarted';
  if (action === 'turn') return state === 'PlayerTurnListening';
  if (action === 'debrief') return state === 'DebriefReady';
  return false;
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

function rowToEvent(row: EventRow) {
  return {
    event_id: row.event_id,
    session_id: row.session_id,
    event_type: row.event_type,
    payload: JSON.parse(row.payload_json) as Record<string, unknown>,
    created_at: row.created_at,
  };
}

function insertEvent(
  session_id: string,
  event_type: string,
  payload: Record<string, unknown>,
): EventRow {
  const db = getDb();
  const now = new Date().toISOString();
  const result = db
    .prepare(
      'INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)',
    )
    .run(session_id, event_type, JSON.stringify(payload), now);
  return db
    .prepare<[number], EventRow>('SELECT * FROM session_events WHERE event_id = ?')
    .get(Number(result.lastInsertRowid))!;
}

function rejectTransition(reply: { status: (code: number) => void }, state: SessionState, msg: string): never {
  reply.status(409);
  const err = new Error(msg) as Error & { statusCode: number; code: string; current_state: string };
  err.statusCode = 409;
  err.code = 'INVALID_TRANSITION';
  err.current_state = state;
  throw err;
}

export async function sessionRoutes(app: FastifyInstance) {
  // GET /api/sessions
  app.get('/api/sessions', async (): Promise<{ sessions: SessionCreateResponse[] }> => {
    const db = getDb();
    const rows = db
      .prepare<[], SessionRow>('SELECT * FROM sessions ORDER BY created_at DESC')
      .all();
    return {
      sessions: rows.map((row) => ({
        session_id: row.session_id,
        scenario_id: row.scenario_id,
        state: row.state as SessionState,
        created_at: row.created_at,
        setup: JSON.parse(row.setup_json) as SessionCreateRequest,
      })),
    };
  });

  // POST /api/sessions
  app.post<{ Body: SessionCreateRequest }>(
    '/api/sessions',
    {
      schema: {
        body: {
          type: 'object',
          required: [
            'scenario_id',
            'difficulty',
            'player_role_name',
            'language',
            'input_mode',
            'tts_enabled',
            'show_state_meters',
            'save_transcript',
            'seed',
          ],
          properties: {
            scenario_id: { type: 'string' },
            difficulty: { type: 'string', enum: ['easy', 'normal', 'hard'] },
            player_role_name: { type: 'string', minLength: 1 },
            language: { type: 'string' },
            input_mode: {
              type: 'string',
              enum: ['push-to-talk', 'hands-free', 'text-only'],
            },
            tts_enabled: { type: 'boolean' },
            show_state_meters: { type: 'boolean' },
            save_transcript: { type: 'boolean' },
            seed: { type: ['integer', 'null'], minimum: 0, maximum: 2147483647 },
          },
        },
      },
    },
    async (req, reply): Promise<SessionCreateResponse> => {
      const body = req.body;

      if (!body.player_role_name.trim()) {
        reply.status(400);
        throw new Error('player_role_name cannot be blank');
      }

      if (!SCENARIOS[body.scenario_id]) {
        reply.status(400);
        throw new Error(`Unknown scenario_id: ${body.scenario_id}`);
      }

      const scenario = SCENARIOS[body.scenario_id]!;

      if (!Object.prototype.hasOwnProperty.call(scenario.difficulty.options, body.difficulty)) {
        reply.status(400);
        throw new Error(
          `Difficulty '${body.difficulty}' is not available for scenario '${body.scenario_id}'`,
        );
      }

      if (!scenario.supported_languages.includes(body.language)) {
        reply.status(400);
        throw new Error(
          `Language '${body.language}' is not supported by scenario '${body.scenario_id}'`,
        );
      }

      if (body.show_state_meters && !scenario.state_meters_permitted) {
        reply.status(400);
        throw new Error(`Scenario '${body.scenario_id}' does not permit state meters`);
      }

      const db = getDb();
      const now = new Date().toISOString();
      const session_id = generateSessionId();

      db
        .prepare(
          'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
        )
        .run(session_id, body.scenario_id, 'NotStarted', now, JSON.stringify(body));

      reply.status(201);
      return {
        session_id,
        scenario_id: body.scenario_id,
        state: 'NotStarted',
        created_at: now,
        setup: body,
      };
    },
  );

  // GET /api/sessions/:session_id
  app.get<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id',
    async (req, reply): Promise<SessionCreateResponse> => {
      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>('SELECT * FROM sessions WHERE session_id = ?')
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      return {
        session_id: row.session_id,
        scenario_id: row.scenario_id,
        state: row.state as SessionState,
        created_at: row.created_at,
        setup: JSON.parse(row.setup_json) as SessionCreateRequest,
      };
    },
  );

  // DELETE /api/sessions/:session_id
  app.delete<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id',
    async (req, reply): Promise<void> => {
      const db = getDb();
      const row = db
        .prepare<[string], Pick<SessionRow, 'session_id'>>(
          'SELECT session_id FROM sessions WHERE session_id = ?',
        )
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      db.prepare('DELETE FROM sessions WHERE session_id = ?').run(req.params.session_id);
      reply.status(204);
    },
  );

  // POST /api/sessions/:session_id/start
  app.post<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id/start',
    async (req, reply): Promise<SessionStartResponse> => {
      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>('SELECT * FROM sessions WHERE session_id = ?')
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      const currentState = row.state as SessionState;
      if (!canTransition(currentState, 'start')) {
        rejectTransition(
          reply,
          currentState,
          `Cannot start session from state '${currentState}'. Session must be in NotStarted state.`,
        );
      }

      // Initialize state vars from baseline defaults and transition to PlayerTurnListening.
      const openingRow = db.transaction(() => {
        db.prepare(
          "UPDATE sessions SET state = 'PlayerTurnListening', state_vars_json = ? WHERE session_id = ?",
        ).run(JSON.stringify(BASELINE_STATE_VARS), req.params.session_id);
        return insertEvent(req.params.session_id, 'npc_opening', {
          content: 'Hello! I am ready to begin our conversation. Please go ahead.',
        });
      })();

      return {
        session_id: req.params.session_id,
        state: 'PlayerTurnListening',
        events: [rowToEvent(openingRow)],
      };
    },
  );

  // POST /api/sessions/:session_id/turn
  app.post<{ Params: { session_id: string }; Body: TurnRequest }>(
    '/api/sessions/:session_id/turn',
    {
      schema: {
        body: {
          type: 'object',
          required: ['content'],
          properties: {
            content: {
              type: 'string',
              minLength: 1,
              maxLength: MAX_TURN_CONTENT_LENGTH,
            },
          },
        },
      },
    },
    async (req, reply): Promise<TurnResponse> => {
      // 1. Normalize player text and reject whitespace-only input.
      const normalized = req.body.content.trim();
      if (!normalized) {
        reply.status(400);
        throw new Error('Turn content cannot be blank after trimming whitespace');
      }

      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>('SELECT * FROM sessions WHERE session_id = ?')
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      const currentState = row.state as SessionState;
      if (!canTransition(currentState, 'turn')) {
        rejectTransition(
          reply,
          currentState,
          `Cannot submit turn from state '${currentState}'. Session must be in PlayerTurnListening state.`,
        );
      }

      // 2. Input safety precheck — placeholder hook, always passes.
      // A production implementation would call a safety classifier here.

      const scenario = SCENARIOS[row.scenario_id];
      const newTurnCount = row.turn_count + 1;
      const maxTurns = scenario?.duration.max_turns ?? 20;

      // 3. Apply NPC response (fake runtime — same structured response as Python fake.py).
      const npc = FAKE_NPC_RESPONSE;

      // 4. Apply state delta (empty from fake runtime).
      const currentStateVars: Record<string, number> = JSON.parse(row.state_vars_json || '{}');
      const newStateVars = { ...currentStateVars };
      for (const [key, delta] of Object.entries(npc.state_delta)) {
        if (key in newStateVars) {
          newStateVars[key] = Math.max(0, Math.min(100, newStateVars[key] + delta));
        }
      }

      // 5. Evaluate safety status.
      const safetyStatus = npc.safety.status;
      const safetyStop = safetyStatus === 'stop';

      // 6. Evaluate ending condition.
      let endingType: EndingType | null = null;
      let nextState: SessionState = 'PlayerTurnListening';

      if (safetyStop) {
        endingType = 'safety_stop';
        nextState = 'Ended';
      } else if (!npc.session_control.continue_session) {
        endingType = 'player_exit';
        nextState = 'Ended';
      } else if (newTurnCount >= maxTurns) {
        endingType = 'timeout';
        nextState = 'Ended';
      }

      // 7. Persist atomically.
      const [playerRow, npcRow] = db.transaction(() => {
        db.prepare(
          'UPDATE sessions SET turn_count = ?, state_vars_json = ?, state = ?, ending_type = ? WHERE session_id = ?',
        ).run(
          newTurnCount,
          JSON.stringify(newStateVars),
          nextState,
          endingType,
          req.params.session_id,
        );

        const player = insertEvent(req.params.session_id, 'player_turn', {
          content: normalized,
        });
        const npcEvent = insertEvent(req.params.session_id, 'npc_turn', {
          content: npc.npc_utterance,
          emotion: npc.npc_emotion,
          state_delta: npc.state_delta,
          event_flags: npc.event_flags,
          safety: { status: safetyStatus },
          ending_type: endingType,
        });
        return [player, npcEvent] as const;
      })();

      return {
        session_id: req.params.session_id,
        state: nextState,
        events: [rowToEvent(playerRow), rowToEvent(npcRow)],
      };
    },
  );

  // POST /api/sessions/:session_id/end
  app.post<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id/end',
    async (req, reply): Promise<SessionEndResponse> => {
      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>('SELECT * FROM sessions WHERE session_id = ?')
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      const currentState = row.state as SessionState;
      if (!canTransition(currentState, 'end')) {
        rejectTransition(
          reply,
          currentState,
          `Cannot end session from state '${currentState}'. Session is already in a terminal state.`,
        );
      }

      // Preserve an existing ending type (e.g. success/failure) set by a scenario ending;
      // fall back to player_exit when none is recorded.
      const endingType: EndingType = (row.ending_type as EndingType | null) ?? 'player_exit';

      db.transaction(() => {
        db.prepare(
          "UPDATE sessions SET state = 'Ended', ending_type = ? WHERE session_id = ?",
        ).run(endingType, req.params.session_id);
        insertEvent(req.params.session_id, 'session_ended', { ending_type: endingType });
      })();

      return {
        session_id: req.params.session_id,
        state: 'Ended',
        ending_type: endingType,
      };
    },
  );

  // POST /api/sessions/:session_id/debrief
  app.post<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id/debrief',
    async (req, reply): Promise<SessionDebriefResponse> => {
      const db = getDb();
      const row = db
        .prepare<[string], SessionRow>('SELECT * FROM sessions WHERE session_id = ?')
        .get(req.params.session_id);

      if (!row) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }

      const currentState = row.state as SessionState;
      if (!canTransition(currentState, 'debrief')) {
        rejectTransition(
          reply,
          currentState,
          `Cannot generate debrief from state '${currentState}'. Session must be in DebriefReady state.`,
        );
      }

      const summary = 'Stub debrief: the session has completed. Full analysis is not yet available.';

      db.transaction(() => {
        db.prepare("UPDATE sessions SET state = 'Ended' WHERE session_id = ?").run(
          req.params.session_id,
        );
        insertEvent(req.params.session_id, 'debrief_generated', { summary });
      })();

      return {
        session_id: req.params.session_id,
        state: 'Ended',
        summary,
      };
    },
  );
}
