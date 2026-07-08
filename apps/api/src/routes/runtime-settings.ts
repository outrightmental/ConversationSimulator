// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import { getDb } from '../db.js';
import type {
  RuntimeSettings,
  RuntimeSettingsResponse,
  RuntimeSettingsRequest,
  RuntimeSettingsFieldError,
} from '@convsim/shared';

const SETTING_KEYS: (keyof RuntimeSettings)[] = [
  'context_length',
  'gpu_layers',
  'threads',
  'temperature',
  'top_p',
  'repeat_penalty',
];

const RESTART_REQUIRED: Set<keyof RuntimeSettings> = new Set(['context_length', 'gpu_layers']);

const NULL_SETTINGS: RuntimeSettings = {
  context_length: null,
  gpu_layers: null,
  threads: null,
  temperature: null,
  top_p: null,
  repeat_penalty: null,
};

interface ModelConfigRow { key: string; value: string }

export function loadRuntimeSettings(): RuntimeSettings {
  const db = getDb();
  const rows = db
    .prepare<[], ModelConfigRow>("SELECT key, value FROM model_config WHERE key LIKE 'setting.%'")
    .all();
  const map: Record<string, string> = {};
  for (const r of rows) map[r.key.slice('setting.'.length)] = r.value;

  function num(k: string): number | null {
    const v = map[k];
    if (v === undefined || v === '' || v === 'null') return null;
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  return {
    context_length: num('context_length'),
    gpu_layers: num('gpu_layers'),
    threads: num('threads'),
    temperature: num('temperature'),
    top_p: num('top_p'),
    repeat_penalty: num('repeat_penalty'),
  };
}

function saveRuntimeSettings(patch: Partial<RuntimeSettings>): void {
  const db = getDb();
  const stmt = db.prepare(
    'INSERT OR REPLACE INTO model_config (key, value) VALUES (?, ?)',
  );
  db.transaction(() => {
    for (const k of SETTING_KEYS) {
      if (!(k in patch)) continue;
      const v = patch[k];
      stmt.run(`setting.${k}`, v === null || v === undefined ? 'null' : String(v));
    }
  })();
}

function validate(req: RuntimeSettingsRequest): RuntimeSettingsFieldError[] {
  const errs: RuntimeSettingsFieldError[] = [];

  const cl = req.context_length;
  if (cl !== null && cl !== undefined) {
    if (!Number.isInteger(cl) || cl < 512 || cl > 131072) {
      errs.push({
        field: 'context_length',
        message: 'Context length must be an integer between 512 and 131072.',
      });
    }
  }

  const gl = req.gpu_layers;
  if (gl !== null && gl !== undefined) {
    if (!Number.isInteger(gl) || gl < -1 || gl > 256) {
      errs.push({
        field: 'gpu_layers',
        message: 'GPU layers must be an integer between -1 (all layers to GPU) and 256.',
      });
    }
  }

  const th = req.threads;
  if (th !== null && th !== undefined) {
    if (!Number.isInteger(th) || th < 1 || th > 64) {
      errs.push({
        field: 'threads',
        message: 'Thread count must be an integer between 1 and 64.',
      });
    }
  }

  const temp = req.temperature;
  if (temp !== null && temp !== undefined) {
    if (temp < 0.0 || temp > 2.0) {
      errs.push({ field: 'temperature', message: 'Temperature must be between 0.0 and 2.0.' });
    }
  }

  const tp = req.top_p;
  if (tp !== null && tp !== undefined) {
    if (tp < 0.0 || tp > 1.0) {
      errs.push({ field: 'top_p', message: 'Top-P must be between 0.0 and 1.0.' });
    }
  }

  const rp = req.repeat_penalty;
  if (rp !== null && rp !== undefined) {
    if (rp < 1.0 || rp > 2.0) {
      errs.push({
        field: 'repeat_penalty',
        message: 'Repeat penalty must be between 1.0 and 2.0.',
      });
    }
  }

  return errs;
}

function needsRestart(patch: Partial<RuntimeSettings>, current: RuntimeSettings): boolean {
  return SETTING_KEYS.some(
    (k) => RESTART_REQUIRED.has(k) && k in patch && patch[k] !== current[k],
  );
}

export async function runtimeSettingsRoutes(app: FastifyInstance): Promise<void> {
  // GET /api/runtime/settings
  app.get('/api/runtime/settings', async (): Promise<RuntimeSettingsResponse> => {
    return {
      settings: loadRuntimeSettings(),
      recommended: NULL_SETTINGS,
      requires_restart: false,
    };
  });

  // PUT /api/runtime/settings
  app.put<{ Body: RuntimeSettingsRequest }>(
    '/api/runtime/settings',
    {
      schema: {
        body: {
          type: 'object',
          properties: {
            context_length: { type: ['integer', 'null'] },
            gpu_layers: { type: ['integer', 'null'] },
            threads: { type: ['integer', 'null'] },
            temperature: { type: ['number', 'null'] },
            top_p: { type: ['number', 'null'] },
            repeat_penalty: { type: ['number', 'null'] },
          },
        },
      },
    },
    async (req, reply): Promise<RuntimeSettingsResponse> => {
      const errs = validate(req.body);
      if (errs.length > 0) {
        const msg = errs.map((e) => e.message).join(' ');
        reply.status(422);
        throw Object.assign(new Error(msg), { errors: errs });
      }

      const current = loadRuntimeSettings();
      const restart = needsRestart(req.body, current);
      saveRuntimeSettings(req.body);

      return {
        settings: loadRuntimeSettings(),
        recommended: NULL_SETTINGS,
        requires_restart: restart,
      };
    },
  );

  // POST /api/runtime/settings/reset
  app.post('/api/runtime/settings/reset', async (): Promise<RuntimeSettingsResponse> => {
    saveRuntimeSettings(NULL_SETTINGS);
    return {
      settings: NULL_SETTINGS,
      recommended: NULL_SETTINGS,
      requires_restart: true,
    };
  });
}
