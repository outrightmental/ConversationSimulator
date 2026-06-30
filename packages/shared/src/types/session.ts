import type { ScenarioDifficulty } from './scenario.js';
import type { InputMode } from './setup.js';

export type SessionState =
  | 'NotStarted'
  | 'LoadingModel'
  | 'LoadingScenario'
  | 'Briefing'
  | 'NpcOpening'
  | 'PlayerTurnListening'
  | 'PlayerTurnReview'
  | 'NpcThinking'
  | 'NpcSpeaking'
  | 'ScenarioEvent'
  | 'DebriefGenerating'
  | 'DebriefReady'
  | 'Ended'
  | 'Error';

export interface SessionCreateRequest {
  scenario_id: string;
  difficulty: ScenarioDifficulty;
  player_role_name: string;
  language: string;
  input_mode: InputMode;
  tts_enabled: boolean;
  show_state_meters: boolean;
  save_transcript: boolean;
  seed: number | null;
}

export interface SessionCreateResponse {
  session_id: string;
  scenario_id: string;
  state: SessionState;
  created_at: string;
  setup: SessionCreateRequest;
}
