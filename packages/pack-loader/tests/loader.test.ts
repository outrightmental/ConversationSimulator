// SPDX-License-Identifier: Apache-2.0
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadPack, resolveBundle, loadPacksFromRoots } from '../src/loader.js';
import { PackLoaderError } from '../src/types.js';
import {
  makeTempPackDir,
  VALID_MANIFEST_YAML,
  VALID_SAFETY_YAML,
  VALID_NPC_YAML,
  VALID_RUBRIC_YAML,
  VALID_SCENARIO_YAML,
  VALID_SCENARIO_WITH_SCENE_YAML,
  VALID_SCENE_YAML,
} from './fixtures.js';

// ---------------------------------------------------------------------------
// Happy-path: valid pack
// ---------------------------------------------------------------------------

describe('loadPack — valid pack', () => {
  it('loads a minimal pack without errors', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir, 'official');
    expect(pack.manifest.pack_id).toBe('test.minimal_pack');
    expect(pack.manifest.version).toBe('0.1.0');
    expect(pack.packRootKind).toBe('official');
  });

  it('loads the scenario list', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir);
    expect(pack.scenarios).toHaveLength(1);
    expect(pack.scenarios[0]?.data.scenario_id).toBe('test_scenario');
  });

  it('loads the NPC referenced by the scenario', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir);
    expect(pack.npcs.size).toBe(1);
    const [npc] = [...pack.npcs.values()];
    expect(npc?.npc_id).toBe('test_npc');
    expect(npc?.fictional).toBe(true);
  });

  it('loads the rubric referenced by the scenario', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir);
    expect(pack.rubrics.size).toBe(1);
    const [rubric] = [...pack.rubrics.values()];
    expect(rubric?.rubric_id).toBe('test_rubric');
  });

  it('resolves the safety policy', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir);
    expect(pack.safety.policy_id).toBe('test_safety');
    expect(pack.safety.content_rating_cap).toBe('PG');
  });

  it('resolves an optional scene ref', () => {
    const dir = makeTempPackDir({
      sceneYaml: VALID_SCENE_YAML,
      scenarioYamls: { 'scenario_with_scene.yaml': VALID_SCENARIO_WITH_SCENE_YAML },
    });
    const pack = loadPack(dir);
    expect(pack.scenes.size).toBe(1);
    const [scene] = [...pack.scenes.values()];
    expect(scene?.scene_id).toBe('test_scene');
  });

  it('handles packs with multiple scenarios', () => {
    const SECOND_SCENARIO = VALID_SCENARIO_YAML
      .replace('scenario_id: test_scenario', 'scenario_id: test_scenario_two')
      .replace('title: Test Scenario', 'title: Test Scenario Two');

    const dir = makeTempPackDir({
      scenarioYamls: {
        'test_scenario.yaml': VALID_SCENARIO_YAML,
        'test_scenario_two.yaml': SECOND_SCENARIO,
      },
    });
    const pack = loadPack(dir);
    expect(pack.scenarios).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// resolveBundle
// ---------------------------------------------------------------------------

describe('resolveBundle', () => {
  it('returns a fully resolved bundle for a valid scenario', () => {
    const dir = makeTempPackDir({
      sceneYaml: VALID_SCENE_YAML,
      scenarioYamls: { 'scenario.yaml': VALID_SCENARIO_WITH_SCENE_YAML },
    });
    const pack = loadPack(dir);
    const bundle = resolveBundle(pack, 'test_scenario_scene');
    expect(bundle.scenarioId).toBe('test_scenario_scene');
    expect(bundle.packId).toBe('test.minimal_pack');
    expect(bundle.npc.npc_id).toBe('test_npc');
    expect(bundle.rubric.rubric_id).toBe('test_rubric');
    expect(bundle.scene?.scene_id).toBe('test_scene');
    expect(bundle.safety.policy_id).toBe('test_safety');
  });

  it('returns scene=null when the scenario has no scene ref', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir);
    const bundle = resolveBundle(pack, 'test_scenario');
    expect(bundle.scene).toBeNull();
  });

  it('throws MISSING_FILE for an unknown scenario_id', () => {
    const dir = makeTempPackDir();
    const pack = loadPack(dir);
    expect(() => resolveBundle(pack, 'nonexistent')).toThrow(PackLoaderError);
    try {
      resolveBundle(pack, 'nonexistent');
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('MISSING_FILE');
    }
  });
});

