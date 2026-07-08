// SPDX-License-Identifier: Apache-2.0
import { resolve } from 'node:path';
import { loadPack, PackLoaderError } from '@convsim/pack-loader';
import { runPackTests } from '../runner/index.js';
import type { PackTestRunResult, FixtureRunResult } from '../runner/index.js';
import { writeJson, writeLine, writeErrorLine } from '../output.js';

export type { PackTestRunResult };

// ---------------------------------------------------------------------------
// Command
// ---------------------------------------------------------------------------

/**
 * Run the automated test suite for a pack.
 *
 * Runs all pack-test fixtures found in the pack's `tests/` directory using the
 * deterministic fake runtime. No language model is required for CI.
 *
 * Exit codes:
 *   0 — all fixtures passed (skipped fixtures are not counted as failures)
 *   1 — one or more fixtures failed, or the pack could not be loaded
 *   3 — unexpected system error
 */
export function runTestPack(packPath: string, json: boolean): number {
  const absPath = resolve(packPath);

  try {
    const pack = loadPack(absPath, 'local-dev');
    const result = runPackTests(pack);

    if (json) {
      writeJson(result);
    } else {
      renderHuman(result);
    }

    return result.failed === 0 ? 0 : 1;
  } catch (e) {
    if (e instanceof PackLoaderError) {
      if (json) {
        writeJson({
          status: 'error',
          error: {
            code: e.code,
            message: e.message,
            ...(e.filePath !== undefined ? { file: e.filePath } : {}),
          },
        });
      } else {
        writeErrorLine(`✗ Pack load failed: ${e.code}`);
        writeErrorLine(`  ${e.message}`);
        if (e.filePath !== undefined) {
          writeErrorLine(`  File: ${e.filePath}`);
        }
      }
      return 1;
    }

    const msg = e instanceof Error ? e.message : String(e);
    if (json) {
      writeJson({ status: 'error', error: { code: 'UNEXPECTED_ERROR', message: msg } });
    } else {
      writeErrorLine(`✗ Unexpected error: ${msg}`);
    }
    return 3;
  }
}

// ---------------------------------------------------------------------------
// Human-readable rendering
// ---------------------------------------------------------------------------

function renderHuman(result: PackTestRunResult): void {
  writeLine(
    `Running pack tests: ${result.pack_name} (${result.pack_id})`,
  );
  writeLine('');

  for (const fixture of result.fixtures) {
    renderFixture(fixture);
  }

  writeLine('');

  const total = result.fixture_count;
  if (result.failed === 0) {
    const parts: string[] = [];
    if (result.passed > 0) parts.push(`${result.passed} passed`);
    if (result.skipped > 0) parts.push(`${result.skipped} skipped`);
    writeLine(`✓ ${parts.join(', ')} (${total} fixture${total !== 1 ? 's' : ''} total)`);
  } else {
    writeErrorLine(
      `✗ ${result.failed} failed, ${result.passed} passed` +
        (result.skipped > 0 ? `, ${result.skipped} skipped` : '') +
        ` (${total} fixture${total !== 1 ? 's' : ''} total)`,
    );
  }
}

function renderFixture(fixture: FixtureRunResult): void {
  const icon = fixture.status === 'passed' ? '✓' : fixture.status === 'skipped' ? '–' : '✗';
  const label = `[${fixture.mode}]`;

  writeLine(`  ${icon} ${fixture.fixture_id}  ${label}  ${fixture.scenario_id}`);

  if (fixture.status === 'skipped' && fixture.skip_reason) {
    writeLine(`    skip: ${fixture.skip_reason}`);
    return;
  }

  if (fixture.status === 'failed') {
    for (const failure of fixture.failures) {
      writeErrorLine(`    ✗ ${failure.description}`);
      if (failure.path !== undefined) {
        writeErrorLine(`      path:   ${failure.path}`);
      }
      if (failure.check !== undefined) {
        writeErrorLine(`      check:  ${failure.check}`);
      }
      if (failure.actual !== undefined) {
        writeErrorLine(`      actual: ${JSON.stringify(failure.actual)}`);
      }
    }
  }
}
