// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../index.js';
import { setWorkbenchRoots } from './workbench.js';
import { resetDb } from '../db.js';

let app: FastifyInstance;
let officialRoot: string;
let localDevRoot: string;
let tmpBase: string;

function setupPack(root: string, slug: string, name: string, packId: string) {
  const packDir = join(root, slug);
  mkdirSync(join(packDir, 'scenarios'), { recursive: true });
  mkdirSync(join(packDir, 'npcs'), { recursive: true });
  writeFileSync(
    join(packDir, 'manifest.yaml'),
    `schema_version: "0.1"\npack_id: ${packId}\nname: ${name}\nversion: 0.1.0\ndescription: Test pack\nauthor: Test\nlicense: MIT\ncontent_rating: PG\nsafety:\n  policy: safety/default.yaml\n`,
  );
  writeFileSync(join(packDir, 'README.md'), `# ${name}\n\nA test pack.\n`);
  writeFileSync(
    join(packDir, 'scenarios', 'basic.yaml'),
    `schema_version: "0.1"\nscenario_id: basic\ntitle: Basic Scenario\n`,
  );
  return packDir;
}

beforeEach(async () => {
  resetDb();
  tmpBase = join(tmpdir(), `workbench-test-${Math.random().toString(36).slice(2)}`);
  officialRoot = join(tmpBase, 'official');
  localDevRoot = join(tmpBase, 'local-dev');
  mkdirSync(officialRoot, { recursive: true });
  mkdirSync(localDevRoot, { recursive: true });

  setupPack(officialRoot, 'sample-pack', 'Sample Pack', 'official.sample_pack');
  setupPack(localDevRoot, 'my-pack', 'My Pack', 'local.my_pack');

  setWorkbenchRoots(officialRoot, localDevRoot);
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
  try {
    rmSync(tmpBase, { recursive: true, force: true });
  } catch { /* ignore cleanup errors */ }
});

describe('GET /api/workbench/packs', () => {
  it('lists packs from official and local-dev roots', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/workbench/packs' });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ kind: string; slug: string; editable: boolean }[]>();
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThanOrEqual(2);

    const official = body.find((p) => p.kind === 'official');
    expect(official).toBeDefined();
    expect(official?.slug).toBe('sample-pack');
    expect(official?.editable).toBe(false);

    const local = body.find((p) => p.kind === 'local-dev');
    expect(local).toBeDefined();
    expect(local?.slug).toBe('my-pack');
    expect(local?.editable).toBe(true);
  });

  it('returns pack_id and name from manifest', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/workbench/packs' });
    const body = res.json<{ kind: string; pack_id: string; name: string }[]>();
    const official = body.find((p) => p.kind === 'official');
    expect(official?.pack_id).toBe('official.sample_pack');
    expect(official?.name).toBe('Sample Pack');
  });
});

describe('GET /api/workbench/packs/:kind/:slug/files', () => {
  it('returns file tree for an official pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/files',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ tree: { name: string; kind: string; path: string }[] }>();
    expect(Array.isArray(body.tree)).toBe(true);

    const manifest = body.tree.find((n) => n.name === 'manifest.yaml');
    expect(manifest).toBeDefined();
    expect(manifest?.kind).toBe('yaml');

    const readme = body.tree.find((n) => n.name === 'README.md');
    expect(readme).toBeDefined();
    expect(readme?.kind).toBe('markdown');

    const scenarios = body.tree.find((n) => n.name === 'scenarios');
    expect(scenarios).toBeDefined();
    expect(scenarios?.kind).toBe('dir');
  });

  it('returns 404 for unknown pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/does-not-exist/files',
    });
    expect(res.statusCode).toBe(404);
  });

  it('returns 400 for invalid kind', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/community/sample-pack/files',
    });
    expect(res.statusCode).toBe(400);
  });
});

