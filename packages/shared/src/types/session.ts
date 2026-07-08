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

export type EndingType = 'player_exit' | 'success' | 'failure' | 'timeout' | 'safety_stop';

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

export interface SessionEvent {
  event_id: number;
  session_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface SessionStartResponse {
  session_id: string;
  state: SessionState;
  events: SessionEvent[];
}

export interface TurnRequest {
  content: string;
}

export interface TurnResponse {
  session_id: string;
  state: SessionState;
  events: SessionEvent[];
}

export interface SessionEndResponse {
  session_id: string;
  state: SessionState;
  ending_type: EndingType;
}

export interface SessionDebriefResponse {
  session_id: string;
  state: SessionState;
  summary: string;
  outcome?: string;
  turn_count?: number;
  scenario_id?: string;
  strengths?: string[];
  improvements?: string[];
  replay_suggestions?: string[];
}

export interface SessionTransitionError {
  code: 'INVALID_TRANSITION' | 'SESSION_NOT_FOUND' | 'VALIDATION_ERROR';
  message: string;
  current_state?: SessionState;
}
