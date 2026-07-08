// SPDX-License-Identifier: Apache-2.0
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { parseAndValidate } from './validator.js';
import type { RawFixture } from './types.js';

export interface LoadedFixture {
  filePath: string;
  fixture: RawFixture;
}

export interface FixtureLoadError {
  filePath: string;
  error: string;
}

export interface LoadFixturesResult {
  fixtures: LoadedFixture[];
  errors: FixtureLoadError[];
}

/**
 * Load and validate all pack-test fixture YAML files from a pack's `tests/`
 * subdirectory. Files that fail schema validation are collected in `errors`
 * and excluded from `fixtures`.
 */
export function loadFixtures(packRoot: string): LoadFixturesResult {
  const testsDir = join(packRoot, 'tests');

  if (!existsSync(testsDir)) {
    return { fixtures: [], errors: [] };
  }

  const fixtures: LoadedFixture[] = [];
  const errors: FixtureLoadError[] = [];

  let files: string[];
  try {
    files = readdirSync(testsDir)
      .filter((f) => f.endsWith('.yaml') || f.endsWith('.yml'))
      .sort()
      .map((f) => join(testsDir, f));
  } catch {
    return { fixtures: [], errors: [] };
  }

  for (const filePath of files) {
    try {
      const text = readFileSync(filePath, 'utf8');
      const fixture = parseAndValidate<RawFixture>(text, 'pack-test', filePath);
      fixtures.push({ filePath, fixture });
    } catch (e) {
      errors.push({
        filePath,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return { fixtures, errors };
}
