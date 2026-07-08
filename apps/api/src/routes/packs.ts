// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import Database from 'better-sqlite3';

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
