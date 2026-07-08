// SPDX-License-Identifier: Apache-2.0
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import AdmZip from 'adm-zip';

import { runValidatePack } from '../src/commands/validate-pack.js';
import { runTestPack } from '../src/commands/test-pack.js';
import { runImportPack } from '../src/commands/import-pack.js';
import { runExportPack } from '../src/commands/export-pack.js';

// ---------------------------------------------------------------------------
// Re-use the same fixtures as pack-loader so we test the same validation paths
// ---------------------------------------------------------------------------

const VALID_MANIFEST = `schema_version: "0.1"
pack_id: test.cli_pack
name: CLI Test Pack
version: 0.2.0
description: A pack for testing the convsim CLI.
author: CLI Test Suite
license: MIT
content_rating: PG
safety:
  policy: safety/policy.yaml
`;

const VALID_SAFETY = `schema_version: "0.1"
policy_id: cli_test_safety
content_rating_cap: PG
content_categories:
  nsfw_sexual: block
  real_person_impersonation: block
  instructional_criminal: block
  crisis_content: redirect
redirect_message: "Redirected."
`;

const VALID_NPC = `schema_version: "0.1"
npc_id: cli_test_npc
display_name: CLI NPC
archetype: test_archetype
fictional: true
age_band: adult
public_persona:
  occupation: A test NPC
  speaking_style: Direct
  demeanor: Neutral
private_persona: {}
`;

