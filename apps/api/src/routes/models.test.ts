// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import crypto from 'node:crypto';
import { Readable } from 'node:stream';
import { buildApp } from '../index.js';
import { resetDb, getDb } from '../db.js';
import type { FastifyInstance } from 'fastify';
import type { InstalledModelInfo, ModelsResponse } from '@convsim/shared';
import { runDownload } from './models.js';

let app: FastifyInstance;
let tmpDir: string;

beforeEach(async () => {
  resetDb();
  app = await buildApp();
  tmpDir = mkdtempSync(join(tmpdir(), 'convsim-models-test-'));
});

afterEach(async () => {
  vi.restoreAllMocks();
  await app.close();
  rmSync(tmpDir, { recursive: true, force: true });
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function sha256hex(data: Buffer): string {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function makeReadableStream(data: Buffer): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(data));
      controller.close();
    },
  });
}

function mockFetch(data: Buffer, opts: { ok?: boolean; status?: number; noContentLength?: boolean } = {}) {
  const { ok = true, status = 200, noContentLength = false } = opts;
  return vi.fn(async (_url: unknown, _init?: unknown) => ({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: {
      get(name: string) {
        if (name === 'content-length' && !noContentLength) return String(data.length);
        return null;
      },
    },
    body: makeReadableStream(data),
  }));
}

// ── GET /api/models ───────────────────────────────────────────────────────────

describe('GET /api/models', () => {
  it('returns 200 with registry entries', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    expect(res.statusCode).toBe(200);
    const body = res.json<ModelsResponse>();
    expect(body.registry.length).toBeGreaterThan(0);
  });

  it('includes the starter model in the registry', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    const starter = body.registry.find((m) => m.role === 'starter');
    expect(starter).toBeDefined();
    expect(starter!.id).toBe('qwen3-4b-instruct-q4_k_m');
  });

  it('exposes license_spdx and license_url for each registry entry', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    for (const entry of body.registry) {
      expect(entry.license_spdx).toBeTruthy();
      expect(entry.license_url).toBeTruthy();
    }
  });

  it('exposes source_type for each registry entry', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    for (const entry of body.registry) {
      expect(entry.source_type).toBe('registry');
    }
  });

  it('returns empty installed list on a fresh DB', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    expect(body.installed).toEqual([]);
  });

  it('returns null active runtime and model when unconfigured', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    expect(body.active.runtime_id).toBeNull();
    expect(body.active.model_id).toBeNull();
  });

  it('returns an ollama_models array (empty when Ollama is not running)', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    expect(Array.isArray(body.ollama_models)).toBe(true);
  });

  it('includes runtime_health with a checked_at timestamp', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    expect(body.runtime_health.checked_at).toBeTruthy();
    expect(typeof body.runtime_health.checked_at).toBe('string');
  });

  it('reflects installed models in the response after registration', async () => {
    const filePath = join(tmpDir, 'model.gguf');
    writeFileSync(filePath, 'fake content');
    await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: filePath },
    });
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    expect(body.installed.length).toBe(1);
    expect(body.installed[0].file_path).toBe(filePath);
  });
});

// ── POST /api/models/use ─────────────────────────────────────────────────────

describe('POST /api/models/use', () => {
  it('returns 200 with the active runtime info', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/use',
      payload: { runtime_id: 'ollama', model_id: 'llama3:latest' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.runtime_id).toBe('ollama');
    expect(body.model_id).toBe('llama3:latest');
    expect(body.runtime_name).toBe('Ollama');
    expect(body.status).toBe('ready');
  });

  it('persists the active config so GET /api/models reflects it', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/models/use',
      payload: { runtime_id: 'fake', model_id: null },
    });
    const res = await app.inject({ method: 'GET', url: '/api/models' });
    const body = res.json<ModelsResponse>();
    expect(body.active.runtime_id).toBe('fake');
    expect(body.active.model_id).toBeNull();
  });

  it('accepts null model_id for runtimes that do not need one', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/use',
      payload: { runtime_id: 'fake', model_id: null },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().model_id).toBeNull();
  });

  it('returns 400 when runtime_id is missing', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/use',
      payload: { model_id: 'some-model' },
    });
    expect(res.statusCode).toBe(400);
  });
});

