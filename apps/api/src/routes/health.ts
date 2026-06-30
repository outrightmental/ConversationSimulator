import type { FastifyInstance } from 'fastify';
import type { HealthResponse } from '@convsim/shared';

export async function healthRoutes(app: FastifyInstance) {
  app.get('/api/health', async (): Promise<HealthResponse> => {
    return {
      status: 'ok',
      version: '0.1.0',
      runtime: {
        llm_ready: false,
        llm_model_name: null,
        stt_ready: false,
        tts_ready: false,
        tts_voice_name: null,
        network_required: false,
      },
    };
  });
}
