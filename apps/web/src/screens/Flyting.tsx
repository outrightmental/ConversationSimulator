// SPDX-License-Identifier: Apache-2.0
//
// The play screen: one input, a shot clock, the meters that matter for the
// chosen format, and a scorecard for every volley as it is scored. The newest
// volley is at the top and fully expanded; everything behind it collapses to a
// compact row, because the only scorecard a player is reading is the one that
// just landed.
//
// The shot clock lives here rather than on the server: the server cannot see
// when the player was prompted. The elapsed times go up with the volley and
// the engine decides what they cost — a client that lied about its clock would
// only be cheating a local high-score table, and everything that affects the
// score itself is recomputed server-side regardless.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import type {
  FlytingRunState,
  FlytingVolleyLogEntry,
  RevealedAttackSurfaceTrait,
  VolleyScorecard as Scorecard,
} from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'
import VolleyScorecard from '../flyting/VolleyScorecard'
import {
  HeatMeter,
  MomentumMeter,
  ShotClock,
  Stat,
  Tag,
  formatLabel,
} from '../flyting/primitives'

const MAX_VOLLEY_CHARS = 500

/** One entry in the on-screen log: a scorecard plus the text it scored. */
interface LogEntry {
  key: string
  card: Scorecard
  text: string
  npcLine?: string | null
}

function logFromHistory(volleys: FlytingVolleyLogEntry[]): LogEntry[] {
  // Newest exchange first, matching the live ordering exactly — a reload must
  // not reorder the log a player was reading.
  //
  // "Newest first" is not a plain reverse. The engine writes an exchange as
  // player-then-opponent, and the live path puts the *player's* card at the top
  // of each exchange with the counter beneath it, because only index 0 renders
  // uncompacted and the player's own arithmetic is what they came to read. A
  // flat reverse would hand that slot to the opponent after a reload. So group
  // each player volley with the opponent volleys that answered it, reverse the
  // groups, and keep the order inside each one.
  const groups: LogEntry[][] = []
  for (const [i, v] of volleys.entries()) {
    if (v.scorecard == null) continue
    const entry: LogEntry = {
      key: `${v.speaker}-${v.scorecard.volley_number ?? i}-${i}`,
      card: v.scorecard,
      text: v.text,
    }
    // An opponent volley belongs to the exchange above it; anything arriving
    // before the first player volley opens its own group rather than being lost.
    if (v.speaker === 'npc' && groups.length > 0) {
      groups[groups.length - 1].push(entry)
    } else {
      groups.push([entry])
    }
  }
  return groups.reverse().flat()
}

