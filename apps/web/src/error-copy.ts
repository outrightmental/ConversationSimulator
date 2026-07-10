// SPDX-License-Identifier: Apache-2.0
// Error copy module — maps API error codes to localised user-facing messages.
// First file migrated to the i18n framework (issue #312).
// The error codes are defined in @convsim/shared-types; the copy lives here so
// it can be updated independently of the schema.

import type { TranslateFn } from './i18n'

const ERROR_KEYS: Record<string, string> = {
  SCHEMA_VALIDATION_ERROR: 'errors.schemaValidation',
  PACK_NOT_FOUND: 'errors.packNotFound',
  SCENARIO_NOT_FOUND: 'errors.scenarioNotFound',
  SESSION_NOT_FOUND: 'errors.sessionNotFound',
  MODEL_NOT_LOADED: 'errors.modelNotLoaded',
  RUNTIME_UNAVAILABLE: 'errors.runtimeUnavailable',
  SAFETY_VIOLATION: 'errors.safetyViolation',
  TURN_LIMIT_EXCEEDED: 'errors.turnLimitExceeded',
  TURN_TIMEOUT: 'errors.turnTimeout',
  INTERNAL_ERROR: 'errors.internalError',
  UNAUTHORIZED: 'errors.unauthorized',
}

/**
 * Returns a localised error message for the given API error code.
 * Falls back to `fallback` (if provided) or the generic "unknown error" message.
 */
export function getErrorMessage(
  t: TranslateFn,
  code: string | null | undefined,
  fallback?: string,
): string {
  const key = code != null ? ERROR_KEYS[code] : undefined
  return key != null ? t(key) : (fallback ?? t('errors.unknown'))
}
