// SPDX-License-Identifier: Apache-2.0
import { resolve } from 'node:path';
import { loadPack, PackLoaderError } from '@convsim/pack-loader';
import type { ValidationWarning } from '@convsim/pack-loader';
import { writeJson, writeLine, writeErrorLine } from '../output.js';

// ---------------------------------------------------------------------------
// Result shape (stable contract for --json mode and CI)
// ---------------------------------------------------------------------------

export type ValidatePackWarning = {
  code: string;
  message: string;
  field: string;
};

export type ValidatePackResult =
  | {
      status: 'ok';
      pack_id: string;
      name: string;
      version: string;
      content_rating: string;
      license: string;
      scenario_count: number;
      npc_count: number;
      rubric_count: number;
      scene_count: number;
      warning_count: number;
      warnings: ValidatePackWarning[];
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
 *   0 — pack is valid (warnings may be present)
 *   1 — pack is invalid or cannot be found (PackLoaderError)
 *   3 — unexpected system error (OS error, out of memory, etc.)
 */
export function runValidatePack(packPath: string, json: boolean): number {
  const absPath = resolve(packPath);

  try {
    const pack = loadPack(absPath, 'local-dev');

    const warnings: ValidatePackWarning[] = pack.warnings.map((w: ValidationWarning) => ({
      code: w.code,
      message: w.message,
      field: w.field,
    }));

    const result: ValidatePackResult = {
      status: 'ok',
      pack_id: pack.manifest.pack_id,
      name: pack.manifest.name,
      version: pack.manifest.version,
      content_rating: pack.manifest.content_rating,
      license: pack.manifest.license,
      scenario_count: pack.scenarios.length,
      npc_count: pack.npcs.size,
      rubric_count: pack.rubrics.size,
      scene_count: pack.scenes.size,
      warning_count: warnings.length,
      warnings,
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
      writeLine(`  License: ${pack.manifest.license}  Rating: ${pack.manifest.content_rating}`);
      if (warnings.length > 0) {
        writeLine(`  ${warnings.length} warning${warnings.length !== 1 ? 's' : ''}:`);
        for (const w of warnings) {
          writeLine(`  ⚠ [${w.code}] ${w.field}`);
          writeLine(`    ${w.message}`);
        }
      }
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
