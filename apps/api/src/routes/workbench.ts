// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import fs from 'node:fs';
import { randomBytes } from 'node:crypto';
import path from 'node:path';
import { loadPack, PackLoaderError, type PackRootKind } from '@convsim/pack-loader';

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
  if (!abs.startsWith(packRoot + path.sep)) {
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

// ---------------------------------------------------------------------------
// Validation types and helpers
// ---------------------------------------------------------------------------

export interface WorkbenchValidationIssue {
  severity: 'error' | 'warning';
  rule_id: string;
  file: string;
  pointer: string;
  message: string;
  suggested_fix: string;
  category?: 'security' | 'schema' | 'structure' | 'syntax';
}

export interface WorkbenchValidationResponse {
  valid: boolean;
  errors: WorkbenchValidationIssue[];
  warnings: WorkbenchValidationIssue[];
}

const FORBIDDEN_EXTENSIONS = new Set([
  '.exe', '.bat', '.cmd', '.sh', '.ps1', '.py', '.js', '.mjs', '.cjs',
  '.ts', '.rb', '.pl', '.php', '.jar', '.class', '.so', '.dll', '.dylib',
  '.vbs', '.ws', '.wsf', '.com', '.scr', '.pif', '.msi', '.deb', '.rpm',
  '.pkg', '.app', '.command', '.wasm',
]);

function getSuggestedFix(code: string, pointer?: string): string {
  switch (code) {
    case 'INVALID_YAML':
      return 'Fix the YAML syntax: check for indentation errors, missing colons, or unclosed brackets. Run `yamllint` for detailed diagnostics.';
    case 'SCHEMA_VALIDATION':
      if (pointer && (pointer === '(root)' || pointer === '')) {
        return 'The file is missing required fields. See the authoring guide for the full schema.';
      }
      return `Check the value at '${pointer ?? ''}' matches the expected type or format. See the authoring guide.`;
    case 'FORBIDDEN_FILE':
      return 'Remove this file from the pack. Only YAML, Markdown, image, and audio files are allowed. MVP packs are strictly data — no executable content.';
    case 'FORBIDDEN_BINARY':
      return 'Remove this binary file. Executable content is not permitted even with non-executable extensions. MVP packs are strictly data.';
    case 'MISSING_FILE':
      return 'Add the missing file, or update the reference to point to an existing file within the pack directory.';
    case 'DUPLICATE_ID':
      return 'Ensure all IDs (scenario_id, npc_id) are unique within the pack.';
    case 'UNSUPPORTED_VERSION':
      return 'Add `schema_version: "0.1"` at the top of the file. This is the only supported schema version.';
    case 'PATH_TRAVERSAL':
      return 'Use relative paths that stay within the pack directory. References cannot point outside the pack root.';
    default:
      return 'See the authoring guide for details on how to fix this issue.';
  }
}

const ERROR_CATEGORY: Record<string, 'security' | 'schema' | 'structure' | 'syntax'> = {
  INVALID_YAML: 'syntax',
  SCHEMA_VALIDATION: 'schema',
  FORBIDDEN_FILE: 'security',
  FORBIDDEN_BINARY: 'security',
  MISSING_FILE: 'structure',
  DUPLICATE_ID: 'structure',
  PATH_TRAVERSAL: 'structure',
  UNSUPPORTED_VERSION: 'schema',
};

function convertPackLoaderError(e: PackLoaderError, packRoot: string): WorkbenchValidationIssue[] {
  const relFile = e.filePath
    ? path.relative(packRoot, e.filePath).replace(/\\/g, '/')
    : '';

  // SCHEMA_VALIDATION messages embed all AJV sub-errors joined by '; '.
  // Explode them into individual issues so creators see the full picture.
  if (e.code === 'SCHEMA_VALIDATION' && e.filePath) {
    const prefix = `Schema validation failed for ${e.filePath}: `;
    const errsString = e.message.startsWith(prefix)
      ? e.message.slice(prefix.length)
      : e.message;

    const parts = errsString.split('; ').filter((p) => p.trim() !== '');
    if (parts.length > 0) {
      return parts.map((part) => {
        const colonIdx = part.indexOf(': ');
        const pointer = colonIdx >= 0 ? part.slice(0, colonIdx) : '';
        const message = colonIdx >= 0 ? part.slice(colonIdx + 2) : part;
        return {
          severity: 'error' as const,
          rule_id: 'SCHEMA_VIOLATION',
          file: relFile,
          pointer,
          message,
          suggested_fix: getSuggestedFix('SCHEMA_VALIDATION', pointer),
          category: 'schema' as const,
        };
      });
    }
  }

  return [{
    severity: 'error' as const,
    rule_id: e.code,
    file: relFile,
    pointer: '',
    message: e.filePath
      ? e.message.replace(e.filePath, relFile)
      : e.message,
    suggested_fix: getSuggestedFix(e.code),
    category: ERROR_CATEGORY[e.code] ?? 'schema',
  }];
}

// Scan the entire pack directory for forbidden file extensions, collecting all
// violations instead of failing on the first one.
function scanForbiddenFiles(packRoot: string): WorkbenchValidationIssue[] {
  const issues: WorkbenchValidationIssue[] = [];

  function scan(dir: string): void {
    let entries: string[];
    try { entries = fs.readdirSync(dir); } catch { return; }
    for (const entry of entries) {
      const fullPath = path.join(dir, entry);
      let stat: fs.Stats;
      try { stat = fs.statSync(fullPath); } catch { continue; }
      if (stat.isDirectory()) { scan(fullPath); continue; }
      if (!stat.isFile()) continue;
      const relPath = path.relative(packRoot, fullPath).replace(/\\/g, '/');
      const ext = path.extname(entry).toLowerCase();
      if (FORBIDDEN_EXTENSIONS.has(ext)) {
        issues.push({
          severity: 'error',
          rule_id: 'FORBIDDEN_FILE',
          file: relPath,
          pointer: '',
          message: `Executable or script file not allowed in pack: '${relPath}'. MVP packs are data, not code.`,
          suggested_fix: getSuggestedFix('FORBIDDEN_FILE'),
          category: 'security',
        });
      }
    }
  }

  scan(packRoot);
  return issues;
}

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
      let stat: fs.Stats;
      try {
        stat = fs.statSync(absPath);
      } catch {
        reply.status(404);
        throw new Error(`File not found: ${relPath}`);
      }
      if (!stat.isFile()) {
        reply.status(400);
        throw new Error(`Path is not a file: ${relPath}`);
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
      const tmpPath = `${absPath}.tmp.${randomBytes(4).toString('hex')}`;
      try {
        fs.writeFileSync(tmpPath, content, 'utf-8');
        fs.renameSync(tmpPath, absPath);
      } catch (err) {
        try { fs.unlinkSync(tmpPath); } catch { /* ignore cleanup failure */ }
        throw err;
      }
      return { ok: true };
    },
  );

  // GET /api/workbench/packs/:kind/:slug/validate — validate all files in a pack
  app.get<{ Params: { kind: string; slug: string } }>(
    '/api/workbench/packs/:kind/:slug/validate',
    async (req, reply): Promise<WorkbenchValidationResponse> => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      const packRoot = getPackRoot(kind, slug, reply);

      if (!fs.existsSync(packRoot)) {
        reply.status(404);
        throw new Error(`Pack "${slug}" not found`);
      }

      // Phase 1: scan all files for forbidden extensions — collects every violation
      // rather than stopping at the first, so creators can fix them all at once.
      const securityErrors = scanForbiddenFiles(packRoot);

      // Phase 2: structural + schema validation via loadPack.
      // Skip when security errors are present to avoid duplicate reports
      // (loadPack would surface the same forbidden-file violation first).
      const structuralErrors: WorkbenchValidationIssue[] = [];
      if (securityErrors.length === 0) {
        try {
          loadPack(packRoot, kind as PackRootKind);
        } catch (e) {
          if (e instanceof PackLoaderError) {
            structuralErrors.push(...convertPackLoaderError(e, packRoot));
          } else {
            throw e;
          }
        }
      }

      const errors = [...securityErrors, ...structuralErrors];
      return { valid: errors.length === 0, errors, warnings: [] };
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