// ── POST /api/models/install ─────────────────────────────────────────────────

describe('POST /api/models/install', () => {
  it('returns 404 for an unknown registry_id', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/install',
      payload: { registry_id: 'nonexistent-model' },
    });
    expect(res.statusCode).toBe(404);
  });

  it('returns 400 when sha256 is PENDING', async () => {
    // All current registry entries have PENDING checksums.
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/install',
      payload: { registry_id: 'qwen3-4b-instruct-q4_k_m' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().message).toMatch(/checksum/i);
  });

  it('does not create an install record when sha256 is PENDING', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/models/install',
      payload: { registry_id: 'qwen3-4b-instruct-q4_k_m' },
    });
    const db = getDb();
    const rows = db
      .prepare("SELECT id FROM installed_models WHERE registry_id='qwen3-4b-instruct-q4_k_m'")
      .all();
    expect(rows).toHaveLength(0);
  });

  it('does not make any network call when sha256 is PENDING', async () => {
    const spy = vi.spyOn(globalThis, 'fetch');
    await app.inject({
      method: 'POST',
      url: '/api/models/install',
      payload: { registry_id: 'qwen3-4b-instruct-q4_k_m' },
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it('returns 400 when registry_id is missing', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/install',
      payload: {},
    });
    expect(res.statusCode).toBe(400);
  });
});

// ── GET /api/models/install/:id ───────────────────────────────────────────────

describe('GET /api/models/install/:id', () => {
  function insertPendingRecord() {
    const db = getDb();
    const result = db
      .prepare(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status, installed_at) VALUES ('test-model', 'test.gguf', '', 'pending', '2026-01-01T00:00:00Z')",
      )
      .run();
    return Number(result.lastInsertRowid);
  }

  it('returns 404 for an unknown install ID', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models/install/9999' });
    expect(res.statusCode).toBe(404);
  });

  it('returns 200 with install record fields', async () => {
    const id = insertPendingRecord();
    const res = await app.inject({ method: 'GET', url: `/api/models/install/${id}` });
    expect(res.statusCode).toBe(200);
    const body = res.json<InstalledModelInfo>();
    expect(body.id).toBe(id);
    expect(body.install_status).toBe('pending');
    expect(body.filename).toBe('test.gguf');
  });

  it('includes progress_bytes, error_message, and verified_sha256 fields', async () => {
    const id = insertPendingRecord();
    const res = await app.inject({ method: 'GET', url: `/api/models/install/${id}` });
    const body = res.json<InstalledModelInfo>();
    expect('progress_bytes' in body).toBe(true);
    expect('error_message' in body).toBe(true);
    expect('verified_sha256' in body).toBe(true);
  });

  it('returns 400 for a non-numeric id', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/models/install/abc' });
    expect(res.statusCode).toBe(400);
  });
});

// ── DELETE /api/models/install/:id ───────────────────────────────────────────

