// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import { resetDb, getDb } from '../db.js';
import type { FastifyInstance } from 'fastify';
import type { SessionCreateRequest, SessionCreateResponse } from '@convsim/shared';

let app: FastifyInstance;

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

beforeEach(async () => {
  resetDb();
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
});

async function createSession(overrides: Partial<SessionCreateRequest> = {}) {
  const res = await app.inject({
    method: 'POST',
    url: '/api/sessions',
    payload: { ...validRequest, ...overrides },
  });
  return res.json<SessionCreateResponse>();
}

// ---------------------------------------------------------------------------
// GET /api/privacy/data-folder
// ---------------------------------------------------------------------------

describe('GET /api/privacy/data-folder', () => {
  it('returns 200 with a path field', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/privacy/data-folder' });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ path: string }>();
    expect(typeof body.path).toBe('string');
  });
});

// ---------------------------------------------------------------------------
// GET /api/privacy/folders
// ---------------------------------------------------------------------------

describe('GET /api/privacy/folders', () => {
  it('returns 200 with data, logs, models, and packs fields', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/privacy/folders' });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ data: string; logs: string; models: string; packs: string }>();
    expect(typeof body.data).toBe('string');
    expect(typeof body.logs).toBe('string');
    expect(typeof body.models).toBe('string');
    expect(typeof body.packs).toBe('string');
  });
});

// ---------------------------------------------------------------------------
// POST /api/privacy/clear
// ---------------------------------------------------------------------------

