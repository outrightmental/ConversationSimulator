import type { FastifyInstance } from 'fastify';
import type {
  SessionCreateRequest,
  SessionCreateResponse,
  SessionState,
} from '@convsim/shared';
import { SCENARIOS } from '../data/scenarios.js';

function generateSessionId(): string {
  const bytes = Array.from({ length: 8 }, () =>
    Math.floor(Math.random() * 256)
      .toString(16)
      .padStart(2, '0'),
  );
  return `sess-${bytes.join('')}`;
}

interface StoredSession {
  session_id: string;
  scenario_id: string;
  state: SessionState;
  created_at: string;
  setup: SessionCreateRequest;
}

const sessions = new Map<string, StoredSession>();

export async function sessionRoutes(app: FastifyInstance) {
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
        throw new Error(
          `Scenario '${body.scenario_id}' does not permit state meters`,
        );
      }

      const session: StoredSession = {
        session_id: generateSessionId(),
        scenario_id: body.scenario_id,
        state: 'NotStarted',
        created_at: new Date().toISOString(),
        setup: body,
      };

      sessions.set(session.session_id, session);

      reply.status(201);
      return session;
    },
  );

  app.get<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id',
    async (req, reply): Promise<StoredSession> => {
      const session = sessions.get(req.params.session_id);
      if (!session) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }
      return session;
    },
  );

  app.delete<{ Params: { session_id: string } }>(
    '/api/sessions/:session_id',
    async (req, reply): Promise<void> => {
      if (!sessions.has(req.params.session_id)) {
        reply.status(404);
        throw new Error(`Session '${req.params.session_id}' not found`);
      }
      sessions.delete(req.params.session_id);
      reply.status(204);
    },
  );
}

export { sessions };
