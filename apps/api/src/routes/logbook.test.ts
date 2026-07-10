// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import { resetDb, getDb } from '../db.js';
import type { FastifyInstance } from 'fastify';
import type { SessionCreateRequest, SessionCreateResponse, LogbookProfile, LogbookExport } from '@convsim/shared';

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

async function createAndEndSession(overrides: Partial<SessionCreateRequest> = {}) {
  const createRes = await app.inject({
    method: 'POST',
    url: '/api/sessions',
    payload: { ...validRequest, ...overrides },
  });
  const { session_id } = createRes.json<SessionCreateResponse>();
  await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
  await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
  return session_id;
}

async function createAndDebrief(overrides: Partial<SessionCreateRequest> = {}) {
  const createRes = await app.inject({
    method: 'POST',
    url: '/api/sessions',
    payload: { ...validRequest, ...overrides },
  });
  const { session_id } = createRes.json<SessionCreateResponse>();
  await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
  // Force into DebriefReady so debrief can be called
  getDb()
    .prepare("UPDATE sessions SET state = 'DebriefReady' WHERE session_id = ?")
    .run(session_id);
  await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });
  return session_id;
}

// ---------------------------------------------------------------------------
// GET /api/logbook/profile
// ---------------------------------------------------------------------------

describe('GET /api/logbook/profile', () => {
  it('returns 200 with zero sessions when database is empty', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    expect(res.statusCode).toBe(200);
    const body = res.json<LogbookProfile>();
    expect(body.total_sessions).toBe(0);
    expect(body.streak_days).toBe(0);
    expect(body.last_session_date).toBeNull();
    expect(body.dimension_scores).toEqual([]);
    expect(body.personal_records).toEqual([]);
    expect(body.strongest_dimension).toBeNull();
    expect(body.weakest_dimension).toBeNull();
    expect(body.last_session_delta).toBeNull();
  });

  it('counts only ended sessions', async () => {
    // Create a session but do not end it
    await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest });

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.total_sessions).toBe(0);
  });

  it('counts ended sessions correctly', async () => {
    await createAndEndSession();
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.total_sessions).toBe(2);
  });

  it('excludes workbench test sessions', async () => {
    await createAndEndSession({ scenario_id: 'workbench_test' });
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.total_sessions).toBe(1);
  });

  it('sets last_session_date when sessions exist', async () => {
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.last_session_date).not.toBeNull();
    // ISO date string YYYY-MM-DD
    expect(body.last_session_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('computes streak_days >= 1 when a session was ended today', async () => {
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.streak_days).toBeGreaterThanOrEqual(1);
  });

  it('computes total_practice_seconds when ended_at is set', async () => {
    // ended_at is set by the /end route; sleep is not needed because times
    // in the same test can still differ slightly, but we just check >= 0.
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.total_practice_seconds).toBeGreaterThanOrEqual(0);
  });

  it('includes dimension_scores from debrief events that have scores', async () => {
    const session_id = await createAndDebrief();
    // Inject non-empty scores into the debrief_generated event
    getDb()
      .prepare(
        `UPDATE session_events
         SET payload_json = '{"summary":"x","scores":{"clarity":80},"overall_score":75}'
         WHERE session_id = ? AND event_type = 'debrief_generated'`,
      )
      .run(session_id);

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.dimension_scores.length).toBeGreaterThan(0);
    const clarity = body.dimension_scores.find((d) => d.dimension_id === 'clarity');
    expect(clarity).toBeDefined();
    expect(clarity!.rolling_score).toBe(80);
  });

  it('counts a re-debriefed session only once in dimension scores', async () => {
    // A session can be debriefed again from the Ended state (the debrief screen's
    // retry button does exactly this), producing a second debrief_generated event.
    // Only the most recent debrief per session must count toward dimension scores.
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/sessions',
      payload: validRequest,
    });
    const { session_id } = createRes.json<SessionCreateResponse>();
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
    getDb()
      .prepare("UPDATE sessions SET state = 'DebriefReady' WHERE session_id = ?")
      .run(session_id);
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });
    // Retry: from Ended, generate a debrief a second time.
    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/debrief` });
    getDb()
      .prepare(
        `UPDATE session_events
         SET payload_json = '{"summary":"x","scores":{"clarity":80},"overall_score":75}'
         WHERE session_id = ? AND event_type = 'debrief_generated'`,
      )
      .run(session_id);

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.total_sessions).toBe(1);
    const clarity = body.dimension_scores.find((d) => d.dimension_id === 'clarity');
    expect(clarity).toBeDefined();
    expect(clarity!.session_count).toBe(1);
  });

  it('sets strongest_dimension and weakest_dimension from debrief scores', async () => {
    const s1 = await createAndDebrief();
    getDb()
      .prepare(
        `UPDATE session_events
         SET payload_json = '{"summary":"x","scores":{"empathy":90,"assertiveness":30},"overall_score":60}'
         WHERE session_id = ? AND event_type = 'debrief_generated'`,
      )
      .run(s1);

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.strongest_dimension).toBe('empathy');
    expect(body.weakest_dimension).toBe('assertiveness');
  });

  it('records personal records per scenario and difficulty', async () => {
    const s1 = await createAndDebrief();
    getDb()
      .prepare(
        `UPDATE session_events
         SET payload_json = '{"summary":"x","scores":{},"overall_score":70}'
         WHERE session_id = ? AND event_type = 'debrief_generated'`,
      )
      .run(s1);

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.personal_records.length).toBeGreaterThan(0);
    expect(body.personal_records[0].best_score).toBe(70);
  });

  it('computes last_session_delta when two or more debriefs exist', async () => {
    const s1 = await createAndDebrief();
    const s2 = await createAndDebrief();
    getDb()
      .prepare(
        `UPDATE session_events
         SET payload_json = '{"summary":"x","scores":{},"overall_score":60}'
         WHERE session_id = ? AND event_type = 'debrief_generated'`,
      )
      .run(s1);
    getDb()
      .prepare(
        `UPDATE session_events
         SET payload_json = '{"summary":"x","scores":{},"overall_score":80}'
         WHERE session_id = ? AND event_type = 'debrief_generated'`,
      )
      .run(s2);
    // Make s2 the most recent by giving it an ended_at one second ahead of s1.
    // Use ISO format to match the format written by the /end and /debrief handlers.
    const futureIso = new Date(Date.now() + 2000).toISOString();
    getDb()
      .prepare('UPDATE sessions SET ended_at = ? WHERE session_id = ?')
      .run(futureIso, s2);

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    // s2 (score 80) is most recent; s1 (score 60) is penultimate → delta = 80 - 60 = 20
    expect(body.last_session_delta).toBe(20);
  });

  it('returns null last_session_delta when only one session with a debrief exists', async () => {
    await createAndDebrief();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/profile' });
    const body = res.json<LogbookProfile>();
    expect(body.last_session_delta).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// GET /api/logbook/export
// ---------------------------------------------------------------------------

describe('GET /api/logbook/export', () => {
  it('returns 200 with exported_at, profile, and session_scores fields', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/logbook/export' });
    expect(res.statusCode).toBe(200);
    const body = res.json<LogbookExport>();
    expect(body.exported_at).toBeDefined();
    expect(body.profile).toBeDefined();
    expect(Array.isArray(body.session_scores)).toBe(true);
  });

  it('includes session scores for ended sessions', async () => {
    await createAndDebrief();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/export' });
    const body = res.json<LogbookExport>();
    expect(body.session_scores.length).toBe(1);
    expect(body.session_scores[0].scenario_id).toBe('behavioral_interview');
    expect(body.session_scores[0].difficulty).toBe('normal');
  });

  it('has an ISO timestamp for exported_at', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/logbook/export' });
    const body = res.json<LogbookExport>();
    expect(new Date(body.exported_at).toISOString()).toBe(body.exported_at);
  });

  it('export profile and session_scores are consistent', async () => {
    await createAndDebrief();
    await createAndDebrief();

    const res = await app.inject({ method: 'GET', url: '/api/logbook/export' });
    const body = res.json<LogbookExport>();
    expect(body.profile.total_sessions).toBe(body.session_scores.length);
  });
});

// ---------------------------------------------------------------------------
// GET /api/sessions — extended fields
// ---------------------------------------------------------------------------

describe('GET /api/sessions — logbook fields', () => {
  it('includes ending_type and turn_count in list response', async () => {
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/sessions' });
    const body = res.json<{ sessions: Array<{ ending_type: string | null; turn_count: number }> }>();
    expect(body.sessions[0].ending_type).toBe('player_exit');
    expect(typeof body.sessions[0].turn_count).toBe('number');
  });

  it('includes ended_at in list response for ended sessions', async () => {
    await createAndEndSession();

    const res = await app.inject({ method: 'GET', url: '/api/sessions' });
    const body = res.json<{ sessions: Array<{ ended_at: string | null }> }>();
    expect(body.sessions[0].ended_at).not.toBeNull();
  });

  it('ended_at is null for sessions that have not been ended', async () => {
    await app.inject({ method: 'POST', url: '/api/sessions', payload: validRequest });

    const res = await app.inject({ method: 'GET', url: '/api/sessions' });
    const body = res.json<{ sessions: Array<{ ended_at: string | null }> }>();
    expect(body.sessions[0].ended_at).toBeNull();
  });
});
