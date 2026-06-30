import type { FastifyInstance } from 'fastify';
import type { ScenarioInfo } from '@convsim/shared';
import { SCENARIOS } from '../data/scenarios.js';

export async function scenarioRoutes(app: FastifyInstance) {
  app.get('/api/scenarios', async (): Promise<ScenarioInfo[]> => {
    return Object.values(SCENARIOS);
  });

  app.get<{ Params: { scenario_id: string } }>(
    '/api/scenarios/:scenario_id',
    async (req, reply): Promise<ScenarioInfo> => {
      const scenario = SCENARIOS[req.params.scenario_id];
      if (!scenario) {
        reply.status(404);
        throw new Error(`Scenario '${req.params.scenario_id}' not found`);
      }
      return scenario;
    },
  );
}
