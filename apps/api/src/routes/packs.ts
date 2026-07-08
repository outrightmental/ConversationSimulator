// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import type { PackValidationResult } from '@convsim/shared';
import { SCENARIOS } from '../data/scenarios.js';

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
