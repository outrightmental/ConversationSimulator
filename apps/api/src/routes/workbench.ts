// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import fs from 'node:fs';
import path from 'node:path';

let _officialRoot = '';
let _localDevRoot = '';

export function setWorkbenchRoots(officialRoot: string, localDevRoot: string): void {
  _officialRoot = officialRoot;
  _localDevRoot = localDevRoot;
}

export type PackKind = 'official' | 'local-dev';

export interface WorkbenchPackSummary {
  kind: PackKind;
  slug: string;
  pack_id: string | null;
  name: string | null;
  editable: boolean;
}

export interface FileNode {
  name: string;
  path: string;
  kind: 'yaml' | 'markdown' | 'text' | 'dir' | 'other';
  children?: FileNode[];
}

function rootForKind(kind: PackKind): string {
  return kind === 'official' ? _officialRoot : _localDevRoot;
}

function readManifestBasics(packDir: string): { pack_id: string | null; name: string | null } {
  let pack_id: string | null = null;
  let name: string | null = null;
  try {
    const content = fs.readFileSync(path.join(packDir, 'manifest.yaml'), 'utf-8');
    for (const line of content.split('\n')) {
      if (!pack_id) {
        const m = /^pack_id:\s*['"]?([^'"\n]+)['"]?\s*$/.exec(line);
        if (m) pack_id = m[1].trim();
      }
      if (!name) {
        const m = /^name:\s*['"]?([^'"\n]+)['"]?\s*$/.exec(line);
        if (m) name = m[1].trim();
      }
      if (pack_id && name) break;
    }
  } catch {
    // ignore — manifest may be missing or malformed
  }
  return { pack_id, name };
}

function scanRoot(kind: PackKind): WorkbenchPackSummary[] {
  const root = rootForKind(kind);
  if (!root) return [];
  let entries: string[];
  try {
    entries = fs.readdirSync(root);
  } catch {
    return [];
  }
  return entries
    .filter((e) => {
      try {
        return fs.statSync(path.join(root, e)).isDirectory();
      } catch {
        return false;
      }
    })
    .map((slug) => {
      const { pack_id, name } = readManifestBasics(path.join(root, slug));
      return { kind, slug, pack_id, name: name ?? slug, editable: kind === 'local-dev' };
    });
}

function buildTree(dir: string, packRoot: string): FileNode[] {
  let entries: string[];
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return [];
  }

  const nodes: FileNode[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry);
    let stat: fs.Stats;
    try {
      stat = fs.statSync(fullPath);
    } catch {
      continue;
    }

    const relPath = path.relative(packRoot, fullPath).replace(/\\/g, '/');

    if (stat.isDirectory()) {
      nodes.push({ name: entry, path: relPath, kind: 'dir', children: buildTree(fullPath, packRoot) });
    } else if (stat.isFile()) {
      const ext = path.extname(entry).toLowerCase();
      let kind: FileNode['kind'] = 'other';
      if (ext === '.yaml' || ext === '.yml') kind = 'yaml';
      else if (ext === '.md') kind = 'markdown';
      else if (ext === '.txt') kind = 'text';
      nodes.push({ name: entry, path: relPath, kind });
    }
  }

  return nodes.sort((a, b) => {
    if (a.kind === 'dir' && b.kind !== 'dir') return -1;
    if (a.kind !== 'dir' && b.kind === 'dir') return 1;
    return a.name.localeCompare(b.name);
  });
}

interface Reply {
  status(code: number): void;
}

function assertValidKind(kind: string, reply: Reply): asserts kind is PackKind {
  if (kind !== 'official' && kind !== 'local-dev') {
    reply.status(400);
    throw new Error(`Invalid kind "${kind}": must be "official" or "local-dev"`);
  }
}

function getPackRoot(kind: PackKind, slug: string, reply: Reply): string {
  const root = rootForKind(kind);
  if (!root) {
    reply.status(503);
    throw new Error(`Pack root for "${kind}" is not configured`);
  }
  const normalRoot = path.normalize(root);
  const packRoot = path.normalize(path.resolve(normalRoot, slug));
  if (!packRoot.startsWith(normalRoot + path.sep) || packRoot === normalRoot) {
    reply.status(400);
    throw new Error('Invalid pack slug');
  }
  return packRoot;
}

function resolveFilePath(packRoot: string, relPath: string, reply: Reply): string {
  const abs = path.normalize(path.resolve(packRoot, relPath));
  if (!abs.startsWith(packRoot + path.sep) && abs !== packRoot) {
    reply.status(400);
    throw new Error('Path traversal not allowed');
  }
  return abs;
}

function copyDirRecursive(src: string, dst: string): void {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src)) {
    const srcPath = path.join(src, entry);
    const dstPath = path.join(dst, entry);
    if (fs.statSync(srcPath).isDirectory()) {
      copyDirRecursive(srcPath, dstPath);
    } else {
      fs.copyFileSync(srcPath, dstPath);
    }
  }
}

