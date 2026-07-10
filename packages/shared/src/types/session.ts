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
  // Approved built-in TTS voice id. Omitted when no voice is selected, in which
  // case the backend applies its default. Matches the backend `tts_voice_id`
  // field, which validates the value against the approved voice list.
  tts_voice_id?: string;
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
  // Included in list responses (GET /api/sessions) but absent from creation responses
  ending_type?: EndingType | null;
  turn_count?: number;
  ended_at?: string | null;
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

export interface DebriefTurningPoint {
  turn_number: number;
  description: string;
  impact?: 'positive' | 'negative' | 'neutral';
}

export interface DebriefStateArcEntry {
  turn_number: number;
  state: Record<string, number>;
}

export interface DebriefMetrics {
  metrics_version: '1';
  talk_ratio: number;
  words_per_turn_player: number;
  words_per_turn_npc: number;
  open_questions: number;
  closed_questions: number;
  filler_word_count: number;
  interruption_count: number;
  response_latency_p50_ms: number | null;
  response_latency_p95_ms: number | null;
  state_arc: DebriefStateArcEntry[];
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
  missed_opportunities?: string[];
  replay_suggestions?: string[];
  scores?: Record<string, number>;
  overall_score?: number;
  turning_points?: DebriefTurningPoint[];
  used_fallback?: boolean;
  transcript_saving_disabled?: boolean;
  metrics?: DebriefMetrics;
}

export interface SessionTranscriptResponse {
  session_id: string;
  scenario_id: string;
  transcript_saved: boolean;
  message?: string;
  events: SessionEvent[];
}

export interface SessionExportSession {
  session_id: string;
  scenario_id: string;
  state: string;
  ending_type: string | null;
  created_at: string;
  turn_count: number;
  setup: SessionCreateRequest;
  state_vars: Record<string, number>;
}

export interface SessionExportResponse {
  session: SessionExportSession;
  events: SessionEvent[];
}

export interface SessionTransitionError {
  code: 'INVALID_TRANSITION' | 'SESSION_NOT_FOUND' | 'VALIDATION_ERROR';
  message: string;
  current_state?: SessionState;
}
