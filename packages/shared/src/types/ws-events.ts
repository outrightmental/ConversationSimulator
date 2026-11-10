// SPDX-License-Identifier: Apache-2.0
import type { SessionState, EndingType } from './session.js';
import type { TurnStage, TurnTiming } from './metrics.js';

/** Base fields present on every WebSocket event. */
export interface WsEventBase {
  /** Monotonically increasing per-session sequence number. Gaps indicate missed events. */
  seq: number;
  /** Session this event belongs to. */
  session_id: string;
  /** ISO 8601 timestamp when the event was emitted. */
  ts: string;
}

/** Session state changed (start, turn, end, or error transitions). */
export interface WsSessionStateEvent extends WsEventBase {
  type: 'session.state';
  payload: {
    state: SessionState;
    state_vars?: Record<string, number>;
    ending_type?: EndingType | null;
  };
}

/**
 * Which stage a running turn is in (issue #538), and how far the engine has
 * read the prompt when it says so. Sent on every stage change and on every
 * prompt-reading progress report. `elapsed_ms` is measured from the moment
 * the turn request reached the core.
 */
export interface WsTurnProgressEvent extends WsEventBase {
  type: 'turn.progress';
  payload: {
    stage: TurnStage;
    /** Prompt tokens processed of total, and how many came from cache; null when the engine gave no count. */
    prompt: { processed: number | null; total: number | null; cached: number | null } | null;
    output_tokens: number;
    elapsed_ms: number;
  };
}

/**
 * One checked sentence of the NPC's line (issue #538). Each `text` is an exact
 * slice of the line, released only once the line so far has passed the output
 * check; concatenating every `npc.token` of a turn reproduces the committed
 * line, and nothing shown is ever withdrawn.
 */
export interface WsNpcTokenEvent extends WsEventBase {
  type: 'npc.token';
  payload: {
    text: string;
  };
}

/**
 * The NPC's spoken line is complete. The turn is still being written — its
 * state change, emotion and flags arrive on `scenario.state_delta` at commit —
 * but the player can read (and reply to) the whole line now.
 */
export interface WsNpcFinalEvent extends WsEventBase {
  type: 'npc.final';
  payload: {
    content: string;
    /** Not known when the line closes; present only on events from older servers. */
    emotion?: string;
    state_delta?: Record<string, number>;
    event_flags?: string[];
  };
}

/** The turn committed: the state change the reply produced, and the rest of the turn's bookkeeping. */
export interface WsScenarioStateDeltaEvent extends WsEventBase {
  type: 'scenario.state_delta';
  payload: {
    delta: Record<string, number>;
    state_vars: Record<string, number>;
    turn_number?: number;
    emotion?: string;
    event_flags?: string[];
    triggered_scenario_events?: string[];
    ending_type?: EndingType | null;
    /** True when the turn was built from released words plus whatever bookkeeping completed (#538). */
    salvaged?: boolean;
    timing?: TurnTiming | null;
  };
}

/** The scenario triggered a narrative event. */
export interface WsScenarioEventEvent extends WsEventBase {
  type: 'scenario.event';
  payload: {
    flags: string[];
  };
}

/** Input safety classifier redirected the conversation. */
export interface WsSafetyRedirectEvent extends WsEventBase {
  type: 'safety.redirect';
  payload: {
    reason: string;
  };
}

/** A typed error occurred during session processing. Does not kill the session unless state transitions to Error. */
export interface WsErrorEvent extends WsEventBase {
  type: 'error';
  payload: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ---------------------------------------------------------------------------
// Reserved event types — emitted by future speech issues.
// Clients should be prepared to receive and ignore unknown types gracefully.
// ---------------------------------------------------------------------------

/** Partial speech-to-text transcript (interim result). Reserved for future speech support. */
export interface WsSttPartialEvent extends WsEventBase {
  type: 'stt.partial';
  payload: { text: string };
}

/** Final speech-to-text transcript. Reserved for future speech support. */
export interface WsSttFinalEvent extends WsEventBase {
  type: 'stt.final';
  payload: { text: string; confidence: number };
}

/** A synthesized sentence chunk from the local TTS cache. */
export interface WsTtsAudioChunkEvent extends WsEventBase {
  type: 'tts.audio_chunk';
  payload: {
    /** Zero-based position of this chunk within the utterance. */
    chunk_index: number;
    /** Total number of chunks for this utterance. */
    total_chunks: number;
    /** Sentence text (always present; use as fallback when cache_path is null). */
    text: string;
    /** Voice used for synthesis. */
    voice_id: string;
    /** Absolute path to the cached WAV file on localhost, or null on failure. */
    cache_path: string | null;
    /** Error message if synthesis failed; null on success. */
    error: string | null;
    /**
     * NPC thinking-pause duration in ms. Only present on the first chunk
     * (chunk_index === 0) when the feature is enabled. The client should
     * delay playback start by this many ms to simulate the NPC pausing
     * before speaking.
     */
    thinking_pause_ms?: number;
  };
}

/** Union of all WebSocket event shapes. */
export type WsEvent =
  | WsSessionStateEvent
  | WsTurnProgressEvent
  | WsNpcTokenEvent
  | WsNpcFinalEvent
  | WsScenarioStateDeltaEvent
  | WsScenarioEventEvent
  | WsSafetyRedirectEvent
  | WsErrorEvent
  | WsSttPartialEvent
  | WsSttFinalEvent
  | WsTtsAudioChunkEvent;

/** Union of all valid WebSocket event type strings. */
export type WsEventType = WsEvent['type'];
