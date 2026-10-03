// SPDX-License-Identifier: Apache-2.0
import type { CSSProperties } from 'react'
import { formatApproxDuration, formatDuration } from '../lib/formatDuration'

// The elapsed wait is read out on this coarser grid. The visible clock ticks
// every second, but a polite live region re-announces on every text change, and
// 270 announcements over a five-minute turn drowns out everything else — so the
// screen-reader copy only changes once per interval.
const ANNOUNCE_INTERVAL_MS = 30_000
// Nothing is announced before the first interval: a turn that finishes in a few
// seconds needs no commentary at all.
const FIRST_ANNOUNCE_MS = ANNOUNCE_INTERVAL_MS
// The bar stops short of full while the turn is still out. A bar sitting at 100%
// with nothing on screen reads as a finished turn the app failed to show.
const MAX_FILL_PERCENT = 95

const srOnly: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0,0,0,0)',
  whiteSpace: 'nowrap',
  border: 0,
}

export interface NpcTurnProgressProps {
  /** How long the current turn has been out. */
  elapsedMs: number
  /** Expected turn length for this machine, or null before any turn was timed. */
  estimateMs: number | null
}

/**
 * The work-time estimate shown while the NPC is thinking (issue #488).
 *
 * A local model gives no progress signal to report — no token count, no percent
 * complete — so the only honest measure is the clock plus what turns on this
 * machine have cost before. Both are shown: the elapsed time (so the app never
 * looks frozen), and, once a turn has been timed, how long this one is expected
 * to take and how far through that it is.
 *
 * Accessibility: the visible clock ticks every second, so it is hidden from
 * assistive tech and a single polite live region carries the same news on a 30 s
 * grid. The bar keeps its progressbar role and value for anyone who navigates to
 * it deliberately.
 */
export default function NpcTurnProgress({ elapsedMs, estimateMs }: NpcTurnProgressProps) {
  const hasEstimate = estimateMs !== null && estimateMs > 0
  const overrun = hasEstimate && elapsedMs > estimateMs
  const fillPercent = hasEstimate
    ? Math.min(MAX_FILL_PERCENT, Math.round((elapsedMs / estimateMs) * 100))
    : 0
  const remainingMs = hasEstimate ? Math.max(0, estimateMs - elapsedMs) : 0

  const elapsedText = formatDuration(elapsedMs)
  const estimateText = hasEstimate ? formatApproxDuration(estimateMs) : ''

  // What the player reads next to the clock: a countdown while the turn is
  // tracking the estimate, and plain honesty once it is not.
  const detail = !hasEstimate
    ? 'Timing this turn so the next one can be estimated.'
    : overrun
      ? `Longer than the usual ${estimateText} on this machine — the reply is not lost.`
      : `About ${formatApproxDuration(remainingMs)} to go, based on recent turns (usually ${estimateText}).`

  const announcedElapsedMs = Math.floor(elapsedMs / ANNOUNCE_INTERVAL_MS) * ANNOUNCE_INTERVAL_MS

  return (
    <div
      data-testid="npc-turn-progress"
      style={{
        padding: '0.6rem 0.75rem',
        borderRadius: 8,
        border: '1px solid var(--cs-border, #27272a)',
        background: 'var(--cs-raise, #18181b)',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.4rem',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          gap: '0.75rem',
          fontSize: '0.8rem',
          color: 'var(--cs-text-muted, #a1a1aa)',
        }}
      >
        <span>NPC is thinking…</span>
        <span
          data-testid="npc-turn-progress-clock"
          style={{
            fontVariantNumeric: 'tabular-nums',
            color: overrun ? 'var(--cs-event, #fbbf24)' : 'var(--cs-text, #e8e8ea)',
          }}
        >
          {hasEstimate ? `${elapsedText} / ~${estimateText}` : elapsedText}
        </span>
      </div>

      <div
        role="progressbar"
        aria-label="NPC response progress"
        // An indeterminate bar (no turn timed yet) deliberately reports no value:
        // claiming 0% of an unknown total would be a guess dressed as a fact.
        {...(hasEstimate
          ? {
              'aria-valuemin': 0,
              'aria-valuemax': 100,
              'aria-valuenow': fillPercent,
              'aria-valuetext': overrun
                ? `${elapsedText} elapsed, longer than the usual ${estimateText}`
                : `${elapsedText} elapsed of about ${estimateText}`,
            }
          : {})}
        style={{
          height: 6,
          borderRadius: 3,
          background: 'var(--cs-border, #27272a)',
          overflow: 'hidden',
        }}
      >
        <div
          data-testid="npc-turn-progress-fill"
          aria-hidden="true"
          style={{
            width: hasEstimate ? `${fillPercent}%` : '100%',
            height: '100%',
            borderRadius: 3,
            ...(hasEstimate
              ? { background: overrun ? 'var(--cs-event, #fbbf24)' : 'var(--cs-them-deep, #10b981)' }
              : {
                  // Indeterminate: there is no fraction to draw, so the track is
                  // hatched rather than filled. An empty bar would read as "no
                  // progress" and a full one as "done"; neither is true, and the
                  // app animates nothing (nothing else here does either).
                  background:
                    'repeating-linear-gradient(135deg, var(--cs-border, #27272a) 0 6px, var(--cs-raise, #18181b) 6px 12px)',
                }),
          }}
        />
      </div>

      <div
        data-testid="npc-turn-progress-detail"
        aria-hidden="true"
        style={{ fontSize: '0.75rem', color: 'var(--cs-text-faint, #71717a)' }}
      >
        {detail}
      </div>

      {elapsedMs >= FIRST_ANNOUNCE_MS && (
        <span data-testid="npc-turn-progress-announcement" role="status" aria-live="polite" style={srOnly}>
          {hasEstimate
            ? `Still waiting on the NPC — ${formatDuration(announcedElapsedMs)} of about ${estimateText}. The reply is not lost.`
            : `Still waiting on the NPC — ${formatDuration(announcedElapsedMs)} so far. The reply is not lost.`}
        </span>
      )}
    </div>
  )
}