// ---------------------------------------------------------------------------
// Error cases
// ---------------------------------------------------------------------------

describe('loadPack — error cases', () => {
  it('throws MISSING_FILE when manifest.yaml is absent', () => {
    const emptyDir = mkdtempSync(join(tmpdir(), 'convsim-empty-'));
    mkdirSync(join(emptyDir, 'scenarios'));

    expect(() => loadPack(emptyDir)).toThrowError(PackLoaderError);
    try {
      loadPack(emptyDir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('MISSING_FILE');
    }
  });

  it('throws MISSING_FILE when the referenced NPC file is absent', () => {
    const dir = makeTempPackDir({
      scenarioYamls: {
        'test_scenario.yaml': VALID_SCENARIO_YAML.replace(
          'ref: ../npcs/test_npc.yaml',
          'ref: ../npcs/nonexistent_npc.yaml',
        ),
      },
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('MISSING_FILE');
    }
  });

  it('throws MISSING_FILE when the safety policy file is absent', () => {
    const dir = makeTempPackDir({
      manifestYaml: VALID_MANIFEST_YAML.replace(
        'policy: safety/policy.yaml',
        'policy: safety/nonexistent.yaml',
      ),
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('MISSING_FILE');
    }
  });

  it('throws PATH_TRAVERSAL when a ref tries to escape the pack root', () => {
    const dir = makeTempPackDir({
      scenarioYamls: {
        'test_scenario.yaml': VALID_SCENARIO_YAML.replace(
          'ref: ../npcs/test_npc.yaml',
          'ref: ../../outside/npc.yaml',
        ),
      },
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('PATH_TRAVERSAL');
    }
  });

  it('throws DUPLICATE_ID when two scenarios share the same scenario_id', () => {
    const dir = makeTempPackDir({
      scenarioYamls: {
        'test_scenario.yaml': VALID_SCENARIO_YAML,
        'test_scenario_copy.yaml': VALID_SCENARIO_YAML,
      },
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('DUPLICATE_ID');
    }
  });

  it('throws UNSUPPORTED_VERSION when schema_version is not "0.1"', () => {
    const dir = makeTempPackDir({
      manifestYaml: VALID_MANIFEST_YAML.replace('schema_version: "0.1"', 'schema_version: "9.9"'),
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('UNSUPPORTED_VERSION');
    }
  });

  it('throws SCHEMA_VALIDATION when the manifest is missing a required field', () => {
    const invalidManifest = VALID_MANIFEST_YAML.replace(/^content_rating:.*\n/m, '');
    const dir = makeTempPackDir({ manifestYaml: invalidManifest });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('SCHEMA_VALIDATION');
    }
  });

  it('throws SCHEMA_VALIDATION when an NPC has fictional: false', () => {
    const badNpc = `schema_version: "0.1"
npc_id: bad_npc
display_name: Bad NPC
archetype: tester
fictional: false
age_band: adult
public_persona:
  occupation: A test
  speaking_style: Direct
  demeanor: Neutral
private_persona: {}
`;
    const dir = makeTempPackDir({ npcYaml: badNpc });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('SCHEMA_VALIDATION');
    }
  });

  it('throws INVALID_YAML when a file contains invalid YAML syntax', () => {
    const dir = makeTempPackDir({ manifestYaml: ': broken: yaml:' });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      const code = (e as PackLoaderError).code;
      expect(['INVALID_YAML', 'SCHEMA_VALIDATION']).toContain(code);
    }
  });

  it('throws PATH_TRAVERSAL when an NPC portrait path escapes the pack root', () => {
    const dir = makeTempPackDir({
      npcYaml: VALID_NPC_YAML + 'portrait: ../../outside.png\n',
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('PATH_TRAVERSAL');
    }
  });

  it('throws PATH_TRAVERSAL when a scene background path escapes the pack root', () => {
    const dir = makeTempPackDir({
      sceneYaml: VALID_SCENE_YAML + 'background: ../../outside.png\n',
      scenarioYamls: { 'scenario_with_scene.yaml': VALID_SCENARIO_WITH_SCENE_YAML },
    });
    expect(() => loadPack(dir)).toThrowError(PackLoaderError);
    try {
      loadPack(dir);
    } catch (e) {
      expect((e as PackLoaderError).code).toBe('PATH_TRAVERSAL');
    }
  });
});

// ---------------------------------------------------------------------------
// loadPacksFromRoots
// ---------------------------------------------------------------------------

/**
 * Build a valid pack directory tree directly inside `parentDir` and return its
 * absolute path.  Unlike makeTempPackDir(), the directory is created *within*
 * a caller-supplied parent so it shows up when loadPacksFromRoots() scans that
 * parent for subdirectories.
 */
function makePackSubdir(parentDir: string, manifestYaml: string = VALID_MANIFEST_YAML): string {
  const dir = mkdtempSync(join(parentDir, 'pack-'));
  for (const sub of ['scenarios', 'npcs', 'rubrics', 'safety']) {
    mkdirSync(join(dir, sub), { recursive: true });
  }
  writeFileSync(join(dir, 'manifest.yaml'), manifestYaml, 'utf8');
  writeFileSync(join(dir, 'safety', 'policy.yaml'), VALID_SAFETY_YAML, 'utf8');
  writeFileSync(join(dir, 'npcs', 'test_npc.yaml'), VALID_NPC_YAML, 'utf8');
  writeFileSync(join(dir, 'rubrics', 'test_rubric.yaml'), VALID_RUBRIC_YAML, 'utf8');
  writeFileSync(join(dir, 'scenarios', 'test_scenario.yaml'), VALID_SCENARIO_YAML, 'utf8');
  return dir;
}

describe('loadPacksFromRoots', () => {
  it('loads packs from an official root', () => {
    const officialRoot = mkdtempSync(join(tmpdir(), 'convsim-official-root-'));
    const manifestA = VALID_MANIFEST_YAML.replace('pack_id: test.minimal_pack', 'pack_id: official.pack_a');
    const manifestB = VALID_MANIFEST_YAML.replace('pack_id: test.minimal_pack', 'pack_id: official.pack_b');
    makePackSubdir(officialRoot, manifestA);
    makePackSubdir(officialRoot, manifestB);

    const result = loadPacksFromRoots({ officialRoot });
    expect(result.errors).toHaveLength(0);
    expect(result.packs).toHaveLength(2);
    expect(result.packs.every((p) => p.packRootKind === 'official')).toBe(true);
    const ids = result.packs.map((p) => p.manifest.pack_id).sort();
    expect(ids).toContain('official.pack_a');
    expect(ids).toContain('official.pack_b');
  });

  it('collects errors for invalid packs without throwing', () => {
    const localDevRoot = mkdtempSync(join(tmpdir(), 'convsim-local-root-'));
    makePackSubdir(localDevRoot);
    mkdirSync(join(localDevRoot, 'broken-pack'), { recursive: true }); // empty dir, no manifest

    const result = loadPacksFromRoots({ localDevRoot });
    expect(result.packs).toHaveLength(1);
    expect(result.errors).toHaveLength(1);
    expect(result.packs[0]?.manifest.pack_id).toBe('test.minimal_pack');
    expect(result.packs[0]?.packRootKind).toBe('local-dev');
  });

  it('returns empty results when root directories do not exist', () => {
    const result = loadPacksFromRoots({
      officialRoot: join(tmpdir(), 'convsim-nonexistent-official-zzz'),
      communityRoot: join(tmpdir(), 'convsim-nonexistent-community-zzz'),
    });
    expect(result.packs).toHaveLength(0);
    expect(result.errors).toHaveLength(0);
  });

  it('loads from multiple roots and tags packs with their root kind', () => {
    const officialRoot = mkdtempSync(join(tmpdir(), 'convsim-multi-official-'));
    const communityRoot = mkdtempSync(join(tmpdir(), 'convsim-multi-community-'));
    makePackSubdir(officialRoot, VALID_MANIFEST_YAML.replace('pack_id: test.minimal_pack', 'pack_id: official.one'));
    makePackSubdir(communityRoot, VALID_MANIFEST_YAML.replace('pack_id: test.minimal_pack', 'pack_id: community.one'));

    const result = loadPacksFromRoots({ officialRoot, communityRoot });
    expect(result.errors).toHaveLength(0);
    expect(result.packs).toHaveLength(2);

    const official = result.packs.find((p) => p.manifest.pack_id === 'official.one');
    const community = result.packs.find((p) => p.manifest.pack_id === 'community.one');
    expect(official?.packRootKind).toBe('official');
    expect(community?.packRootKind).toBe('community');
  });
});
