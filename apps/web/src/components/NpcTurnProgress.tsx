// SPDX-License-Identifier: Apache-2.0
import type { CSSProperties } from 'react'
import { formatApproxDuration, formatDuration, roundApproxDuration } from '../lib/formatDuration'

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
  /** True while the NPC is out. False between turns: the panel draws nothing,
   *  but its live regions stay mounted — see the accessibility note below. */
  active: boolean
  /** How long the current turn has been out. */
  elapsedMs: number
  /** Expected turn length for this machine, or null before any turn was timed. */
  estimateMs: number | null
  /** True once tokens are arriving. The turn is not finished — the estimate
   *  covers the whole round trip — but the NPC is visibly speaking rather than
   *  thinking, and the transcript is already announcing the words. */
  streaming?: boolean
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
 * Once tokens start arriving the heading says the NPC is replying rather than
 * thinking: the estimate still covers the whole round trip, but a panel claiming
 * the NPC is thinking under a reply being typed out is simply wrong.
 *
 * Accessibility: everything the panel draws changes every second, so all of it
 * is hidden from assistive tech and two sr-only live regions carry the news
 * instead — one with the status phrase and the estimate (this panel is the only
 * thing on screen saying the NPC is working, and the estimate is what issue #488
 * asked for), one with the elapsed time on a 30 s grid. Both are rendered
 * whether or not a turn is out, with empty text between turns: a live region
 * created in the same breath as its text is not reliably announced, and the line
 * this panel replaced was announced by the transcript's own always-present
 * region. MicButton's recording status works the same way. The bar keeps its
 * progressbar role and value for anyone who navigates to it deliberately.
 */
export default function NpcTurnProgress({
  active,
  elapsedMs,
  estimateMs,
  streaming = false,
}: NpcTurnProgressProps) {
  const hasEstimate = estimateMs !== null && estimateMs > 0
  // The panel compares against the estimate as *quoted*, not the raw median
  // behind it. A median of 87 s is quoted as "1m 30s", and judged against the
  // median the clock turns amber at 1m 28s under the caption "longer than the
  // usual 1m 30s"; at 29 s the 30 s announcement reads "30s, longer than the
  // usual 30s". The player can only check the figure they were given, so that
  // is the figure every verdict here is made against.
  const quotedEstimateMs = hasEstimate ? roundApproxDuration(estimateMs) : 0
  const overrun = hasEstimate && elapsedMs > quotedEstimateMs
  const fillPercent = hasEstimate
    ? Math.min(MAX_FILL_PERCENT, Math.round((elapsedMs / quotedEstimateMs) * 100))
    : 0
  const remainingMs = hasEstimate ? Math.max(0, quotedEstimateMs - elapsedMs) : 0

  const elapsedText = formatDuration(elapsedMs)
  const estimateText = hasEstimate ? formatDuration(quotedEstimateMs) : ''
  const phrase = streaming ? 'NPC is replying…' : 'NPC is thinking…'

  // What the player reads next to the clock: a countdown while the turn is
  // tracking the estimate, and plain honesty once it is not.
  const detail = !hasEstimate
    ? 'Timing this turn so the next one can be estimated.'
    : overrun
      ? `Longer than the usual ${estimateText} on this machine — the reply is not lost.`
      : `About ${formatApproxDuration(remainingMs)} to go, based on recent turns (usually ${estimateText}).`

  // The announced status. It changes at most once per turn (thinking → replying),
  // unlike the clock, and carries the estimate because the clock and caption
  // that show it visually are both hidden.
  const statusText = !active
    ? ''
    : hasEstimate
      ? `${phrase} Usually about ${estimateText} on this machine.`
      : `${phrase} No turn has been timed on this machine yet.`

  // Nothing to announce once the words are arriving: the transcript is a polite
  // live region, so it is already reading the reply out, and "still waiting"
  // over the top of it contradicts what the player is hearing.
  const announcedElapsedMs = Math.floor(elapsedMs / ANNOUNCE_INTERVAL_MS) * ANNOUNCE_INTERVAL_MS
  // "1m 00s of about 30s" would be left to arithmetic to notice what the amber
  // caption says outright. Decided on the announced figure rather than the live
  // one, so the wording still only changes on the grid: judged against the
  // ticking clock it would flip mid-interval and read "30s, longer than the
  // usual 45s". Against the quoted estimate for the same reason as above: a
  // median of 29 s is quoted as "30s", and the raw median makes the very first
  // announcement read "30s, longer than the usual 30s".
  const announcedOverrun = hasEstimate && announcedElapsedMs > quotedEstimateMs
  const announcementText =
    !active || streaming || elapsedMs < FIRST_ANNOUNCE_MS
      ? ''
      : announcedOverrun
        ? `Still waiting on the NPC — ${formatDuration(announcedElapsedMs)}, longer than the usual ${estimateText}. The reply is not lost.`
        : hasEstimate
          ? `Still waiting on the NPC — ${formatDuration(announcedElapsedMs)} of about ${estimateText}. The reply is not lost.`
          : `Still waiting on the NPC — ${formatDuration(announcedElapsedMs)} so far. The reply is not lost.`

  return (
    <>
      {/* Mounted for the whole screen, not just the turn: see the note above. */}
      <span data-testid="npc-turn-progress-status" role="status" style={srOnly}>
        {statusText}
      </span>
      <span
        data-testid="npc-turn-progress-announcement"
        role="status"
        aria-live="polite"
        style={srOnly}
      >
        {announcementText}
      </span>

      {active && (
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
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: '0.75rem',
              fontSize: '0.8rem',
              color: 'var(--cs-text-muted, #a1a1aa)',
            }}
          >
            {/* Hidden like the rest of the panel: the sr-only status above says
                the same thing, and says it without waiting for a mutation to a
                region that did not exist a moment ago. */}
            <span data-testid="npc-turn-progress-heading" aria-hidden="true">
              {phrase}
            </span>
            <span
              data-testid="npc-turn-progress-clock"
              aria-hidden="true"
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
            // Muted, not faint: this caption is the answer to "how long?", and
            // --cs-text-faint at 12px lands at 3.7:1 on --cs-raise (see the AA note
            // in ScenarioSetup.css), short of the 4.5:1 body text needs.
            style={{ fontSize: '0.75rem', color: 'var(--cs-text-muted, #a1a1aa)' }}
          >
            {detail}
          </div>
        </div>
      )}
    </>
  )
}
