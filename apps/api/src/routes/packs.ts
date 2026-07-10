// SPDX-License-Identifier: Apache-2.0
import { cpSync, mkdirSync, mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs';
import { isAbsolute, join, resolve as resolvePath } from 'node:path';
import { tmpdir } from 'node:os';
import type { FastifyInstance } from 'fastify';
import type { PackValidationResult } from '@convsim/shared';
import AdmZip from 'adm-zip';
import Database from 'better-sqlite3';
import { loadPack, PackIndex, PackLoaderError } from '@convsim/pack-loader';
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

export interface ImportPackResponse {
  pack_id: string;
  name: string;
  version: string;
  dest: string;
}

let _packsDbPath: string | null = null;
let _packsDataDir: string | null = null;

export function setPacksDbPath(dbPath: string | null): void {
  _packsDbPath = dbPath;
}

export function setPacksDataDir(dataDir: string | null): void {
  _packsDataDir = dataDir;
}

const _MAX_ZIP_BYTES = 100 * 1024 * 1024; // 100 MB

/** Throw if any zip entry could escape the extraction root (zip-slip attack). */
function assertNoZipSlip(zip: AdmZip): void {
  for (const entry of zip.getEntries()) {
    const name = entry.entryName;
    if (isAbsolute(name)) {
      const err = Object.assign(new Error(`Zip entry has absolute path: "${name}"`), {
        statusCode: 422,
        code: 'UNSAFE_ZIP',
      });
      throw err;
    }
    const parts = name.split(/[\\/]/);
    if (parts.some((p) => p === '..')) {
      const err = Object.assign(
        new Error(`Zip entry attempts path traversal: "${name}"`),
        { statusCode: 422, code: 'UNSAFE_ZIP' },
      );
      throw err;
    }
  }
}

/** If the extraction root contains exactly one subdirectory, return it. */
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

export async function packsRoutes(app: FastifyInstance): Promise<void> {
  // Register binary content type parsers for the zip import endpoint.
  app.addContentTypeParser(
    ['application/zip', 'application/octet-stream'],
    { parseAs: 'buffer' },
    (_req, body, done) => { done(null, body); },
  );

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

  app.post(
    '/api/packs/import',
    { bodyLimit: _MAX_ZIP_BYTES },
    async (req, reply): Promise<ImportPackResponse> => {
      if (!_packsDbPath || !_packsDataDir) {
        reply.status(503);
        throw Object.assign(new Error('Pack storage is not configured.'), {
          statusCode: 503,
          code: 'NOT_CONFIGURED',
        });
      }

      const zipBytes = req.body as Buffer;

      if (!zipBytes || zipBytes.length === 0) {
        reply.status(422);
        throw Object.assign(new Error('Request body must be a zip archive.'), {
          statusCode: 422,
          code: 'INVALID_ZIP',
        });
      }

      if (zipBytes.length > _MAX_ZIP_BYTES) {
        reply.status(413);
        throw Object.assign(
          new Error(`Upload exceeds the ${_MAX_ZIP_BYTES / (1024 * 1024)} MB limit.`),
          { statusCode: 413, code: 'FILE_TOO_LARGE' },
        );
      }

      let zip: AdmZip;
      try {
        zip = new AdmZip(zipBytes);
      } catch {
        reply.status(422);
        throw Object.assign(new Error('Uploaded file is not a valid zip archive.'), {
          statusCode: 422,
          code: 'INVALID_ZIP',
        });
      }

      assertNoZipSlip(zip);

      const tempDir = mkdtempSync(join(tmpdir(), 'convsim-api-import-'));
      try {
        zip.extractAllTo(tempDir, /* overwrite */ true);
        const packDir = unwrapSingleSubdir(tempDir);

        let pack;
        try {
          pack = loadPack(packDir, 'community');
        } catch (e) {
          if (e instanceof PackLoaderError) {
            reply.status(422);
            throw Object.assign(new Error(e.message), {
              statusCode: 422,
              code: e.code,
            });
          }
          throw e;
        }

        const destDir = join(_packsDataDir, pack.manifest.pack_id);
        mkdirSync(_packsDataDir, { recursive: true });
        if (resolvePath(packDir) !== resolvePath(destDir)) {
          rmSync(destDir, { recursive: true, force: true });
          cpSync(packDir, destDir, { recursive: true });
        }

        const index = PackIndex.open(_packsDbPath);
        try {
          const installedPack = loadPack(destDir, 'community');
          index.importPack(installedPack);
        } finally {
          index.close();
        }

        reply.status(201);
        return {
          pack_id: pack.manifest.pack_id,
          name: pack.manifest.name,
          version: pack.manifest.version,
          dest: destDir,
        };
      } finally {
        rmSync(tempDir, { recursive: true, force: true });
      }
    },
  );
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

  app.get<{ Params: { pack_id: string } }>(
    '/api/packs/:pack_id/export',
    async (req, reply) => {
      if (!_packsDbPath) {
        reply.status(503);
        throw Object.assign(new Error('Pack storage is not configured.'), {
          statusCode: 503,
          code: 'NOT_CONFIGURED',
        });
      }

      const { pack_id } = req.params;

      // Use PackIndex so the canonical schema is applied. Opening a
      // not-yet-existing index creates an empty one (correct schema) rather
      // than a divergent minimal table that would break later imports.
      let packRoot: string;
      const index = PackIndex.open(_packsDbPath);
      try {
        const entry = index.getPack(pack_id);
        if (!entry) {
          reply.status(404);
          throw Object.assign(new Error(`Pack '${pack_id}' not found.`), {
            statusCode: 404,
            code: 'NOT_FOUND',
          });
        }
        packRoot = entry.pack_root;
      } finally {
        index.close();
      }

      const zip = new AdmZip();
      const safeId = pack_id.replace(/[^a-zA-Z0-9._-]/g, '_');
      // addLocalFolder stores entries relative to packRoot with safeId/ prefix
      zip.addLocalFolder(packRoot, safeId);
      const zipBuffer = zip.toBuffer();

      const filename = `${safeId}.zip`;

      reply
        .header('Content-Type', 'application/zip')
        .header('Content-Disposition', `attachment; filename="${filename}"`)
        .header('Content-Length', String(zipBuffer.length));

      return reply.send(zipBuffer);
    },
  );
}
