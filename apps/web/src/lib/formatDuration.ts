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
 * An estimate rounded to the grid it deserves to be quoted on, in milliseconds.
 *
 * An estimate is a median of a handful of turns, so printing "about 43s" claims
 * a precision it does not have — and the second digit changes between turns for
 * no reason the player can see. Round to the nearest second under ten seconds,
 * five seconds under a minute, and ten seconds beyond that.
 *
 * Exported as a number, not only as formatted text, so a caller that quotes the
 * rounded figure can also *compare* against it. Deciding "longer than usual"
 * against the raw median while quoting the rounded one makes the panel
 * contradict itself: a 43 s median is quoted as "45s" but turns amber at 44 s.
 */
export function roundApproxDuration(ms: number): number {
  const safeMs = Math.max(0, ms)
  const grainMs = safeMs < 10_000 ? 1_000 : safeMs < 60_000 ? 5_000 : 10_000
  // Never round down to nothing: "about 0s" is not an estimate.
  return Math.max(grainMs, Math.round(safeMs / grainMs) * grainMs)
}

/** The same thing as `formatDuration`, on the grid `roundApproxDuration` sets. */
export function formatApproxDuration(ms: number): string {
  return formatDuration(roundApproxDuration(ms))
}
