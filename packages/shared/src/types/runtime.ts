export interface RuntimeReadiness {
  llm_ready: boolean;
  llm_model_name: string | null;
  stt_ready: boolean;
  tts_ready: boolean;
  tts_voice_name: string | null;
  network_required: boolean;
  last_error?: string | null;
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error';
  runtime: RuntimeReadiness;
  version: string;
}
