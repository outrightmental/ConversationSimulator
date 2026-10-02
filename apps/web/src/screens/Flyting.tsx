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
  // Newest first, matching the live ordering, so a reload does not silently
  // reverse the log a player was reading.
  return volleys
    .map((v, i) => ({
      key: `${v.speaker}-${v.scorecard?.volley_number ?? i}-${i}`,
      card: v.scorecard,
      text: v.text,
    }))
    .filter((entry) => entry.card != null)
    .reverse()
}

export default function Flyting() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const routeState = location.state as { umpireLabel?: string } | null

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

  // The shot clock. `promptedAt` is when the player became free to type; it
  // resets after every scored volley. `startedAt` is the whole run's clock,
  // which the timed drill is measured against.
  const promptedAt = useRef<number>(Date.now())
  const startedAt = useRef<number>(Date.now())
  const [clockLeft, setClockLeft] = useState<number | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const shotClockS = run?.shot_clock_s ?? 20
  const isBout = run?.play_format === 'bout'
  const isTimed = run?.batting_format === 'timed_90'
  const isEndless = run?.batting_format === 'endless'
  const umpireLabel = routeState?.umpireLabel || 'The umpire'

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
      setLog(logFromHistory(r.data.volleys))
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
  useEffect(() => {
    if (phase !== 'ready') {
      setClockLeft(null)
      return
    }
    function tick() {
      const sincePrompt = (Date.now() - promptedAt.current) / 1000
      setClockLeft(Math.max(0, shotClockS - sincePrompt))
      if (isTimed) {
        const sinceStart = (Date.now() - startedAt.current) / 1000
        setSecondsRemaining(Math.max(0, 90 - sinceStart))
      }
    }
    tick()
    const timer = window.setInterval(tick, 200)
    return () => window.clearInterval(timer)
  }, [phase, shotClockS, isTimed])

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
        elapsedSincePrompt,
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
      setVolleysRemaining(data.volleys_remaining)
      setWhiffsRemaining(data.whiffs_remaining)
      if (!isTimed) setSecondsRemaining(data.seconds_remaining)
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
    [sessionId, isTimed],
  )

  // The shot clock expiring is itself a submission: in Endless it is a whiff,
  // and the engine is the thing that decides that. Submitting the box as it
  // stands (even empty, which scores as a dud) keeps the rule in one place.
  useEffect(() => {
    if (phase !== 'ready' || clockLeft == null || clockLeft > 0) return
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
    const r = await api.flyting.endRun(sessionId)
    if (!r.ok) {
      setVolleyError(r.error)
      setEnding(false)
      return
    }
    navigate(`/flyting/debrief/${sessionId}`, { state: { umpireLabel } })
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
            <MomentumMeter momentum={run.momentum} winAt={85} />
            <Stat label="Round" value={run.round_number} />
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
              umpireLabel={umpireLabel}
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
      </div>
    </div>
  )
}
