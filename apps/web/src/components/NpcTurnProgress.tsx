// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { TurnStage } from '@convsim/shared'
import { formatApproxDuration, formatDuration, roundApproxDuration } from '../lib/formatDuration'
import { useTranslation } from '../i18n'
import { useReducedMotion } from '../hooks/useReducedMotion'

// The elapsed wait is read out on this coarser grid. The visible clock ticks
// every second, but a polite live region re-announces on every text change, and
// 270 announcements over a five-minute turn drowns out everything else — so the
// screen-reader copy only changes once per interval.
const ANNOUNCE_INTERVAL_MS = 30_000
// Nothing is announced before the first interval: a turn that finishes in a few
// seconds needs no commentary at all.
const FIRST_ANNOUNCE_MS = ANNOUNCE_INTERVAL_MS
// The time-based bar stops short of full while the turn is still out. A bar
// sitting at 100% with nothing on screen reads as a finished turn the app
// failed to show. The reading bar is exempt: it measures tokens, and reading
// really does finish before the first word.
const MAX_FILL_PERCENT = 95
// Once a wait has run this long, the panel adds its one footnote: where the
// next replies can be made shorter (issue #501 §1). Before that a turn is
// simply a turn; after it a player may start looking for a speed setting, and
// the footnote names the one that exists so nobody leaves the turn to hunt.
const SPEED_HINT_MS = 5_000

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

export interface TurnProgressPrompt {
  processed: number | null
  total: number | null
  cached: number | null
}

export interface NpcTurnProgressProps {
  /** True while the NPC is out. False between turns: the panel draws nothing,
   *  but its live regions stay mounted — see the accessibility note below. */
  active: boolean
  /** How long the current turn has been out. */
  elapsedMs: number
  /** Expected whole-turn length for this machine (PR #513), or null before any
   *  turn was timed. Used only when no stage events arrive (no socket). */
  estimateMs: number | null
  /** True once words are arriving. */
  streaming?: boolean
  /** The character's name when the pack gives one. "NPC" never appears. */
  npcName?: string | null
  /** The stage the core says the turn is in (issue #539), or null when no
   *  socket is delivering stage events. */
  stage?: TurnStage | null
  /** The engine's prompt-reading progress, when it reports one. */
  prompt?: TurnProgressPrompt | null
  /** When the reply is expected to start, as a range, or null when there is
   *  nothing honest to say (no data, under the threshold, or already streaming). */
  replyStart?: { lowMs: number; highMs: number } | null
  /** True once the turn has landed and the session is back at the player:
   *  announced once as "Your turn." */
  yourTurn?: boolean
  /** True in the demo edition, whose model is fixed and whose Settings has no
   *  engine panel. The slow footnote then also offers the one hardware lever
   *  that edition has: closing other apps. */
  demo?: boolean
}

/**
 * What the turn is doing while the player waits (issues #488, #539).
 *
 * With stage events from the core the panel says which stage the turn is in,
 * in the fiction and with the character's name, draws the one real bar there
 * is — prompt tokens read of total, with the cached share already filled — and
 * quotes when the reply will *start*, as a range, only when the expected wait
 * is worth a number. Once words stream there is no estimate: the transcript
 * is the progress.
 *
 * Without stage events (no socket), the PR #513 behaviour stands unchanged: the
 * clock, the median of recent whole turns, and plain honesty when the turn
 * outruns it.
 *
 * Once a wait passes five seconds the panel adds one footnote, from issue
 * #501: the next replies can be made shorter under Reply speed, in Settings,
 * once this one arrives. It is text and never a link, because leaving the
 * screen mid-turn loses the pending message on resume. It says nothing about
 * the wait itself; the heading and the half-minute announcement already do.
 *
 * Accessibility: everything the panel draws changes every second, so all of it
 * is hidden from assistive tech and three sr-only live regions carry the news
 * instead. One has the stage phrase and the estimate as that stage began (it
 * changes when the stage does, never with a progress report); one has the
 * elapsed time on a 30 s grid, with the current estimate while the turn is
 * still getting ready or reading; one has the
 * reply-speed footnote from five seconds on. Nothing is announced about the
 * wait while the reply streams, since the transcript's live region is already
 * reading it, and "Your turn." is announced at commit. All three regions are
 * rendered whether or not a turn is out, with empty text between turns: a
 * live region created in the same breath as its text is not reliably
 * announced. During a wait, focus rests on the panel so a controller's next
 * press does not leave the conversation.
 */