export default function Flyting() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const routeState = location.state as { umpireFlavor?: string } | null

  const [run, setRun] = useState<FlytingRunState | null>(null)
  const [log, setLog] = useState<LogEntry[]>([])
  const [text, setText] = useState('')
  const [phase, setPhase] = useState<'loading' | 'ready' | 'scoring' | 'over' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [volleyError, setVolleyError] = useState<ApiError | null>(null)
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null)
  const [whiffsRemaining, setWhiffsRemaining] = useState<number | null>(null)
  const [volleysRemaining, setVolleysRemaining] = useState<number | null>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [ending, setEnding] = useState(false)
  // A bout's finish line and round count are the scenario's, not the engine's
  // defaults: a pack that sets momentum_win: 70 must not be drawn with the
  // marker at 85. They are not on the run state, so a bout reads them from its
  // scenario's setup payload — which also survives a reload, unlike route
  // state. A batting-practice run has no momentum, so it asks for nothing.
  const [bout, setBout] = useState<{ momentumWin: number; rounds: number } | null>(null)
  // The timed drill's length, from the same payload. The engine owns the number
  // (`limits.timed_seconds`) and is the thing that ends the run on it, so
  // hardcoding 90 here would put a second copy of a format rule in the UI, free
  // to drift from the one being enforced.
  const [timedSeconds, setTimedSeconds] = useState<number | null>(null)
  // The line the run opened on, and the target's surface as this run knows it.
  // The surface comes back with every volley rather than being read once at
  // mount: a discoverable trait is revealed the moment it is struck, and the
  // screen the player is looking at is where that has to show.
  const [opening, setOpening] = useState('')
  const [surface, setSurface] = useState<RevealedAttackSurfaceTrait[]>([])

  // The shot clock. `promptedAt` is when the player became free to type; it
  // resets after every scored volley. `startedAt` is the whole run's clock,
  // which the timed drill is measured against.
  const promptedAt = useRef<number>(Date.now())
  const startedAt = useRef<number>(Date.now())
  const [clockLeft, setClockLeft] = useState<number | null>(null)
  // Which prompt window the shot clock has already auto-submitted for. A
  // refused volley deliberately leaves the clock expired, so without this latch
  // the auto-submit below would fire again on the very next render — a retry
  // loop against the same rejection, not a shot clock.
  const autoSubmittedFor = useRef<number>(0)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const shotClockS = run?.shot_clock_s ?? 20
  const isBout = run?.play_format === 'bout'
  const isTimed = run?.batting_format === 'timed_90'
  const isEndless = run?.batting_format === 'endless'
  // The scenario's judge_flavor, carried through so the umpire's voice is
  // readable on each line. A character note, not a label — the scorecard shows
  // it as a tooltip rather than printing it inline.
  const umpireFlavor = routeState?.umpireFlavor

  // ── Load (or rehydrate) the run ────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    void api.flyting.getRun(sessionId).then((r) => {
      if (cancelled) return
      if (!r.ok) {
        setError(r.error)
        setPhase('error')
        return
      }
      setRun(r.data.run)
      const needsScenario =
        r.data.run.play_format === 'bout' || r.data.run.batting_format === 'timed_90'
      if (needsScenario) {
        void api.flyting.getScenario(r.data.scenario_id).then((sc) => {
          if (!cancelled && sc.ok) {
            setBout({ momentumWin: sc.data.bout.momentum_win, rounds: sc.data.bout.rounds })
            setTimedSeconds(sc.data.limits.timed_seconds)
          }
        })
      }
      setLog(logFromHistory(r.data.volleys))
      setOpening(r.data.opening)
      setSurface(r.data.target_surface)
      setSecondsRemaining(r.data.seconds_remaining)
      setWhiffsRemaining(r.data.whiffs_remaining)
      setVolleysRemaining(r.data.volleys_remaining)
      const done = r.data.run.outcome && r.data.run.outcome !== 'in_progress'
      setOutcome(done ? r.data.run.outcome : null)
      setPhase(done ? 'over' : 'ready')
      // A reloaded run restarts the shot clock rather than pretending to know
      // when the player last looked at the screen.
      promptedAt.current = Date.now()
      startedAt.current = Date.now() - (r.data.run.elapsed_s ?? 0) * 1000
    })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  // ── The ticking clocks ─────────────────────────────────────────────────────
  // The shot clock is a batting-practice mechanic — the drill is a reflex
  // exercise, which is what the clock is for. A bout is bounded by its rounds
  // and decided on momentum, so there is nothing for a clock to bound, and
  // force-submitting a dud would hand the opponent the exchange for the crime
  // of thinking about the reply.
  useEffect(() => {
    if (phase !== 'ready' || isBout) {
      setClockLeft(null)
      return
    }
    function tick() {
      const sincePrompt = (Date.now() - promptedAt.current) / 1000
      setClockLeft(Math.max(0, shotClockS - sincePrompt))
      // Until the payload arrives there is no authoritative length to count
      // down from, so the server's own `seconds_remaining` stands rather than a
      // guess that might end the drill early.
      if (isTimed && timedSeconds != null) {
        const sinceStart = (Date.now() - startedAt.current) / 1000
        setSecondsRemaining(Math.max(0, timedSeconds - sinceStart))
      }
    }
    tick()
    const timer = window.setInterval(tick, 200)
    return () => window.clearInterval(timer)
  }, [phase, shotClockS, isTimed, isBout, timedSeconds])

  useEffect(() => {
    if (phase === 'ready') inputRef.current?.focus()
  }, [phase, log.length])

  const submit = useCallback(
    async (content: string) => {
      if (!sessionId || !content.trim()) return
      setPhase('scoring')
      setVolleyError(null)
      const elapsedSincePrompt = (Date.now() - promptedAt.current) / 1000
      const elapsedTotal = (Date.now() - startedAt.current) / 1000
      const r = await api.flyting.submitVolley(
        sessionId,
        content,
        // No shot clock in a bout, so no reading to report: sending one would
        // ask the engine to rule on a clock this format does not run.
        isBout ? undefined : elapsedSincePrompt,
        elapsedTotal,
      )
      if (!r.ok) {
        setVolleyError(r.error)
        // A refused volley leaves the text in the box so the player can fix it
        // rather than retyping — but the clock has moved on, which is the cost.
        setPhase('ready')
        return
      }
      const data = r.data
      setText('')
      setRun(data.run)
      setSurface(data.target_surface)
      setVolleysRemaining(data.volleys_remaining)
      setWhiffsRemaining(data.whiffs_remaining)
      if (!isTimed || timedSeconds == null) setSecondsRemaining(data.seconds_remaining)
      setLog((prev) => {
        const next: LogEntry[] = []
        if (data.npc_volley) {
          next.push({
            key: `npc-${data.npc_volley.volley_number}`,
            card: data.npc_volley,
            text: data.npc_line ?? '',
          })
        }
        next.push({
          key: `player-${data.player_volley.volley_number}`,
          card: data.player_volley,
          text: content.trim(),
          npcLine: data.npc_volley ? null : data.npc_line,
        })
        return [...next.reverse(), ...prev]
      })
      promptedAt.current = Date.now()
      if (data.run_outcome) {
        setOutcome(data.run_outcome)
        setPhase('over')
      } else {
        setPhase('ready')
      }
    },
    [sessionId, isTimed, isBout, timedSeconds],
  )

  // The shot clock expiring is itself a submission: in Endless it is a whiff,
  // and the engine is the thing that decides that. Submitting the box as it
  // stands (even empty, which scores as a dud) keeps the rule in one place.
  // Once per prompt window only — `promptedAt` is what re-arms it, and it moves
  // only when a volley actually scored.
  useEffect(() => {
    if (phase !== 'ready' || clockLeft == null || clockLeft > 0) return
    if (autoSubmittedFor.current === promptedAt.current) return
    autoSubmittedFor.current = promptedAt.current
    void submit(text.trim() || '…')
  }, [clockLeft, phase, submit, text])

  // A timed drill ends when its own clock does, not when the player notices.
  useEffect(() => {
    if (!isTimed || phase !== 'ready' || secondsRemaining == null) return
    if (secondsRemaining <= 0) setPhase('over')
  }, [isTimed, phase, secondsRemaining])

  async function handleEnd() {
    if (!sessionId || ending) return
    setEnding(true)
    // The run clock goes up with the request: a timed drill finishes when its
    // ninety seconds pass with nobody typing, and this screen is the only thing
    // that watched them pass.
    const r = await api.flyting.endRun(sessionId, (Date.now() - startedAt.current) / 1000)
    if (!r.ok) {
      setVolleyError(r.error)
      setEnding(false)
      return
    }
    navigate(`/flyting/debrief/${sessionId}`, { state: { umpireFlavor } })
  }

  const remainingChars = MAX_VOLLEY_CHARS - text.length
  const wordCount = useMemo(
    () => text.trim().split(/\s+/).filter(Boolean).length,
    [text],
  )

  if (phase === 'loading') {
    return <div style={{ padding: '1.5rem', color: '#71717a' }}>Loading the run…</div>
  }

  if (phase === 'error' || !run) {
    return (
      <div style={{ padding: '1.5rem' }}>
        <ApiErrorView
          error={error ?? { kind: 'schema-mismatch', message: 'The run could not be read.' }}
          context="Flyting"
        />
      </div>
    )
  }

  return (
    <div style={{ padding: '1rem 1.25rem', display: 'grid', gap: '0.8rem', maxWidth: 880 }}>
      {/* Run header — the meters that matter for this format, and nothing else. */}
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: '1.25rem',
          flexWrap: 'wrap',
          padding: '0.7rem 0.9rem',
          border: '1px solid #27272a',
          borderRadius: 8,
          background: '#111113',
        }}
      >
        <Stat
          label={isBout ? 'Your points' : 'Session score'}
          value={isBout ? run.player_total : run.banked_total}
          accent="#a855f7"
          testId="run-total"
        />
        {isBout ? (
          <>
            <Stat label="Their points" value={run.npc_total} testId="npc-total" />
            {bout && <MomentumMeter momentum={run.momentum} winAt={bout.momentumWin} />}
            <Stat
              label="Round"
              value={bout ? `${run.round_number} / ${bout.rounds}` : run.round_number}
            />
          </>
        ) : (
          <>
            <HeatMeter heat={run.heat} />
            <Stat label="Best volley" value={run.best_volley_score} />
          </>
        )}
        {phase === 'ready' && clockLeft != null && (
          <ShotClock remaining={clockLeft} total={shotClockS} />
        )}
        {isTimed && secondsRemaining != null && (
          <Stat label="Time left" value={`${Math.ceil(secondsRemaining)}s`} testId="time-left" />
        )}
        {volleysRemaining != null && !isBout && (
          <Stat label="Volleys left" value={volleysRemaining} testId="volleys-left" />
        )}
        {isEndless && whiffsRemaining != null && (
          <Stat
            label="Whiffs left"
            value={whiffsRemaining}
            accent={whiffsRemaining <= 1 ? '#ef4444' : undefined}
            testId="whiffs-left"
          />
        )}
        <span style={{ flex: 1 }} />
        <Tag label={formatLabel(run.play_format, run.batting_format)} color="#a855f7" />
        {run.daily_seed != null && <Tag label="Daily seed" color="#38bdf8" />}
      </header>

      {/* What is fair game, as this run knows it. A discoverable trait appears
          here the volley after it is struck — the engine sends only what the
          run has revealed, so nothing hidden is in the page to be read. */}
      {surface.length > 0 && (
        <details data-testid="target-surface" style={{ fontSize: '0.8rem' }}>
          <summary style={{ cursor: 'pointer', color: '#a1a1aa' }}>
            What is fair game ({surface.length})
            {surface.some((t) => t.discovered) && (
              <span style={{ color: '#a855f7' }}> · one discovered</span>
            )}
          </summary>
          <ul
            style={{
              listStyle: 'none',
              margin: '0.4rem 0 0',
              padding: 0,
              display: 'grid',
              gap: '0.3rem',
            }}
          >
            {surface.map((trait) => (
              <li
                key={trait.id}
                data-testid={`surface-${trait.id}`}
                style={{ display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}
              >
                <Tag
                  label={trait.id.replace(/_/g, ' ')}
                  color={trait.discovered ? '#a855f7' : '#22c55e'}
                  title={trait.discovered ? 'You found this one' : undefined}
                />
                <span style={{ color: '#d4d4d8', lineHeight: 1.5 }}>{trait.brief}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {run.sudden_death && phase === 'ready' && (
        <p role="status" style={{ margin: 0, color: '#fcd34d', fontSize: '0.85rem', fontWeight: 600 }}>
          Sudden death. One volley decides it.
        </p>
      )}

      {/* The input. Disabled while scoring, gone once the run is over. */}
      {phase !== 'over' ? (
        <div style={{ display: 'grid', gap: '0.4rem' }}>
          <label htmlFor="volley-input" style={{ fontSize: '0.8rem', color: '#a1a1aa' }}>
            Your volley — one turn, one volley. Three words minimum; past sixty, length is taxed.
          </label>
          <textarea
            id="volley-input"
            ref={inputRef}
            data-testid="volley-input"
            value={text}
            maxLength={MAX_VOLLEY_CHARS}
            disabled={phase === 'scoring'}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void submit(text)
              }
            }}
            rows={3}
            placeholder="Let them have it…"
            style={{
              width: '100%',
              padding: '0.6rem 0.7rem',
              borderRadius: 6,
              border: '1px solid #3f3f46',
              background: '#09090b',
              color: '#f4f4f5',
              fontSize: '0.95rem',
              lineHeight: 1.5,
              resize: 'vertical',
              fontFamily: 'inherit',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
            <button
              type="button"
              onClick={() => void submit(text)}
              disabled={phase === 'scoring' || !text.trim()}
              data-testid="submit-volley"
              style={{
                padding: '0.4rem 1rem',
                borderRadius: 6,
                border: '1px solid rgba(168,85,247,0.5)',
                background: 'rgba(168,85,247,0.18)',
                color: '#e9d5ff',
                fontWeight: 600,
                fontSize: '0.85rem',
                cursor: phase === 'scoring' || !text.trim() ? 'default' : 'pointer',
                opacity: phase === 'scoring' || !text.trim() ? 0.5 : 1,
              }}
            >
              {phase === 'scoring' ? 'Scoring…' : 'Let fly'}
            </button>
            <span style={{ fontSize: '0.72rem', color: wordCount > 60 ? '#f59e0b' : '#71717a' }}>
              {wordCount} {wordCount === 1 ? 'word' : 'words'}
              {wordCount > 60 ? ' — past the soft cap' : ''} · {remainingChars} characters left
            </span>
            <span style={{ flex: 1 }} />
            <button
              type="button"
              onClick={() => void handleEnd()}
              style={{
                padding: '0.3rem 0.7rem',
                borderRadius: 6,
                border: '1px solid #3f3f46',
                background: 'transparent',
                color: '#a1a1aa',
                fontSize: '0.78rem',
                cursor: 'pointer',
              }}
            >
              Retire
            </button>
          </div>
        </div>
      ) : (
        <div
          role="status"
          data-testid="run-over"
          style={{
            padding: '0.8rem 1rem',
            borderRadius: 8,
            border: '1px solid rgba(168,85,247,0.4)',
            background: 'rgba(168,85,247,0.1)',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ color: '#e9d5ff', fontSize: '0.95rem', fontWeight: 600 }}>
            {outcome === 'momentum_win'
              ? 'The crowd carries you out on their shoulders.'
              : 'That is the run.'}
          </span>
          <button
            type="button"
            onClick={() => void handleEnd()}
            disabled={ending}
            data-testid="see-scorecard"
            style={{
              padding: '0.4rem 1rem',
              borderRadius: 6,
              border: '1px solid rgba(168,85,247,0.5)',
              background: 'rgba(168,85,247,0.2)',
              color: '#e9d5ff',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: ending ? 'default' : 'pointer',
            }}
          >
            {ending ? 'Tallying…' : 'See the scorecard'}
          </button>
        </div>
      )}

      {volleyError && <ApiErrorView error={volleyError} context="Flyting-volley" />}

      {/* The volley log. Newest expanded, the rest compact. */}
      <div style={{ display: 'grid', gap: '0.6rem' }} aria-label="Volley log" aria-live="polite">
        {log.map((entry, index) => (
          <div key={entry.key}>
            {entry.npcLine && (
              <p
                style={{
                  margin: '0 0 0.4rem',
                  fontSize: '0.85rem',
                  fontStyle: 'italic',
                  color: '#a1a1aa',
                }}
              >
                {entry.npcLine}
              </p>
            )}
            <VolleyScorecard
              card={entry.card}
              text={entry.text}
              umpireFlavor={umpireFlavor}
              defaultOpen={index === 0}
              compact={index > 0}
            />
          </div>
        ))}
        {log.length === 0 && (
          <p style={{ color: '#71717a', fontSize: '0.85rem', margin: 0 }}>
            No volleys yet. The clock is running.
          </p>
        )}
        {/* The scenario's opening line, at the foot of a newest-first log —
            the oldest thing said in the room, and in a bout the line the first
            volley answers. */}
        {opening && (
          <p
            data-testid="run-opening"
            style={{
              margin: 0,
              fontSize: '0.85rem',
              fontStyle: 'italic',
              color: '#a1a1aa',
              lineHeight: 1.6,
            }}
          >
            {opening}
          </p>
        )}
      </div>
    </div>
  )
}
