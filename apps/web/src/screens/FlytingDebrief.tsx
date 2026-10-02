// SPDX-License-Identifier: Apache-2.0
//
// The flyting debrief: what the run was worth, and what to do differently.
//
// Every number here is an aggregate the engine computed over the volley log —
// nothing is recomputed in the browser, because the debrief and the live
// scorecards have to agree to the point. The sections are the ones issue #454
// asks for: the best volley, the redundancy report (a theme's value visibly
// decaying as you return to it), the rarest words that landed, the device
// histogram, and coaching notes read off the log rather than from a second
// model call.
//
// Ending a run is idempotent on the server — one board row per run, updated in
// place — so reloading this screen is safe and a reopened debrief neither
// doubles the run on the board nor inflates any later run's rank.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import type {
  FlytingHighScore,
  FlytingRunSummary,
  FlytingVolleyLogEntry,
} from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'
import HighScoreTable from '../flyting/HighScoreTable'
import VolleyScorecard from '../flyting/VolleyScorecard'
import {
  bandColor,
  bandLabel,
  foulLabel,
  formatLabel,
  outcomeLabel,
  ScoreBar,
  Stat,
  Tag,
} from '../flyting/primitives'

function Section({
  title,
  hint,
  children,
  testId,
}: {
  title: string
  hint?: string
  children: React.ReactNode
  testId?: string
}) {
  return (
    <section
      data-testid={testId}
      style={{
        border: '1px solid #27272a',
        borderRadius: 8,
        padding: '0.85rem 1rem',
        background: '#111113',
      }}
    >
      <h2 style={{ fontSize: '0.95rem', margin: '0 0 0.15rem', color: '#f4f4f5' }}>{title}</h2>
      {hint && <p style={{ fontSize: '0.78rem', color: '#71717a', margin: '0 0 0.6rem' }}>{hint}</p>}
      {children}
    </section>
  )
}

/**
 * The redundancy report. The point is not that a theme was reused — it is what
 * the *next* use would be worth, which is the number that changes behaviour.
 */
function ThemeReport({ summary }: { summary: FlytingRunSummary }) {
  if (summary.theme_report.length === 0) {
    return (
      <p style={{ fontSize: '0.8rem', color: '#71717a', margin: 0 }}>
        No themes were tagged this run — the judge was unavailable, or nothing
        scored.
      </p>
    )
  }
  return (
    <div style={{ display: 'grid', gap: '0.3rem' }} data-testid="theme-report">
      {summary.theme_report.map((entry) => (
        <ScoreBar
          key={entry.theme}
          label={entry.theme.replace(/_/g, ' ')}
          value={entry.remaining_value}
          max={1}
          color={
            entry.remaining_value >= 0.75
              ? '#22c55e'
              : entry.remaining_value >= 0.4
                ? '#eab308'
                : '#ef4444'
          }
          valueText={`${entry.uses}× · ${Math.round(entry.remaining_value * 100)}%`}
          testId={`theme-${entry.theme}`}
        />
      ))}
      <p style={{ fontSize: '0.72rem', color: '#71717a', margin: '0.2rem 0 0' }}>
        The percentage is what your <em>next</em> volley on that theme would carry.
      </p>
    </div>
  )
}