describe('DELETE /api/models/install/:id', () => {
  function insertRecord(status = 'pending') {
    const db = getDb();
    const result = db
      .prepare(
        `INSERT INTO installed_models (registry_id, filename, file_path, install_status, installed_at)
         VALUES ('test-model', 'test.gguf', '', '${status}', '2026-01-01T00:00:00Z')`,
      )
      .run();
    return Number(result.lastInsertRowid);
  }

  it('returns 404 for an unknown install ID', async () => {
    const res = await app.inject({ method: 'DELETE', url: '/api/models/install/9999' });
    expect(res.statusCode).toBe(404);
  });

  it('marks a pending record as cancelled and returns 204', async () => {
    const id = insertRecord('pending');
    const res = await app.inject({ method: 'DELETE', url: `/api/models/install/${id}` });
    expect(res.statusCode).toBe(204);
    const db = getDb();
    const row = db
      .prepare<[number], { install_status: string }>(
        'SELECT install_status FROM installed_models WHERE id=?',
      )
      .get(id);
    expect(row!.install_status).toBe('cancelled');
  });

  it('returns 409 for a record already in a terminal state (ready)', async () => {
    const id = insertRecord('ready');
    const res = await app.inject({ method: 'DELETE', url: `/api/models/install/${id}` });
    expect(res.statusCode).toBe(409);
  });

  it('returns 409 for a record in terminal state (failed)', async () => {
    const id = insertRecord('failed');
    const res = await app.inject({ method: 'DELETE', url: `/api/models/install/${id}` });
    expect(res.statusCode).toBe(409);
  });

  it('returns 409 for a record in terminal state (checksum_mismatch)', async () => {
    const id = insertRecord('checksum_mismatch');
    const res = await app.inject({ method: 'DELETE', url: `/api/models/install/${id}` });
    expect(res.statusCode).toBe(409);
  });
});

// ── POST /api/models/register-gguf ───────────────────────────────────────────

describe('POST /api/models/register-gguf', () => {
  it('returns 200 with profile data for a valid .gguf path', async () => {
    const filePath = join(tmpDir, 'my-model.gguf');
    writeFileSync(filePath, 'fake gguf weights');

    const res = await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: filePath },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.file_path).toBe(filePath);
    expect(body.filename).toBe('my-model.gguf');
    expect(body.active_runtime_id).toBe('llama_cpp');
    expect(body.active_model_id).toBe(filePath);
    expect(Array.isArray(body.warnings)).toBe(true);
  });

  it('sets the active config to llama_cpp with the file path', async () => {
    const filePath = join(tmpDir, 'my-model.gguf');
    writeFileSync(filePath, 'fake gguf weights');

    await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: filePath },
    });

    const modelsRes = await app.inject({ method: 'GET', url: '/api/models' });
    const body = modelsRes.json<ModelsResponse>();
    expect(body.active.runtime_id).toBe('llama_cpp');
    expect(body.active.model_id).toBe(filePath);
  });

  it('returns 400 when path lacks .gguf extension', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: '/home/user/model.bin' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().message).toMatch(/gguf/i);
  });

  it('returns 404 when the file does not exist', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: join(tmpDir, 'missing.gguf') },
    });
    expect(res.statusCode).toBe(404);
    expect(res.json().message).toMatch(/file not found/i);
  });

  it('uses the provided display_name when given', async () => {
    const filePath = join(tmpDir, 'my-model.gguf');
    writeFileSync(filePath, 'fake gguf weights');

    const res = await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: filePath, display_name: 'My Custom Model' },
    });
    expect(res.json().display_name).toBe('My Custom Model');
  });

  it('falls back to filename as display_name when none provided', async () => {
    const filePath = join(tmpDir, 'another-model.gguf');
    writeFileSync(filePath, 'fake gguf weights');

    const res = await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: filePath },
    });
    expect(res.json().display_name).toBe('another-model.gguf');
  });

  it('creates an installed_models row marked ready', async () => {
    const filePath = join(tmpDir, 'my-model.gguf');
    writeFileSync(filePath, 'fake gguf weights');

    await app.inject({
      method: 'POST',
      url: '/api/models/register-gguf',
      payload: { path: filePath },
    });

    const db = getDb();
    const rows = db
      .prepare<[], { install_status: string; file_path: string }>(
        "SELECT install_status, file_path FROM installed_models WHERE registry_id='user-supplied-gguf'",
      )
      .all();
    expect(rows).toHaveLength(1);
    expect(rows[0].install_status).toBe('ready');
    expect(rows[0].file_path).toBe(filePath);
  });
});

// ── POST /api/sidecar/start ───────────────────────────────────────────────────

