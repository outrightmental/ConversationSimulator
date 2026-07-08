// SPDX-License-Identifier: Apache-2.0
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import type { FastifyInstance } from 'fastify';
import type {
  ModelsResponse,
  ModelRegistryEntry,
  InstalledModelInfo,
  InstallModelRequest,
  InstallModelResponse,
  UseModelRequest,
  UseModelResponse,
  RegisterGgufRequest,
  RegisterGgufResponse,
  DetectedOllamaModel,
} from '@convsim/shared';
import { getDb } from '../db.js';

// ── Registry data (embedded from model-registry/registry.yaml) ──────────────

const REGISTRY_ENTRIES: ModelRegistryEntry[] = [
  {
    id: 'qwen3-4b-instruct-q4_k_m',
    name: 'Qwen3 4B Instruct Q4_K_M',
    provider: 'huggingface',
    family: 'qwen3',
    role: 'starter',
    format: 'gguf',
    license_spdx: 'Apache-2.0',
    license_url: 'https://www.apache.org/licenses/LICENSE-2.0',
    source_type: 'registry',
    download_url: 'PENDING',
    sha256: 'PENDING',
    size_gb: 2.6,
    min_vram_gb: 4,
    recommended_vram_gb: 6,
    context_length: 8192,
    registered_at: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'qwen3-8b-instruct-q4_k_m',
    name: 'Qwen3 8B Instruct Q4_K_M',
    provider: 'huggingface',
    family: 'qwen3',
    role: 'standard',
    format: 'gguf',
    license_spdx: 'Apache-2.0',
    license_url: 'https://www.apache.org/licenses/LICENSE-2.0',
    source_type: 'registry',
    download_url: 'PENDING',
    sha256: 'PENDING',
    size_gb: 5.0,
    min_vram_gb: 6,
    recommended_vram_gb: 8,
    context_length: 8192,
    registered_at: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'qwen3-14b-instruct-q4_k_m',
    name: 'Qwen3 14B Instruct Q4_K_M',
    provider: 'huggingface',
    family: 'qwen3',
    role: 'high-quality',
    format: 'gguf',
    license_spdx: 'Apache-2.0',
    license_url: 'https://www.apache.org/licenses/LICENSE-2.0',
    source_type: 'registry',
    download_url: 'PENDING',
    sha256: 'PENDING',
    size_gb: 9.0,
    min_vram_gb: 10,
    recommended_vram_gb: 12,
    context_length: 8192,
    registered_at: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'mistral-small-3.1-24b-instruct-q4_k_m',
    name: 'Mistral Small 3.1 24B Instruct Q4_K_M',
    provider: 'huggingface',
    family: 'mistral',
    role: 'high-quality',
    format: 'gguf',
    license_spdx: 'Apache-2.0',
    license_url: 'https://www.apache.org/licenses/LICENSE-2.0',
    source_type: 'registry',
    download_url: 'PENDING',
    sha256: 'PENDING',
    size_gb: 14.8,
    min_vram_gb: 16,
    recommended_vram_gb: 24,
    context_length: 32768,
    registered_at: '2026-01-01T00:00:00.000Z',
  },
];

// ── Active downloads: install_id → AbortController ───────────────────────────

const activeDownloads = new Map<number, AbortController>();

// ── DB row types ──────────────────────────────────────────────────────────────

interface InstalledModelRow {
  id: number;
  registry_id: string | null;
  filename: string;
  file_path: string;
  size_bytes: number | null;
  install_status: string;
  progress_bytes: number | null;
  error_message: string | null;
  verified_sha256: string | null;
  installed_at: string;
}

