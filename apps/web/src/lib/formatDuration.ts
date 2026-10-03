// SPDX-License-Identifier: Apache-2.0
//
// Player-facing wait times. A turn on a CPU-only machine can run for minutes
// (docs/performance.md), so every duration the conversation screen shows has to
// read as well at three minutes as at three seconds.

/** "45s" / "2m 05s" — a wait long enough to show is long enough to read. */
export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

/**
 * The same thing, rounded to a grid the number deserves.
 *
 * An estimate is a median of a handful of turns, so printing "about 43s" claims
 * a precision it does not have — and the second digit changes between turns for
 * no reason the player can see. Round to the nearest second under ten seconds,
 * five seconds under a minute, and ten seconds beyond that.
 */
export function formatApproxDuration(ms: number): string {
  const safeMs = Math.max(0, ms)
  const grainMs = safeMs < 10_000 ? 1_000 : safeMs < 60_000 ? 5_000 : 10_000
  // Never round down to nothing: "about 0s" is not an estimate.
  const rounded = Math.max(grainMs, Math.round(safeMs / grainMs) * grainMs)
  return formatDuration(rounded)
}
