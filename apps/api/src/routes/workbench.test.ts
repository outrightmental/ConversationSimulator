// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdirSync, writeFileSync, rmSync, symlinkSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import AdmZip from 'adm-zip';
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
  mkdirSync(join(packDir, 'rubrics'), { recursive: true });
  mkdirSync(join(packDir, 'safety'), { recursive: true });
  writeFileSync(
    join(packDir, 'manifest.yaml'),
    `schema_version: "0.1"\npack_id: ${packId}\nname: ${name}\nversion: 0.1.0\ndescription: Test pack\nauthor: Test\nlicense: MIT\ncontent_rating: PG\nsafety:\n  policy: safety/default.yaml\n`,
  );
  writeFileSync(join(packDir, 'README.md'), `# ${name}\n\nA test pack.\n`);
  writeFileSync(
    join(packDir, 'safety', 'default.yaml'),
    `schema_version: "0.1"\npolicy_id: default\ncontent_rating_cap: PG\ncontent_categories: {}\n`,
  );
  writeFileSync(
    join(packDir, 'npcs', 'npc.yaml'),
    `schema_version: "0.1"\nnpc_id: test_npc\ndisplay_name: Test NPC\narchetype: helper\nfictional: true\nage_band: adult\npublic_persona:\n  occupation: Tester\n  speaking_style: direct\n  demeanor: neutral\nprivate_persona: {}\n`,
  );
  writeFileSync(
    join(packDir, 'rubrics', 'rubric.yaml'),
    `schema_version: "0.1"\nrubric_id: test_rubric\ntitle: Test Rubric\ndimensions:\n  - id: clarity\n    name: Clarity\n    description: How clear was the communication\n    scoring:\n      low: Unclear\n      medium: Somewhat clear\n      high: Very clear\n`,
  );
  writeFileSync(
    join(packDir, 'scenarios', 'basic.yaml'),
    `schema_version: "0.1"\nscenario_id: basic\ntitle: Basic Scenario\nsummary: A basic test scenario.\nplayer_role:\n  label: Tester\n  brief: You are testing the NPC.\nnpc:\n  ref: ../npcs/npc.yaml\nrubric:\n  ref: ../rubrics/rubric.yaml\nduration:\n  max_turns: 10\nopening:\n  npc_says: Hello!\ngoals: {}\n`,
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

describe('GET /api/workbench/packs/:kind/:slug/validate', () => {
  it('returns valid:true for a well-formed pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: unknown[]; warnings: unknown[] }>();
    expect(body.valid).toBe(true);
    expect(body.errors).toHaveLength(0);
    expect(body.warnings).toHaveLength(0);
  });

  it('returns validation errors for a pack with a missing required field', async () => {
    // Overwrite manifest with an invalid YAML that is missing required fields
    const packDir = join(localDevRoot, 'my-pack');
    writeFileSync(
      join(packDir, 'manifest.yaml'),
      // Missing: version, author, license, etc.
      `schema_version: "0.1"\npack_id: local.my_pack\nname: My Pack\n`,
    );

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: { rule_id: string; file: string; severity: string }[] }>();
    expect(body.valid).toBe(false);
    expect(body.errors.length).toBeGreaterThan(0);
    expect(body.errors.every((e) => e.severity === 'error')).toBe(true);
    // All errors should be associated with a file
    expect(body.errors.every((e) => typeof e.file === 'string')).toBe(true);
  });

  it('returns multiple SCHEMA_VIOLATION errors when a file has several missing fields', async () => {
    const packDir = join(localDevRoot, 'my-pack');
    writeFileSync(
      join(packDir, 'manifest.yaml'),
      // schema_version present but many required fields missing
      `schema_version: "0.1"\npack_id: local.my_pack\n`,
    );

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: { rule_id: string }[] }>();
    expect(body.valid).toBe(false);
    // AJV allErrors:true produces one issue per missing field
    expect(body.errors.length).toBeGreaterThan(1);
  });

  it('returns FORBIDDEN_FILE errors for executable files and collects all of them', async () => {
    const packDir = join(localDevRoot, 'my-pack');
    writeFileSync(join(packDir, 'run.sh'), '#!/bin/sh\necho hello\n');
    writeFileSync(join(packDir, 'setup.py'), 'print("hi")\n');

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: { rule_id: string; category: string; file: string }[] }>();
    expect(body.valid).toBe(false);
    const secErrors = body.errors.filter((e) => e.rule_id === 'FORBIDDEN_FILE');
    // Both forbidden files should be reported, not just the first one
    expect(secErrors.length).toBeGreaterThanOrEqual(2);
    expect(secErrors.every((e) => e.category === 'security')).toBe(true);
  });

  it('flags a disguised binary (allowed extension, executable content) as a security issue', async () => {
    const packDir = join(localDevRoot, 'my-pack');
    // A .yaml file whose bytes are actually an ELF executable header. Phase 1's
    // extension scan can't catch this; only the loader's magic-byte check does.
    // The file-specific dedup must not suppress this loader-only finding.
    writeFileSync(join(packDir, 'notes.yaml'), Buffer.from([0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01]));

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: { rule_id: string; category: string; file: string }[] }>();
    expect(body.valid).toBe(false);
    const binary = body.errors.find((e) => e.rule_id === 'FORBIDDEN_BINARY');
    expect(binary).toBeDefined();
    expect(binary?.category).toBe('security');
    expect(binary?.file).toBe('notes.yaml');
  });

  it('flags symlinks as forbidden without following them', async () => {
    const packDir = join(localDevRoot, 'my-pack');
    // A symlink pointing outside the pack — must be reported, never followed.
    symlinkSync(tmpBase, join(packDir, 'escape-link'));

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<{ valid: boolean; errors: { rule_id: string; category: string; file: string }[] }>();
    expect(body.valid).toBe(false);
    const link = body.errors.find((e) => e.file === 'escape-link');
    expect(link).toBeDefined();
    expect(link?.rule_id).toBe('FORBIDDEN_FILE');
    expect(link?.category).toBe('security');
    // No error should reference a path outside the pack (i.e. the symlink was not followed).
    expect(body.errors.every((e) => !e.file.startsWith('..'))).toBe(true);
  });

  it('returns 404 for a non-existent pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/does-not-exist/validate',
    });
    expect(res.statusCode).toBe(404);
  });

  it('returns 400 for an invalid kind', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/community/sample-pack/validate',
    });
    expect(res.statusCode).toBe(400);
  });

  it('includes suggested_fix for each error', async () => {
    const packDir = join(localDevRoot, 'my-pack');
    writeFileSync(join(packDir, 'manifest.yaml'), `schema_version: "0.1"\npack_id: local.my_pack\n`);

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/validate',
    });
    const body = res.json<{ errors: { suggested_fix: string }[] }>();
    expect(body.errors.every((e) => typeof e.suggested_fix === 'string' && e.suggested_fix.length > 0)).toBe(true);
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