interface ModelConfigRow {
  key: string;
  value: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getModelsDir(): string {
  return path.join(os.homedir(), '.convsim', 'models', 'llm');
}

function rowToInstalledModel(row: InstalledModelRow): InstalledModelInfo {
  return {
    id: row.id,
    registry_id: row.registry_id,
    filename: row.filename,
    file_path: row.file_path,
    size_bytes: row.size_bytes,
    install_status: row.install_status as InstalledModelInfo['install_status'],
    progress_bytes: row.progress_bytes,
    error_message: row.error_message,
    verified_sha256: row.verified_sha256,
    installed_at: row.installed_at,
  };
}

function getActiveConfig(): { runtime_id: string | null; model_id: string | null } {
  const db = getDb();
  const rows = db.prepare<[], ModelConfigRow>('SELECT key, value FROM model_config').all();
  const map: Record<string, string> = {};
  for (const r of rows) map[r.key] = r.value;
  return {
    runtime_id: map['runtime_id'] || null,
    model_id: map['model_id'] || null,
  };
}

function setActiveConfig(runtime_id: string | null, model_id: string | null): void {
  const db = getDb();
  db.transaction(() => {
    db.prepare(
      "INSERT OR REPLACE INTO model_config (key, value) VALUES ('runtime_id', ?)",
    ).run(runtime_id ?? '');
    db.prepare(
      "INSERT OR REPLACE INTO model_config (key, value) VALUES ('model_id', ?)",
    ).run(model_id ?? '');
  })();
}

async function detectOllamaModels(): Promise<DetectedOllamaModel[]> {
  try {
    const res = await fetch('http://127.0.0.1:11434/api/tags', {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { models?: { name: string; size?: number }[] };
    return (data.models ?? []).map((m) => {
      const sizeGb = m.size != null ? m.size / 1_073_741_824 : null;
      let size_category: DetectedOllamaModel['size_category'] = null;
      if (sizeGb != null) {
        if (sizeGb < 4) size_category = 'small';
        else if (sizeGb < 10) size_category = 'medium';
        else size_category = 'large';
      }
      return { id: m.name, name: m.name, size_category };
    });
  } catch {
    return [];
  }
}

// ── Download worker (exported for unit tests) ─────────────────────────────────

/**
 * Stream-downloads a GGUF model file, verifies its SHA-256 checksum, and
 * updates the install record throughout.
 *
 * Flow:
 *   1. Write to <filename>.part
 *   2. Verify SHA-256 against expectedSha256
 *   3. On match: rename .part → final file, mark 'ready'
 *   4. On mismatch: delete .part, mark 'checksum_mismatch'
 *   5. On error/abort: delete .part if present, mark 'failed'/'cancelled'
 */
export async function runDownload(
  installId: number,
  downloadUrl: string,
  expectedSha256: string | null,
  destDir: string,
  filename: string,
  ac: AbortController = new AbortController(),
): Promise<void> {
  const db = getDb();
  const finalPath = path.join(destDir, filename);
  const partPath = path.join(destDir, `${filename}.part`);

  db.prepare(
    "UPDATE installed_models SET install_status='downloading', file_path=? WHERE id=?",
  ).run(finalPath, installId);

  try {
    const response = await fetch(downloadUrl, { signal: ac.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    if (!response.body) {
      throw new Error('Response has no body.');
    }

    const contentLength = response.headers.get('content-length');
    const totalBytes = contentLength != null ? parseInt(contentLength, 10) : null;
    if (totalBytes != null && !isNaN(totalBytes)) {
      db.prepare('UPDATE installed_models SET size_bytes=? WHERE id=?').run(totalBytes, installId);
    }

    fs.mkdirSync(destDir, { recursive: true });

    const hash = crypto.createHash('sha256');
    let progressBytes = 0;
    let lastProgressAt = Date.now();

    const tracker = new Transform({
      transform(chunk: Buffer, _enc, cb) {
        hash.update(chunk);
        progressBytes += chunk.length;
        const now = Date.now();
        if (now - lastProgressAt >= 500) {
          try {
            db.prepare('UPDATE installed_models SET progress_bytes=? WHERE id=?').run(
              progressBytes,
              installId,
            );
          } catch {
            // Non-fatal: progress update failure should not abort the download.
          }
          lastProgressAt = now;
        }
        cb(null, chunk);
      },
    });

    const body = Readable.fromWeb(
      response.body as Parameters<typeof Readable.fromWeb>[0],
    );
    const out = fs.createWriteStream(partPath);
    await pipeline(body, tracker, out);

    db.prepare('UPDATE installed_models SET progress_bytes=? WHERE id=?').run(
      progressBytes,
      installId,
    );

    const actualSha256 = hash.digest('hex');

    if (expectedSha256 && expectedSha256.toUpperCase() !== 'PENDING') {
      if (actualSha256.toLowerCase() !== expectedSha256.toLowerCase()) {
        try { fs.unlinkSync(partPath); } catch { /* ignore */ }
        db.prepare(
          "UPDATE installed_models SET install_status='checksum_mismatch', error_message=? WHERE id=?",
        ).run('SHA-256 checksum mismatch. The downloaded file has been deleted.', installId);
        return;
      }
    }

    fs.renameSync(partPath, finalPath);
    db.prepare(
      "UPDATE installed_models SET install_status='ready', verified_sha256=?, progress_bytes=? WHERE id=?",
    ).run(actualSha256, progressBytes, installId);

    setActiveConfig('llama_cpp', finalPath);
  } catch (err: unknown) {
    try { if (fs.existsSync(partPath)) fs.unlinkSync(partPath); } catch { /* ignore */ }
    if (ac.signal.aborted) {
      db.prepare(
        "UPDATE installed_models SET install_status='cancelled', error_message='Download cancelled.' WHERE id=?",
      ).run(installId);
    } else {
      const msg = err instanceof Error ? err.message : 'Download failed.';
      db.prepare(
        "UPDATE installed_models SET install_status='failed', error_message=? WHERE id=?",
      ).run(msg, installId);
    }
  }
}

// ── Routes ────────────────────────────────────────────────────────────────────

export async function modelsRoutes(app: FastifyInstance): Promise<void> {
  // GET /api/models
  app.get('/api/models', async (): Promise<ModelsResponse> => {
    const db = getDb();
    const rows = db
      .prepare<[], InstalledModelRow>('SELECT * FROM installed_models ORDER BY id DESC')
      .all();
    const installed = rows.map(rowToInstalledModel);
    const active = getActiveConfig();
    const ollamaModels = await detectOllamaModels();

    const runtimeNames: Record<string, string> = {
      ollama: 'Ollama',
      llama_cpp: 'llama.cpp',
      fake: 'Fake (deterministic)',
    };

    return {
      registry: REGISTRY_ENTRIES,
      installed,
      ollama_models: ollamaModels,
      active,
      runtime_health: {
        runtime_id: active.runtime_id ?? 'none',
        runtime_name: runtimeNames[active.runtime_id ?? ''] ?? 'None',
        status: 'unavailable',
        model_id: active.model_id,
        latency_ms: null,
        message: active.runtime_id
          ? 'Model configured. Start the runtime to use it.'
          : 'No model configured',
        checked_at: new Date().toISOString(),
      },
      total: REGISTRY_ENTRIES.length,
    };
  });

  // POST /api/models/use
  app.post<{ Body: UseModelRequest }>(
    '/api/models/use',
    {
      schema: {
        body: {
          type: 'object',
          required: ['runtime_id'],
          properties: {
            runtime_id: { type: 'string' },
            model_id: { type: ['string', 'null'] },
          },
        },
      },
    },
    async (req): Promise<UseModelResponse> => {
      const { runtime_id, model_id = null } = req.body;
      setActiveConfig(runtime_id, model_id ?? null);
      const runtimeNames: Record<string, string> = {
        ollama: 'Ollama',
        llama_cpp: 'llama.cpp',
        fake: 'Fake (deterministic)',
      };
      return {
        runtime_id,
        model_id: model_id ?? null,
        runtime_name: runtimeNames[runtime_id] ?? runtime_id,
        status: 'ready',
        message: null,
      };
    },
  );

  // POST /api/models/install
  app.post<{ Body: InstallModelRequest }>(
    '/api/models/install',
    {
      schema: {
        body: {
          type: 'object',
          required: ['registry_id'],
          properties: {
            registry_id: { type: 'string' },
          },
        },
      },
    },
    async (req, reply): Promise<InstallModelResponse> => {
      const { registry_id } = req.body;
      const entry = REGISTRY_ENTRIES.find((e) => e.id === registry_id);
      if (!entry) {
        reply.status(404);
        throw new Error(`Model '${registry_id}' not found in the local registry.`);
      }

      const sha256 = entry.sha256 ?? '';
      if (!sha256 || sha256.toUpperCase() === 'PENDING') {
        reply.status(400);
        throw new Error(
          `Registry entry '${registry_id}' has no verified SHA-256 checksum. ` +
          'Cannot install until a confirmed checksum is available.',
        );
      }

      const downloadUrl = entry.download_url ?? '';
      if (!downloadUrl || downloadUrl.toUpperCase() === 'PENDING') {
        reply.status(400);
        throw new Error(
          `Registry entry '${registry_id}' has no download URL. ` +
          'Cannot start a download without a source URL.',
        );
      }

      const db = getDb();
      const now = new Date().toISOString();
      const filename = `${registry_id}.gguf`;
      const result = db
        .prepare(
          "INSERT INTO installed_models (registry_id, filename, file_path, install_status, installed_at) VALUES (?, ?, '', 'pending', ?)",
        )
        .run(registry_id, filename, now);
      const installId = Number(result.lastInsertRowid);

      const ac = new AbortController();
      activeDownloads.set(installId, ac);

      const modelsDir = getModelsDir();
      void runDownload(installId, downloadUrl, sha256, modelsDir, filename, ac).finally(() => {
        activeDownloads.delete(installId);
      });

      reply.status(202);
      return {
        install_id: installId,
        registry_id,
        status: 'pending',
        message: `Downloading '${entry.name}'. Poll GET /api/models/install/${installId} for progress.`,
      };
    },
  );

  // GET /api/models/install/:id
  app.get<{ Params: { id: string } }>(
    '/api/models/install/:id',
    async (req, reply): Promise<InstalledModelInfo> => {
      const id = parseInt(req.params.id, 10);
      if (isNaN(id)) {
        reply.status(400);
        throw new Error('Invalid install ID.');
      }
      const db = getDb();
      const row = db
        .prepare<[number], InstalledModelRow>('SELECT * FROM installed_models WHERE id=?')
        .get(id);
      if (!row) {
        reply.status(404);
        throw new Error(`Install record ${id} not found.`);
      }
      return rowToInstalledModel(row);
    },
  );

  // DELETE /api/models/install/:id
  app.delete<{ Params: { id: string } }>(
    '/api/models/install/:id',
    async (req, reply): Promise<void> => {
      const id = parseInt(req.params.id, 10);
      if (isNaN(id)) {
        reply.status(400);
        throw new Error('Invalid install ID.');
      }
      const db = getDb();
      const row = db
        .prepare<[number], InstalledModelRow>('SELECT * FROM installed_models WHERE id=?')
        .get(id);
      if (!row) {
        reply.status(404);
        throw new Error(`Install record ${id} not found.`);
      }

      const TERMINAL = new Set(['ready', 'complete', 'failed', 'cancelled', 'checksum_mismatch']);
      if (TERMINAL.has(row.install_status)) {
        reply.status(409);
        throw new Error(
          `Install ${id} is already in terminal state '${row.install_status}'.`,
        );
      }

      const ac = activeDownloads.get(id);
      if (ac) {
        ac.abort();
      } else {
        db.prepare(
          "UPDATE installed_models SET install_status='cancelled', error_message='Cancelled by user.' WHERE id=?",
        ).run(id);
      }
      reply.status(204);
    },
  );

  // POST /api/models/register-gguf
  app.post<{ Body: RegisterGgufRequest }>(
    '/api/models/register-gguf',
    {
      schema: {
        body: {
          type: 'object',
          required: ['path'],
          properties: {
            path: { type: 'string', minLength: 1 },
            display_name: { type: ['string', 'null'] },
            family_guess: { type: ['string', 'null'] },
            context_length: { type: ['integer', 'null'] },
          },
        },
      },
    },
    async (req, reply): Promise<RegisterGgufResponse> => {
      const { path: filePath, display_name, family_guess, context_length } = req.body;
      const trimmed = filePath.trim();

      if (!trimmed.toLowerCase().endsWith('.gguf')) {
        reply.status(400);
        throw new Error('GGUF_INVALID_EXTENSION: The file must have a .gguf extension.');
      }

      if (!fs.existsSync(trimmed)) {
        reply.status(404);
        throw new Error(
          `GGUF_FILE_NOT_FOUND: file not found: ${trimmed}. ` +
          'Verify the path is correct and the file is accessible, then try again.',
        );
      }

      const filename = path.basename(trimmed);
      const derivedName = display_name ?? filename;

      setActiveConfig('llama_cpp', trimmed);

      const db = getDb();
      const now = new Date().toISOString();
      const result = db
        .prepare(
          "INSERT INTO installed_models (registry_id, filename, file_path, install_status, installed_at) VALUES (?, ?, ?, 'ready', ?)",
        )
        .run('user-supplied-gguf', filename, trimmed, now);

      return {
        profile_id: Number(result.lastInsertRowid),
        file_path: trimmed,
        display_name: derivedName,
        filename,
        family_guess: family_guess ?? null,
        context_length_default: context_length ?? null,
        warnings: [],
        active_runtime_id: 'llama_cpp',
        active_model_id: trimmed,
      };
    },
  );

  // POST /api/sidecar/start
  app.post<{ Body: { model_path: string } }>(
    '/api/sidecar/start',
    {
      schema: {
        body: {
          type: 'object',
          required: ['model_path'],
          properties: {
            model_path: { type: 'string' },
          },
        },
      },
    },
    async (): Promise<{
      state: string;
      pid: number | null;
      log_path: string;
      host: string;
      port: number;
    }> => {
      return {
        state: 'running',
        pid: null,
        log_path: path.join(os.homedir(), '.convsim', 'logs', 'llama-server.log'),
        host: '127.0.0.1',
        port: 7356,
      };
    },
  );
}
