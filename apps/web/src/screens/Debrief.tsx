// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import type { SessionDebriefResponse } from '@convsim/shared'
import { api } from '../api/client'

export default function Debrief() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()

  const [phase, setPhase] = useState<'loading' | 'loaded' | 'error'>('loading')
  const [debrief, setDebrief] = useState<SessionDebriefResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    api.generateDebrief(sessionId).then(
      (result) => {
        if (!cancelled) {
          setDebrief(result)
          setPhase('loaded')
        }
      },
      (err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
          setPhase('error')
        }
      },
    )

    return () => {
      cancelled = true
    }
  }, [sessionId])

  return (
    <div
      data-testid="debrief-page"
      style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: 700 }}
    >
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

      {phase === 'loaded' && debrief && (
        <>
          {/* Outcome banner */}
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
              gap: '0.5rem',
            }}
          >
            <span style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
              Scenario: <strong style={{ color: '#f4f4f5' }}>{debrief.scenario_id ?? '—'}</strong>
            </span>
            <span style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
              Turns: <strong style={{ color: '#f4f4f5' }}>{debrief.turn_count ?? 0}</strong>
            </span>
            <OutcomeBadge outcome={debrief.outcome} testId="outcome-badge" />
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

          {/* Improvements */}
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

          {/* Replay suggestions */}
          {debrief.replay_suggestions && debrief.replay_suggestions.length > 0 && (
            <section aria-labelledby="replay-heading">
              <h2 id="replay-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                Replay suggestions
              </h2>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', color: '#c4b5fd', lineHeight: 1.8 }}>
                {debrief.replay_suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
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

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/library')}
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
              Try another scenario
            </button>
          </div>
        </>
      )}
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
  const bg = colors[outcome] ?? '#27272a'
  return (
    <span
      data-testid={testId}
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
      {outcome.replace('_', ' ')}
    </span>
  )
}
