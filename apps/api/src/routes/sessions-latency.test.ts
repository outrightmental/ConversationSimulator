// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import { resetDb } from '../db.js';
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

async function createStartedSession(a: FastifyInstance): Promise<string> {
  const { session_id } = (
    await a.inject({ method: 'POST', url: '/api/sessions', payload: validRequest })
  ).json<SessionCreateResponse>();
  await a.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
  return session_id;
}

beforeEach(async () => {
  delete process.env['CONVSIM_FAKE_DELAY_MS'];
  delete process.env['CONVSIM_LLM_TIMEOUT_MS'];
  resetDb();
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
  delete process.env['CONVSIM_FAKE_DELAY_MS'];
  delete process.env['CONVSIM_LLM_TIMEOUT_MS'];
});

// ── Normal turn (no delay) ──────────────────────────────────────────────────

describe('turn endpoint — normal operation', () => {
  it('returns 200 for a normal turn with no delay configured', async () => {
    const session_id = await createStartedSession(app);
    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello there.' },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().state).toBe('PlayerTurnListening');
  });
});

// ── Timeout behavior ────────────────────────────────────────────────────────

describe('turn endpoint — LLM timeout', () => {
  it('returns 504 when the LLM exceeds the configured timeout', async () => {
    // Fake runtime delay: 200ms. Timeout: 50ms → guaranteed timeout.
    process.env['CONVSIM_FAKE_DELAY_MS'] = '200';
    process.env['CONVSIM_LLM_TIMEOUT_MS'] = '50';

    const session_id = await createStartedSession(app);
    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello, slow NPC.' },
    });

    expect(res.statusCode).toBe(504);
  });

  it('includes a timeout error message with suggested fixes', async () => {
    process.env['CONVSIM_FAKE_DELAY_MS'] = '200';
    process.env['CONVSIM_LLM_TIMEOUT_MS'] = '50';

    const session_id = await createStartedSession(app);
    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'This will time out.' },
    });

    const body = res.json<{ message: string }>();
    expect(body.message).toMatch(/timed out/i);
    expect(body.message).toMatch(/runtime settings/i);
  });

  it('leaves the session in PlayerTurnListening after a timeout so the user can retry', async () => {
    process.env['CONVSIM_FAKE_DELAY_MS'] = '200';
    process.env['CONVSIM_LLM_TIMEOUT_MS'] = '50';

    const session_id = await createStartedSession(app);
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'This will time out.' },
    });

    // Session state must be unchanged — user should be able to retry.
    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.statusCode).toBe(200);
    expect(getRes.json().state).toBe('PlayerTurnListening');
  });

  it('succeeds on a retry after a timeout when the delay is cleared', async () => {
    process.env['CONVSIM_FAKE_DELAY_MS'] = '200';
    process.env['CONVSIM_LLM_TIMEOUT_MS'] = '50';

    const session_id = await createStartedSession(app);
    const timedOut = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'First attempt — will time out.' },
    });
    expect(timedOut.statusCode).toBe(504);

    // Clear the delay to simulate the runtime recovering.
    delete process.env['CONVSIM_FAKE_DELAY_MS'];
    delete process.env['CONVSIM_LLM_TIMEOUT_MS'];

    const retry = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Retry after timeout.' },
    });
    expect(retry.statusCode).toBe(200);
  });
});

// ── Fake delay — fast path ──────────────────────────────────────────────────

describe('turn endpoint — fake delay within timeout', () => {
  it('returns 200 when delay is shorter than the timeout', async () => {
    process.env['CONVSIM_FAKE_DELAY_MS'] = '50';
    process.env['CONVSIM_LLM_TIMEOUT_MS'] = '500';

    const session_id = await createStartedSession(app);
    const res = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Slow but not timed out.' },
    });
    expect(res.statusCode).toBe(200);
  });
});
