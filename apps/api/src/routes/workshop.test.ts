// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../index.js';
import { setWorkshopRoot, setWorkshopPacksDbPath } from './workshop.js';
import { setPacksDbPath, setPacksDataDir } from './packs.js';
import { setScenariosDbPath } from './scenarios.js';
import { resetDb, getDb } from '../db.js';

let app: FastifyInstance;
let workshopRoot: string;
let packsDbPath: string;
let tmpBase: string;

// Writes a minimal valid pack directory to the given parent dir under `slug`.
function setupValidPack(parentDir: string, slug: string, packId: string): string {
  const packDir = join(parentDir, slug);
  mkdirSync(join(packDir, 'scenarios'), { recursive: true });
  mkdirSync(join(packDir, 'npcs'), { recursive: true });
  mkdirSync(join(packDir, 'rubrics'), { recursive: true });
  mkdirSync(join(packDir, 'safety'), { recursive: true });
  writeFileSync(
    join(packDir, 'manifest.yaml'),
    `schema_version: "0.1"\npack_id: ${packId}\nname: Workshop Pack\nversion: 0.1.0\ndescription: A workshop pack\nauthor: WorkshopCreator\nlicense: MIT\ncontent_rating: PG\nsafety:\n  policy: safety/default.yaml\n`,
  );
  writeFileSync(
    join(packDir, 'safety', 'default.yaml'),
    `schema_version: "0.1"\npolicy_id: default\ncontent_rating_cap: PG\ncontent_categories: {}\nredirect_message: ""\n`,
  );
  writeFileSync(
    join(packDir, 'npcs', 'npc.yaml'),
    `schema_version: "0.1"\nnpc_id: ws_npc\ndisplay_name: Workshop NPC\narchetype: helper\nfictional: true\nage_band: adult\npublic_persona:\n  occupation: Tester\n  speaking_style: direct\n  demeanor: neutral\nprivate_persona: {}\n`,
  );
  writeFileSync(
    join(packDir, 'rubrics', 'rubric.yaml'),
    `schema_version: "0.1"\nrubric_id: ws_rubric\ntitle: Workshop Rubric\ndimensions:\n  - id: clarity\n    name: Clarity\n    description: How clear\n    scoring:\n      low: Unclear\n      medium: Somewhat clear\n      high: Very clear\n`,
  );
  writeFileSync(
    join(packDir, 'scenarios', 'basic.yaml'),
    `schema_version: "0.1"\nscenario_id: ws_basic\ntitle: Workshop Basic\nsummary: A workshop scenario.\nplayer_role:\n  label: Tester\n  brief: You are testing.\nnpc:\n  ref: ../npcs/npc.yaml\nrubric:\n  ref: ../rubrics/rubric.yaml\nduration:\n  max_turns: 10\nopening:\n  npc_says: Hello from Workshop!\ngoals: {}\n`,
  );
  return packDir;
}

beforeEach(async () => {
  resetDb();
  tmpBase = join(tmpdir(), `workshop-test-${Math.random().toString(36).slice(2)}`);
  workshopRoot = join(tmpBase, 'workshop');
  mkdirSync(workshopRoot, { recursive: true });
  setWorkshopRoot(workshopRoot);
  // Wire the shared pack index so workshop imports register into installed_packs
  // and become visible via /api/packs and /api/scenarios, exactly like manual import.
  packsDbPath = join(tmpBase, 'packs.db');
  mkdirSync(join(tmpBase, 'packs-data'), { recursive: true });
  setWorkshopPacksDbPath(packsDbPath);
  setPacksDbPath(packsDbPath);
  setPacksDataDir(join(tmpBase, 'packs-data'));
  setScenariosDbPath(packsDbPath);
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
  setWorkshopPacksDbPath(null);
  setPacksDbPath(null);
  setPacksDataDir(null);
  setScenariosDbPath(null);
  try { rmSync(tmpBase, { recursive: true, force: true }); } catch { /* ignore */ }
});

// ---------------------------------------------------------------------------
// POST /api/workshop/sync
// ---------------------------------------------------------------------------

