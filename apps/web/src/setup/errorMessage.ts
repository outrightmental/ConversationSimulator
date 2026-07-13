// SPDX-License-Identifier: Apache-2.0
import type { ApiError } from '../api/errors'

/** Extract a human-readable string from an ApiError. */
export function errorMessage(err: ApiError | null): string {
  if (!err) return ''
  return err.message
}
