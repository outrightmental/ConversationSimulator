import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import { resetDb, getDb } from '../db.js';
import type { FastifyInstance } from 'fastify';
import type {
  SessionCreateRequest,
  SessionCreateResponse,
  SessionStartResponse,
  TurnResponse,
  SessionEndResponse,
} from '@convsim/shared';

let app: FastifyInstance;

beforeEach(async () => {
  resetDb();
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
});

const validRequest: SessionCreateRequest = {
  scenario_id: 'behavioral_interview',
  difficulty: 'normal',
  player_role_name: 'Alice',
  language: 'en',
  input_mode: 'text-only',
  tts_enabled: false,
  show_state_meters: false,
  save_transcript: true,
  seed: null,
};

// ---------------------------------------------------------------------------
// POST /api/sessions
// ---------------------------------------------------------------------------

describe('POST /api/sessions', () => {
  it('creates a session and returns 201 with session id', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: validRequest,
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<SessionCreateResponse>();
    expect(body.session_id).toMatch(/^sess-/);
    expect(body.scenario_id).toBe('behavioral_interview');
    expect(body.state).toBe('NotStarted');
    expect(body.setup.difficulty).toBe('normal');
    expect(body.setup.player_role_name).toBe('Alice');
    expect(body.setup.language).toBe('en');
    expect(body.setup.input_mode).toBe('text-only');
    expect(body.setup.tts_enabled).toBe(false);
    expect(body.setup.show_state_meters).toBe(false);
    expect(body.setup.save_transcript).toBe(true);
    expect(body.setup.seed).toBeNull();
  });

  it('persists all setup fields including seed', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, seed: 1234, difficulty: 'hard', tts_enabled: false },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<SessionCreateResponse>();
    expect(body.setup.seed).toBe(1234);
    expect(body.setup.difficulty).toBe('hard');
  });

  it('persists input mode and language', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, input_mode: 'push-to-talk', language: 'en' },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<SessionCreateResponse>();
    expect(body.setup.input_mode).toBe('push-to-talk');
    expect(body.setup.language).toBe('en');
  });

  it('returns 400 for unknown scenario_id', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, scenario_id: 'nonexistent_scenario' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when difficulty is not available for the scenario', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, scenario_id: 'hostile_executive_interview', difficulty: 'easy' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when language is not supported by scenario', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, language: 'fr' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when show_state_meters is true but not permitted by scenario', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, show_state_meters: true },
    });
    expect(res.statusCode).toBe(400);
  });

  it('allows show_state_meters when scenario permits it', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, scenario_id: 'used_car_negotiation', show_state_meters: true },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<SessionCreateResponse>();
    expect(body.setup.show_state_meters).toBe(true);
  });

  it('returns 400 for missing required field player_role_name', async () => {
    const { player_role_name: _omitted, ...rest } = validRequest;
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: rest,
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when player_role_name is whitespace-only', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, player_role_name: '   ' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 for invalid input_mode value', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, input_mode: 'telepathy' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when seed is omitted', async () => {
    const { seed: _omitted, ...rest } = validRequest;
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: rest,
    });
    expect(res.statusCode).toBe(400);
  });

  it('text-only input mode is always accepted', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, input_mode: 'text-only', tts_enabled: false },
    });
    expect(res.statusCode).toBe(201);
  });

  it('persists save_transcript=false choice', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: { ...validRequest, save_transcript: false },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<SessionCreateResponse>();
    expect(body.setup.save_transcript).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// GET /api/sessions/:session_id
// ---------------------------------------------------------------------------

describe('GET /api/sessions/:session_id', () => {
  it('retrieves a previously created session', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: validRequest,
    });
    const created = createRes.json<SessionCreateResponse>();

    const getRes = await app.inject({
      method: 'GET',
      url: `/api/sessions/${created.session_id}`,
    });
    expect(getRes.statusCode).toBe(200);
    const body = getRes.json<SessionCreateResponse>();
    expect(body.session_id).toBe(created.session_id);
  });

  it('returns 404 for unknown session id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/sessions/sess-doesnotexist',
    });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// DELETE /api/sessions/:session_id
// ---------------------------------------------------------------------------