describe('POST /api/workshop/sync', () => {
  it('returns 400 when body has no items array', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/workshop/sync', payload: {} });
    expect(res.statusCode).toBe(400);
  });

  it('skips items with missing item_id', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: { items: [{ install_path: '/some/path', needs_update: false, updated_at: 0 }] },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { results: Array<{ status: string }> };
    expect(body.results[0]?.status).toBe('skipped');
  });

  it('skips items with empty install_path (not yet downloaded)', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: { items: [{ item_id: '123', install_path: '', needs_update: false, updated_at: 0 }] },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { results: Array<{ status: string }> };
    expect(body.results[0]?.status).toBe('skipped');
  });

  it('skips items whose install_path does not exist', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '456',
          install_path: '/nonexistent/path/12345',
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { results: Array<{ status: string }> };
    expect(body.results[0]?.status).toBe('skipped');
  });

  it('imports a valid pack from a real directory', async () => {
    const packDir = setupValidPack(tmpBase, 'item-99999', 'workshop.valid_pack');

    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '99999',
          install_path: packDir,
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      results: Array<{ item_id: string; pack_id: string | null; status: string }>;
      imported: number;
    };
    expect(body.imported).toBe(1);
    expect(body.results[0]?.status).toBe('imported');
    expect(body.results[0]?.pack_id).toBe('workshop.valid_pack');
  });

  it('registers the imported pack in the shared index so its scenarios appear in the library', async () => {
    const packDir = setupValidPack(tmpBase, 'item-44444', 'workshop.indexed_pack');

    await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '44444',
          install_path: packDir,
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });

    // The pack must show up in /api/packs (installed_packs index).
    const packsRes = await app.inject({ method: 'GET', url: '/api/packs' });
    const packsBody = packsRes.json() as { packs: Array<{ pack_id: string }> };
    expect(packsBody.packs.some((p) => p.pack_id === 'workshop.indexed_pack')).toBe(true);

    // And its scenario must be browsable/launchable via /api/scenarios.
    const scenRes = await app.inject({ method: 'GET', url: '/api/scenarios' });
    const scenBody = scenRes.json() as Array<{ scenario_id: string; pack_id: string }>;
    expect(scenBody.some((s) => s.scenario_id === 'ws_basic' && s.pack_id === 'workshop.indexed_pack')).toBe(true);
  });

  it('records the import in workshop_items table', async () => {
    const packDir = setupValidPack(tmpBase, 'item-88888', 'workshop.db_pack');

    await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '88888',
          install_path: packDir,
          needs_update: false,
          updated_at: 1710000001,
        }],
      },
    });

    const db = getDb();
    const row = db.prepare('SELECT * FROM workshop_items WHERE item_id = ?').get('88888') as {
      pack_id: string;
      author_name: string;
      workshop_updated_at: number;
    } | undefined;
    expect(row).toBeDefined();
    expect(row?.pack_id).toBe('workshop.db_pack');
    expect(row?.author_name).toBe('WorkshopCreator');
    expect(row?.workshop_updated_at).toBe(1710000001);
  });

  it('quarantines a pack with a forbidden executable file', async () => {
    const badPackDir = join(tmpBase, 'item-77777');
    mkdirSync(join(badPackDir, 'scenarios'), { recursive: true });
    mkdirSync(join(badPackDir, 'npcs'), { recursive: true });
    mkdirSync(join(badPackDir, 'rubrics'), { recursive: true });
    mkdirSync(join(badPackDir, 'safety'), { recursive: true });
    writeFileSync(join(badPackDir, 'evil.exe'), 'MZ\x00\x00');
    writeFileSync(
      join(badPackDir, 'manifest.yaml'),
      `schema_version: "0.1"\npack_id: bad.pack\nname: Bad Pack\nversion: 0.1.0\ndescription: evil\nauthor: Attacker\nlicense: MIT\ncontent_rating: PG\nsafety:\n  policy: safety/default.yaml\n`,
    );
    writeFileSync(join(badPackDir, 'safety', 'default.yaml'), `schema_version: "0.1"\npolicy_id: default\ncontent_rating_cap: PG\ncontent_categories: {}\nredirect_message: ""\n`);

    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '77777',
          install_path: badPackDir,
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      results: Array<{ status: string; reason?: string }>;
      quarantined: number;
    };
    expect(body.quarantined).toBe(1);
    expect(body.results[0]?.status).toBe('quarantined');
    expect(body.results[0]?.reason).toContain('FORBIDDEN_FILE');

    // Verify quarantine is recorded in DB
    const db = getDb();
    const row = db.prepare('SELECT * FROM workshop_quarantine WHERE item_id = ?').get('77777');
    expect(row).toBeDefined();
  });

  it('marks unchanged when item_id + updated_at match existing record', async () => {
    const packDir = setupValidPack(tmpBase, 'item-66666', 'workshop.unchanged_pack');

    // Import once
    await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '66666',
          install_path: packDir,
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });

    // Sync again with same updated_at
    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '66666',
          install_path: packDir,
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });

    const body = res.json() as { results: Array<{ status: string }>; unchanged: number };
    expect(body.unchanged).toBe(1);
    expect(body.results[0]?.status).toBe('unchanged');
  });

  it('handles an empty items array without error', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: { items: [] },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { results: unknown[]; imported: number };
    expect(body.results).toHaveLength(0);
    expect(body.imported).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// GET /api/workshop/items
// ---------------------------------------------------------------------------

describe('GET /api/workshop/items', () => {
  it('returns empty items array on a fresh DB', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/workshop/items' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: unknown[] };
    expect(Array.isArray(body.items)).toBe(true);
    expect(body.items).toHaveLength(0);
  });

  it('returns synced Workshop items after a successful import', async () => {
    const packDir = setupValidPack(tmpBase, 'item-55555', 'workshop.list_pack');
    await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{
          item_id: '55555',
          install_path: packDir,
          needs_update: false,
          updated_at: 1710000000,
        }],
      },
    });

    const res = await app.inject({ method: 'GET', url: '/api/workshop/items' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      items: Array<{ item_id: string; pack_id: string; author_name: string }>;
    };
    expect(body.items).toHaveLength(1);
    expect(body.items[0]?.item_id).toBe('55555');
    expect(body.items[0]?.pack_id).toBe('workshop.list_pack');
    expect(body.items[0]?.author_name).toBe('WorkshopCreator');
  });
});

