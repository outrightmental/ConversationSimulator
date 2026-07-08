// SPDX-License-Identifier: Apache-2.0
import { statSync } from 'node:fs';
import { resolve, join } from 'node:path';
import AdmZip from 'adm-zip';
import { loadPack, PackLoaderError } from '@convsim/pack-loader';
import { writeJson, writeLine, writeErrorLine, formatBytes } from '../output.js';

// ---------------------------------------------------------------------------
// Result shape
// ---------------------------------------------------------------------------

export type ExportPackResult =
  | {
      status: 'ok';
      pack_id: string;
      name: string;
      version: string;
      output: string;
      size_bytes: number;
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
 * Export a pack directory to a .zip archive.
 *
 * The pack is validated before archiving, so the output is guaranteed to be
 * a valid pack.  All paths inside the zip are relative to the pack root —
 * no absolute paths leak into the archive.
 *
 * `outputPath` defaults to `<cwd>/<pack_id>-<version>.zip`.
 *
 * Exit codes:
 *   0 — archive created successfully
 *   1 — pack is invalid
 *   3 — unexpected system error
 */
export function runExportPack(
  packPath: string,
  json: boolean,
  outputPath?: string,
): number {
  const absPackPath = resolve(packPath);

  try {
    // Validate the pack before archiving (runs security scan + schema validation).
    const pack = loadPack(absPackPath, 'local-dev');

    const safeName = pack.manifest.pack_id.replace(/[^a-zA-Z0-9._-]/g, '_');
    const filename = `${safeName}-${pack.manifest.version}.zip`;
    const dest = outputPath ? resolve(outputPath) : join(process.cwd(), filename);

    // Build the zip with paths relative to the pack root.
    // addLocalFolder(localPath, zipPath='') places files at the zip root with
    // their path relative to localPath — no absolute or parent-directory refs.
    const zip = new AdmZip();
    zip.addLocalFolder(absPackPath, '');
    zip.writeZip(dest);

    const sizeBytes = statSync(dest).size;

    const result: ExportPackResult = {
      status: 'ok',
      pack_id: pack.manifest.pack_id,
      name: pack.manifest.name,
      version: pack.manifest.version,
      output: dest,
      size_bytes: sizeBytes,
    };

    if (json) {
      writeJson(result);
    } else {
      writeLine(
        `✓ Pack exported: ${pack.manifest.name} (${pack.manifest.pack_id}) v${pack.manifest.version}`,
      );
      writeLine(`  Archive: ${dest} (${formatBytes(sizeBytes)})`);
    }

    return 0;
  } catch (e) {
    if (e instanceof PackLoaderError) {
      const result: ExportPackResult = {
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
        writeErrorLine(`✗ Export failed: ${e.code}`);
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
