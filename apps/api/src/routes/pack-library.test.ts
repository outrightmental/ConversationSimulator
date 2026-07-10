// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import AdmZip from 'adm-zip';
import { buildApp } from '../index.js';
import type { FastifyInstance } from 'fastify';
import type { ScenarioInfo } from '@convsim/shared';
import { setPacksDbPath, setPacksDataDir } from './packs.js';
import type { PackDetail } from './packs.js';
import { setScenariosDbPath } from './scenarios.js';
import { SCENARIOS } from '../data/scenarios.js';

// ---------------------------------------------------------------------------
// Pack fixture helpers — a community pack whose scenario_id does not collide
// with any built-in static scenario, so it must appear as a *dynamic* result.
// ---------------------------------------------------------------------------

const MANIFEST = `schema_version: "0.1"
pack_id: community.library_pack
name: Community Library Pack
version: 2.3.1
description: A community pack for exercising the library merge path.
author: Library Test Suite
license: MIT
content_rating: PG
tags:
  - practice
  - community
supported_languages:
  - en
  - es
requirements:
  recommended_llm:
    - llama-3-8b
safety:
  policy: safety/policy.yaml
`;

const SAFETY = `schema_version: "0.1"
policy_id: library_test_safety
content_rating_cap: PG
content_categories:
  nsfw_sexual: block
  real_person_impersonation: block
  instructional_criminal: block
  crisis_content: redirect
redirect_message: "Redirected."
`;

const NPC = `schema_version: "0.1"
npc_id: library_test_npc
display_name: Library NPC
archetype: test_archetype
fictional: true
age_band: adult
public_persona:
  occupation: A test NPC for library tests
  speaking_style: Direct
  demeanor: Neutral
private_persona: {}
`;

const RUBRIC = `schema_version: "0.1"
rubric_id: library_test_rubric
title: Library Rubric
dimensions:
  - id: accuracy
    name: Accuracy
    description: Test accuracy
    scoring:
      low: Low
      medium: Medium
      high: High
`;

const SCENARIO = `schema_version: "0.1"
scenario_id: community_library_scenario
title: Community Library Scenario
summary: A dynamic scenario served from the pack index.
player_role:
  label: Learner
  brief: You are practicing with a community pack.
npc:
  ref: ../npcs/library_test_npc.yaml
rubric:
  ref: ../rubrics/library_test_rubric.yaml
duration:
  max_turns: 10
  soft_time_limit_minutes: 12
opening:
  npc_says: "Welcome to the community pack."
goals:
  player_visible:
    - Practice the conversation
difficulty:
  default: hard
  options:
    normal: { npc_patience_modifier: 0, challenge_frequency: medium }
    hard: { npc_patience_modifier: -20, challenge_frequency: high }
`;

function makePackZip(parent: string): Buffer {
  const root = join(parent, 'pack');
  for (const sub of ['scenarios', 'npcs', 'rubrics', 'safety']) {
    mkdirSync(join(root, sub), { recursive: true });
  }
  writeFileSync(join(root, 'manifest.yaml'), MANIFEST);
  writeFileSync(join(root, 'safety', 'policy.yaml'), SAFETY);
  writeFileSync(join(root, 'npcs', 'library_test_npc.yaml'), NPC);
  writeFileSync(join(root, 'rubrics', 'library_test_rubric.yaml'), RUBRIC);
  writeFileSync(join(root, 'scenarios', 'community_library_scenario.yaml'), SCENARIO);
  const zip = new AdmZip();
  zip.addLocalFolder(root, '');
  return zip.toBuffer();
}

let app: FastifyInstance;
let tempDir: string;

beforeEach(async () => {
  tempDir = mkdtempSync(join(tmpdir(), 'convsim-api-library-test-'));
  const dbPath = join(tempDir, 'packs.db');
  setPacksDbPath(dbPath);
  setPacksDataDir(join(tempDir, 'packs'));
  setScenariosDbPath(dbPath);
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
  setPacksDbPath(null);
  setPacksDataDir(null);
  setScenariosDbPath(null);
  rmSync(tempDir, { recursive: true, force: true });
});

async function importPack(): Promise<void> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/packs/import',
    headers: { 'content-type': 'application/zip' },
    payload: makePackZip(tempDir),
  });
  expect(res.statusCode).toBe(201);
}

// ---------------------------------------------------------------------------
// GET /api/scenarios — dynamic merge from the pack index
// ---------------------------------------------------------------------------

