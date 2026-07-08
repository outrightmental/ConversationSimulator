// SPDX-License-Identifier: Apache-2.0
import { statSync, mkdirSync, cpSync, rmSync, mkdtempSync, readdirSync } from 'node:fs';
import { resolve, join, extname, dirname, isAbsolute } from 'node:path';
import { tmpdir } from 'node:os';
import AdmZip from 'adm-zip';
import { loadPack, PackIndex, PackLoaderError } from '@convsim/pack-loader';
import { getPacksDir, getDbPath } from '../paths.js';
import { writeJson, writeLine, writeErrorLine } from '../output.js';

// ---------------------------------------------------------------------------
// Result shape
// ---------------------------------------------------------------------------

export type ImportPackResult =
  | {
      status: 'ok';
      pack_id: string;
      name: string;
      version: string;
      dest: string;
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
// Helpers
// ---------------------------------------------------------------------------

function detectSourceKind(absPath: string): 'zip' | 'dir' {
  let st;
  try {
    st = statSync(absPath);
  } catch {
    throw new PackLoaderError('MISSING_FILE', `Path does not exist: ${absPath}`, absPath);
  }
  if (st.isDirectory()) return 'dir';
  if (st.isFile() && extname(absPath).toLowerCase() === '.zip') return 'zip';
  throw new PackLoaderError(
    'INVALID_SOURCE',
    `Source must be a directory or a .zip file: ${absPath}`,
    absPath,
  );
}

/**
 * Reject zip entries that would escape the extraction root (zip-slip).
 * AdmZip does not sanitise entry names, so a crafted zip could write to
 * arbitrary filesystem locations before loadPack's security scan runs.
 * Throws PackLoaderError so the caller treats it as a user-facing rejection
 * (exit code 1) rather than an unexpected error (exit code 3).
 */
function assertNoZipSlip(zip: AdmZip): void {
  for (const entry of zip.getEntries()) {
    const name = entry.entryName;
    if (isAbsolute(name)) {
      throw new PackLoaderError('UNSAFE_ZIP', `Zip entry has absolute path: "${name}"`, name);
    }
    const parts = name.split(/[\\/]/);
    if (parts.some((p) => p === '..')) {
      throw new PackLoaderError(
        'UNSAFE_ZIP',
        `Zip entry attempts path traversal: "${name}"`,
        name,
      );
    }
  }
}

/**
 * If the extracted zip contains exactly one top-level directory, return it.
 * This handles zips created with `zip -r pack-name.zip my-pack/`.
 */
function unwrapSingleSubdir(dir: string): string {
  const entries = readdirSync(dir);
  if (entries.length === 1) {
    const first = entries[0];
    if (first !== undefined) {
      const candidate = join(dir, first);
      if (statSync(candidate).isDirectory()) return candidate;
    }
  }
  return dir;
}

// ---------------------------------------------------------------------------
// Command
// ---------------------------------------------------------------------------

/**
 * Import (copy) a pack into the user data directory and register it in the index.
 *
 * Accepts either a directory or a .zip file.  The pack is fully validated
 * (including the security scan in loadPack) before any files are written.
 *
 * `dataDir` overrides the default data root — useful for tests and CI.
 *
 * Exit codes:
 *   0 — pack imported successfully
 *   1 — pack is invalid or unsafe
 *   3 — unexpected system error
 */
export function runImportPack(
  source: string,
  json: boolean,
  dataDir?: string,
): number {
  const absSource = resolve(source);
  let tempDir: string | null = null;

  try {
    let packDir: string;
    const kind = detectSourceKind(absSource);

    if (kind === 'zip') {
      tempDir = mkdtempSync(join(tmpdir(), 'convsim-import-'));
      const zip = new AdmZip(absSource);
      assertNoZipSlip(zip);
      zip.extractAllTo(tempDir, /* overwrite */ true);
      packDir = unwrapSingleSubdir(tempDir);
    } else {
      packDir = absSource;
    }

    // Validate (runs security scan + schema validation) — reads only, no writes yet.
    const pack = loadPack(packDir, 'community');

    const packsDir = dataDir ? join(dataDir, 'packs') : getPacksDir();
    const destDir = join(packsDir, pack.manifest.pack_id);

    // Atomically replace any previous installation.
    mkdirSync(packsDir, { recursive: true });
    rmSync(destDir, { recursive: true, force: true });
    cpSync(packDir, destDir, { recursive: true });

    // Register in the SQLite index from the installed location.
    const dbPath = dataDir ? join(dataDir, 'index.db') : getDbPath();
    mkdirSync(dirname(dbPath), { recursive: true });
    const index = PackIndex.open(dbPath);
    try {
      const installedPack = loadPack(destDir, 'community');
      index.importPack(installedPack);
    } finally {
      index.close();
    }

    const result: ImportPackResult = {
      status: 'ok',
      pack_id: pack.manifest.pack_id,
      name: pack.manifest.name,
      version: pack.manifest.version,
      dest: destDir,
    };

    if (json) {
      writeJson(result);
    } else {
      writeLine(
        `✓ Pack imported: ${pack.manifest.name} (${pack.manifest.pack_id}) v${pack.manifest.version}`,
      );
      writeLine(`  Installed to: ${destDir}`);
    }

    return 0;
  } catch (e) {
    if (e instanceof PackLoaderError) {
      const result: ImportPackResult = {
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
        writeErrorLine(`✗ Import rejected: ${e.code}`);
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
  } finally {
    if (tempDir !== null) {
      rmSync(tempDir, { recursive: true, force: true });
    }
  }
}
