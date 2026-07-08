// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import fs from 'node:fs';
import os from 'node:os';
import { randomBytes } from 'node:crypto';
import path from 'node:path';
import AdmZip from 'adm-zip';
import { getDb, WORKBENCH_TEST_SCENARIO_ID } from '../db.js';
import { loadPack, PackLoaderError } from '@convsim/pack-loader';

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

function readManifestBasics(packDir: string): { pack_id: string | null; name: string | null; version: string | null } {
  let pack_id: string | null = null;
  let name: string | null = null;
  let version: string | null = null;
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
      if (!version) {
        const m = /^version:\s*['"]?([^'"\n]+)['"]?\s*$/.exec(line);
        if (m) version = m[1].trim();
      }
      if (pack_id && name && version) break;
    }
  } catch {
    // ignore — manifest may be missing or malformed
  }
  return { pack_id, name, version };
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
      // lstat (not stat) so symlinks are never followed. Following them would
      // let a symlink escape the pack root — scanning arbitrary directories —
      // and a symlink cycle would recurse forever, hanging the request. This
      // matches the pack-loader's own scanner, which rejects symlinks outright.
      try { stat = fs.lstatSync(fullPath); } catch { continue; }
      const relPath = path.relative(packRoot, fullPath).replace(/\\/g, '/');
      if (stat.isSymbolicLink()) {
        issues.push({
          severity: 'error',
          rule_id: 'FORBIDDEN_FILE',
          file: relPath,
          pointer: '',
          message: `Symlinks are not permitted in a pack: '${relPath}'. Remove the symlink and include the file content directly.`,
          suggested_fix: getSuggestedFix('FORBIDDEN_FILE'),
          category: 'security',
        });
        continue;
      }
      if (stat.isDirectory()) { scan(fullPath); continue; }
      if (!stat.isFile()) continue;
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

export interface WorkbenchImportResponse extends WorkbenchPackSummary {
  /** Present when the pack was installed under a different slug than its pack_id to avoid a collision. */
  renamed_from?: string;
}

