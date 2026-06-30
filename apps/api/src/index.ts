import Fastify from 'fastify';
import cors from '@fastify/cors';
import { healthRoutes } from './routes/health.js';
import { scenarioRoutes } from './routes/scenarios.js';
import { sessionRoutes } from './routes/sessions.js';

export async function buildApp() {
  const app = Fastify({ logger: true });

  await app.register(cors, { origin: 'http://localhost:7354' });

  await app.register(healthRoutes);
  await app.register(scenarioRoutes);
  await app.register(sessionRoutes);

  return app;
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  const app = await buildApp();
  await app.listen({ port: 7355, host: '127.0.0.1' });
}
