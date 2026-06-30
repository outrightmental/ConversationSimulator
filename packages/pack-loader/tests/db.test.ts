// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { join } from 'node:path';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { PackIndex } from '../src/db.js';
import { loadPack } from '../src/loader.js';
import { makeTempPackDir, VALID_MANIFEST_YAML, VALID_SCENARIO_YAML } from './fixtures.js';

let workDir: string;
let dbPath: string;
let index: PackIndex;

beforeEach(() => {
  workDir = mkdtempSync(join(tmpdir(), 'convsim-db-test-'));
  dbPath = join(workDir, 'packs.db');
  index = PackIndex.open(dbPath);
});

afterEach(() => {
  index.close();
  rmSync(workDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Import
// ---------------------------------------------------------------------------

describe('PackIndex.importPack', () => {
  it('adds the pack to the index', () => {
    const packDir = makeTempPackDir();
    const pack = loadPack(packDir, 'official');
    index.importPack(pack);

    const packs = index.listPacks();
    expect(packs).toHaveLength(1);
    expect(packs[0]?.pack_id).toBe('test.minimal_pack');
    expect(packs[0]?.name).toBe('Minimal Test Pack');
    expect(packs[0]?.content_rating).toBe('PG');
    expect(packs[0]?.pack_root_kind).toBe('official');
  });

  it('records the correct scenario count', () => {
    const packDir = makeTempPackDir();
    const pack = loadPack(packDir);
    index.importPack(pack);

    const entry = index.getPack('test.minimal_pack');
    expect(entry?.scenario_count).toBe(1);
  });

  it('indexes scenarios', () => {
    const packDir = makeTempPackDir();
    const pack = loadPack(packDir);
    index.importPack(pack);

    const scenarios = index.listScenarios('test.minimal_pack');
    expect(scenarios).toHaveLength(1);
    expect(scenarios[0]?.scenario_id).toBe('test_scenario');
    expect(scenarios[0]?.title).toBe('Test Scenario');
    expect(scenarios[0]?.max_turns).toBe(5);
  });

  it('indexes multiple scenarios', () => {
    const secondScenario = VALID_SCENARIO_YAML
      .replace('scenario_id: test_scenario', 'scenario_id: test_scenario_two')
      .replace('title: Test Scenario', 'title: Test Scenario Two');

    const packDir = makeTempPackDir({
      scenarioYamls: {
        'test_scenario.yaml': VALID_SCENARIO_YAML,
        'test_scenario_two.yaml': secondScenario,
      },
    });
    const pack = loadPack(packDir);
    index.importPack(pack);

    const scenarios = index.listScenarios('test.minimal_pack');
    expect(scenarios).toHaveLength(2);

    const entry = index.getPack('test.minimal_pack');
    expect(entry?.scenario_count).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Replace (re-import same pack_id)
// ---------------------------------------------------------------------------

describe('PackIndex.importPack — replace', () => {
  it('updates existing pack metadata on re-import', () => {
    const v1Dir = makeTempPackDir();
    const v1Pack = loadPack(v1Dir, 'official');
    index.importPack(v1Pack);

    const updatedManifest = VALID_MANIFEST_YAML
      .replace('version: 0.1.0', 'version: 0.2.0')
      .replace('name: Minimal Test Pack', 'name: Updated Test Pack');
    const v2Dir = makeTempPackDir({ manifestYaml: updatedManifest });
    const v2Pack = loadPack(v2Dir, 'official');
    index.importPack(v2Pack);

    const packs = index.listPacks();
    expect(packs).toHaveLength(1);
    expect(packs[0]?.version).toBe('0.2.0');
    expect(packs[0]?.name).toBe('Updated Test Pack');
  });

  it('replaces the scenario list when pack is updated', () => {
    const v1Dir = makeTempPackDir();
    index.importPack(loadPack(v1Dir));

    const newScenario = VALID_SCENARIO_YAML
      .replace('scenario_id: test_scenario', 'scenario_id: replacement_scenario')
      .replace('title: Test Scenario', 'title: Replacement Scenario');

    const v2Dir = makeTempPackDir({
      scenarioYamls: { 'replacement.yaml': newScenario },
    });
    index.importPack(loadPack(v2Dir));

    const scenarios = index.listScenarios('test.minimal_pack');
    expect(scenarios).toHaveLength(1);
    expect(scenarios[0]?.scenario_id).toBe('replacement_scenario');
  });

  it('search index updates when pack is replaced', () => {
    const v1Dir = makeTempPackDir();
    index.importPack(loadPack(v1Dir));

    const secondScenario = VALID_SCENARIO_YAML
      .replace('scenario_id: test_scenario', 'scenario_id: extra_scenario')
      .replace('title: Test Scenario', 'title: Extra Scenario');
    const v2Dir = makeTempPackDir({
      scenarioYamls: {
        'test_scenario.yaml': VALID_SCENARIO_YAML,
        'extra_scenario.yaml': secondScenario,
      },
    });
    index.importPack(loadPack(v2Dir));

    expect(index.listScenarios('test.minimal_pack')).toHaveLength(2);
    expect(index.getPack('test.minimal_pack')?.scenario_count).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Remove
// ---------------------------------------------------------------------------

describe('PackIndex.removePack', () => {
  it('removes the pack from the index', () => {
    const packDir = makeTempPackDir();
    index.importPack(loadPack(packDir));
    expect(index.listPacks()).toHaveLength(1);

    index.removePack('test.minimal_pack');
    expect(index.listPacks()).toHaveLength(0);
    expect(index.getPack('test.minimal_pack')).toBeUndefined();
  });

  it('cascades removal to indexed scenarios', () => {
    const packDir = makeTempPackDir();
    index.importPack(loadPack(packDir));
    expect(index.listScenarios('test.minimal_pack')).toHaveLength(1);

    index.removePack('test.minimal_pack');
    expect(index.listScenarios('test.minimal_pack')).toHaveLength(0);
    expect(index.listScenarios()).toHaveLength(0);
  });

  it('is a no-op for a pack_id that was never imported', () => {
    expect(() => index.removePack('does.not.exist')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// listScenarios filtering
// ---------------------------------------------------------------------------

describe('PackIndex.listScenarios', () => {
  it('returns all scenarios when no pack_id filter is given', () => {
    const packAManifest = VALID_MANIFEST_YAML.replace('pack_id: test.minimal_pack', 'pack_id: pack.a');
    const packBManifest = VALID_MANIFEST_YAML.replace('pack_id: test.minimal_pack', 'pack_id: pack.b');
    const scenarioB = VALID_SCENARIO_YAML
      .replace('scenario_id: test_scenario', 'scenario_id: scenario_b');

    index.importPack(loadPack(makeTempPackDir({ manifestYaml: packAManifest })));
    index.importPack(loadPack(makeTempPackDir({
      manifestYaml: packBManifest,
      scenarioYamls: { 'scenario_b.yaml': scenarioB },
    })));

    expect(index.listScenarios()).toHaveLength(2);
  });
});