function DeviceHistogram({ summary }: { summary: FlytingRunSummary }) {
  const entries = useMemo(
    () =>
      Object.entries(summary.device_histogram).sort(
        (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
      ),
    [summary.device_histogram],
  )
  if (entries.length === 0) {
    return (
      <p style={{ fontSize: '0.8rem', color: '#71717a', margin: 0 }}>
        No rhetorical devices were identified. Metaphor, triple, antithesis — the
        rotation bonus rewards not reaching for the same one twice.
      </p>
    )
  }
  const max = Math.max(...entries.map(([, count]) => count))
  return (
    <div style={{ display: 'grid', gap: '0.3rem' }} data-testid="device-histogram">
      {entries.map(([device, count]) => (
        <ScoreBar
          key={device}
          label={device.replace(/_/g, ' ')}
          value={count}
          max={max}
          color="#818cf8"
          valueText={`${count}`}
          testId={`device-${device}`}
        />
      ))}
    </div>
  )
}

/** One volley in the log: a summary row that opens into its full scorecard. */
function VolleyRow({
  entry,
  index,
  umpireLabel,
}: {
  entry: FlytingVolleyLogEntry
  index: number
  umpireLabel: string
}) {
  const card = entry.scorecard
  const color = bandColor(entry.band)
  return (
    <details style={{ border: '1px solid #27272a', borderRadius: 8, background: '#111113' }}>
      <summary
        data-testid={`volley-row-${index}`}
        style={{
          cursor: 'pointer',
          padding: '0.45rem 0.7rem',
          display: 'flex',
          gap: '0.6rem',
          alignItems: 'baseline',
          fontSize: '0.8rem',
          color: '#d4d4d8',
        }}
      >
        <span style={{ color: '#71717a', width: 76, flexShrink: 0 }}>
          {entry.speaker === 'npc' ? 'Opponent' : `Volley ${card?.volley_number ?? index + 1}`}
        </span>
        <span
          style={{
            color,
            fontWeight: 700,
            width: 44,
            flexShrink: 0,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {entry.score}
        </span>
        <span style={{ color, width: 96, flexShrink: 0, fontSize: '0.75rem' }}>
          {bandLabel(entry.band)}
        </span>
        <span
          style={{
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: '#a1a1aa',
          }}
        >
          {entry.text}
        </span>
      </summary>
      <div style={{ padding: '0 0.5rem 0.5rem' }}>
        {card ? (
          <VolleyScorecard card={card} text={entry.text} umpireLabel={umpireLabel} />
        ) : (
          <p style={{ fontSize: '0.78rem', color: '#71717a', margin: '0.4rem 0 0' }}>
            This volley has no stored scorecard.
          </p>
        )}
      </div>
    </details>
  )
}

export default function FlytingDebrief() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const location = useLocation()
  const routeState = location.state as { umpireLabel?: string } | null
  const umpireLabel = routeState?.umpireLabel || 'The umpire'

  const [summary, setSummary] = useState<FlytingRunSummary | null>(null)
  const [volleys, setVolleys] = useState<FlytingVolleyLogEntry[]>([])
  const [scenarioId, setScenarioId] = useState<string | null>(null)
  const [rank, setRank] = useState<number | null>(null)
  const [personalBest, setPersonalBest] = useState<number | null>(null)
  const [board, setBoard] = useState<FlytingHighScore[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    if (!sessionId) return
    setLoading(true)
    // POST, not GET: the run may still be open (the player retired, or the
    // format ended it) and ending it is what produces the aggregates. It is
    // idempotent, so a reload re-reads rather than re-records.
    void api.flyting.endRun(sessionId).then((r) => {
      setLoading(false)
      if (!r.ok) {
        setError(r.error)
        return
      }
      setError(null)
      setSummary(r.data.summary)
      setVolleys(r.data.volleys)
      setScenarioId(r.data.scenario_id)
      setRank(r.data.high_score_rank)
      setPersonalBest(r.data.personal_best)
      void api.flyting
        .highScores(r.data.scenario_id, r.data.summary.play_format, r.data.summary.batting_format)
        .then((b) => {
          if (b.ok) setBoard(b.data.entries)
        })
    })
  }, [sessionId])

  useEffect(() => load(), [load])

  if (loading) {
    return (
      <div style={{ padding: '1.5rem', color: '#71717a', fontSize: '0.875rem' }}>
        Tallying the run…
      </div>
    )
  }

  if (error || !summary) {
    return (
      <div style={{ padding: '1.5rem', display: 'grid', gap: '0.8rem' }}>
        <ApiErrorView
          error={
            error ?? { kind: 'schema-mismatch', message: 'The run summary could not be read.' }
          }
          context="FlytingDebrief"
          onRetry={load}
        />
        <Link to="/library" style={{ color: '#93c5fd', fontSize: '0.85rem' }}>
          ← Back to the library
        </Link>
      </div>
    )
  }

  const isBout = summary.play_format === 'bout'
  const fouls = Object.entries(summary.fouls).filter(([, count]) => count > 0)
  const won = summary.outcome === 'momentum_win' || summary.outcome === 'points_win'

  return (
    <div style={{ padding: '1.25rem', display: 'grid', gap: '0.85rem', maxWidth: 880 }}>
      <header>
        <Link to="/library" style={{ color: '#93c5fd', fontSize: '0.8rem', textDecoration: 'none' }}>
          ← Scenario library
        </Link>
        <h1 style={{ fontSize: '1.4rem', margin: '0.4rem 0 0.3rem', color: '#fafafa' }}>
          {outcomeLabel(summary.outcome)}
        </h1>
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
          <Tag label={formatLabel(summary.play_format, summary.batting_format)} color="#a855f7" />
          {won && <Tag label="Won" color="#22c55e" />}
          {rank != null && <Tag label={`#${rank} on this board`} color="#38bdf8" />}
        </div>
      </header>

      <div
        style={{
          display: 'flex',
          gap: '1.4rem',
          flexWrap: 'wrap',
          padding: '0.75rem 0.9rem',
          border: '1px solid #27272a',
          borderRadius: 8,
          background: '#111113',
        }}
      >
        <Stat
          label={isBout ? 'Your points' : 'Session score'}
          value={isBout ? summary.player_total : summary.total_score}
          accent="#a855f7"
          testId="summary-total"
        />
        {isBout && <Stat label="Their points" value={summary.npc_total} testId="summary-npc-total" />}
        {isBout && summary.final_momentum != null && (
          <Stat label="Final momentum" value={summary.final_momentum} />
        )}
        <Stat label="Volleys" value={summary.volley_count} />
        <Stat label="Best volley" value={summary.best_volley_score} testId="summary-best" />
        {!isBout && <Stat label="Peak heat" value={`×${summary.peak_heat.toFixed(1)}`} />}
        {summary.whiffs > 0 && <Stat label="Whiffs" value={summary.whiffs} accent="#ef4444" />}
        <Stat label="Personal best" value={personalBest ?? '—'} testId="summary-personal-best" />
      </div>

      {fouls.length > 0 && (
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }} aria-label="Fouls">
          {fouls.map(([foul, count]) => (
            <Tag key={foul} label={`${foulLabel(foul)} ×${count}`} color="#ef4444" />
          ))}
        </div>
      )}

      <Section
        title="Best volley"
        hint="The line to remember — and the one to open with next time."
        testId="best-volley"
      >
        {summary.best_volley_text ? (
          <blockquote
            style={{
              margin: 0,
              paddingLeft: '0.7rem',
              borderLeft: `3px solid ${bandColor('highlight')}`,
              color: '#f4f4f5',
              fontSize: '0.95rem',
              lineHeight: 1.6,
            }}
          >
            {summary.best_volley_text}
            <footer
              style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: '#a855f7', fontWeight: 600 }}
            >
              {summary.best_volley_score} points
            </footer>
          </blockquote>
        ) : (
          <p style={{ fontSize: '0.8rem', color: '#71717a', margin: 0 }}>
            Nothing scored this run.
          </p>
        )}
      </Section>

      <Section
        title="Coaching notes"
        hint="Read off your own volley log — no second opinion from a model, and nothing left this computer."
        testId="coaching-notes"
      >
        <ul style={{ margin: 0, paddingLeft: '1.1rem', display: 'grid', gap: '0.3rem' }}>
          {summary.coaching_notes.map((note) => (
            <li key={note} style={{ fontSize: '0.85rem', color: '#e4e4e7', lineHeight: 1.5 }}>
              {note}
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Redundancy report"
        hint="Every return to a theme is worth less than the last. Variety is the meta."
        testId="redundancy"
      >
        <ThemeReport summary={summary} />
      </Section>

      <Section
        title="Devices you reached for"
        hint="A device unused in the last three volleys earns the rotation bonus."
        testId="devices"
      >
        <DeviceHistogram summary={summary} />
      </Section>

      <Section
        title="Rarest words that landed"
        hint="Uncommon vocabulary pays in a band — enough to be worth reaching for, never enough to carry a volley alone."
        testId="rarest-words"
      >
        {summary.rarest_words.length > 0 ? (
          <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
            {summary.rarest_words.map((word) => (
              <Tag key={word} label={word} color="#38bdf8" />
            ))}
          </div>
        ) : (
          <p style={{ fontSize: '0.8rem', color: '#71717a', margin: 0 }}>
            Nothing uncommon this run.
          </p>
        )}
      </Section>

      <Section
        title="Every volley"
        hint="Open one for its full arithmetic and the raw judge verdict. Both are kept on this computer, so it reads the same months later."
        testId="volley-log"
      >
        <div style={{ display: 'grid', gap: '0.35rem' }}>
          {volleys.map((entry, index) => (
            <VolleyRow
              key={`${entry.speaker}-${index}`}
              entry={entry}
              index={index}
              umpireLabel={umpireLabel}
            />
          ))}
          {volleys.length === 0 && (
            <p style={{ fontSize: '0.8rem', color: '#71717a', margin: 0 }}>
              No volleys were recorded.
            </p>
          )}
        </div>
      </Section>

      <Section title="Your board" hint="Stored on this computer only.">
        <HighScoreTable entries={board} highlightSessionId={sessionId ?? null} />
      </Section>

      <div style={{ display: 'flex', gap: '0.8rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {scenarioId && (
          <Link
            to={`/flyting/setup/${scenarioId}`}
            data-testid="run-again"
            style={{
              padding: '0.45rem 1.1rem',
              borderRadius: 6,
              border: '1px solid rgba(168,85,247,0.5)',
              background: 'rgba(168,85,247,0.18)',
              color: '#e9d5ff',
              fontSize: '0.875rem',
              fontWeight: 600,
              textDecoration: 'none',
            }}
          >
            One more run
          </Link>
        )}
        <Link to="/logbook" style={{ color: '#93c5fd', fontSize: '0.82rem' }}>
          Logbook
        </Link>
      </div>
    </div>
  )
}
