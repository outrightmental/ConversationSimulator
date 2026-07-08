// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import { resetDb, getDb } from '../db.js';
import type { FastifyInstance } from 'fastify';
import type { RuntimeSettingsResponse } from '@convsim/shared';

let app: FastifyInstance;

beforeEach(async () => {
  resetDb();
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
});

// ── GET /api/runtime/settings ─────────────────────────────────────────────────

describe('GET /api/runtime/settings', () => {
  it('returns 200 with all null settings on a fresh DB', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    expect(res.statusCode).toBe(200);
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.settings.context_length).toBeNull();
    expect(body.settings.gpu_layers).toBeNull();
    expect(body.settings.threads).toBeNull();
    expect(body.settings.temperature).toBeNull();
    expect(body.settings.top_p).toBeNull();
    expect(body.settings.repeat_penalty).toBeNull();
  });

  it('returns requires_restart: false on initial GET', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(false);
  });

  it('returns recommended field with all nulls', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.recommended).toMatchObject({
      context_length: null,
      gpu_layers: null,
      threads: null,
      temperature: null,
      top_p: null,
      repeat_penalty: null,
    });
  });
});

// ── PUT /api/runtime/settings ─────────────────────────────────────────────────

describe('PUT /api/runtime/settings', () => {
  it('returns 200 and updated settings', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 4096, temperature: 0.7 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.settings.context_length).toBe(4096);
    expect(body.settings.temperature).toBe(0.7);
  });

  it('persists settings across requests', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { gpu_layers: 32, threads: 8 },
    });
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.settings.gpu_layers).toBe(32);
    expect(body.settings.threads).toBe(8);
  });

  it('returns requires_restart: true when context_length changes', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 8192 },
    });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(true);
  });

  it('returns requires_restart: true when gpu_layers changes', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { gpu_layers: -1 },
    });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(true);
  });

  it('returns requires_restart: false when only temperature changes', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { temperature: 0.9 },
    });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(false);
  });

  it('returns requires_restart: false when only top_p changes', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { top_p: 0.95 },
    });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(false);
  });

  it('returns requires_restart: false when only repeat_penalty changes', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { repeat_penalty: 1.1 },
    });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(false);
  });

  it('allows setting fields back to null', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 4096 },
    });
    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: null },
    });
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    expect(res.json<RuntimeSettingsResponse>().settings.context_length).toBeNull();
  });

  it('accepts -1 as a valid gpu_layers value', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { gpu_layers: -1 },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json<RuntimeSettingsResponse>().settings.gpu_layers).toBe(-1);
  });
});

// ── PUT /api/runtime/settings — server-side validation ───────────────────────

describe('PUT /api/runtime/settings — validation', () => {
  it('returns 422 when context_length is below 512', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 128 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when context_length is above 131072', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 200000 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when gpu_layers is below -1', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { gpu_layers: -5 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when gpu_layers is above 256', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { gpu_layers: 512 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when threads is 0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { threads: 0 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when threads is above 64', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { threads: 128 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when temperature is negative', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { temperature: -0.1 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when temperature exceeds 2.0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { temperature: 3.0 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when top_p exceeds 1.0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { top_p: 1.5 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when repeat_penalty is below 1.0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { repeat_penalty: 0.5 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when repeat_penalty exceeds 2.0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { repeat_penalty: 3.0 },
    });
    expect(res.statusCode).toBe(422);
  });

  it('includes a descriptive message in 422 responses', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 100 },
    });
    const body = res.json<{ message: string }>();
    expect(body.message).toMatch(/512/);
  });

  it('does not persist settings when validation fails', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 100 },
    });
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    expect(res.json<RuntimeSettingsResponse>().settings.context_length).toBeNull();
  });
});

// ── POST /api/runtime/settings/reset ─────────────────────────────────────────

describe('POST /api/runtime/settings/reset', () => {
  it('returns 200 with all null settings', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 4096, temperature: 0.7, gpu_layers: 32 },
    });
    const res = await app.inject({ method: 'POST', url: '/api/runtime/settings/reset' });
    expect(res.statusCode).toBe(200);
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.settings.context_length).toBeNull();
    expect(body.settings.temperature).toBeNull();
    expect(body.settings.gpu_layers).toBeNull();
  });

  it('returns requires_restart: true after reset', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/runtime/settings/reset' });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.requires_restart).toBe(true);
  });

  it('GET /api/runtime/settings returns nulls after reset', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { threads: 8, top_p: 0.95 },
    });
    await app.inject({ method: 'POST', url: '/api/runtime/settings/reset' });
    const res = await app.inject({ method: 'GET', url: '/api/runtime/settings' });
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.settings.threads).toBeNull();
    expect(body.settings.top_p).toBeNull();
  });
});

// ── Persistence across buildApp calls (simulating restarts) ──────────────────

describe('runtime settings — persistence across restarts', () => {
  it('settings survive a simulated restart (new app instance, same DB)', async () => {
    const db = getDb();

    await app.inject({
      method: 'PUT',
      url: '/api/runtime/settings',
      payload: { context_length: 16384, temperature: 0.8 },
    });
    await app.close();

    // Build a new app instance with the same DB
    const app2 = await buildApp();
    // Swap the module-level DB reference to the existing one
    db.pragma('integrity_check');

    const res = await app2.inject({ method: 'GET', url: '/api/runtime/settings' });
    expect(res.statusCode).toBe(200);
    const body = res.json<RuntimeSettingsResponse>();
    expect(body.settings.context_length).toBe(16384);
    expect(body.settings.temperature).toBe(0.8);

    await app2.close();
  });
});
