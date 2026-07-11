// SPDX-License-Identifier: Apache-2.0
//
// Steam Workshop sync routes.
//
// These routes implement the server-side half of the Workshop subscribe/sync
// flow. The Tauri desktop bridge supplies subscribed item paths via the
// `steam_workshop_get_subscribed_items` command; this layer validates and
// imports them through the same pipeline as manual zip import (pack-loader
// schema validation + no-executable-content guard).
//
// Non-Steam builds never call these routes — the Workshop UI is hidden when
// `SteamStatus.is_steam_enabled` is false.

import fs from 'node:fs';
import path from 'node:path';
import type { FastifyInstance } from 'fastify';
import { loadPack, PackIndex, PackLoaderError, type LoadedPack } from '@convsim/pack-loader';
import { getDb } from '../db.js';
import {
  scanForbiddenFiles,
  convertPackLoaderError,
  type WorkbenchValidationIssue,
} from './workbench.js';

let _workshopRoot = '';

export function setWorkshopRoot(workshopRoot: string): void {
  _workshopRoot = workshopRoot;
}

export function getWorkshopRoot(): string {
  return _workshopRoot;
}

// Path to the shared pack index (installed_packs / indexed_scenarios). Workshop
// packs are registered here through the same PackIndex used by manual import so
// their scenarios become visible in the library and launchable at runtime.
let _packsDbPath: string | null = null;

export function setWorkshopPacksDbPath(dbPath: string | null): void {
  _packsDbPath = dbPath;
}

export function getWorkshopPacksDbPath(): string | null {
  return _packsDbPath;
}

// ---------------------------------------------------------------------------
// Request / response shapes
// ---------------------------------------------------------------------------

/** A single subscribed Workshop item as reported by the Tauri Steam bridge. */
export interface WorkshopSyncItem {
  item_id: string;
  install_path: string;
  needs_update: boolean;
  updated_at: number;
}

export interface WorkshopSyncRequest {
  items: WorkshopSyncItem[];
}

export interface WorkshopSyncResultEntry {
  item_id: string;
  pack_id: string | null;
  status: 'imported' | 'updated' | 'unchanged' | 'quarantined' | 'skipped';
  /** Present when status is 'quarantined'. */
  reason?: string;
  /** Non-fatal warnings from content analysis. */
  warnings?: WorkbenchValidationIssue[];
}

export interface WorkshopSyncResponse {
  results: WorkshopSyncResultEntry[];
  imported: number;
  updated: number;
  unchanged: number;
  quarantined: number;
  skipped: number;
}

export interface WorkshopItemRecord {
  item_id: string;
  pack_id: string;
  author_name: string;
  install_path: string;
  workshop_updated_at: number;
  synced_at: number;
}

// ---------------------------------------------------------------------------
// Route registration
// ---------------------------------------------------------------------------