describe('POST /api/sidecar/start', () => {
  it('returns 200 with running state', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sidecar/start',
      payload: { model_path: '/tmp/model.gguf' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state).toBe('running');
    expect(body.host).toBe('127.0.0.1');
    expect(typeof body.port).toBe('number');
    expect(typeof body.log_path).toBe('string');
  });

  it('returns 400 when model_path is missing', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/sidecar/start',
      payload: {},
    });
    expect(res.statusCode).toBe(400);
  });
});

// ── runDownload unit tests ────────────────────────────────────────────────────

describe('runDownload — checksum verification', () => {
  function insertInstallRecord(registryId: string | null = null): number {
    const db = getDb();
    const result = db
      .prepare(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status, installed_at) VALUES (?, 'test.gguf', '', 'pending', '2026-01-01T00:00:00Z')",
      )
      .run(registryId);
    return Number(result.lastInsertRowid);
  }

  function getInstallRecord(id: number) {
    return getDb()
      .prepare<[number], InstalledModelRow>(
        'SELECT * FROM installed_models WHERE id=?',
      )
      .get(id);
  }

  interface InstalledModelRow {
    id: number;
    install_status: string;
    verified_sha256: string | null;
    error_message: string | null;
    size_bytes: number | null;
    progress_bytes: number | null;
    file_path: string;
  }

  it('marks status ready and stores verified_sha256 when checksum matches', async () => {
    const content = Buffer.from('fake gguf model data');
    const expectedSha256 = sha256hex(content);
    vi.stubGlobal('fetch', mockFetch(content));

    const installId = insertInstallRecord('test-model');
    await runDownload(
      installId,
      'http://example.test/model.gguf',
      expectedSha256,
      tmpDir,
      'test.gguf',
    );

    const record = getInstallRecord(installId);
    expect(record!.install_status).toBe('ready');
    expect(record!.verified_sha256).toBe(expectedSha256);
  });

  it('marks status checksum_mismatch and deletes the file on digest mismatch', async () => {
    const content = Buffer.from('corrupted download data');
    const wrongSha256 = 'b'.repeat(64);
    vi.stubGlobal('fetch', mockFetch(content));

    const installId = insertInstallRecord('test-model');
    await runDownload(
      installId,
      'http://example.test/model.gguf',
      wrongSha256,
      tmpDir,
      'test.gguf',
    );

    const record = getInstallRecord(installId);
    expect(record!.install_status).toBe('checksum_mismatch');
    expect(record!.error_message).toMatch(/mismatch/i);
    expect(existsSync(join(tmpDir, 'test.gguf'))).toBe(false);
    expect(existsSync(join(tmpDir, 'test.gguf.part'))).toBe(false);
  });

  it('does not leave a .part file on disk after a checksum mismatch', async () => {
    const content = Buffer.from('data that will fail checksum');
    vi.stubGlobal('fetch', mockFetch(content));

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', 'f'.repeat(64), tmpDir, 'test.gguf');

    expect(existsSync(join(tmpDir, 'test.gguf.part'))).toBe(false);
  });

  it('marks status failed on a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')));

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://unreachable.test/model.gguf', 'a'.repeat(64), tmpDir, 'test.gguf');

    const record = getInstallRecord(installId);
    expect(record!.install_status).toBe('failed');
    expect(record!.error_message).toMatch(/connection refused/i);
  });

  it('marks status failed when HTTP response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: { get: () => null },
        body: null,
      })),
    );

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', 'a'.repeat(64), tmpDir, 'test.gguf');

    const record = getInstallRecord(installId);
    expect(record!.install_status).toBe('failed');
    expect(record!.error_message).toMatch(/503/);
  });

  it('records size_bytes from content-length header', async () => {
    const content = Buffer.from('hello world model');
    const expectedSha256 = sha256hex(content);
    vi.stubGlobal('fetch', mockFetch(content));

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', expectedSha256, tmpDir, 'test.gguf');

    const record = getInstallRecord(installId);
    expect(record!.size_bytes).toBe(content.length);
  });

  it('marks status cancelled when the AbortController is aborted', async () => {
    const content = Buffer.from('x'.repeat(200_000));
    const expectedSha256 = sha256hex(content);
    const ac = new AbortController();

    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: unknown, init?: { signal?: AbortSignal }) => {
        // Simulate immediate abort.
        if (init?.signal?.aborted) throw new Error('AbortError');
        throw Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' });
      }),
    );

    ac.abort();
    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', expectedSha256, tmpDir, 'test.gguf', ac);

    const record = getInstallRecord(installId);
    expect(record!.install_status).toBe('cancelled');
  });

  it('writes to .part file first then renames to final on success', async () => {
    const content = Buffer.from('model content');
    const expectedSha256 = sha256hex(content);
    vi.stubGlobal('fetch', mockFetch(content));

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', expectedSha256, tmpDir, 'test.gguf');

    expect(existsSync(join(tmpDir, 'test.gguf'))).toBe(true);
    expect(existsSync(join(tmpDir, 'test.gguf.part'))).toBe(false);
  });

  it('sets install status to downloading before the download completes', async () => {
    const content = Buffer.from('model data for status test');
    const expectedSha256 = sha256hex(content);
    const statusDuringDownload: string[] = [];

    const originalFetch = vi.fn(async () => {
      const db = getDb();
      const row = db
        .prepare<[number], { install_status: string }>(
          'SELECT install_status FROM installed_models WHERE id=?',
        )
        .get(1);
      if (row) statusDuringDownload.push(row.install_status);
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: { get: (n: string) => (n === 'content-length' ? String(content.length) : null) },
        body: makeReadableStream(content),
      };
    });
    vi.stubGlobal('fetch', originalFetch);

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', expectedSha256, tmpDir, 'test.gguf');

    expect(statusDuringDownload).toContain('downloading');
  });

  it('accepts PENDING as expectedSha256 and skips verification (marks ready)', async () => {
    const content = Buffer.from('some model bytes');
    vi.stubGlobal('fetch', mockFetch(content));

    const installId = insertInstallRecord();
    await runDownload(installId, 'http://example.test/model.gguf', 'PENDING', tmpDir, 'test.gguf');

    const record = getInstallRecord(installId);
    expect(record!.install_status).toBe('ready');
    expect(record!.verified_sha256).toBeTruthy();
  });
});