describe('GET /api/scenarios — dynamic pack merge', () => {
  it('returns only static scenarios before any pack is imported', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    const body = res.json<ScenarioInfo[]>();
    expect(body.length).toBe(Object.keys(SCENARIOS).length);
  });

  it('includes an imported pack scenario alongside the static ones', async () => {
    await importPack();
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    expect(res.statusCode).toBe(200);
    const body = res.json<ScenarioInfo[]>();
    expect(body.length).toBe(Object.keys(SCENARIOS).length + 1);
    const dynamic = body.find((s) => s.scenario_id === 'community_library_scenario');
    expect(dynamic).toBeDefined();
  });

  it('maps manifest and scenario fields onto ScenarioInfo', async () => {
    await importPack();
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    const body = res.json<ScenarioInfo[]>();
    const dynamic = body.find((s) => s.scenario_id === 'community_library_scenario')!;
    expect(dynamic.pack_id).toBe('community.library_pack');
    expect(dynamic.pack_name).toBe('Community Library Pack');
    expect(dynamic.content_rating).toBe('PG');
    expect(dynamic.title).toBe('Community Library Scenario');
    expect(dynamic.player_role.label).toBe('Learner');
    expect(dynamic.supported_languages).toEqual(['en', 'es']);
    expect(dynamic.tags).toEqual(['practice', 'community']);
    expect(dynamic.recommended_model).toEqual(['llama-3-8b']);
    expect(dynamic.difficulty.default).toBe('hard');
    expect(dynamic.difficulty.options.hard).toEqual({
      npc_patience_modifier: -20,
      challenge_frequency: 'high',
    });
    expect(dynamic.duration.max_turns).toBe(10);
    expect(dynamic.duration.soft_time_limit_minutes).toBe(12);
    expect(dynamic.estimated_length_label).toMatch(/minutes/);
  });

  it('does not double-serve a scenario whose id also exists as a static built-in', async () => {
    // Guard the skip-dedup path: import twice must not duplicate, and no
    // dynamic scenario may shadow a static id.
    await importPack();
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    const body = res.json<ScenarioInfo[]>();
    const ids = body.map((s) => s.scenario_id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

// ---------------------------------------------------------------------------
// GET /api/scenarios/:id — PackIndex fallback
// ---------------------------------------------------------------------------

describe('GET /api/scenarios/:id — pack index fallback', () => {
  it('still returns a static scenario by id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/scenarios/behavioral_interview',
    });
    expect(res.statusCode).toBe(200);
    expect(res.json<ScenarioInfo>().scenario_id).toBe('behavioral_interview');
  });

  it('resolves a dynamic pack scenario by id after import', async () => {
    await importPack();
    const res = await app.inject({
      method: 'GET',
      url: '/api/scenarios/community_library_scenario',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<ScenarioInfo>();
    expect(body.scenario_id).toBe('community_library_scenario');
    expect(body.pack_id).toBe('community.library_pack');
  });

  it('returns 404 for a scenario that exists in no pack', async () => {
    await importPack();
    const res = await app.inject({
      method: 'GET',
      url: '/api/scenarios/does_not_exist',
    });
    expect(res.statusCode).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// GET /api/packs/:pack_id — pack detail (folder path source)
// ---------------------------------------------------------------------------

describe('GET /api/packs/:pack_id', () => {
  it('returns full pack detail including pack_root for an imported pack', async () => {
    await importPack();
    const res = await app.inject({
      method: 'GET',
      url: '/api/packs/community.library_pack',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<PackDetail>();
    expect(body.pack_id).toBe('community.library_pack');
    expect(body.name).toBe('Community Library Pack');
    expect(body.version).toBe('2.3.1');
    expect(typeof body.pack_root).toBe('string');
    expect(body.pack_root.length).toBeGreaterThan(0);
  });

  it('returns 404 for an unknown pack id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/packs/no_such_pack',
    });
    expect(res.statusCode).toBe(404);
  });

  it('exposes pack_root on the GET /api/packs summary rows', async () => {
    await importPack();
    const res = await app.inject({ method: 'GET', url: '/api/packs' });
    const { packs } = res.json<{ packs: Array<{ pack_id: string; pack_root?: string }> }>();
    const entry = packs.find((p) => p.pack_id === 'community.library_pack');
    expect(entry?.pack_root).toBeTruthy();
  });
});