const VALID_RUBRIC = `schema_version: "0.1"
rubric_id: cli_test_rubric
title: CLI Rubric
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
scenario_id: cli_test_scenario
title: CLI Test Scenario
summary: A test scenario for the CLI.
player_role:
  label: Tester
  brief: You are testing the CLI.
npc:
  ref: ../npcs/cli_test_npc.yaml
rubric:
  ref: ../rubrics/cli_test_rubric.yaml
duration:
  max_turns: 5
opening:
  npc_says: "Hello from CLI test."
goals:
  player_visible:
    - Test the CLI
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeValidPackDir(parent?: string): string {
  const root = parent
    ? (() => { const d = join(parent, 'pack'); mkdirSync(d); return d; })()
    : mkdtempSync(join(tmpdir(), 'convsim-cli-test-'));

  for (const sub of ['scenarios', 'npcs', 'rubrics', 'safety']) {
    mkdirSync(join(root, sub), { recursive: true });
  }
  writeFileSync(join(root, 'manifest.yaml'), VALID_MANIFEST);
  writeFileSync(join(root, 'safety', 'policy.yaml'), VALID_SAFETY);
  writeFileSync(join(root, 'npcs', 'cli_test_npc.yaml'), VALID_NPC);
  writeFileSync(join(root, 'rubrics', 'cli_test_rubric.yaml'), VALID_RUBRIC);
  writeFileSync(join(root, 'scenarios', 'cli_test_scenario.yaml'), VALID_SCENARIO);
  return root;
}

function makeBrokenPackDir(): string {
  const root = mkdtempSync(join(tmpdir(), 'convsim-cli-broken-'));
  writeFileSync(join(root, 'manifest.yaml'), 'schema_version: "0.1"\nnot_a_valid_field: true\n');
  return root;
}

// ---------------------------------------------------------------------------
// Output capture
// ---------------------------------------------------------------------------

interface Captured {
  stdout: string;
  stderr: string;
}

function capture(fn: () => unknown): Captured {
  let stdout = '';
  let stderr = '';
  const spyOut = vi.spyOn(process.stdout, 'write').mockImplementation((data) => {
    stdout += String(data);
    return true;
  });
  const spyErr = vi.spyOn(process.stderr, 'write').mockImplementation((data) => {
    stderr += String(data);
    return true;
  });
  try {
    fn();
  } finally {
    spyOut.mockRestore();
    spyErr.mockRestore();
  }
  return { stdout, stderr };
}

// ---------------------------------------------------------------------------
// Test lifecycle
// ---------------------------------------------------------------------------

let tempDirs: string[] = [];

function track(dir: string): string {
  tempDirs.push(dir);
  return dir;
}

beforeEach(() => {
  tempDirs = [];
});

afterEach(() => {
  vi.restoreAllMocks();
  for (const d of tempDirs) {
    rmSync(d, { recursive: true, force: true });
  }
});

// ===========================================================================
// validate-pack
// ===========================================================================

describe('validate-pack — valid pack', () => {
  it('returns exit code 0', () => {
    const packDir = track(makeValidPackDir());
    const code = runValidatePack(packDir, false);
    expect(code).toBe(0);
  });

  it('human output contains pack name and version', () => {
    const packDir = track(makeValidPackDir());
    const { stdout } = capture(() => runValidatePack(packDir, false));
    expect(stdout).toContain('✓');
    expect(stdout).toContain('CLI Test Pack');
    expect(stdout).toContain('0.2.0');
  });

  it('JSON output has status ok and expected fields', () => {
    const packDir = track(makeValidPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runValidatePack(packDir, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('ok');
    expect(result['pack_id']).toBe('test.cli_pack');
    expect(result['name']).toBe('CLI Test Pack');
    expect(result['version']).toBe('0.2.0');
    expect(result['scenario_count']).toBe(1);
  });
});

describe('validate-pack — broken pack', () => {
  it('returns exit code 1', () => {
    const packDir = track(makeBrokenPackDir());
    const code = runValidatePack(packDir, false);
    expect(code).toBe(1);
  });

  it('human output contains failure indicator', () => {
    const packDir = track(makeBrokenPackDir());
    const { stderr } = capture(() => runValidatePack(packDir, false));
    expect(stderr).toContain('✗');
  });

  it('JSON output has status error and error code', () => {
    const packDir = track(makeBrokenPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runValidatePack(packDir, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('error');
    expect(typeof (result['error'] as Record<string, unknown>)['code']).toBe('string');
  });
});

describe('validate-pack — path handling', () => {
  it('resolves paths relative to process.cwd()', () => {
    // Use an absolute path — the function must resolve it regardless of cwd.
    const packDir = track(makeValidPackDir());
    const code = runValidatePack(packDir, true);
    expect(code).toBe(0);
  });

  it('returns exit code 1 for non-existent path', () => {
    const code = runValidatePack('/tmp/this-does-not-exist-convsim-test', false);
    expect(code).toBe(1);
  });
});

// ===========================================================================
// test-pack
// ===========================================================================

describe('test-pack', () => {
  it('returns exit code 1 (not implemented)', () => {
    const code = runTestPack('/some/path', false);
    expect(code).toBe(1);
  });

  it('human output mentions the runner is not yet implemented', () => {
    const { stderr } = capture(() => runTestPack('/some/path', false));
    expect(stderr).toContain('not yet implemented');
    expect(stderr).toContain('validate-pack');
  });

  it('JSON output has status not_implemented', () => {
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runTestPack('/some/path', true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('not_implemented');
    expect(typeof result['message']).toBe('string');
  });
});

// ===========================================================================
// import-pack
// ===========================================================================

describe('import-pack — from directory', () => {
  it('returns exit code 0 for a valid pack', () => {
    const packDir = track(makeValidPackDir());
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(packDir, false, dataDir);
    expect(code).toBe(0);
  });

  it('human output confirms installation path', () => {
    const packDir = track(makeValidPackDir());
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const { stdout } = capture(() => runImportPack(packDir, false, dataDir));
    expect(stdout).toContain('✓');
    expect(stdout).toContain('CLI Test Pack');
    expect(stdout).toContain('test.cli_pack');
  });

  it('JSON output has status ok and dest field', () => {
    const packDir = track(makeValidPackDir());
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runImportPack(packDir, true, dataDir);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('ok');
    expect(result['pack_id']).toBe('test.cli_pack');
    expect(typeof result['dest']).toBe('string');
  });

  it('rejects a broken pack before writing anything', () => {
    const brokenDir = track(makeBrokenPackDir());
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(brokenDir, false, dataDir);
    expect(code).toBe(1);
  });

  it('rejects a pack containing an executable file', () => {
    const packDir = track(makeValidPackDir());
    writeFileSync(join(packDir, 'run.sh'), '#!/bin/sh\necho evil\n');
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(packDir, false, dataDir);
    expect(code).toBe(1);
    const { stderr } = capture(() => runImportPack(packDir, false, dataDir));
    expect(stderr).toContain('FORBIDDEN_FILE');
  });
});

describe('import-pack — from zip', () => {
  it('returns exit code 0 for a valid zip', () => {
    const packDir = makeValidPackDir();
    const tmp = track(mkdtempSync(join(tmpdir(), 'convsim-zip-src-')));
    track(packDir);
    const zipPath = join(tmp, 'test-pack.zip');
    const zip = new AdmZip();
    zip.addLocalFolder(packDir, '');
    zip.writeZip(zipPath);
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(zipPath, false, dataDir);
    expect(code).toBe(0);
  });

  it('imports from a zip that has a single top-level subdirectory', () => {
    const tmp = track(mkdtempSync(join(tmpdir(), 'convsim-zip-src-')));
    const packDir = makeValidPackDir(tmp);
    const zipPath = join(tmp, 'test-pack.zip');
    const zip = new AdmZip();
    // Add the pack with a directory prefix (common zip convention)
    zip.addLocalFolder(packDir, 'pack');
    zip.writeZip(zipPath);
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(zipPath, false, dataDir);
    expect(code).toBe(0);
  });

  it('rejects a zip containing an unsafe pack', () => {
    const packDir = makeValidPackDir();
    track(packDir);
    writeFileSync(join(packDir, 'run.sh'), '#!/bin/sh\necho evil\n');
    const tmp = track(mkdtempSync(join(tmpdir(), 'convsim-zip-src-')));
    const zipPath = join(tmp, 'unsafe.zip');
    const zip = new AdmZip();
    zip.addLocalFolder(packDir, '');
    zip.writeZip(zipPath);
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(zipPath, false, dataDir);
    expect(code).toBe(1);
  });

  it('rejects a zip with path-traversal entries (zip-slip)', () => {
    const tmp = track(mkdtempSync(join(tmpdir(), 'convsim-zip-slip-')));
    const zipPath = join(tmp, 'slip.zip');
    const zip = new AdmZip();
    zip.addFile('../../evil.txt', Buffer.from('pwned'));
    zip.writeZip(zipPath);
    const dataDir = track(mkdtempSync(join(tmpdir(), 'convsim-data-')));
    const code = runImportPack(zipPath, false, dataDir);
    expect(code).toBe(1);
  });
});

// ===========================================================================
// export-pack
// ===========================================================================

describe('export-pack', () => {
  it('returns exit code 0 for a valid pack', () => {
    const packDir = track(makeValidPackDir());
    const outDir = track(mkdtempSync(join(tmpdir(), 'convsim-export-')));
    const outputPath = join(outDir, 'out.zip');
    const code = runExportPack(packDir, false, outputPath);
    expect(code).toBe(0);
  });

  it('creates a zip file at the specified output path', () => {
    const packDir = track(makeValidPackDir());
    const outDir = track(mkdtempSync(join(tmpdir(), 'convsim-export-')));
    const outputPath = join(outDir, 'out.zip');
    runExportPack(packDir, false, outputPath);
    const st = statSync(outputPath);
    expect(st.size).toBeGreaterThan(0);
  });

  it('zip contains manifest.yaml at the root (no absolute paths)', () => {
    const packDir = track(makeValidPackDir());
    const outDir = track(mkdtempSync(join(tmpdir(), 'convsim-export-')));
    const outputPath = join(outDir, 'out.zip');
    runExportPack(packDir, false, outputPath);
    const zip = new AdmZip(outputPath);
    const entries = zip.getEntries().map((e) => e.entryName);
    expect(entries.some((e) => e === 'manifest.yaml' || e.endsWith('/manifest.yaml'))).toBe(true);
    // No entry should start with '/' or contain an absolute Windows path
    for (const e of entries) {
      expect(e.startsWith('/')).toBe(false);
      expect(/^[A-Za-z]:[\\/]/.test(e)).toBe(false);
    }
  });

  it('JSON output contains output path and size', () => {
    const packDir = track(makeValidPackDir());
    const outDir = track(mkdtempSync(join(tmpdir(), 'convsim-export-')));
    const outputPath = join(outDir, 'out.zip');
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runExportPack(packDir, true, outputPath);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('ok');
    expect(result['output']).toBe(outputPath);
    expect(typeof result['size_bytes']).toBe('number');
  });

  it('defaults output filename to <pack_id>-<version>.zip', () => {
    const packDir = track(makeValidPackDir());
    const outDir = track(mkdtempSync(join(tmpdir(), 'convsim-export-')));
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    // Override cwd so the default output lands in outDir
    const origCwd = process.cwd;
    process.cwd = () => outDir;
    try {
      runExportPack(packDir, true);
    } finally {
      process.cwd = origCwd;
      spy.mockRestore();
    }
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(String(result['output'])).toContain('test.cli_pack-0.2.0.zip');
  });

  it('returns exit code 1 for a broken pack', () => {
    const brokenDir = track(makeBrokenPackDir());
    const outDir = track(mkdtempSync(join(tmpdir(), 'convsim-export-')));
    const outputPath = join(outDir, 'out.zip');
    const code = runExportPack(brokenDir, false, outputPath);
    expect(code).toBe(1);
  });
});