describe('POST /api/privacy/clear', () => {
  it('returns 200 with deleted_sessions count', async () => {
    await createSession();
    await createSession();

    const res = await app.inject({ method: 'POST', url: '/api/privacy/clear' });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ deleted_sessions: number }>();
    expect(body.deleted_sessions).toBe(2);
  });

  it('removes all sessions from the database', async () => {
    const { session_id } = await createSession();

    await app.inject({ method: 'POST', url: '/api/privacy/clear' });

    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.statusCode).toBe(404);
  });

  it('removes all session events from the database', async () => {
    const { session_id } = await createSession();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    await app.inject({ method: 'POST', url: '/api/privacy/clear' });

    const eventCount = getDb()
      .prepare<[], { n: number }>('SELECT COUNT(*) AS n FROM session_events')
      .get()?.n ?? 0;
    expect(eventCount).toBe(0);
  });

  it('returns deleted_sessions=0 when no sessions exist', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/privacy/clear' });
    expect(res.statusCode).toBe(200);
    expect(res.json<{ deleted_sessions: number }>().deleted_sessions).toBe(0);
  });

  it('is idempotent — a second clear returns 0 deleted sessions', async () => {
    await createSession();
    await app.inject({ method: 'POST', url: '/api/privacy/clear' });

    const res = await app.inject({ method: 'POST', url: '/api/privacy/clear' });
    expect(res.statusCode).toBe(200);
    expect(res.json<{ deleted_sessions: number }>().deleted_sessions).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// GET /api/sessions/:session_id/export
// ---------------------------------------------------------------------------

describe('GET /api/sessions/:session_id/export', () => {
  it('returns 200 with session and events fields', async () => {
    const { session_id } = await createSession();

    const res = await app.inject({
      method: 'GET',
      url: `/api/sessions/${session_id}/export`,
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ session: unknown; events: unknown[] }>();
    expect(body.session).toBeDefined();
    expect(Array.isArray(body.events)).toBe(true);
  });

  it('export includes session_id, scenario_id, state, and setup', async () => {
    const { session_id } = await createSession();

    const res = await app.inject({
      method: 'GET',
      url: `/api/sessions/${session_id}/export`,
    });
    const body = res.json<{
      session: { session_id: string; scenario_id: string; state: string; setup: unknown };
      events: unknown[];
    }>();
    expect(body.session.session_id).toBe(session_id);
    expect(body.session.scenario_id).toBe('behavioral_interview');
    expect(body.session.state).toBe('NotStarted');
    expect(body.session.setup).toBeDefined();
  });

  it('export includes parsed setup (not a raw JSON string)', async () => {
    const { session_id } = await createSession();

    const res = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    const body = res.json<{
      session: { setup: { scenario_id?: string } };
      events: unknown[];
    }>();
    expect(typeof body.session.setup).toBe('object');
    expect(body.session.setup?.scenario_id).toBe('behavioral_interview');
  });

  it('includes events produced during the session', async () => {
    const { session_id } = await createSession();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    const res = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    const body = res.json<{
      session: unknown;
      events: Array<{ event_type: string }>;
    }>();
    expect(body.events.length).toBeGreaterThan(0);
    expect(body.events[0].event_type).toBe('npc_opening');
  });

  it('events include parsed payload (not a raw JSON string)', async () => {
    const { session_id } = await createSession();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    const res = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    const body = res.json<{
      session: unknown;
      events: Array<{ payload: { content?: string } }>;
    }>();
    expect(typeof body.events[0].payload).toBe('object');
    expect(typeof body.events[0].payload.content).toBe('string');
  });

  it('returns 404 for unknown session id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/sessions/sess-doesnotexist/export',
    });
    expect(res.statusCode).toBe(404);
  });

  it('save_transcript=false — events are not persisted; start response still carries event for display', async () => {
    const { session_id } = await createSession({ save_transcript: false });

    // The start response must still include the NPC opening so the UI can display it in real time.
    const startRes = await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    expect(startRes.json<{ events: unknown[] }>().events).toHaveLength(1);

    // The export must return no events — the conversation was not persisted.
    const res = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    expect(res.statusCode).toBe(200);
    const body = res.json<{
      session: { setup: { save_transcript: boolean } };
      events: unknown[];
    }>();
    expect(body.session.setup.save_transcript).toBe(false);
    expect(body.events).toHaveLength(0);
  });

  it('save_transcript=false — turn events are not persisted; turn response still carries events for display', async () => {
    const { session_id } = await createSession({ save_transcript: false });
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });

    // The turn response must still include player_turn and npc_turn for real-time display.
    const turnRes = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello' },
    });
    const turnBody = turnRes.json<{ events: Array<{ event_type: string }> }>();
    expect(turnBody.events).toHaveLength(2);
    expect(turnBody.events[0].event_type).toBe('player_turn');
    expect(turnBody.events[1].event_type).toBe('npc_turn');

    // The export must return no events — the conversation was not persisted.
    const exportRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    expect(exportRes.json<{ events: unknown[] }>().events).toHaveLength(0);
  });

  it('export is unavailable after the session is deleted', async () => {
    const { session_id } = await createSession();
    await app.inject({ method: 'DELETE', url: `/api/sessions/${session_id}` });

    const res = await app.inject({
      method: 'GET',
      url: `/api/sessions/${session_id}/export`,
    });
    expect(res.statusCode).toBe(404);
  });

  it('save_transcript=false — session_ended event is not persisted when session ends', async () => {
    const { session_id } = await createSession({ save_transcript: false });
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });

    const res = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    const body = res.json<{ session: { state: string }; events: unknown[] }>();
    expect(body.session.state).toBe('Ended');
    expect(body.events).toHaveLength(0);
  });

  it('save_transcript=false — debrief_generated event is not persisted when debrief is requested', async () => {
    const { session_id } = await createSession({ save_transcript: false });
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/turn`, payload: { content: 'Hello' } });
    // Force session into DebriefReady state to allow debrief
    getDb()
      .prepare("UPDATE sessions SET state = 'DebriefReady' WHERE session_id = ?")
      .run(session_id);
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });

    const res = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}/export` });
    const body = res.json<{ session: { state: string }; events: unknown[] }>();
    expect(body.session.state).toBe('Ended');
    expect(body.events).toHaveLength(0);
  });
});
