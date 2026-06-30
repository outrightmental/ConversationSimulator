// SPDX-License-Identifier: Apache-2.0

/** Overall health status of a local model runtime. */
export type RuntimeStatus = "ok" | "degraded" | "unavailable";

/** Health snapshot returned by the /health API and the ChatRuntime.health() method. */
export interface RuntimeHealth {
  /** Unique runtime identifier (e.g. "llama_cpp", "ollama"). */
  runtime_id: string;
  /** Human-readable display name. */
  runtime_name: string;
  /** Aggregated health status across all runtime components. */
  status: RuntimeStatus;
  /** Active model identifier, if a model is loaded. */
  model_id?: string;
  /** Observed round-trip latency in milliseconds, if measured. */
  latency_ms?: number;
  /** Human-readable status message (error description when status != "ok"). */
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
