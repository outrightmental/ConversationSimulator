// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import AdmZip from 'adm-zip';
import { buildApp } from '../index.js';
import type { FastifyInstance } from 'fastify';
import type { PackValidationResult } from '@convsim/shared';
import { setPacksDbPath, setPacksDataDir } from './packs.js';
import type { ImportPackResponse } from './packs.js';

// ---------------------------------------------------------------------------
// Pack fixture helpers
// ---------------------------------------------------------------------------

const VALID_MANIFEST = `schema_version: "0.1"
pack_id: test.api_pack
name: API Test Pack
version: 1.0.0
description: A pack for testing the Fastify API.
author: API Test Suite
license: MIT
content_rating: PG
safety:
  policy: safety/policy.yaml
`;

const VALID_SAFETY = `schema_version: "0.1"
policy_id: api_test_safety
content_rating_cap: PG
content_categories:
  nsfw_sexual: block
  real_person_impersonation: block
  instructional_criminal: block
  crisis_content: redirect
redirect_message: "Redirected."
`;

const VALID_NPC = `schema_version: "0.1"
npc_id: api_test_npc
display_name: API NPC
archetype: test_archetype
fictional: true
age_band: adult
public_persona:
  occupation: A test NPC for API tests
  speaking_style: Direct
  demeanor: Neutral
private_persona: {}
`;

const VALID_RUBRIC = `schema_version: "0.1"
rubric_id: api_test_rubric
title: API Rubric
dimensions:
  - id: accuracy
    name: Accuracy
    description: Test accuracy
    scoring:
      low: Low
      medium: Medium
      high: High
`;

const VALID_SCENARIO = `schema_version: "0.1"
scenario_id: api_test_scenario
title: API Test Scenario
summary: A test scenario for the Fastify API.
player_role:
  label: Tester
  brief: You are testing the Fastify API.
npc:
  ref: ../npcs/api_test_npc.yaml
rubric:
  ref: ../rubrics/api_test_rubric.yaml
duration:
  max_turns: 5
opening:
  npc_says: "Hello from API test."
goals:
  player_visible:
    - Test the API
`;

function makeValidPackDir(parent: string): string {
  const root = join(parent, 'pack');
  for (const sub of ['scenarios', 'npcs', 'rubrics', 'safety']) {
    mkdirSync(join(root, sub), { recursive: true });
  }
  writeFileSync(join(root, 'manifest.yaml'), VALID_MANIFEST);
  writeFileSync(join(root, 'safety', 'policy.yaml'), VALID_SAFETY);
  writeFileSync(join(root, 'npcs', 'api_test_npc.yaml'), VALID_NPC);
  writeFileSync(join(root, 'rubrics', 'api_test_rubric.yaml'), VALID_RUBRIC);
  writeFileSync(join(root, 'scenarios', 'api_test_scenario.yaml'), VALID_SCENARIO);
  return root;
}

function makeValidPackZip(parent: string): Buffer {
  const packDir = makeValidPackDir(parent);
  const zip = new AdmZip();
  zip.addLocalFolder(packDir, '');
  return zip.toBuffer();
}

// ---------------------------------------------------------------------------
// State: per-test temp dirs
// ---------------------------------------------------------------------------

let app: FastifyInstance;
let tempDir: string;