const EDITABLE_EXTENSIONS = new Set(['.yaml', '.yml', '.md', '.txt']);

export async function workbenchRoutes(app: FastifyInstance): Promise<void> {
  // GET /api/workbench/packs — list all packs from official and local-dev roots
  app.get('/api/workbench/packs', async (): Promise<WorkbenchPackSummary[]> => {
    return [...scanRoot('official'), ...scanRoot('local-dev')];
  });

  // GET /api/workbench/packs/:kind/:slug/files — file tree for a pack
  app.get<{ Params: { kind: string; slug: string } }>(
    '/api/workbench/packs/:kind/:slug/files',
    async (req, reply): Promise<{ tree: FileNode[] }> => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      const packRoot = getPackRoot(kind, slug, reply);
      if (!fs.existsSync(packRoot)) {
        reply.status(404);
        throw new Error(`Pack "${slug}" not found`);
      }
      return { tree: buildTree(packRoot, packRoot) };
    },
  );

  // GET /api/workbench/packs/:kind/:slug/file?path=... — read a file
  app.get<{
    Params: { kind: string; slug: string };
    Querystring: { path?: string };
  }>(
    '/api/workbench/packs/:kind/:slug/file',
    async (req, reply): Promise<{ content: string; editable: boolean }> => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      const relPath = req.query.path;
      if (!relPath) {
        reply.status(400);
        throw new Error('Missing required query parameter: path');
      }
      const packRoot = getPackRoot(kind, slug, reply);
      const absPath = resolveFilePath(packRoot, relPath, reply);
      if (!fs.existsSync(absPath)) {
        reply.status(404);
        throw new Error(`File not found: ${relPath}`);
      }
      const content = fs.readFileSync(absPath, 'utf-8');
      return { content, editable: kind === 'local-dev' };
    },
  );

  // PUT /api/workbench/packs/:kind/:slug/file?path=... — write a file (local-dev only)
  app.put<{
    Params: { kind: string; slug: string };
    Querystring: { path?: string };
    Body: { content: unknown };
  }>(
    '/api/workbench/packs/:kind/:slug/file',
    async (req, reply): Promise<{ ok: boolean }> => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      if (kind !== 'local-dev') {
        reply.status(403);
        throw new Error('Official packs are read-only. Copy to local-dev first.');
      }
      const relPath = req.query.path;
      if (!relPath) {
        reply.status(400);
        throw new Error('Missing required query parameter: path');
      }
      const { content } = req.body;
      if (typeof content !== 'string') {
        reply.status(400);
        throw new Error('Body must include a "content" string field');
      }
      const packRoot = getPackRoot(kind, slug, reply);
      const absPath = resolveFilePath(packRoot, relPath, reply);
      const ext = path.extname(absPath).toLowerCase();
      if (!EDITABLE_EXTENSIONS.has(ext)) {
        reply.status(400);
        throw new Error(`File type "${ext}" is not editable via the workbench`);
      }
      fs.mkdirSync(path.dirname(absPath), { recursive: true });
      fs.writeFileSync(absPath, content, 'utf-8');
      return { ok: true };
    },
  );

  // POST /api/workbench/packs/:kind/:slug/copy-to-local — copy pack to local-dev
  app.post<{ Params: { kind: string; slug: string } }>(
    '/api/workbench/packs/:kind/:slug/copy-to-local',
    async (req, reply): Promise<WorkbenchPackSummary> => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      if (kind === 'local-dev') {
        reply.status(400);
        throw new Error('Pack is already in local-dev');
      }
      const srcRoot = getPackRoot(kind, slug, reply);
      if (!fs.existsSync(srcRoot)) {
        reply.status(404);
        throw new Error(`Pack "${slug}" not found`);
      }
      if (!_localDevRoot) {
        reply.status(503);
        throw new Error('Local-dev root is not configured');
      }
      fs.mkdirSync(_localDevRoot, { recursive: true });
      let destSlug = slug;
      let destPath = path.join(_localDevRoot, destSlug);
      if (fs.existsSync(destPath)) {
        destSlug = `${slug}-copy`;
        destPath = path.join(_localDevRoot, destSlug);
      }
      if (fs.existsSync(destPath)) {
        // Avoid collisions with a numeric suffix
        let n = 2;
        while (fs.existsSync(path.join(_localDevRoot, `${slug}-copy-${n}`))) n++;
        destSlug = `${slug}-copy-${n}`;
        destPath = path.join(_localDevRoot, destSlug);
      }
      copyDirRecursive(srcRoot, destPath);
      const { pack_id, name } = readManifestBasics(destPath);
      return { kind: 'local-dev', slug: destSlug, pack_id, name: name ?? destSlug, editable: true };
    },
  );
}