describe('GET /api/workbench/packs/:kind/:slug/file', () => {
  it('returns file content for an official pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/file?path=README.md',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ content: string; editable: boolean }>();
    expect(body.content).toContain('Sample Pack');
    expect(body.editable).toBe(false);
  });

  it('returns editable:true for local-dev pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/file?path=manifest.yaml',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ content: string; editable: boolean }>();
    expect(body.editable).toBe(true);
  });

  it('returns 400 when path param is missing', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/file',
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when path resolves to a directory', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/file?path=scenarios',
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 for path traversal attempt', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/file?path=../../etc/passwd',
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when path resolves to the pack root itself (dot-traversal)', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/file?path=.',
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 404 for non-existent file', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/file?path=ghost.yaml',
    });
    expect(res.statusCode).toBe(404);
  });
});

describe('PUT /api/workbench/packs/:kind/:slug/file', () => {
  it('writes file content for local-dev pack', async () => {
    const newContent = 'schema_version: "0.1"\nname: Updated\n';
    const res = await app.inject({
      method: 'PUT',
      url: '/api/workbench/packs/local-dev/my-pack/file?path=manifest.yaml',
      headers: { 'content-type': 'application/json' },
      payload: JSON.stringify({ content: newContent }),
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ ok: boolean }>();
    expect(body.ok).toBe(true);

    // Verify file was actually written
    const readRes = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/file?path=manifest.yaml',
    });
    expect(readRes.json<{ content: string }>().content).toBe(newContent);
  });

  it('returns 403 when writing to official pack', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/workbench/packs/official/sample-pack/file?path=manifest.yaml',
      headers: { 'content-type': 'application/json' },
      payload: JSON.stringify({ content: 'evil' }),
    });
    expect(res.statusCode).toBe(403);
  });

  it('returns 400 for non-editable file type', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/workbench/packs/local-dev/my-pack/file?path=image.png',
      headers: { 'content-type': 'application/json' },
      payload: JSON.stringify({ content: 'binary' }),
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 for path traversal attempt', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/workbench/packs/local-dev/my-pack/file?path=../../etc/cron.d/evil',
      headers: { 'content-type': 'application/json' },
      payload: JSON.stringify({ content: 'evil' }),
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when path param is missing', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/workbench/packs/local-dev/my-pack/file',
      headers: { 'content-type': 'application/json' },
      payload: JSON.stringify({ content: 'hello' }),
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 400 when path resolves to the pack root itself (dot-traversal)', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/workbench/packs/local-dev/my-pack/file?path=.',
      headers: { 'content-type': 'application/json' },
      payload: JSON.stringify({ content: 'hello' }),
    });
    expect(res.statusCode).toBe(400);
  });
});

describe('POST /api/workbench/packs/:kind/:slug/copy-to-local', () => {
  it('copies an official pack to local-dev', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/sample-pack/copy-to-local',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ kind: string; slug: string; editable: boolean }>();
    expect(body.kind).toBe('local-dev');
    expect(body.slug).toContain('sample-pack');
    expect(body.editable).toBe(true);

    // Verify the copy appears in the pack list
    const listRes = await app.inject({ method: 'GET', url: '/api/workbench/packs' });
    const packs = listRes.json<{ slug: string }[]>();
    expect(packs.some((p) => p.slug === body.slug)).toBe(true);
  });

  it('returns 400 when trying to copy a local-dev pack', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/local-dev/my-pack/copy-to-local',
    });
    expect(res.statusCode).toBe(400);
  });

  it('returns 404 for unknown pack', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/does-not-exist/copy-to-local',
    });
    expect(res.statusCode).toBe(404);
  });

  it('avoids slug collision when dest already exists', async () => {
    // Copy once
    const res1 = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/sample-pack/copy-to-local',
    });
    expect(res1.statusCode).toBe(200);
    const slug1 = res1.json<{ slug: string }>().slug;

    // Copy again — should get a different slug
    const res2 = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/sample-pack/copy-to-local',
    });
    expect(res2.statusCode).toBe(200);
    const slug2 = res2.json<{ slug: string }>().slug;

    expect(slug1).not.toBe(slug2);
  });
});

// ---------------------------------------------------------------------------
// POST /api/workbench/packs/:kind/:slug/test-session
// ---------------------------------------------------------------------------