export default function NpcTurnProgress({
  active,
  elapsedMs,
  estimateMs,
  streaming = false,
  npcName = null,
  stage = null,
  prompt = null,
  replyStart = null,
  yourTurn = false,
  demo = false,
}: NpcTurnProgressProps) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const panelRef = useRef<HTMLDivElement>(null)

  // Focus rests here while the turn is out (issue #539): the control that held
  // focus is disabled, so without this a gamepad's next press leaves the page.
  useEffect(() => {
    if (active) panelRef.current?.focus({ preventScroll: true })
  }, [active])

  const name = npcName?.trim() || null
  // Seconds under a minute and minutes from a minute on, the grid
  // replyStartRange rounds to: "about 1–2 min", never "about 86–135 s".
  const replyStartCopy = ({ lowMs, highMs }: { lowMs: number; highMs: number }): string => {
    const seconds = (ms: number) => Math.round(ms / 1000)
    const minutes = (ms: number) => Math.max(1, Math.round(ms / 60_000))
    if (highMs < 60_000) return t('turnProgress.replyStartsInSeconds', { low: seconds(lowMs), high: seconds(highMs) })
    if (lowMs >= 60_000) return t('turnProgress.replyStartsInMinutes', { low: minutes(lowMs), high: minutes(highMs) })
    return t('turnProgress.replyStartsInSecondsToMinutes', { low: seconds(lowMs), high: minutes(highMs) })
  }
  const phraseFor = (s: TurnStage): string =>
    name ? t(`turnProgress.named.${s}`, { name }) : t(`turnProgress.unnamed.${s}`)

  // With stage events the core is the authority; without them, fall back to
  // the two phrases PR #513 had: thinking until words arrive, replying after.
  const liveStage: TurnStage = stage ?? (streaming ? 'writing' : 'reading')
  const phrase = phraseFor(liveStage)
  const hasStages = stage !== null

  // ── The reading bar: the one real fraction a turn has ───────────────────
  const promptTotal = prompt?.total ?? null
  const promptProcessed = prompt?.processed ?? null
  const hasReadingBar =
    hasStages && stage === 'reading' && promptTotal !== null && promptTotal > 0 && promptProcessed !== null
  const readPercent = hasReadingBar
    ? Math.max(0, Math.min(100, Math.round((promptProcessed! / promptTotal!) * 100)))
    : 0
  const cachedPercent = hasReadingBar && prompt?.cached
    ? Math.max(0, Math.min(readPercent, Math.round((prompt.cached / promptTotal!) * 100)))
    : 0

  // ── PR #513's whole-turn estimate, for the no-socket case only ─────────
  const hasEstimate = !hasStages && estimateMs !== null && estimateMs > 0
  // The panel compares against the estimate as *quoted*, not the raw median:
  // the player can only check the figure they were given.
  const quotedEstimateMs = hasEstimate ? roundApproxDuration(estimateMs) : 0
  const overrun = hasEstimate && elapsedMs > quotedEstimateMs
  const fillPercent = hasEstimate
    ? Math.max(0, Math.min(MAX_FILL_PERCENT, Math.round((elapsedMs / quotedEstimateMs) * 100)))
    : 0
  const remainingMs = hasEstimate ? Math.max(0, quotedEstimateMs - elapsedMs) : 0

  const elapsedText = formatDuration(elapsedMs)
  const estimateText = hasEstimate ? formatDuration(quotedEstimateMs) : ''

  // ── Captions ───────────────────────────────────────────────────────────
  // A reply-start estimate only means something while the engine has yet to
  // start the reply: getting ready or reading. Once words stream the
  // transcript is the progress, and checking is a second, unstreamed try that
  // no figure describes. The screen already passes none then; the panel holds
  // to the same rule itself, because the announcements below keep a figure
  // sampled earlier and would otherwise carry it into a later stage.
  const estimateCanApply = hasStages && !streaming && (liveStage === 'waiting' || liveStage === 'reading')
  const replyStartText = estimateCanApply && replyStart ? replyStartCopy(replyStart) : ''
  const detail = hasStages
    ? replyStartText
    : !hasEstimate
      ? t('turnProgress.timingThisTurn')
      : overrun
        ? t('turnProgress.longerThanUsual', { estimate: estimateText })
        : t('turnProgress.toGo', { remaining: formatApproxDuration(remainingMs), estimate: estimateText })

  // The caption above follows every progress report and every tick of the
  // clock, and it is hidden from assistive tech. A live region that did the
  // same would read the whole phrase out again on every batch of prompt the
  // engine reports, several times a wait. So what is announced is sampled:
  // the status takes the estimate as it stood when the stage began (or when
  // one first existed in that stage) and keeps it until the stage changes,
  // and the half-minute announcement takes it as it stands on that grid.
  const stageKey: TurnStage | null = active && hasStages ? liveStage : null
  const [heardInStage, setHeardInStage] = useState<{ stage: TurnStage | null; text: string }>({ stage: null, text: '' })
  const stageHasChanged = heardInStage.stage !== stageKey
  const stageEstimateText = stageHasChanged || heardInStage.text === '' ? replyStartText : heardInStage.text
  // Updating state during render is React's pattern for keeping a value from
  // an earlier render: the render is redone before anything is committed, so
  // the live region never shows the unsampled text.
  if (stageHasChanged || heardInStage.text !== stageEstimateText) {
    setHeardInStage({ stage: stageKey, text: stageEstimateText })
  }
  const announceSlot = active ? Math.floor(elapsedMs / ANNOUNCE_INTERVAL_MS) : -1
  const [heardInSlot, setHeardInSlot] = useState<{ slot: number; text: string }>({ slot: -1, text: '' })
  const slotEstimateText = heardInSlot.slot === announceSlot ? heardInSlot.text : replyStartText
  if (heardInSlot.slot !== announceSlot) setHeardInSlot({ slot: announceSlot, text: replyStartText })

  // The announced status: the stage and the estimate as the stage began, and
  // "Your turn." when the turn lands. It changes when the stage does, never
  // with a progress report.
  const statusText = active
    ? hasStages
      ? [phrase, stageEstimateText].filter(Boolean).join(' ')
      : hasEstimate
        ? t('turnProgress.statusWithEstimate', { phrase, estimate: estimateText })
        : t('turnProgress.statusNoEstimate', { phrase })
    : yourTurn
      ? t('turnProgress.yourTurn')
      : ''

  // Nothing to announce once the words are arriving: the transcript is a polite
  // live region, so it is already reading the reply out.
  const announcedElapsedMs = Math.floor(elapsedMs / ANNOUNCE_INTERVAL_MS) * ANNOUNCE_INTERVAL_MS
  const announcedOverrun = hasEstimate && announcedElapsedMs > quotedEstimateMs
  const announcedElapsedText = formatDuration(announcedElapsedMs)
  const suffix = name ? 'Named' : 'Unnamed'
  const elapsedAnnouncement =
    !active || streaming || liveStage === 'writing' || elapsedMs < FIRST_ANNOUNCE_MS
      ? ''
      : announcedOverrun
        ? t(`turnProgress.stillWaitingLonger${suffix}`, { name: name ?? '', elapsed: announcedElapsedText, estimate: estimateText })
        : hasEstimate
          ? t(`turnProgress.stillWaitingOf${suffix}`, { name: name ?? '', elapsed: announcedElapsedText, estimate: estimateText })
          : t(`turnProgress.stillWaiting${suffix}`, { name: name ?? '', elapsed: announcedElapsedText })
  // The estimate rides along on the same half-minute grid, so a long wait
  // hears an up-to-date figure without hearing one per progress report. The
  // figure was sampled when the slot began, so it is dropped once the turn
  // has moved on to a stage no estimate applies to: reading, then writing,
  // then checking can all fall within one half-minute.
  const announcementText = elapsedAnnouncement
    ? [elapsedAnnouncement, estimateCanApply ? slotEstimateText : ''].filter(Boolean).join(' ')
    : ''

  const indeterminate = !hasReadingBar && !hasEstimate
  const barValue = hasReadingBar ? readPercent : fillPercent
  const barValueText = hasReadingBar
    ? t('turnProgress.readingProgress', { percent: readPercent })
    : overrun
      ? t('turnProgress.elapsedLonger', { elapsed: elapsedText, estimate: estimateText })
      : t('turnProgress.elapsedOf', { elapsed: elapsedText, estimate: estimateText })

  const fillTransition = reduceMotion ? 'none' : 'width 300ms ease'
  // Judged on the clock the player sees, whether or not words have started: a
  // long reply is exactly what Reply speed shortens.
  const showSpeedHint = elapsedMs >= SPEED_HINT_MS
  const speedHintText =
    active && showSpeedHint
      ? [demo ? t('turnProgress.closeOtherApps') : '', t('turnProgress.speedHint')].filter(Boolean).join(' ')
      : ''

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
      <span data-testid="npc-turn-progress-hint" role="status" style={srOnly}>
        {speedHintText}
      </span>

      {active && (
        <div
          ref={panelRef}
          tabIndex={-1}
          data-testid="npc-turn-progress"
          data-stage={liveStage}
          style={{
            padding: '0.6rem 0.75rem',
            borderRadius: 8,
            border: '1px solid var(--cs-border, #27272a)',
            background: 'var(--cs-raise, #18181b)',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.4rem',
            outline: 'none',
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
            aria-label={t('turnProgress.progressLabel')}
            // An indeterminate bar deliberately reports no value: claiming 0%
            // of an unknown total would be a guess dressed as a fact.
            {...(!indeterminate
              ? {
                  'aria-valuemin': 0,
                  'aria-valuemax': 100,
                  'aria-valuenow': barValue,
                  'aria-valuetext': barValueText,
                }
              : {})}
            style={{
              position: 'relative',
              height: 6,
              borderRadius: 3,
              background: 'var(--cs-border, #27272a)',
              overflow: 'hidden',
            }}
          >
            {hasReadingBar && cachedPercent > 0 && (
              // The share of the prompt the engine already had in its cache: it
              // starts filled, because that part is not being read again.
              <div
                data-testid="npc-turn-progress-cached"
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  width: `${cachedPercent}%`,
                  height: '100%',
                  background: 'var(--cs-text-faint, #71717a)',
                }}
              />
            )}
            <div
              // A new element when the bar changes mode. The hatch is drawn at
              // full width, and a transition runs from the old width to the
              // new one: reusing the element made every reading stage open
              // with a full bar sweeping back to the share read so far.
              key={indeterminate ? 'hatch' : 'fill'}
              data-testid="npc-turn-progress-fill"
              aria-hidden="true"
              style={{
                position: 'relative',
                width: indeterminate ? '100%' : `${barValue}%`,
                height: '100%',
                borderRadius: 3,
                transition: indeterminate ? 'none' : fillTransition,
                ...(!indeterminate
                  ? {
                      background: overrun
                        ? 'var(--cs-event, #fbbf24)'
                        : 'var(--cs-them-deep, #10b981)',
                    }
                  : {
                      // Indeterminate: there is no fraction to draw, so the track is
                      // hatched rather than filled. An empty bar would read as "no
                      // progress" and a full one as "done"; neither is true, and the
                      // app animates nothing. Striped in --cs-text-faint, which is
                      // 3.1:1 against the --cs-border track and clears the 3:1 floor
                      // a non-text graphic needs. Grey, not emerald: a visible hatch
                      // in the fill colour would read as progress.
                      background:
                        'repeating-linear-gradient(135deg, var(--cs-text-faint, #71717a) 0 4px, var(--cs-border, #27272a) 4px 10px)',
                    }),
              }}
            />
          </div>

          {detail && (
            <div
              data-testid="npc-turn-progress-detail"
              aria-hidden="true"
              // Muted, not faint: this caption is the answer to "how long?", and
              // --cs-text-faint at 12px lands at 3.7:1 on --cs-raise, short of
              // the 4.5:1 body text needs.
              style={{ fontSize: '0.75rem', color: 'var(--cs-text-muted, #a1a1aa)' }}
            >
              {detail}
            </div>
          )}

          {showSpeedHint && (
            // The moment the player actually wants the speed setting is this
            // one. Before #501 the slow notice said "you can adjust settings"
            // and left them to find out which: the detour that lost a
            // playtester their session. So it names the setting, as text and
            // not a link: this footnote only exists while a turn is in flight,
            // and convsim-core keeps the session in PlayerTurnListening until
            // the reply commits, so leaving now and resuming would rebuild the
            // screen without the pending message, re-enable the composer, and
            // number the next exchange one behind the server (issue #501 §4).
            // The demo gets the same sentence: its model is fixed, so reply
            // speed is the one lever it has, plus the one thing its hardware
            // can do. The test ids are the ones the #501 tests were written
            // against; the sentence moved, its meaning did not.
            // Hidden like the rest of the panel: the sr-only hint region above
            // carries the same sentence, and was mounted before it had any.
            <div
              data-testid="slow-response-indicator"
              aria-hidden="true"
              style={{ fontSize: '0.75rem', color: 'var(--cs-text-muted, #a1a1aa)' }}
            >
              {demo && <>{t('turnProgress.closeOtherApps')} </>}
              <span data-testid="slow-response-speed-hint">{t('turnProgress.speedHint')}</span>
            </div>
          )}
        </div>
      )}
    </>
  )
}
