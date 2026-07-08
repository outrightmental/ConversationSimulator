// SPDX-License-Identifier: Apache-2.0
import type { SessionState, EndingType } from './session.js';

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

/** A single streamed token from the NPC text generation. */
export interface WsNpcTokenEvent extends WsEventBase {
  type: 'npc.token';
  payload: {
    text: string;
  };
}

/** The NPC has finished generating its response. */
export interface WsNpcFinalEvent extends WsEventBase {
  type: 'npc.final';
  payload: {
    content: string;
    emotion: string;
    state_delta: Record<string, number>;
    event_flags: string[];
  };
}

/** Scenario state variables changed as a result of the turn. */
export interface WsScenarioStateDeltaEvent extends WsEventBase {
  type: 'scenario.state_delta';
  payload: {
    delta: Record<string, number>;
    state_vars: Record<string, number>;
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
  };
}

/** Union of all WebSocket event shapes. */
export type WsEvent =
  | WsSessionStateEvent
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
