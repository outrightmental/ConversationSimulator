// SPDX-License-Identifier: Apache-2.0
import { readFileSync, existsSync } from 'node:fs';
import { resolve, relative, normalize, isAbsolute } from 'node:path';
import { PackLoaderError } from './types.js';

/**
 * Resolve `ref` relative to `baseDir` and verify the result stays within
 * `packRoot`. Throws PackLoaderError with code PATH_TRAVERSAL if the resolved
 * path would escape the pack root directory.
 *
 * Two traversal vectors are guarded:
 *   - `rel.startsWith('..')` — catches ancestor-directory escapes on any OS.
 *   - `isAbsolute(rel)` — catches cross-drive refs on Windows, where
 *     `path.relative('C:\\pack', 'D:\\evil')` returns `'D:\\evil'` (an
 *     absolute path) rather than a `..`-prefixed relative path.
 */
export function resolveRef(baseDir: string, packRoot: string, ref: string): string {
  if (ref.includes('\0')) {
    throw new PackLoaderError('PATH_TRAVERSAL', `Null byte in ref: "${ref}"`, ref);
  }
  const abs = normalize(resolve(baseDir, ref));
  const rel = relative(normalize(packRoot), abs);
  if (rel.startsWith('..') || isAbsolute(rel)) {
    throw new PackLoaderError(
      'PATH_TRAVERSAL',
      `Ref "${ref}" escapes the pack root "${packRoot}"`,
      ref,
    );
  }
  return abs;
}

/** Read a file as UTF-8. Throws PackLoaderError(MISSING_FILE) if not found. */
export function readPackFile(absPath: string): string {
  if (!existsSync(absPath)) {
    throw new PackLoaderError('MISSING_FILE', `File not found: ${absPath}`, absPath);
  }
  return readFileSync(absPath, 'utf8');
}
