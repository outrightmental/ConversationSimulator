// SPDX-License-Identifier: Apache-2.0
import { resolve } from 'node:path';
import { loadPack, PackLoaderError } from '@convsim/pack-loader';
import { writeJson, writeLine, writeErrorLine } from '../output.js';

// ---------------------------------------------------------------------------
// Result shape (stable contract for --json mode and CI)
// ---------------------------------------------------------------------------

export type ValidatePackResult =
  | {
      status: 'ok';
      pack_id: string;
      name: string;
      version: string;
      scenario_count: number;
      npc_count: number;
      rubric_count: number;
    }
  | {
      status: 'error';
      error: {
        code: string;
        message: string;
        file?: string;
      };
    };

// ---------------------------------------------------------------------------
// Command
// ---------------------------------------------------------------------------

/**
 * Validate a pack directory and report the result.
 *
 * Exit codes:
 *   0 — pack is valid
 *   1 — pack has validation errors
 *   3 — unexpected system error (e.g. path does not exist)
 */
export function runValidatePack(packPath: string, json: boolean): number {
  const absPath = resolve(packPath);

  try {
    const pack = loadPack(absPath, 'local-dev');

    const result: ValidatePackResult = {
      status: 'ok',
      pack_id: pack.manifest.pack_id,
      name: pack.manifest.name,
      version: pack.manifest.version,
      scenario_count: pack.scenarios.length,
      npc_count: pack.npcs.size,
      rubric_count: pack.rubrics.size,
    };

    if (json) {
      writeJson(result);
    } else {
      writeLine(
        `✓ Pack valid: ${pack.manifest.name} (${pack.manifest.pack_id}) v${pack.manifest.version}`,
      );
      const parts = [
        `${pack.scenarios.length} scenario${pack.scenarios.length !== 1 ? 's' : ''}`,
        `${pack.npcs.size} NPC${pack.npcs.size !== 1 ? 's' : ''}`,
        `${pack.rubrics.size} rubric${pack.rubrics.size !== 1 ? 's' : ''}`,
      ];
      if (pack.scenes.size > 0) {
        parts.push(`${pack.scenes.size} scene${pack.scenes.size !== 1 ? 's' : ''}`);
      }
      writeLine(`  ${parts.join(' · ')}`);
    }

    return 0;
  } catch (e) {
    if (e instanceof PackLoaderError) {
      const result: ValidatePackResult = {
        status: 'error',
        error: {
          code: e.code,
          message: e.message,
          ...(e.filePath !== undefined ? { file: e.filePath } : {}),
        },
      };

      if (json) {
        writeJson(result);
      } else {
        writeErrorLine(`✗ Pack validation failed: ${e.code}`);
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