// ---------------------------------------------------------------------------
// Helper: build a valid zip from the fixture pack in a temp directory
// ---------------------------------------------------------------------------

function buildValidZip(packDir: string): Buffer {
  const zip = new AdmZip();
  zip.addLocalFolder(packDir, '');
  return zip.toBuffer();
}

// ---------------------------------------------------------------------------
// GET /api/workbench/packs/:kind/:slug/export
// ---------------------------------------------------------------------------

describe('GET /api/workbench/packs/:kind/:slug/export', () => {
  it('returns a zip binary for a valid local-dev pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/export',
    });
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('application/zip');
    expect(res.headers['content-disposition']).toContain('.zip');
    expect(res.rawPayload.length).toBeGreaterThan(0);

    // Verify the zip is actually readable and contains key pack files.
    const zip = new AdmZip(res.rawPayload);
    const names = zip.getEntries().map((e) => e.entryName);
    expect(names).toContain('manifest.yaml');
    expect(names).toContain('README.md');
  });

  it('returns a zip for an official pack too', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/official/sample-pack/export',
    });
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('application/zip');
  });

  it('zip entries use relative paths only — no absolute paths', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/export',
    });
    expect(res.statusCode).toBe(200);
    const zip = new AdmZip(res.rawPayload);
    for (const entry of zip.getEntries()) {
      // Entry names must be relative (never start with / or a Windows drive letter).
      expect(entry.entryName).not.toMatch(/^[/\\]/);
      expect(entry.entryName).not.toMatch(/^[A-Za-z]:\\/);
    }
  });

  it('returns 422 with validation errors when the pack is invalid', async () => {
    // Corrupt the manifest so validation fails.
    writeFileSync(
      join(localDevRoot, 'my-pack', 'manifest.yaml'),
      `schema_version: "0.1"\npack_id: local.my_pack\n`,
    );

    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/export',
    });
    expect(res.statusCode).toBe(422);
    const body = res.json<{ valid: boolean; errors: unknown[] }>();
    expect(body.valid).toBe(false);
    expect(body.errors.length).toBeGreaterThan(0);
  });

  it('returns 404 for a non-existent pack', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/ghost/export',
    });
    expect(res.statusCode).toBe(404);
  });

  it('returns 400 for an invalid kind', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/community/sample-pack/export',
    });
    expect(res.statusCode).toBe(400);
  });
});

// ---------------------------------------------------------------------------
// POST /api/workbench/packs/import
// ---------------------------------------------------------------------------

