// SPDX-License-Identifier: Apache-2.0

/**
 * All states a conversation session can occupy.
 * Canonical enum shared by the frontend and backend — both sides must use these
 * exact string values when serialising session state over the API/WebSocket.
 */
export enum SessionState {
  NotStarted = "NotStarted",
  LoadingModel = "LoadingModel",
  LoadingScenario = "LoadingScenario",
  Briefing = "Briefing",
  NpcOpening = "NpcOpening",
  PlayerTurnListening = "PlayerTurnListening",
  PlayerTurnReview = "PlayerTurnReview",
  NpcThinking = "NpcThinking",
  NpcSpeaking = "NpcSpeaking",
  ScenarioEvent = "ScenarioEvent",
  DebriefGenerating = "DebriefGenerating",
  DebriefReady = "DebriefReady",
  Ended = "Ended",
  Error = "Error",
}

/** Union of all valid session state strings. */
export type SessionStateValue = `${SessionState}`;

/** Ending type emitted in session_control.ending_type from turn-output. */
export type SessionEndingType =
  | "none"
  | "success"
  | "failure"
  | "timeout"
  | "safety_stop"
  | "player_exit";