export async function workbenchRoutes(app: FastifyInstance): Promise<void> {
  // Register binary content-type parser for zip uploads (scoped to this plugin's routes).
  app.addContentTypeParser(
    'application/zip',
    { parseAs: 'buffer' },
    (_req, body, done) => { done(null, body as Buffer); },
  );

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

  // GET /api/workbench/packs/:kind/:slug/validate — validate a pack's files and schema
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

      const issues: WorkbenchValidationIssue[] = [];

      // Phase 1: security scan — collect ALL forbidden files/symlinks up front,
      // rather than stopping at the first one like the pack loader does. This
      // is extension/symlink based; it does NOT sniff file content.
      const phase1Issues = scanForbiddenFiles(packRoot);
      issues.push(...phase1Issues);
      // Track the exact files phase 1 already flagged so we can drop the loader's
      // duplicate report of the same file — but keep loader-only security findings
      // (e.g. FORBIDDEN_BINARY, a disguised executable with an allowed extension)
      // that phase 1 cannot detect.
      const reportedSecurityFiles = new Set(phase1Issues.map((i) => i.file));

      // Phase 2: structural/schema validation via the pack loader. It throws on
      // the first PackLoaderError it encounters; convert that into one or more
      // findings (SCHEMA_VALIDATION is exploded into per-field issues).
      try {
        loadPack(packRoot, kind);
      } catch (e) {
        if (e instanceof PackLoaderError) {
          for (const issue of convertPackLoaderError(e, packRoot)) {
            // Skip only the specific file phase 1 already reported, not every
            // security finding — otherwise a disguised binary in one file is
            // suppressed just because an unrelated script file also exists.
            if (issue.category === 'security' && reportedSecurityFiles.has(issue.file)) continue;
            issues.push(issue);
          }
        } else {
          throw e;
        }
      }

      const errors = issues.filter((i) => i.severity === 'error');
      const warnings = issues.filter((i) => i.severity === 'warning');
      return { valid: errors.length === 0, errors, warnings };
    },
  );

  // POST /api/workbench/packs/:kind/:slug/test-session — create+start a temporary test session
  app.post<{ Params: { kind: string; slug: string } }>(
    '/api/workbench/packs/:kind/:slug/test-session',
    async (req, reply): Promise<{
      session_id: string;
      state: string;
      npc_opening: string;
      state_vars: Record<string, number>;
    }> => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      const packRoot = getPackRoot(kind, slug, reply);
      if (!fs.existsSync(packRoot)) {
        reply.status(404);
        throw new Error(`Pack "${slug}" not found`);
      }

      const db = getDb();
      const now = new Date().toISOString();
      const bytes = Array.from({ length: 8 }, () =>
        Math.floor(Math.random() * 256).toString(16).padStart(2, '0'),
      );
      const session_id = `test-${bytes.join('')}`;

      const baselineStateVars: Record<string, number> = {
        trust: 50,
        patience: 75,
        pressure: 25,
        rapport: 50,
        openness: 50,
        objective_progress: 0,
      };

      const setupJson = JSON.stringify({
        scenario_id: WORKBENCH_TEST_SCENARIO_ID,
        difficulty: 'normal',
        player_role_name: 'Creator',
        language: 'en',
        input_mode: 'text-only',
        tts_enabled: false,
        show_state_meters: true,
        save_transcript: false,
        seed: null,
        workbench_pack_kind: kind,
        workbench_pack_slug: slug,
      });

      db.prepare(
        'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json, state_vars_json) VALUES (?, ?, ?, ?, ?, ?)',
      ).run(
        session_id,
        WORKBENCH_TEST_SCENARIO_ID,
        'PlayerTurnListening',
        now,
        setupJson,
        JSON.stringify(baselineStateVars),
      );

      reply.status(201);
      return {
        session_id,
        state: 'PlayerTurnListening',
        npc_opening: 'Ready to test. Send a message to begin the conversation.',
        state_vars: baselineStateVars,
      };
    },
  );

  // GET /api/workbench/packs/:kind/:slug/export — export a pack as a .zip archive
  // Runs validation preflight; returns 422 with full issue list if the pack is invalid.
  // No absolute local paths are included — all zip entries are relative to the pack root.
  app.get<{ Params: { kind: string; slug: string } }>(
    '/api/workbench/packs/:kind/:slug/export',
    async (req, reply) => {
      const { kind, slug } = req.params;
      assertValidKind(kind, reply);
      const packRoot = getPackRoot(kind, slug, reply);
      if (!fs.existsSync(packRoot)) {
        reply.status(404);
        throw new Error(`Pack "${slug}" not found`);
      }

      // Validation preflight — identical two-phase approach as the validate endpoint.
      const issues: WorkbenchValidationIssue[] = scanForbiddenFiles(packRoot);
      const reportedSecurityFiles = new Set(issues.map((i) => i.file));
      try {
        loadPack(packRoot, kind);
      } catch (e) {
        if (e instanceof PackLoaderError) {
          for (const issue of convertPackLoaderError(e, packRoot)) {
            if (issue.category === 'security' && reportedSecurityFiles.has(issue.file)) continue;
            issues.push(issue);
          }
        } else {
          throw e;
        }
      }

      const errors = issues.filter((i) => i.severity === 'error');
      if (errors.length > 0) {
        reply.status(422);
        return reply.send({
          valid: false,
          errors,
          warnings: issues.filter((i) => i.severity === 'warning'),
        });
      }

      // Build the zip with paths relative to the pack root — no absolute paths leak out.
      const { pack_id, version } = readManifestBasics(packRoot);
      const safeName = (pack_id ?? slug).replace(/[^a-zA-Z0-9._-]/g, '_');
      const filename = version ? `${safeName}-${version}.zip` : `${safeName}.zip`;

      const zip = new AdmZip();
      zip.addLocalFolder(packRoot, '');
      const zipBuffer = zip.toBuffer();

      return reply
        .header('Content-Type', 'application/zip')
        .header('Content-Disposition', `attachment; filename="${filename}"`)
        .header('Content-Length', String(zipBuffer.length))
        .send(zipBuffer);
    },
  );

  // POST /api/workbench/packs/import — import a .zip file into local-dev
  // Accepts a raw zip binary body (Content-Type: application/zip).
  // Validates the pack; rejects with 422 + full issue list on failure.
  // Handles slug conflicts by renaming (default) or overwriting (?conflict=overwrite).
  app.post<{
    Querystring: { conflict?: string };
    Body: Buffer;
  }>(
    '/api/workbench/packs/import',
    async (req, reply): Promise<WorkbenchImportResponse> => {
      const body = req.body;
      if (!Buffer.isBuffer(body) || body.length === 0) {
        reply.status(400);
        throw new Error('Request body must be a non-empty .zip file (Content-Type: application/zip)');
      }

      if (!_localDevRoot) {
        reply.status(503);
        throw new Error('Local-dev root is not configured');
      }

      const tmpDir = path.join(os.tmpdir(), `convsim-import-${randomBytes(4).toString('hex')}`);
      try {
        fs.mkdirSync(tmpDir, { recursive: true });

        // Parse zip and check for zip-slip attacks before extracting anything.
        let zip: AdmZip;
        try {
          zip = new AdmZip(body);
        } catch {
          reply.status(422);
          throw new Error('Uploaded file is not a valid .zip archive');
        }

        const extractDir = path.join(tmpDir, 'extracted');
        fs.mkdirSync(extractDir);
        const normalExtract = path.normalize(extractDir);

        for (const entry of zip.getEntries()) {
          const entryPath = path.normalize(path.join(normalExtract, entry.entryName));
          if (!entryPath.startsWith(normalExtract + path.sep) && entryPath !== normalExtract) {
            reply.status(422);
            throw new Error(`Unsafe path in zip: "${entry.entryName}"`);
          }
        }

        zip.extractAllTo(extractDir, /* overwrite */ true);

        // Single-subdir unwrap: if the zip contains exactly one top-level directory,
        // treat that directory as the pack root (common convention for exported packs).
        let packDir = extractDir;
        const topEntries = fs.readdirSync(extractDir);
        if (topEntries.length === 1) {
          const candidate = path.join(extractDir, topEntries[0]);
          if (fs.statSync(candidate).isDirectory()) {
            packDir = candidate;
          }
        }

        // Two-phase validation (mirrors the validate endpoint).
        const issues: WorkbenchValidationIssue[] = scanForbiddenFiles(packDir);
        const reportedSecurityFiles = new Set(issues.filter((i) => i.category === 'security').map((i) => i.file));
        try {
          loadPack(packDir, 'local-dev');
        } catch (e) {
          if (e instanceof PackLoaderError) {
            for (const issue of convertPackLoaderError(e, packDir)) {
              if (issue.category === 'security' && reportedSecurityFiles.has(issue.file)) continue;
              issues.push(issue);
            }
          } else {
            throw e;
          }
        }

        const errors = issues.filter((i) => i.severity === 'error');
        if (errors.length > 0) {
          reply.status(422);
          return reply.send({
            valid: false,
            errors,
            warnings: issues.filter((i) => i.severity === 'warning'),
          });
        }

        // Determine destination slug from pack_id, falling back to the extracted dir name.
        const { pack_id, name } = readManifestBasics(packDir);
        const baseSlug = (pack_id ?? path.basename(packDir))
          .replace(/[^a-zA-Z0-9._-]/g, '-')
          .replace(/^[.-]+/, '')
          || 'imported-pack';

        fs.mkdirSync(_localDevRoot, { recursive: true });

        const conflictMode = req.query.conflict === 'overwrite' ? 'overwrite' : 'rename';
        let destSlug = baseSlug;
        let destPath = path.join(_localDevRoot, destSlug);
        let renamedFrom: string | undefined;

        if (fs.existsSync(destPath)) {
          if (conflictMode === 'overwrite') {
            fs.rmSync(destPath, { recursive: true, force: true });
          } else {
            // Find a free slug with a numeric suffix.
            let n = 2;
            while (fs.existsSync(path.join(_localDevRoot, `${baseSlug}-${n}`))) n++;
            renamedFrom = baseSlug;
            destSlug = `${baseSlug}-${n}`;
            destPath = path.join(_localDevRoot, destSlug);
          }
        }

        copyDirRecursive(packDir, destPath);

        const { pack_id: finalPackId, name: finalName } = readManifestBasics(destPath);
        const result: WorkbenchImportResponse = {
          kind: 'local-dev',
          slug: destSlug,
          pack_id: finalPackId,
          name: finalName ?? destSlug,
          editable: true,
          ...(renamedFrom !== undefined ? { renamed_from: renamedFrom } : {}),
        };

        reply.status(201);
        return result;
      } finally {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore cleanup */ }
      }
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
