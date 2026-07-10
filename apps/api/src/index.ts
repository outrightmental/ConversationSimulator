import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import Fastify from 'fastify';
import cors from '@fastify/cors';
import websocket from '@fastify/websocket';
import { healthRoutes } from './routes/health.js';
import { packsRoutes, packRoutes, setPacksDbPath, setPacksDataDir } from './routes/packs.js';
import { scenarioRoutes } from './routes/scenarios.js';
import { sessionRoutes } from './routes/sessions.js';
import { sessionWsRoutes } from './routes/session-ws.js';
import { privacyRoutes, setDataFolderPath } from './routes/privacy.js';
import { workbenchRoutes, setWorkbenchRoots } from './routes/workbench.js';
import { modelsRoutes } from './routes/models.js';
import { runtimeSettingsRoutes } from './routes/runtime-settings.js';
import { initDb } from './db.js';
import { getListenConfig } from './config.js';

export async function buildApp() {
  const app = Fastify({ logger: true });

  await app.register(cors, { origin: 'http://localhost:7354' });
  await app.register(websocket);

  // Propagate typed error fields (code, current_state) set by route handlers.
  // Fall back to reply.statusCode when the error itself has no statusCode set,
  // because some routes call reply.status(4xx) and then throw a plain Error.
  app.setErrorHandler((error, _request, reply) => {
    const typed = error as { statusCode?: number; message?: string; code?: string; current_state?: string };
    const statusCode = typed.statusCode ?? (reply.statusCode >= 400 ? reply.statusCode : 500);
    const body: Record<string, unknown> = { statusCode, message: typed.message ?? 'Internal Server Error' };
    if (typed.code) body['code'] = typed.code;
    if (typed.current_state) body['current_state'] = typed.current_state;
    reply.status(statusCode).send(body);
  });

  await app.register(healthRoutes);
  await app.register(packsRoutes);
  await app.register(scenarioRoutes);
  await app.register(sessionRoutes);
  await app.register(sessionWsRoutes);
  await app.register(privacyRoutes);
  await app.register(packRoutes);
  await app.register(workbenchRoutes);
  await app.register(modelsRoutes);
  await app.register(runtimeSettingsRoutes);

  return app;
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  const dbPath =
    process.env['SESSION_DB_PATH'] ??
    path.join(os.homedir(), '.convsim', 'db', 'sessions.db');
  const packsDbPath =
    process.env['PACKS_DB_PATH'] ??
    path.join(os.homedir(), '.convsim', 'db', 'packs.db');
  const listenConfig = getListenConfig();
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  fs.mkdirSync(path.dirname(packsDbPath), { recursive: true });
  const packsDataDir =
    process.env['PACKS_DATA_DIR'] ??
    path.join(path.dirname(packsDbPath), 'packs');
  fs.mkdirSync(packsDataDir, { recursive: true });
  initDb(dbPath);
  setDataFolderPath(path.dirname(dbPath));
  setPacksDbPath(packsDbPath);
  setPacksDataDir(packsDataDir);
  setWorkbenchRoots(
    process.env['PACKS_OFFICIAL_ROOT'] ?? path.join(process.cwd(), 'packs', 'official'),
    process.env['PACKS_LOCAL_DEV_ROOT'] ?? path.join(os.homedir(), '.convsim', 'packs', 'local-dev'),
  );
  const app = await buildApp();
  await app.listen(listenConfig);
}
