// SPDX-License-Identifier: Apache-2.0
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { loadPacksFromRoots } from '../src/loader.js';
import { makePackInDir, VALID_MANIFEST_YAML } from './fixtures.js';

let rootsDir: string;

beforeEach(() => {
  rootsDir = mkdtempSync(join(tmpdir(), 'convsim-roots-test-'));
});

afterEach(() => {
  rmSync(rootsDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Version selection — highest semver wins when the same pack_id spans roots
// ---------------------------------------------------------------------------

describe('loadPacksFromRoots — version selection', () => {
  it('selects the highest version when the same pack_id appears in multiple roots', () => {
    const officialRoot = join(rootsDir, 'official');
    const localRoot = join(rootsDir, 'local');
    mkdirSync(officialRoot);
    mkdirSync(localRoot);

    makePackInDir(officialRoot, 'test-pack', {
      manifestYaml: VALID_MANIFEST_YAML, // version: 0.1.0
    });
    makePackInDir(localRoot, 'test-pack', {
      manifestYaml: VALID_MANIFEST_YAML.replace('version: 0.1.0', 'version: 0.2.0'),
    });

    const result = loadPacksFromRoots({ officialRoot, localDevRoot: localRoot });
    expect(result.packs).toHaveLength(1);
    expect(result.packs[0]?.manifest.version).toBe('0.2.0');
  });

  it('selects the higher version regardless of which root is listed first', () => {
    const officialRoot = join(rootsDir, 'official');
    const localRoot = join(rootsDir, 'local');
    mkdirSync(officialRoot);
    mkdirSync(localRoot);

    // Newer version in the FIRST root (official) — must not be overridden by the older local version
    makePackInDir(officialRoot, 'test-pack', {
      manifestYaml: VALID_MANIFEST_YAML.replace('version: 0.1.0', 'version: 2.0.0'),
    });
    makePackInDir(localRoot, 'test-pack', {
      manifestYaml: VALID_MANIFEST_YAML.replace('version: 0.1.0', 'version: 0.9.0'),
    });

    const result = loadPacksFromRoots({ officialRoot, localDevRoot: localRoot });
    expect(result.packs).toHaveLength(1);
    expect(result.packs[0]?.manifest.version).toBe('2.0.0');
  });

  it('returns a single pack when three roots all contain the same pack_id', () => {
    const officialRoot = join(rootsDir, 'official');
    const communityRoot = join(rootsDir, 'community');
    const localRoot = join(rootsDir, 'local');
    mkdirSync(officialRoot);
    mkdirSync(communityRoot);
    mkdirSync(localRoot);

    makePackInDir(officialRoot, 'p', {
      manifestYaml: VALID_MANIFEST_YAML.replace('version: 0.1.0', 'version: 1.0.0'),
    });
    makePackInDir(communityRoot, 'p', {
      manifestYaml: VALID_MANIFEST_YAML.replace('version: 0.1.0', 'version: 1.1.0'),
    });
    makePackInDir(localRoot, 'p', {
      manifestYaml: VALID_MANIFEST_YAML.replace('version: 0.1.0', 'version: 0.9.0'),
    });

    const result = loadPacksFromRoots({ officialRoot, communityRoot, localDevRoot: localRoot });
    expect(result.packs).toHaveLength(1);
    expect(result.packs[0]?.manifest.version).toBe('1.1.0');
  });
});