// ── verify_sha256 unit tests ──────────────────────────────────────────────────

describe('verify_sha256 (crypto.createHash)', () => {
  it('SHA-256 of known data matches computed hex', () => {
    const data = Buffer.from('hello model weights');
    const expected = sha256hex(data);
    const actual = crypto.createHash('sha256').update(data).digest('hex');
    expect(actual).toBe(expected);
  });

  it('different data produces different SHA-256', () => {
    const a = sha256hex(Buffer.from('content A'));
    const b = sha256hex(Buffer.from('content B'));
    expect(a).not.toBe(b);
  });

  it('SHA-256 is case-insensitive when compared with toLowerCase', () => {
    const data = Buffer.from('case test data');
    const hex = sha256hex(data);
    expect(hex.toLowerCase()).toBe(hex.toUpperCase().toLowerCase());
  });

  it('SHA-256 spans multiple chunks correctly', () => {
    const chunk1 = Buffer.from('chunk one data');
    const chunk2 = Buffer.from('chunk two data');
    const combined = Buffer.concat([chunk1, chunk2]);
    const hashCombined = sha256hex(combined);

    const hash = crypto.createHash('sha256');
    hash.update(chunk1);
    hash.update(chunk2);
    expect(hash.digest('hex')).toBe(hashCombined);
  });
});

// ── Integration: download does not fire from play mode (session routes) ────────

describe('No network calls in play mode', () => {
  it('GET /api/models does not initiate any model downloads', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: { get: () => null } as unknown as Headers,
      json: async () => ({ models: [] }),
      body: null,
    } as unknown as Response);

    await app.inject({ method: 'GET', url: '/api/models' });

    const downloadCalls = spy.mock.calls.filter(
      ([url]) => typeof url === 'string' && !url.includes('11434'),
    );
    expect(downloadCalls).toHaveLength(0);
  });
});
