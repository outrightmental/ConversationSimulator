import type { ScenarioDifficulty } from './scenario.js';

export type InputMode = 'push-to-talk' | 'hands-free' | 'text-only';

export interface SetupFormValues {
  difficulty: ScenarioDifficulty;
  player_role_name: string;
  language: string;
  input_mode: InputMode;
  tts_enabled: boolean;
  show_state_meters: boolean;
  save_transcript: boolean;
  seed: number | null;
}

export interface SetupValidationError {
  field: keyof SetupFormValues | '_form';
  message: string;
}

export interface SetupValidationResult {
  valid: boolean;
  errors: SetupValidationError[];
}

export interface RuntimeReadiness {
  llm_ready: boolean;
  llm_model_name: string | null;
  stt_ready: boolean;
  tts_ready: boolean;
  tts_voice_name: string | null;
  network_required: boolean;
}

export function validateSetup(
  values: SetupFormValues,
  runtime: RuntimeReadiness,
  stateMeterPermitted: boolean,
): SetupValidationResult {
  const errors: SetupValidationError[] = [];

  if (values.tts_enabled && !runtime.tts_ready) {
    errors.push({
      field: 'tts_enabled',
      message:
        'TTS is not available — no TTS model is loaded. Switch to text-only or disable TTS.',
    });
  }

  if (values.input_mode !== 'text-only' && !runtime.stt_ready) {
    errors.push({
      field: 'input_mode',
      message: 'Voice input is not available — no STT model is loaded. Text-only mode is always available.',
    });
  }

  if (values.show_state_meters && !stateMeterPermitted) {
    errors.push({
      field: 'show_state_meters',
      message: 'This scenario does not permit showing state meters.',
    });
  }

  if (!values.player_role_name.trim()) {
    errors.push({ field: 'player_role_name', message: 'Player name is required.' });
  }

  return { valid: errors.length === 0, errors };
}

export function randomSeed(): number {
  return Math.floor(Math.random() * 2 ** 31);
}
