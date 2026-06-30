// SPDX-License-Identifier: Apache-2.0

/**
 * Structured error codes returned by the convsim-core API.
 * Frontend code should switch on `code` rather than parsing `message`.
 */
export type ApiErrorCode =
  | "SCHEMA_VALIDATION_ERROR"
  | "PACK_NOT_FOUND"
  | "SCENARIO_NOT_FOUND"
  | "SESSION_NOT_FOUND"
  | "MODEL_NOT_LOADED"
  | "RUNTIME_UNAVAILABLE"
  | "SAFETY_VIOLATION"
  | "TURN_LIMIT_EXCEEDED"
  | "INTERNAL_ERROR"
  | "UNAUTHORIZED";

/** Error body returned in the `error` field of any 4xx or 5xx API response. */
export interface ApiError {
  /** Machine-readable error code. */
  code: ApiErrorCode;
  /** Human-readable error message (may change between releases; do not parse). */
  message: string;
  /** Additional structured context depending on the error code. */
  details?: Record<string, unknown>;
}

/** Standard API response wrapper used by all convsim-core JSON endpoints. */
export interface ApiResponse<T> {
  data: T;
}

/** Standard API error response body. */
export interface ApiErrorResponse {
  error: ApiError;
}