// ---------------------------------------------------------------------------
// GET /api/workshop/quarantine
// ---------------------------------------------------------------------------

describe('GET /api/workshop/quarantine', () => {
  it('returns empty items array when no packs are quarantined', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/workshop/quarantine' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: unknown[] };
    expect(body.items).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// DELETE /api/workshop/:pack_id
// ---------------------------------------------------------------------------

describe('DELETE /api/workshop/:pack_id', () => {
  it('returns 200 and removed:true when pack exists in workshop_items', async () => {
    const db = getDb();
    db.prepare(
      'INSERT INTO workshop_items (item_id, pack_id, author_name, install_path, workshop_updated_at, synced_at) VALUES (?,?,?,?,?,?)',
    ).run('11111', 'workshop.to_remove', 'Creator', '/some/path', 1710000000, 1710000000);

    const res = await app.inject({ method: 'DELETE', url: '/api/workshop/workshop.to_remove' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { removed: boolean };
    expect(body.removed).toBe(true);

    // Row should be gone from DB
    const row = db.prepare('SELECT * FROM workshop_items WHERE pack_id = ?').get('workshop.to_remove');
    expect(row).toBeUndefined();
  });

  it('removes the imported pack from the shared index on unsubscribe', async () => {
    // Import a real pack so it lands in installed_packs, then unsubscribe it.
    const packDir = setupValidPack(tmpBase, 'item-33333', 'workshop.cleanup_pack');
    await app.inject({
      method: 'POST',
      url: '/api/workshop/sync',
      payload: {
        items: [{ item_id: '33333', install_path: packDir, needs_update: false, updated_at: 1710000000 }],
      },
    });

    // Confirm it is present before removal.
    let packsBody = (await app.inject({ method: 'GET', url: '/api/packs' })).json() as { packs: Array<{ pack_id: string }> };
    expect(packsBody.packs.some((p) => p.pack_id === 'workshop.cleanup_pack')).toBe(true);

    const res = await app.inject({ method: 'DELETE', url: '/api/workshop/workshop.cleanup_pack' });
    expect(res.statusCode).toBe(200);
    expect((res.json() as { removed: boolean }).removed).toBe(true);

    // Pack and its scenarios must be gone from the library index.
    packsBody = (await app.inject({ method: 'GET', url: '/api/packs' })).json() as { packs: Array<{ pack_id: string }> };
    expect(packsBody.packs.some((p) => p.pack_id === 'workshop.cleanup_pack')).toBe(false);
    const scenBody = (await app.inject({ method: 'GET', url: '/api/scenarios' })).json() as Array<{ pack_id: string }>;
    expect(scenBody.some((s) => s.pack_id === 'workshop.cleanup_pack')).toBe(false);
  });

  it('returns removed:true when pack_id is not in workshop_items (idempotent)', async () => {
    const res = await app.inject({ method: 'DELETE', url: '/api/workshop/does.not.exist' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { removed: boolean };
    expect(body.removed).toBe(true);
  });

  it('returns removed:false when active sessions reference the pack', async () => {
    const db = getDb();
    db.prepare(
      'INSERT INTO workshop_items (item_id, pack_id, author_name, install_path, workshop_updated_at, synced_at) VALUES (?,?,?,?,?,?)',
    ).run('22222', 'workshop.active_pack', 'Creator', '/path', 1710000000, 1710000000);
    // Insert a session that references the pack_id
    db.prepare(
      `INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json, state_vars_json)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).run(
      'test-session-1',
      'ws_basic',
      'PlayerTurnListening',
      new Date().toISOString(),
      JSON.stringify({ pack_id: 'workshop.active_pack', scenario_id: 'ws_basic' }),
      '{}',
    );

    const res = await app.inject({ method: 'DELETE', url: '/api/workshop/workshop.active_pack' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { removed: boolean; has_active_sessions: boolean };
    expect(body.removed).toBe(false);
    expect(body.has_active_sessions).toBe(true);
  });
});
