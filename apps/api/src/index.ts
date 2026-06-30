import Fastify from 'fastify';
import cors from '@fastify/cors';
import { healthRoutes } from './routes/health.js';
import { scenarioRoutes } from './routes/scenarios.js';
import { sessionRoutes } from './routes/sessions.js';

export async function buildApp() {
  const app = Fastify({ logger: true });

  await app.register(cors, { origin: 'http://localhost:7354' });

  // Propagate typed error fields (code, current_state) set by route handlers.
  // Fall back to reply.statusCode when the error itself has no statusCode set,
  // because some routes call reply.status(4xx) and then throw a plain Error.
  app.setErrorHandler((error, _request, reply) => {
    const statusCode = error.statusCode ?? reply.statusCode ?? 500;
    const body: Record<string, unknown> = { statusCode, message: error.message };
    const typed = error as Record<string, unknown>;
    if (typed['code']) body['code'] = typed['code'];
    if (typed['current_state']) body['current_state'] = typed['current_state'];
    reply.status(statusCode).send(body);
  });

  await app.register(healthRoutes);
  await app.register(scenarioRoutes);
  await app.register(sessionRoutes);

  return app;
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  const app = await buildApp();
  await app.listen({ port: 7355, host: '127.0.0.1' });
}
