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

/** States a session can be picked back up from — the resumable set (issue #501
 *  §1). `NotStarted` is excluded on purpose: nothing has been said yet, so
 *  there is no conversation to resume.
 *
 *  Mirrors `RESUMABLE_FLOW_STATES` in convsim-core's sessions router, which is
 *  the one copy this cannot import — a pytest guard asserts the two agree.
 *  Everything on the TypeScript side reads it from here: the proxy's
 *  `status=in_progress` filter and Settings' per-session Resume button, which
 *  picks unfinished conversations out of a full listing client-side. A list
 *  that disagreed with the filter would offer to resume a conversation that
 *  had already ended, or hide one that had not. */
export const RESUMABLE_SESSION_STATES = [
  'PlayerTurnListening',
  'PlayerTurnReview',
  'NpcThinking',
  'NpcSpeaking',
  'ScenarioEvent',
] as const satisfies readonly SessionState[];

/** States a session has finished in. `Ended` is only the first: generating the
 *  debrief moves the row to `DebriefGenerating` and then `DebriefReady`, and a
 *  failed debrief leaves `Error`. Mirrors `ENDED_FLOW_STATES` in convsim-core. */
export const ENDED_SESSION_STATES = [
  'Ended',
  'DebriefGenerating',
  'DebriefReady',
  'Error',
] as const satisfies readonly SessionState[];

export function isResumableSessionState(state: string): boolean {
  return (RESUMABLE_SESSION_STATES as readonly string[]).includes(state);
}

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
  // Conversational timing features (issue #308). All optional; backend defaults apply.
  npc_thinking_pause_enabled?: boolean;
  backchannel_enabled?: boolean;
  barge_in_enabled?: boolean;
  show_state_meters: boolean;
  save_transcript: boolean;
  seed: number | null;
  // Pins the session to a model-free runtime for its whole lifetime, instead of
  // following the globally selected runtime. Only the scripted tutorial and demo
  // mode need this; omit it and the backend uses the active selection.
  runtime_id?: 'scripted' | 'fake';
}

export interface SessionCreateResponse {
  session_id: string;
  scenario_id: string;
  state: SessionState;
  created_at: string;
  setup: SessionCreateRequest;
  ending_type?: EndingType | null;
  /** Whole turns completed — one player message plus the NPC's reply. */
  turn_count?: number;
  ended_at?: string | null;
  /** Current meter values, minus the variables the scenario keeps hidden.
   *  Only GET /api/sessions/{id} reports it; a resuming conversation screen
   *  reads its meters back from here. Absent means "not reported". */
  visible_state?: Record<string, number> | null;
}

/** Filter for GET /api/sessions. 'in_progress' is the resumable set: started
 *  and not ended, which is what the resume entry points offer (issue #501). */
export type SessionListStatus = 'all' | 'in_progress' | 'ended';

export interface SessionListResponse {
  sessions: SessionCreateResponse[];
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
  /** Server field name is `total_turns` (see DebriefResponse in routers/sessions.py). */
  total_turns?: number;
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

export interface BranchSessionRequest {
  /** 1-indexed game turn to retry; copies parent transcript up to turn N-1. */
  fork_turn_number: number;
}

export interface BranchSessionResponse {
  branch_session_id: string;
  parent_session_id: string;
  fork_turn_number: number;
  state: SessionState;
  created_at: string;
}

export interface SessionCompareSummary {
  session_id: string;
  outcome: string | null;
  total_turns: number;
  overall_score: number | null;
  headline_metrics: {
    talk_ratio: number | null;
    open_questions: number | null;
    words_per_turn_player: number | null;
    response_latency_p50_ms: number | null;
  } | null;
}

export interface SessionCompareResponse {
  parent_session_id: string;
  branch_session_id: string;
  fork_turn_number: number;
  parent: SessionCompareSummary;
  branch: SessionCompareSummary;
}