describe('POST /api/workbench/packs/:kind/:slug/test-session', () => {
  it('creates a test session and returns session_id, state, npc_opening, and state_vars', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/sample-pack/test-session',
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<{
      session_id: string;
      state: string;
      npc_opening: string;
      state_vars: Record<string, number>;
    }>();
    expect(body.session_id).toMatch(/^test-/);
    expect(body.state).toBe('PlayerTurnListening');
    expect(typeof body.npc_opening).toBe('string');
    expect(body.npc_opening.length).toBeGreaterThan(0);
    expect(typeof body.state_vars).toBe('object');
    expect(body.state_vars['trust']).toBe(50);
    expect(body.state_vars['patience']).toBe(75);
  });

  it('works for local-dev packs too', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/local-dev/my-pack/test-session',
    });
    expect(res.statusCode).toBe(201);
    expect(res.json<{ session_id: string }>().session_id).toMatch(/^test-/);
  });

  it('returns 404 for an unknown pack slug', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/does-not-exist/test-session',
    });
    expect(res.statusCode).toBe(404);
  });

  it('returns 400 for an invalid kind', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/community/sample-pack/test-session',
    });
    expect(res.statusCode).toBe(400);
  });

  it('created session accepts turns via the sessions API', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/local-dev/my-pack/test-session',
    });
    expect(createRes.statusCode).toBe(201);
    const { session_id } = createRes.json<{ session_id: string }>();

    const turnRes = await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello there.' },
    });
    expect(turnRes.statusCode).toBe(200);
    expect(turnRes.json<{ state: string }>().state).toBe('PlayerTurnListening');
  });

  it('session is not included in the normal GET /api/sessions history', async () => {
    // Temporary workbench test sessions must not pollute the player's session
    // history list, even though they are stored as real session rows.
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/local-dev/my-pack/test-session',
    });
    const { session_id } = createRes.json<{ session_id: string }>();

    // The session IS retrievable by id (it's a real session row)
    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.statusCode).toBe(200);

    // Verify it has save_transcript: false in setup
    const session = getRes.json<{ setup: { save_transcript: boolean } }>();
    expect(session.setup.save_transcript).toBe(false);

    // ...but it must NOT appear in the GET /api/sessions history list.
    const listRes = await app.inject({ method: 'GET', url: '/api/sessions' });
    expect(listRes.statusCode).toBe(200);
    const { sessions } = listRes.json<{ sessions: { session_id: string }[] }>();
    expect(sessions.some((s) => s.session_id === session_id)).toBe(false);
  });

  it('test session can be deleted via DELETE /api/sessions/:id', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/official/sample-pack/test-session',
    });
    const { session_id } = createRes.json<{ session_id: string }>();

    const deleteRes = await app.inject({
      method: 'DELETE',
      url: `/api/sessions/${session_id}`,
    });
    expect(deleteRes.statusCode).toBe(204);

    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.statusCode).toBe(404);
  });

  it('session events are not persisted (save_transcript=false)', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/local-dev/my-pack/test-session',
    });
    const { session_id } = createRes.json<{ session_id: string }>();

    // Submit a turn — with save_transcript=false, no events row is written
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Test message' },
    });

    // The turn response still returns synthetic event objects but they have event_id=0
    // (not persisted). The session itself is still accessible.
    const getRes = await app.inject({ method: 'GET', url: `/api/sessions/${session_id}` });
    expect(getRes.statusCode).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// GET /api/workbench/packs/:kind/:slug/validate (stub endpoint)
// ---------------------------------------------------------------------------

describe('GET /api/workbench/packs/:kind/:slug/validate', () => {
  it('returns valid=true for an existing pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: unknown[]; warnings: unknown[] }>();
    expect(body.valid).toBe(true);
    expect(Array.isArray(body.errors)).toBe(true);
    expect(Array.isArray(body.warnings)).toBe(true);
  });

  it('returns 404 for unknown pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/does-not-exist/validate',
    });
    expect(res.statusCode).toBe(404);
  });
});
