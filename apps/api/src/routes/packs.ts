// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import type { PackValidationResult } from '@convsim/shared';
import Database from 'better-sqlite3';
import { SCENARIOS } from '../data/scenarios.js';

export interface PackSummary {
  pack_id: string;
  name: string;
  scenario_count: number;
}

export interface PacksResponse {
  packs: PackSummary[];
  total: number;
}

let _packsDbPath: string | null = null;

export function setPacksDbPath(dbPath: string): void {
  _packsDbPath = dbPath;
}

export async function packsRoutes(app: FastifyInstance): Promise<void> {
  app.get('/api/packs', async (): Promise<PacksResponse> => {
    if (!_packsDbPath) {
      return { packs: [], total: 0 };
    }
    try {
      const db = new Database(_packsDbPath, { readonly: true, fileMustExist: true });
      try {
        const rows = db
          .prepare('SELECT pack_id, name, scenario_count FROM installed_packs ORDER BY name')
          .all() as PackSummary[];
        return { packs: rows, total: rows.length };
      } finally {
        db.close();
      }
    } catch {
      return { packs: [], total: 0 };
    }
  });
}

export async function packRoutes(app: FastifyInstance) {
  app.post<{ Params: { pack_id: string } }>(
    '/api/packs/:pack_id/validate',
    async (req, reply): Promise<PackValidationResult> => {
      const { pack_id } = req.params;
      const known = Object.values(SCENARIOS).some((s) => s.pack_id === pack_id);
      if (!known) {
        reply.status(404);
        throw new Error(`Pack '${pack_id}' not found`);
      }
      return { pack_id, valid: true, errors: [] };
    },
  );
}
