import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import type { FastifyInstance } from 'fastify';
import type { SessionCreateRequest, SessionCreateResponse } from '@convsim/shared';
import { sessions } from './sessions.js';

let app: FastifyInstance;

beforeEach(async () => {
  sessions.clear();
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
});
