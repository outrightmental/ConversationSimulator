// SPDX-License-Identifier: Apache-2.0
import { homedir } from 'node:os';
import { join } from 'node:path';

/**
 * Return the root data directory for convsim user data.
 * Prefer CONVSIM_DATA_DIR so tests and CI can point to a temp directory.
 */
export function getDataDir(): string {
  const override = process.env['CONVSIM_DATA_DIR'];
  if (override) return override;

  const home = homedir();
  if (process.platform === 'darwin') {
    return join(home, 'Library', 'Application Support', 'convsim');
  }
  if (process.platform === 'win32') {
    const appData = process.env['APPDATA'] ?? join(home, 'AppData', 'Roaming');
    return join(appData, 'convsim');
  }
  const xdgData = process.env['XDG_DATA_HOME'] ?? join(home, '.local', 'share');
  return join(xdgData, 'convsim');
}

export function getPacksDir(): string {
  return join(getDataDir(), 'packs');
}

export function getDbPath(): string {
  return join(getDataDir(), 'index.db');
}
