// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import type { DebriefTurningPoint, SessionDebriefResponse } from '@convsim/shared'
import { api } from '../api/client'
import { isDevModeEnabled } from '../privacyPrefs'

type TranscriptEvent = {
  event_id: number
  event_type: string
  payload: Record<string, unknown>
}

export default function Debrief() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()

  const [phase, setPhase] = useState<'loading' | 'loaded' | 'error'>('loading')
  const [debrief, setDebrief] = useState<SessionDebriefResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<TranscriptEvent[]>([])
  const [exporting, setExporting] = useState(false)
  const [exportingText, setExportingText] = useState(false)
  // Debrief-generation latency (ms), captured locally for the dev debug view. No telemetry.
  const [debriefMs, setDebriefMs] = useState<number | null>(null)
  const devMode = isDevModeEnabled()

  const turnRefs = useRef<Map<number, HTMLElement>>(new Map())

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    const debriefStart = performance.now()
    api.generateDebrief(sessionId).then(
      (result) => {
        if (cancelled) return
        setDebriefMs(Math.round(performance.now() - debriefStart))
        setDebrief(result)
        setPhase('loaded')

        if (!result.transcript_saving_disabled) {
          api.exportSession(sessionId).then(
            (data) => {
              if (cancelled) return
              const exportData = data as { events?: TranscriptEvent[] }
              const turns = (exportData.events ?? []).filter(
                (e) =>
                  e.event_type === 'player_turn' ||
                  e.event_type === 'npc_turn' ||
                  e.event_type === 'npc_opening',
              )
              setTranscript(turns)
            },
            () => {},
          )
        }
      },
      (err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setPhase('error')
      },
    )

    return () => {
      cancelled = true
    }
  }, [sessionId])

  const scrollToTurn = useCallback((turnNumber: number) => {
    const el = turnRefs.current.get(turnNumber)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])

  async function handleExport() {
    if (!sessionId) return
    setExporting(true)
    try {
      const data = await api.exportSession(sessionId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `session-${sessionId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  async function handleExportText() {
    if (!sessionId) return
    setExportingText(true)
    try {
      const { text, filename } = await api.exportTranscriptText(sessionId)
      const blob = new Blob([text], { type: 'text/markdown; charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExportingText(false)
    }
  }

  function handleReplay() {
    if (!debrief?.scenario_id) {
      navigate('/library')
      return
    }
    navigate(`/setup/${debrief.scenario_id}`)
  }

  return (
    <div
      data-testid="debrief-page"
      style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: 720 }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <div>
          <h1 style={{ margin: 0 }}>Session Debrief</h1>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#71717a' }}>
            Session: <code>{sessionId}</code>
          </p>
        </div>
        <button
          onClick={() => navigate('/library')}
          style={{
            padding: '0.4rem 1rem',
            borderRadius: 6,
            border: '1px solid #52525b',
            background: 'transparent',
            color: '#a1a1aa',
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          ← Back to library
        </button>
      </div>

      {phase === 'loading' && (
        <p aria-live="polite" aria-busy="true" style={{ color: '#71717a' }}>
          Generating debrief…
        </p>
      )}

      {phase === 'error' && (
        <div
          role="alert"
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 6,
            border: '1px solid #7f1d1d',
            background: '#450a0a',
            color: '#fca5a5',
            fontSize: '0.875rem',
          }}
        >
          <strong>Failed to generate debrief:</strong> {error}
        </div>
      )}

      {devMode && debriefMs !== null && (
        <div
          data-testid="debrief-latency"
          style={{ fontSize: '0.7rem', color: '#6ee7b7' }}
        >
          Debrief generation: {debriefMs.toLocaleString()} ms
        </div>
      )}

      {phase === 'loaded' && debrief && (
        <>
          {/* Fallback notice */}
          {debrief.used_fallback && (
            <div
              data-testid="fallback-notice"
              style={{
                padding: '0.6rem 1rem',
                borderRadius: 6,
                border: '1px solid #78350f',
                background: '#1c0a00',
                color: '#fbbf24',
                fontSize: '0.8rem',
              }}
            >
              Debrief generated from a template — install a local model for detailed feedback.
            </div>
          )}

          {/* Transcript-saving-disabled notice */}
          {debrief.transcript_saving_disabled && (
            <div
              data-testid="transcript-disabled-notice"
              style={{
                padding: '0.6rem 1rem',
                borderRadius: 6,
                border: '1px solid #27272a',
                background: '#18181b',
                color: '#a1a1aa',
                fontSize: '0.8rem',
              }}
            >
              Transcript saving was disabled for this session. Turn details are not available.
            </div>
          )}

          {/* Outcome + score banner */}
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: 8,
              background: '#0c0a09',
              border: '1px solid #27272a',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.75rem',
            }}
          >
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
                Scenario:{' '}
                <strong style={{ color: '#f4f4f5' }}>{debrief.scenario_id ?? '—'}</strong>
              </span>
              <span style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
                Turns: <strong style={{ color: '#f4f4f5' }}>{debrief.turn_count ?? 0}</strong>
              </span>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              {debrief.overall_score != null && (
                <OverallScore score={debrief.overall_score} />
              )}
              <OutcomeBadge outcome={debrief.outcome} testId="outcome-badge" />
            </div>
          </div>

          {/* Summary */}
          <section aria-labelledby="summary-heading" data-testid="summary-section">
            <h2 id="summary-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
              Summary
            </h2>
            <p
              style={{
                padding: '0.75rem 1rem',
                borderRadius: 6,
                background: '#09090b',
                border: '1px solid #27272a',
                color: '#e4e4e7',
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              {debrief.summary}
            </p>
          </section>

          {/* Scorecard */}
          {debrief.scores && Object.keys(debrief.scores).length > 0 && (
            <section aria-labelledby="scorecard-heading" data-testid="scorecard-section">
              <h2 id="scorecard-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                Scorecard
              </h2>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.5rem',
                  padding: '0.75rem',
                  borderRadius: 6,
                  background: '#09090b',
                  border: '1px solid #27272a',
                }}
              >
                {Object.entries(debrief.scores).map(([dim, score]) => (
                  <DimensionRow key={dim} dimension={dim} score={score} />
                ))}
              </div>
            </section>
          )}

          {/* Strengths */}
          {debrief.strengths && debrief.strengths.length > 0 && (
            <section aria-labelledby="strengths-heading">
              <h2 id="strengths-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                Strengths
              </h2>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', color: '#86efac', lineHeight: 1.8 }}>
                {debrief.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          {/* Areas for improvement */}
          {debrief.improvements && debrief.improvements.length > 0 && (
            <section aria-labelledby="improvements-heading">
              <h2 id="improvements-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                Areas for improvement
              </h2>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', color: '#fdba74', lineHeight: 1.8 }}>
                {debrief.improvements.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          {/* Missed opportunities */}
          {debrief.missed_opportunities && debrief.missed_opportunities.length > 0 && (
            <section aria-labelledby="missed-heading" data-testid="missed-opportunities-section">
              <h2 id="missed-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                Missed opportunities
              </h2>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', color: '#fda4af', lineHeight: 1.8 }}>
                {debrief.missed_opportunities.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          {/* Turning points / key moments */}
          {debrief.turning_points && debrief.turning_points.length > 0 && (
            <section
              aria-labelledby="turning-points-heading"
              data-testid="turning-points-section"
            >
              <h2
                id="turning-points-heading"
                style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}
              >
                Key moments
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {debrief.turning_points.map((tp, i) => (
                  <TurningPointCard
                    key={i}
                    point={tp}
                    onScrollTo={transcript.length > 0 ? scrollToTurn : undefined}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Try next time / replay suggestions */}
          {debrief.replay_suggestions && debrief.replay_suggestions.length > 0 && (
            <section aria-labelledby="replay-heading">
              <h2 id="replay-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                Try next time
              </h2>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', color: '#c4b5fd', lineHeight: 1.8 }}>
                {debrief.replay_suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          {/* Transcript */}
          {transcript.length > 0 && (
            <section aria-labelledby="transcript-heading" data-testid="transcript-section">
              <h2
                id="transcript-heading"
                style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}
              >
                Transcript
              </h2>
              <div
                role="log"
                aria-label="Conversation transcript"
                style={{
                  maxHeight: 400,
                  overflowY: 'auto',
                  padding: '1rem',
                  borderRadius: 8,
                  border: '1px solid #27272a',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                }}
              >
                {transcript.map((event, idx) => (
                  <TranscriptTurn
                    key={event.event_id > 0 ? event.event_id : idx}
                    event={event}
                    turnNumber={idx + 1}
                    registerRef={(el) => {
                      if (el) turnRefs.current.set(idx + 1, el)
                      else turnRefs.current.delete(idx + 1)
                    }}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Raw JSON (debug) */}
          <details>
            <summary
              style={{ cursor: 'pointer', fontSize: '0.8rem', color: '#71717a', userSelect: 'none' }}
            >
              Full debrief JSON (debug)
            </summary>
            <pre
              data-testid="debrief-json"
              style={{
                marginTop: '0.5rem',
                padding: '0.75rem',
                borderRadius: 6,
                background: '#09090b',
                border: '1px solid #27272a',
                color: '#a1a1aa',
                fontSize: '0.75rem',
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {JSON.stringify(debrief, null, 2)}
            </pre>
          </details>

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              data-testid="replay-btn"
              onClick={handleReplay}
              style={{
                padding: '0.5rem 1.5rem',
                borderRadius: 6,
                border: 'none',
                background: '#4f46e5',
                color: '#fff',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Replay scenario
            </button>
            <button
              data-testid="export-btn"
              onClick={() => void handleExport()}
              disabled={exporting}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 6,
                border: '1px solid #52525b',
                background: 'transparent',
                color: '#a1a1aa',
                cursor: exporting ? 'default' : 'pointer',
              }}
            >
              {exporting ? 'Exporting…' : 'Export session JSON'}
            </button>
            <button
              data-testid="export-text-btn"
              onClick={() => void handleExportText()}
              disabled={exportingText}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 6,
                border: '1px solid #52525b',
                background: 'transparent',
                color: '#a1a1aa',
                cursor: exportingText ? 'default' : 'pointer',
              }}
            >
              {exportingText ? 'Exporting…' : 'Export transcript (Markdown)'}
            </button>
            <button
              onClick={() => navigate('/library')}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 6,
                border: '1px solid #52525b',
                background: 'transparent',
                color: '#a1a1aa',
                cursor: 'pointer',
              }}
            >
              Try another scenario
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function OverallScore({ score }: { score: number }) {
  const color = score >= 70 ? '#86efac' : score >= 40 ? '#fbbf24' : '#fca5a5'
  const rounded = Math.round(score)
  const grade = rounded >= 70 ? 'Good' : rounded >= 40 ? 'Fair' : 'Needs improvement'
  return (
    <div
      data-testid="overall-score"
      aria-label={`Overall score: ${rounded} out of 100 — ${grade}`}
      role="meter"
      aria-valuenow={rounded}
      aria-valuemin={0}
      aria-valuemax={100}
      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: 1 }}
    >
      <span aria-hidden="true" style={{ fontSize: '1.5rem', fontWeight: 700, color }}>{rounded}</span>
      <span aria-hidden="true" style={{ fontSize: '0.65rem', color: '#71717a', marginTop: 2 }}>/ 100</span>
    </div>
  )
}

function DimensionRow({ dimension, score }: { dimension: string; score: number }) {
  const label = dimension.replace(/_/g, ' ')
  const barColor = score >= 70 ? '#22c55e' : score >= 40 ? '#f97316' : '#ef4444'
  const rounded = Math.round(score)
  return (
    <div
      data-testid={`dimension-row-${dimension}`}
      style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}
    >
      <span
        style={{
          flex: '0 0 140px',
          fontSize: '0.85rem',
          color: '#a1a1aa',
          textTransform: 'capitalize',
        }}
      >
        {label}
      </span>
      <div
        role="meter"
        aria-label={`${label}: ${rounded} out of 100`}
        aria-valuenow={rounded}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{
          flex: 1,
          height: 6,
          borderRadius: 3,
          background: '#27272a',
          overflow: 'hidden',
        }}
      >
        <div
          aria-hidden="true"
          style={{ width: `${score}%`, height: '100%', borderRadius: 3, background: barColor }}
        />
      </div>
      <span
        style={{
          flex: '0 0 36px',
          fontSize: '0.85rem',
          fontWeight: 600,
          color: '#f4f4f5',
          textAlign: 'right',
        }}
      >
        {rounded}
      </span>
    </div>
  )
}

function TurningPointCard({
  point,
  onScrollTo,
}: {
  point: DebriefTurningPoint
  onScrollTo?: (turnNumber: number) => void
}) {
  const impactColor =
    point.impact === 'positive'
      ? '#86efac'
      : point.impact === 'negative'
        ? '#fca5a5'
        : '#a1a1aa'

  return (
    <div
      data-testid="turning-point"
      style={{
        padding: '0.6rem 0.875rem',
        borderRadius: 6,
        background: '#09090b',
        border: '1px solid #27272a',
        display: 'flex',
        gap: '0.75rem',
        alignItems: 'flex-start',
      }}
    >
      {onScrollTo ? (
        <button
          onClick={() => onScrollTo(point.turn_number)}
          aria-label={`Go to turn ${point.turn_number}`}
          style={{
            flexShrink: 0,
            padding: '0.1rem 0.4rem',
            borderRadius: 4,
            border: '1px solid #3f3f46',
            background: '#18181b',
            color: '#a1a1aa',
            cursor: 'pointer',
            fontSize: '0.75rem',
            fontWeight: 600,
            lineHeight: 1.4,
          }}
        >
          #{point.turn_number}
        </button>
      ) : (
        <span
          style={{
            flexShrink: 0,
            padding: '0.1rem 0.4rem',
            borderRadius: 4,
            border: '1px solid #3f3f46',
            background: '#18181b',
            color: '#a1a1aa',
            fontSize: '0.75rem',
            fontWeight: 600,
          }}
        >
          #{point.turn_number}
        </span>
      )}
      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontSize: '0.875rem', color: '#e4e4e7', lineHeight: 1.5 }}>
          {point.description}
        </p>
        {point.impact && (
          <span
            aria-label={`Impact: ${point.impact}`}
            style={{ fontSize: '0.75rem', color: impactColor, textTransform: 'capitalize' }}
          >
            {point.impact === 'positive' ? '▲ ' : point.impact === 'negative' ? '▼ ' : ''}
            {point.impact}
          </span>
        )}
      </div>
    </div>
  )
}

function TranscriptTurn({
  event,
  turnNumber,
  registerRef,
}: {
  event: TranscriptEvent
  turnNumber: number
  registerRef: (el: HTMLElement | null) => void
}) {
  const isPlayer = event.event_type === 'player_turn'
  const content = (event.payload['content'] as string | undefined) ?? ''
  const emotion = event.payload['emotion'] as string | undefined

  return (
    <div
      ref={registerRef}
      data-testid="transcript-turn"
      data-turn-number={turnNumber}
      data-role={isPlayer ? 'player' : 'npc'}
    >
      <div
        style={{
          fontSize: '0.7rem',
          color: isPlayer ? '#a78bfa' : '#6ee7b7',
          marginBottom: 2,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        <span>Turn {turnNumber}</span>
        {' · '}
        <span>{isPlayer ? 'You' : 'NPC'}</span>
        {emotion && emotion !== 'neutral' && (
          <span style={{ marginLeft: 6, opacity: 0.7 }}>({emotion})</span>
        )}
      </div>
      <div
        style={{
          padding: '0.5rem 0.75rem',
          borderRadius: 6,
          background: isPlayer ? '#1e1b4b' : '#052e16',
          color: '#f4f4f5',
          fontSize: '0.9rem',
          lineHeight: 1.5,
        }}
      >
        {content}
      </div>
    </div>
  )
}

function OutcomeBadge({ outcome, testId }: { outcome?: string; testId?: string }) {
  if (!outcome) return null
  const colors: Record<string, string> = {
    success: '#166534',
    failure: '#7f1d1d',
    timeout: '#78350f',
    safety_stop: '#7c2d12',
    player_exit: '#1e3a5f',
  }
  const icons: Record<string, string> = {
    success: '✓ ',
    failure: '✕ ',
    timeout: '⏱ ',
    safety_stop: '⛔ ',
    player_exit: '→ ',
  }
  const bg = colors[outcome] ?? '#27272a'
  const icon = icons[outcome] ?? ''
  return (
    <span
      data-testid={testId}
      aria-label={`Outcome: ${outcome.replace(/_/g, ' ')}`}
      style={{
        padding: '0.2rem 0.7rem',
        borderRadius: 12,
        background: bg,
        color: '#f4f4f5',
        fontSize: '0.8rem',
        fontWeight: 600,
        textTransform: 'capitalize',
      }}
    >
      <span aria-hidden="true">{icon}</span>
      {outcome.replace(/_/g, ' ')}
    </span>
  )
}