beforeEach(async () => {
  tempDir = mkdtempSync(join(tmpdir(), 'convsim-api-packs-test-'));
  setPacksDbPath(join(tempDir, 'packs.db'));
  setPacksDataDir(join(tempDir, 'packs'));
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
  setPacksDbPath(null);
  setPacksDataDir(null);
  rmSync(tempDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// POST /api/packs/:pack_id/validate (existing)
// ---------------------------------------------------------------------------

describe('POST /api/packs/:pack_id/validate', () => {
  it('returns 200 with valid=true for a known pack', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/official.job_interview_basic/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<PackValidationResult>();
    expect(body.pack_id).toBe('official.job_interview_basic');
    expect(body.valid).toBe(true);
    expect(body.errors).toEqual([]);
  });

  it('returns 200 for every installed pack', async () => {
    const packIds = [
      'official.job_interview_basic',
      'official.everyday_negotiation',
      'official.language_cafe',
      'official.difficult_conversations',
    ];
    for (const packId of packIds) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/packs/${packId}/validate`,
      });
      expect(res.statusCode).toBe(200);
      const body = res.json<PackValidationResult>();
      expect(body.valid).toBe(true);
    }
  });

  it('returns 404 for an unknown pack id', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/does_not_exist/validate',
    });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// POST /api/packs/import
// ---------------------------------------------------------------------------

describe('POST /api/packs/import — valid zip', () => {
  it('returns 201 with pack metadata on success', async () => {
    const zipBuffer = makeValidPackZip(tempDir);
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(res.statusCode).toBe(201);
    const body = res.json<ImportPackResponse>();
    expect(body.pack_id).toBe('test.api_pack');
    expect(body.name).toBe('API Test Pack');
    expect(body.version).toBe('1.0.0');
    expect(typeof body.dest).toBe('string');
  });

  it('registers the pack in the index so GET /api/packs lists it', async () => {
    const zipBuffer = makeValidPackZip(tempDir);
    await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    const listRes = await app.inject({ method: 'GET', url: '/api/packs' });
    expect(listRes.statusCode).toBe(200);
    const { packs } = listRes.json<{ packs: Array<{ pack_id: string }>; total: number }>();
    expect(packs.some((p) => p.pack_id === 'test.api_pack')).toBe(true);
  });

  it('replaces an existing pack on re-import (upgrade path)', async () => {
    const zipBuffer = makeValidPackZip(tempDir);
    const first = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(first.statusCode).toBe(201);

    // Build a v2.0.0 zip for the same pack_id
    const v2PackDir = makeValidPackDir(mkdtempSync(join(tmpdir(), 'convsim-api-v2-')));
    writeFileSync(
      join(v2PackDir, 'manifest.yaml'),
      VALID_MANIFEST.replace('version: 1.0.0', 'version: 2.0.0'),
    );
    const v2Zip = new AdmZip();
    v2Zip.addLocalFolder(v2PackDir, '');
    const v2Buffer = v2Zip.toBuffer();

    const second = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: v2Buffer,
    });
    expect(second.statusCode).toBe(201);
    const body = second.json<ImportPackResponse>();
    expect(body.version).toBe('2.0.0');

    // The index must reflect the upgraded version
    const listRes = await app.inject({ method: 'GET', url: '/api/packs' });
    const { packs } = listRes.json<{ packs: Array<{ pack_id: string; version?: string }> }>();
    const entry = packs.find((p) => p.pack_id === 'test.api_pack');
    expect(entry).toBeDefined();
  });
});

describe('POST /api/packs/import — rejected archives', () => {
  it('returns 422 for a non-zip body', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: Buffer.from('this is not a zip'),
    });
    expect(res.statusCode).toBe(422);
    const body = res.json<{ code: string }>();
    expect(body.code).toBe('INVALID_ZIP');
  });

  it('returns 422 for a zip containing an executable file', async () => {
    const packDir = makeValidPackDir(mkdtempSync(join(tmpdir(), 'convsim-exec-')));
    writeFileSync(join(packDir, 'run.sh'), '#!/bin/sh\necho evil\n');
    const zip = new AdmZip();
    zip.addLocalFolder(packDir, '');
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zip.toBuffer(),
    });
    expect(res.statusCode).toBe(422);
    const body = res.json<{ code: string }>();
    expect(body.code).toBe('FORBIDDEN_FILE');
  });

  it('returns 422 for a zip-slip archive', async () => {
    // Craft a raw zip with a path-traversal entry
    const filenameBytes = Buffer.from('../../evil.txt');
    const content = Buffer.from('pwned');
    const localHdr = Buffer.alloc(30);
    localHdr.writeUInt32LE(0x04034b50, 0);
    localHdr.writeUInt16LE(20, 4);
    localHdr.writeUInt16LE(0, 6);
    localHdr.writeUInt16LE(0, 8);
    localHdr.writeUInt16LE(0, 10);
    localHdr.writeUInt16LE(0, 12);
    localHdr.writeUInt32LE(0, 14);
    localHdr.writeUInt32LE(content.length, 18);
    localHdr.writeUInt32LE(content.length, 22);
    localHdr.writeUInt16LE(filenameBytes.length, 26);
    localHdr.writeUInt16LE(0, 28);
    const localEntry = Buffer.concat([localHdr, filenameBytes, content]);
    const cdHdr = Buffer.alloc(46);
    cdHdr.writeUInt32LE(0x02014b50, 0);
    cdHdr.writeUInt16LE(20, 4);
    cdHdr.writeUInt16LE(20, 6);
    cdHdr.writeUInt16LE(0, 8);
    cdHdr.writeUInt16LE(0, 10);
    cdHdr.writeUInt16LE(0, 12);
    cdHdr.writeUInt16LE(0, 14);
    cdHdr.writeUInt32LE(0, 16);
    cdHdr.writeUInt32LE(content.length, 20);
    cdHdr.writeUInt32LE(content.length, 24);
    cdHdr.writeUInt16LE(filenameBytes.length, 28);
    cdHdr.writeUInt16LE(0, 30);
    cdHdr.writeUInt16LE(0, 32);
    cdHdr.writeUInt16LE(0, 34);
    cdHdr.writeUInt16LE(0, 36);
    cdHdr.writeUInt32LE(0, 38);
    cdHdr.writeUInt32LE(0, 42);
    const centralDir = Buffer.concat([cdHdr, filenameBytes]);
    const eocd = Buffer.alloc(22);
    eocd.writeUInt32LE(0x06054b50, 0);
    eocd.writeUInt16LE(0, 4);
    eocd.writeUInt16LE(0, 6);
    eocd.writeUInt16LE(1, 8);
    eocd.writeUInt16LE(1, 10);
    eocd.writeUInt32LE(centralDir.length, 12);
    eocd.writeUInt32LE(localEntry.length, 16);
    eocd.writeUInt16LE(0, 20);
    const slipZip = Buffer.concat([localEntry, centralDir, eocd]);

    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: slipZip,
    });
    expect(res.statusCode).toBe(422);
    const body = res.json<{ code: string }>();
    expect(body.code).toBe('UNSAFE_ZIP');
  });

  it('returns 422 for a zip missing a manifest', async () => {
    const zip = new AdmZip();
    zip.addFile('README.txt', Buffer.from('no manifest here'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zip.toBuffer(),
    });
    expect(res.statusCode).toBe(422);
  });
});

// ---------------------------------------------------------------------------
// GET /api/packs/:pack_id/export
// ---------------------------------------------------------------------------

describe('GET /api/packs/:pack_id/export', () => {
  it('returns 404 for an unknown pack id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/packs/no_such_pack/export',
    });
    expect(res.statusCode).toBe(404);
  });

  it('returns a zip file for an installed pack', async () => {
    // First import a pack
    const zipBuffer = makeValidPackZip(tempDir);
    const importRes = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(importRes.statusCode).toBe(201);

    const res = await app.inject({
      method: 'GET',
      url: '/api/packs/test.api_pack/export',
    });
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('application/zip');
    expect(res.rawPayload.length).toBeGreaterThan(0);

    // Verify the payload is a valid zip containing the manifest
    const exportedZip = new AdmZip(res.rawPayload);
    const entryNames = exportedZip.getEntries().map((e) => e.entryName);
    expect(entryNames.some((n) => n.endsWith('manifest.yaml'))).toBe(true);
  });

  it('does not corrupt the pack index when export is called before any import', async () => {
    // Hitting export on a fresh install (no packs yet) must not create a
    // divergent installed_packs schema that breaks a subsequent import.
    const exportRes = await app.inject({
      method: 'GET',
      url: '/api/packs/no_such_pack/export',
    });
    expect(exportRes.statusCode).toBe(404);

    const zipBuffer = makeValidPackZip(tempDir);
    const importRes = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });
    expect(importRes.statusCode).toBe(201);
  });

  it('round-trips: exported zip can be re-imported', async () => {
    const zipBuffer = makeValidPackZip(tempDir);
    await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: zipBuffer,
    });

    const exportRes = await app.inject({
      method: 'GET',
      url: '/api/packs/test.api_pack/export',
    });
    expect(exportRes.statusCode).toBe(200);

    // Re-import the exported zip
    const reimportRes = await app.inject({
      method: 'POST',
      url: '/api/packs/import',
      headers: { 'content-type': 'application/zip' },
      payload: exportRes.rawPayload,
    });
    // Should succeed (replaces the existing pack)
    expect(reimportRes.statusCode).toBe(201);
    expect(reimportRes.json<ImportPackResponse>().pack_id).toBe('test.api_pack');
  });
});
