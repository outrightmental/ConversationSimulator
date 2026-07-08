// SPDX-License-Identifier: Apache-2.0
import { writeJson, writeErrorLine } from '../output.js';

// ---------------------------------------------------------------------------
// Result shape
// ---------------------------------------------------------------------------

export interface TestPackResult {
  status: 'not_implemented';
  message: string;
}

// ---------------------------------------------------------------------------
// Command
// ---------------------------------------------------------------------------

/**
 * Stub for the future pack test runner.
 *
 * Exit codes:
 *   1 — not implemented (lets CI pipelines catch that this was a no-op)
 */
export function runTestPack(_packPath: string, json: boolean): number {
  const msg =
    'The automated test runner is not yet available. ' +
    'Use validate-pack to check your pack for schema and content errors in the meantime.';

  if (json) {
    writeJson({ status: 'not_implemented', message: msg } satisfies TestPackResult);
  } else {
    writeErrorLine('⚠ test-pack: The automated test runner is not yet implemented.');
    writeErrorLine('  Use validate-pack to check pack schema and content instead.');
  }

  return 1;
}