describe('POST /api/workbench/packs/import', () => {
  it('imports a valid zip and returns the new pack summary', async () => {
    const packDir = join(officialRoot, 'sample-pack');
    const zipBuffer = buildValidZip(packDir);

    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });

    expect(res.statusCode).toBe(201);
    const body = res.json<{ kind: string; slug: string; editable: boolean; pack_id: string }>();
    expect(body.kind).toBe('local-dev');
    expect(body.editable).toBe(true);
    expect(body.pack_id).toBe('official.sample_pack');

    // Verify the pack actually landed in local-dev.
    expect(existsSync(join(localDevRoot, body.slug))).toBe(true);
    expect(existsSync(join(localDevRoot, body.slug, 'manifest.yaml'))).toBe(true);
  });

  it('appears in the pack list after import', async () => {
    const zipBuffer = buildValidZip(join(officialRoot, 'sample-pack'));
    await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });

    const listRes = await app.inject({ method: 'GET', url: '/api/workbench/packs' });
    const packs = listRes.json<{ kind: string; slug: string }[]>();
    expect(packs.some((p) => p.kind === 'local-dev' && p.slug.startsWith('official.sample_pack'))).toBe(true);
  });

  it('renames slug on conflict by default', async () => {
    const zipBuffer = buildValidZip(join(officialRoot, 'sample-pack'));

    const res1 = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    const slug1 = res1.json<{ slug: string }>().slug;

    const res2 = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(res2.statusCode).toBe(201);
    const body2 = res2.json<{ slug: string; renamed_from?: string }>();
    expect(body2.slug).not.toBe(slug1);
    expect(body2.renamed_from).toBe(slug1);
  });

  it('overwrites existing pack when conflict=overwrite', async () => {
    const zipBuffer = buildValidZip(join(officialRoot, 'sample-pack'));

    const res1 = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    const slug1 = res1.json<{ slug: string }>().slug;

    const res2 = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import?conflict=overwrite',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(res2.statusCode).toBe(201);
    const body2 = res2.json<{ slug: string; renamed_from?: string }>();
    // Same slug — no rename needed.
    expect(body2.slug).toBe(slug1);
    expect(body2.renamed_from).toBeUndefined();
  });

  it('returns 422 with validation errors for an invalid zip', async () => {
    // Build a zip with an invalid manifest (missing required fields).
    const zip = new AdmZip();
    zip.addFile('manifest.yaml', Buffer.from(`schema_version: "0.1"\npack_id: bad.pack\n`));
    const zipBuffer = zip.toBuffer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(res.statusCode).toBe(422);
    const body = res.json<{ valid: boolean; errors: unknown[] }>();
    expect(body.valid).toBe(false);
    expect(body.errors.length).toBeGreaterThan(0);
  });

  it('rejects a zip containing a forbidden executable file', async () => {
    const zip = new AdmZip();
    zip.addFile('run.sh', Buffer.from('#!/bin/sh\necho hi\n'));
    // Also add a plausible manifest so the zip extracts to something
    zip.addFile('manifest.yaml', Buffer.from('schema_version: "0.1"\npack_id: evil.pack\n'));
    const zipBuffer = zip.toBuffer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(res.statusCode).toBe(422);
    const body = res.json<{ valid: boolean; errors: { rule_id: string }[] }>();
    expect(body.valid).toBe(false);
    const forbidden = body.errors.find((e) => e.rule_id === 'FORBIDDEN_FILE');
    expect(forbidden).toBeDefined();
  });

  it('rejects a zip containing a zip-slip path', async () => {
    const zip = new AdmZip();
    zip.addFile('../escape.yaml', Buffer.from('evil: true\n'));
    const zipBuffer = zip.toBuffer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 422 when the body is not a valid zip archive', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: Buffer.from('not a zip file'),
    });
    expect(res.statusCode).toBe(422);
  });

  it('returns 400 when the body is empty', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: Buffer.alloc(0),
    });
    expect(res.statusCode).toBe(400);
  });

  it('export then import round-trip produces an equivalent pack', async () => {
    // Export the local-dev my-pack, then re-import it.
    const exportRes = await app.inject({
      method: 'GET',
      url: '/api/workbench/packs/local-dev/my-pack/export',
    });
    expect(exportRes.statusCode).toBe(200);

    const importRes = await app.inject({
      method: 'POST',
      url: '/api/workbench/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: exportRes.rawPayload,
    });
    expect(importRes.statusCode).toBe(201);
    const imported = importRes.json<{ kind: string; pack_id: string; editable: boolean }>();
    expect(imported.kind).toBe('local-dev');
    expect(imported.pack_id).toBe('local.my_pack');
    expect(imported.editable).toBe(true);

    // The imported copy should validate cleanly.
    const validateRes = await app.inject({
      method: 'GET',
      url: `/api/workbench/packs/local-dev/${importRes.json<{ slug: string }>().slug}/validate`,
    });
    expect(validateRes.statusCode).toBe(200);
    expect(validateRes.json<{ valid: boolean }>().valid).toBe(true);
  });
});
