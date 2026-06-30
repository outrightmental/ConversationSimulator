// SPDX-License-Identifier: Apache-2.0

/** Overall health status of a local model runtime. */
export type RuntimeStatus =
  | "unavailable"
  | "starting"
  | "ready"
  | "degraded"
  | "error";

/** Health snapshot returned by the /health API and the ChatRuntime.health() method. */
export interface RuntimeHealth {
  /** Unique runtime identifier (e.g. "llama_cpp", "fake"). */
  runtime_id: string;
  /** Human-readable display name. */
  runtime_name: string;
  /** Aggregated health status across all runtime components. */
  status: RuntimeStatus;
  /** Active model identifier, if a model is loaded. */
  model_id?: string;
  /** Observed round-trip latency in milliseconds, if measured. */
  latency_ms?: number;
  /** Human-readable status message (error description when status != "ready"). */
  message?: string;
  /** ISO 8601 timestamp of when this health snapshot was taken. */
  checked_at: string;
}

/** Capabilities advertised by a ChatRuntime implementation. */
export interface RuntimeCapabilities {
  streaming: boolean;
  json_schema: boolean;
  grammar: boolean;
  tool_calling: boolean;
  embeddings: boolean;
}

/** Minimal model info returned by ChatRuntime.listModels(). */
export interface ModelInfo {
  id: string;
  name: string;
  /** Size category for display purposes. */
  size_category?: "small" | "medium" | "large";
  context_length?: number;
}

/** A single message in a chat conversation. */
export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

/** Request sent to a ChatRuntime chat stream. */
export interface ChatRequest {
  messages: ChatMessage[];
  model_id?: string;
  max_tokens?: number;
  temperature?: number;
  json_schema?: Record<string, unknown>;
}

/** A single streamed text chunk from a ChatRuntime. */
export interface ChatToken {
  type: "token";
  text: string;
}

/** Final completion result streamed by a ChatRuntime. */
export interface ChatFinal {
  type: "final";
  text: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  /** Parsed structured output when json_schema was supplied in the request. */
  structured?: Record<string, unknown>;
}

/** Union type for items emitted by a ChatRuntime stream. */
export type ChatStreamChunk = ChatToken | ChatFinal;