describe('DELETE /api/sessions/:session_id', () => {
  it('deletes a session and returns 204', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: validRequest,
    });
    const created = createRes.json<SessionCreateResponse>();

    const deleteRes = await app.inject({
      method: 'DELETE',
      url: `/api/sessions/${created.session_id}`,
    });
    expect(deleteRes.statusCode).toBe(204);

    const getRes = await app.inject({
      method: 'GET',
      url: `/api/sessions/${created.session_id}`,
    });
    expect(getRes.statusCode).toBe(404);
  });

  it('returns 404 for unknown session id', async () => {
    const res = await app.inject({
      method: 'DELETE',
      url: '/api/sessions/sess-doesnotexist',
    });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// POST /api/sessions/:id/start
// ---------------------------------------------------------------------------

describe('POST /api/sessions/:id/start', () => {
  it('starts a NotStarted session and returns PlayerTurnListening with npc_opening event', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/start`,
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<SessionStartResponse>();
    expect(body.session_id).toBe(session_id);
    expect(body.state).toBe('PlayerTurnListening');
    expect(body.events).toHaveLength(1);
    expect(body.events[0].event_type).toBe('npc_opening');
    expect(typeof body.events[0].payload.content).toBe('string');
  });

  it('persists state change — GET reflects PlayerTurnListening after start', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.json<SessionCreateResponse>().state).toBe('PlayerTurnListening');
  });

  it('returns 409 when called again on an already-started session', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('PlayerTurnListening');
  });

  it('returns 404 for unknown session', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/sessions/sess-unknown/start' });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// POST /api/sessions/:id/turn
// ---------------------------------------------------------------------------

describe('POST /api/sessions/:id/turn', () => {
  async function createStartedSession() {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    return session_id;
  }

  it('accepts a turn and returns player_turn and npc_turn events', async () => {
    const session_id = await createStartedSession();

    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello there.' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<TurnResponse>();
    expect(body.state).toBe('PlayerTurnListening');
    expect(body.events).toHaveLength(2);
    expect(body.events[0].event_type).toBe('player_turn');
    expect(body.events[0].payload.content).toBe('Hello there.');
    expect(body.events[1].event_type).toBe('npc_turn');
  });

  it('rejects turn submission from NotStarted state with 409', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Out of order.' },
    });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('NotStarted');
  });

  it('rejects turn submission from Ended state with 409', async () => {
    const session_id = await createStartedSession();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });

    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Too late.' },
    });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('Ended');
  });

  it('returns 400 for missing turn content', async () => {
    const session_id = await createStartedSession();
    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: {},
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 for empty string turn content', async () => {
    const session_id = await createStartedSession();
    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: '' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 404 for unknown session', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sessions/sess-unknown/turn',
      payload: { content: 'hello' },
    });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// POST /api/sessions/:id/end
// ---------------------------------------------------------------------------

describe('POST /api/sessions/:id/end', () => {
  it('ends a NotStarted session with player_exit', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    expect(res.statusCode).toBe(200);
    const body = res.json<SessionEndResponse>();
    expect(body.state).toBe('Ended');
    expect(body.ending_type).toBe('player_exit');
  });

  it('ends a started session with player_exit', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    expect(res.statusCode).toBe(200);
    expect(res.json<SessionEndResponse>().ending_type).toBe('player_exit');
  });

  it('persists Ended state — GET reflects it', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });

    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.json<SessionCreateResponse>().state).toBe('Ended');
  });

  it('preserves an existing ending_type set by the scenario rather than defaulting to player_exit', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    // Simulate a scenario that already decided the outcome before the player exited.
    getDb()
      .prepare("UPDATE sessions SET ending_type = 'success' WHERE session_id = ?")
      .run(session_id);

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    expect(res.statusCode).toBe(200);
    expect(res.json<SessionEndResponse>().ending_type).toBe('success');
  });

  it('returns 409 when called on an already-ended session', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('Ended');
  });

  it('returns 404 for unknown session', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/sessions/sess-unknown/end' });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// POST /api/sessions/:id/debrief
// ---------------------------------------------------------------------------

describe('POST /api/sessions/:id/debrief', () => {
  it('generates debrief from DebriefReady state and returns Ended with summary', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    // No API path reaches DebriefReady yet; force the state directly.
    getDb().prepare("UPDATE sessions SET state = 'DebriefReady' WHERE session_id = ?").run(session_id);

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.session_id).toBe(session_id);
    expect(body.state).toBe('Ended');
    expect(typeof body.summary).toBe('string');
    expect(body.summary.length).toBeGreaterThan(0);
  });

  it('persists a debrief_generated event in session_events', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    getDb().prepare("UPDATE sessions SET state = 'DebriefReady' WHERE session_id = ?").run(session_id);

    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });

    const events = getDb()
      .prepare<[string], { event_type: string }>(
        'SELECT event_type FROM session_events WHERE session_id = ? ORDER BY event_id',
      )
      .all(session_id);
    expect(events.map((e) => e.event_type)).toContain('debrief_generated');
  });

  it('returns 409 from NotStarted (not in DebriefReady)', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('NotStarted');
  });

  it('returns 409 when session is already Ended', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('Ended');
  });

  it('returns 404 for unknown session', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/sessions/sess-unknown/debrief' });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// State machine: legal and illegal transitions
// ---------------------------------------------------------------------------

describe('state machine transitions', () => {
  it('full lifecycle: create → start → turn → end', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    expect(
      (await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` })).json().state,
    ).toBe('NotStarted');

    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    expect(
      (await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` })).json().state,
    ).toBe('PlayerTurnListening');

    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'My first message.' },
    });
    expect(
      (await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` })).json().state,
    ).toBe('PlayerTurnListening');

    const endRes = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    expect(endRes.json<SessionEndResponse>().state).toBe('Ended');
    expect(endRes.json<SessionEndResponse>().ending_type).toBe('player_exit');
  });

  it('rejects start from PlayerTurnListening', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    expect(res.statusCode).toBe(409);
  });

  it('rejects turn from NotStarted', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'skip the start step' },
    });
    expect(res.statusCode).toBe(409);
  });

  it('allows end from Error state so broken sessions can be exited', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    // Force session into Error state directly (no API path sets this yet).
    getDb().prepare("UPDATE sessions SET state = 'Error' WHERE session_id = ?").run(session_id);

    const endRes = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    expect(endRes.statusCode).toBe(200);
    expect(endRes.json<SessionEndResponse>().state).toBe('Ended');
    expect(endRes.json<SessionEndResponse>().ending_type).toBe('player_exit');
  });

  it('rejects start from Error state with 409', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();
    getDb().prepare("UPDATE sessions SET state = 'Error' WHERE session_id = ?").run(session_id);

    const res = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    expect(res.statusCode).toBe(409);
    expect(res.json().code).toBe('INVALID_TRANSITION');
    expect(res.json().current_state).toBe('Error');
  });

  it('does not mutate state on a rejected transition', async () => {
    const { session_id } = (
      await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
    ).json<SessionCreateResponse>();

    // Attempt an illegal turn (not started yet)
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'illegal' },
    });

    // State must still be NotStarted
    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.json().state).toBe('NotStarted');
  });
});
