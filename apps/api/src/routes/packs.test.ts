// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import type { FastifyInstance } from 'fastify';
import type { PackValidationResult } from '@convsim/shared';

let app: FastifyInstance;

beforeEach(async () => {
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
});

describe('POST /api/packs/:pack_id/validate', () => {
  it('returns 200 with valid=true for a known pack', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/official.job_interview_basic/validate',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<PackValidationResult>();
    expect(body.pack_id).toBe('official.job_interview_basic');
    expect(body.valid).toBe(true);
    expect(body.errors).toEqual([]);
  });

  it('returns 200 for every installed pack', async () => {
    const packIds = [
      'official.job_interview_basic',
      'official.everyday_negotiation',
      'official.language_cafe',
      'official.difficult_conversations',
    ];
    for (const packId of packIds) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/packs/${packId}/validate`,
      });
      expect(res.statusCode).toBe(200);
      const body = res.json<PackValidationResult>();
      expect(body.valid).toBe(true);
    }
  });

  it('returns 404 for an unknown pack id', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/packs/does_not_exist/validate',
    });
    expect(res.statusCode).toBe(404);
  });
});