export async function workshopRoutes(app: FastifyInstance): Promise<void> {
  // POST /api/workshop/sync
  //
  // Accepts the list of subscribed Workshop items from the Tauri bridge and
  // imports any that are new or updated through the exact same pipeline as
  // manual pack import: forbidden-content scan + pack-loader schema validation.
  //
  // Invalid packs are quarantined (recorded in workshop_quarantine) rather than
  // imported; they never crash the library. The caller is responsible for
  // showing quarantine reasons to the user.
  //
  // Items with an empty `install_path` are still downloading and are skipped.
  app.post<{ Body: WorkshopSyncRequest }>(
    '/api/workshop/sync',
    async (req, reply): Promise<WorkshopSyncResponse> => {
      const { items } = req.body;
      if (!Array.isArray(items)) {
        reply.status(400);
        throw new Error('Body must include an "items" array');
      }

      const db = getDb();
      const now = Math.floor(Date.now() / 1000);
      const results: WorkshopSyncResultEntry[] = [];

      for (const item of items) {
        if (!item.item_id || typeof item.item_id !== 'string') {
          results.push({ item_id: String(item.item_id ?? ''), pack_id: null, status: 'skipped', reason: 'Missing item_id' });
          continue;
        }

        // Skip items that Steam hasn't downloaded yet.
        if (!item.install_path || typeof item.install_path !== 'string') {
          results.push({ item_id: item.item_id, pack_id: null, status: 'skipped', reason: 'Not yet downloaded' });
          continue;
        }

        const installPath = item.install_path;

        // Verify the install path exists and is a directory.
        let stat: fs.Stats;
        try {
          stat = fs.statSync(installPath);
        } catch {
          results.push({ item_id: item.item_id, pack_id: null, status: 'skipped', reason: `Install path not accessible: ${installPath}` });
          continue;
        }
        if (!stat.isDirectory()) {
          results.push({ item_id: item.item_id, pack_id: null, status: 'skipped', reason: `Install path is not a directory: ${installPath}` });
          continue;
        }

        // Check if we already have this item at the same version.
        const existing = db
          .prepare('SELECT pack_id, workshop_updated_at FROM workshop_items WHERE item_id = ?')
          .get(item.item_id) as { pack_id: string; workshop_updated_at: number } | undefined;

        if (existing && existing.workshop_updated_at === item.updated_at && !item.needs_update) {
          results.push({ item_id: item.item_id, pack_id: existing.pack_id, status: 'unchanged' });
          continue;
        }

        // Two-phase validation (same pipeline as manual import and workbench validate).
        const securityIssues: WorkbenchValidationIssue[] = scanForbiddenFiles(installPath);
        const reportedSecurityFiles = new Set(securityIssues.filter((i) => i.category === 'security').map((i) => i.file));
        const validationIssues: WorkbenchValidationIssue[] = [...securityIssues];

        let pack_id: string | null = null;
        let author_name = '';
        let packLoadWarnings: WorkbenchValidationIssue[] = [];
        let loadedPack: LoadedPack | null = null;

        try {
          const loaded = loadPack(installPath, 'workshop');
          loadedPack = loaded;
          pack_id = loaded.manifest.pack_id;
          author_name = loaded.manifest.author;
          // Convert pack-loader ValidationWarning to the workbench issue shape.
          packLoadWarnings = loaded.warnings.map((w) => ({
            severity: 'warning' as const,
            rule_id: w.code,
            file: w.field,
            pointer: '',
            message: w.message,
            suggested_fix: '',
          }));
        } catch (e) {
          if (e instanceof PackLoaderError) {
            for (const issue of convertPackLoaderError(e, installPath)) {
              if (issue.category === 'security' && reportedSecurityFiles.has(issue.file)) continue;
              validationIssues.push(issue);
            }
          } else {
            throw e;
          }
        }

        const errors = validationIssues.filter((i) => i.severity === 'error');

        if (errors.length > 0 || pack_id === null || loadedPack === null) {
          // Quarantine the invalid pack — record the reason but never import it.
          const reason = errors.length > 0
            ? errors.map((e) => `${e.rule_id}: ${e.message}`).join('; ')
            : 'Pack manifest could not be loaded';
          db.prepare(`
            INSERT INTO workshop_quarantine (item_id, install_path, reason, quarantined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
              install_path = excluded.install_path,
              reason = excluded.reason,
              quarantined_at = excluded.quarantined_at
          `).run(item.item_id, installPath, reason, now);

          results.push({ item_id: item.item_id, pack_id: null, status: 'quarantined', reason });
          continue;
        }

        // Register the validated pack in the shared pack index — the exact same
        // step manual zip import performs (packs.ts). Without this the pack's
        // scenarios never appear in the library and cannot be launched. The pack
        // is indexed in place at its Steam install path; Steam owns those files
        // and updates them on the next sync.
        if (_packsDbPath) {
          const index = PackIndex.open(_packsDbPath);
          try {
            index.importPack(loadedPack);
          } finally {
            index.close();
          }
        }

        // Remove from quarantine if it was previously listed there (pack was fixed upstream).
        db.prepare('DELETE FROM workshop_quarantine WHERE item_id = ?').run(item.item_id);

        // Record the Workshop item metadata.
        db.prepare(`
          INSERT INTO workshop_items (item_id, pack_id, author_name, install_path, workshop_updated_at, synced_at)
          VALUES (?, ?, ?, ?, ?, ?)
          ON CONFLICT(item_id) DO UPDATE SET
            pack_id = excluded.pack_id,
            author_name = excluded.author_name,
            install_path = excluded.install_path,
            workshop_updated_at = excluded.workshop_updated_at,
            synced_at = excluded.synced_at
        `).run(item.item_id, pack_id, author_name, installPath, item.updated_at, now);

        const status = existing ? 'updated' : 'imported';
        results.push({
          item_id: item.item_id,
          pack_id,
          status,
          warnings: packLoadWarnings.length > 0 ? packLoadWarnings : undefined,
        });
      }

      const counts = {
        imported: results.filter((r) => r.status === 'imported').length,
        updated: results.filter((r) => r.status === 'updated').length,
        unchanged: results.filter((r) => r.status === 'unchanged').length,
        quarantined: results.filter((r) => r.status === 'quarantined').length,
        skipped: results.filter((r) => r.status === 'skipped').length,
      };

      return { results, ...counts };
    },
  );

  // GET /api/workshop/items
  //
  // Returns all successfully synced Workshop items with their metadata.
  // The library uses this to badge Workshop packs with author + update state.
  app.get('/api/workshop/items', async (): Promise<{ items: WorkshopItemRecord[] }> => {
    const db = getDb();
    const rows = db.prepare('SELECT * FROM workshop_items ORDER BY synced_at DESC').all() as WorkshopItemRecord[];
    return { items: rows };
  });

  // GET /api/workshop/quarantine
  //
  // Returns all quarantined Workshop items so the UI can show creators why
  // their subscribed packs were rejected.
  app.get('/api/workshop/quarantine', async (): Promise<{
    items: Array<{ item_id: string; install_path: string; reason: string; quarantined_at: number }>;
  }> => {
    const db = getDb();
    const rows = db
      .prepare('SELECT * FROM workshop_quarantine ORDER BY quarantined_at DESC')
      .all() as Array<{ item_id: string; install_path: string; reason: string; quarantined_at: number }>;
    return { items: rows };
  });

  // DELETE /api/workshop/:pack_id
  //
  // Remove a Workshop pack from the local index after the player unsubscribes.
  // Respects sessions that still reference the pack: when active or in-progress
  // sessions exist, the pack record is kept but marked for cleanup on next sync.
  //
  // The Workshop files themselves are removed by Steam — this only cleans up
  // the in-app metadata and pack index entries.
  app.delete<{ Params: { pack_id: string } }>(
    '/api/workshop/:pack_id',
    async (req, reply): Promise<{
      removed: boolean;
      has_active_sessions: boolean;
      message: string;
    }> => {
      const { pack_id } = req.params;
      if (!pack_id) {
        reply.status(400);
        throw new Error('pack_id is required');
      }

      const db = getDb();

      // Check for sessions that reference this pack's scenarios.
      const activeCount = (db.prepare(`
        SELECT COUNT(*) as cnt FROM sessions
        WHERE setup_json LIKE ?
          AND state NOT IN ('Ended', 'Abandoned')
      `).get(`%"pack_id":"${pack_id}"%`) as { cnt: number }).cnt;

      if (activeCount > 0) {
        return {
          removed: false,
          has_active_sessions: true,
          message: `Pack "${pack_id}" has ${activeCount} active session(s). Unsubscribe will take effect after those sessions end.`,
        };
      }

      // Look up the Steam item_id before we delete the workshop_items row.
      const existingItem = db
        .prepare('SELECT item_id FROM workshop_items WHERE pack_id = ?')
        .get(pack_id) as { item_id: string } | undefined;

      // Remove from workshop_items.
      db.prepare('DELETE FROM workshop_items WHERE pack_id = ?').run(pack_id);

      // Remove the pack (and its scenarios) from the shared pack index so the
      // imported content disappears from the library. Mirrors the registration
      // performed during sync; the Workshop files themselves are removed by Steam.
      if (_packsDbPath) {
        const index = PackIndex.open(_packsDbPath);
        try {
          index.removePack(pack_id);
        } finally {
          index.close();
        }
      }

      // Clean up any quarantine record for the same Steam item (e.g. if the
      // pack was previously quarantined and then successfully imported).
      if (existingItem) {
        db.prepare('DELETE FROM workshop_quarantine WHERE item_id = ?').run(existingItem.item_id);
      }

      return {
        removed: true,
        has_active_sessions: false,
        message: `Workshop pack "${pack_id}" removed from local index.`,
      };
    },
  );
}
