// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLogbookProfile } from '../api/useLogbookProfile'
import { api } from '../api/client'
import { useSteamAchievements, SteamAchievement, SteamStat } from '../hooks/useSteamAchievements'
import { useEffect, useRef } from 'react'

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  const remainingMins = mins % 60
  return remainingMins > 0 ? `${hours}h ${remainingMins}m` : `${hours}h`
}

// Per-skill trajectory sparkline. Renders one point per debriefed session
// (chronological, left = oldest). Returns null when there is not yet enough
// history to draw a line (fewer than two sessions).
function SkillTrajectory({ dimensionId, scores, color }: { dimensionId: string; scores: number[]; color: string }) {
  if (scores.length < 2) return null
  const W = 80
  const H = 20
  const min = 0
  const max = 100
  const points = scores.map((v, i) => {
    const x = (i / (scores.length - 1)) * W
    const y = H - ((Math.min(max, Math.max(min, v)) - min) / (max - min)) * H
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg
      width={W}
      height={H}
      role="img"
      aria-label={`${dimensionId.replace(/_/g, ' ')} trajectory over ${scores.length} sessions`}
      style={{ overflow: 'visible', flexShrink: 0 }}
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

function DeltaBadge({ delta }: { delta: number }) {
  const sign = delta >= 0 ? '+' : ''
  const color = delta > 0 ? '#4ade80' : delta < 0 ? '#f87171' : '#a1a1aa'
  return (
    <span style={{ color, fontWeight: 600, fontSize: '0.85rem' }}>
      {sign}{Math.round(delta)}
    </span>
  )
}

export default function Logbook() {
  const { state, profile } = useLogbookProfile()
  const { unlock, incrementStat } = useSteamAchievements()
  const achievementsChecked = useRef(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  useEffect(() => {
    if (state !== 'ready' || !profile || achievementsChecked.current) return
    achievementsChecked.current = true

    if (profile.streak_days >= 7) {
      void unlock(SteamAchievement.PRACTICE_STREAK)
    }
    if (profile.total_sessions >= 10) {
      void incrementStat(SteamStat.SCENARIOS_COMPLETED)
    }
  }, [state, profile, unlock, incrementStat])

  async function handleExport() {
    setExporting(true)
    setExportError(null)
    const r = await api.exportLogbook()
    if (r.ok) {
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'logbook-export.json'
      a.click()
      URL.revokeObjectURL(url)
    } else {
      setExportError('Export failed. Please try again.')
    }
    setExporting(false)
  }

  if (state === 'loading') {
    return (
      <div>
        <h1>Logbook</h1>
        <p style={{ color: '#a1a1aa' }}>Loading your training history…</p>
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div>
        <h1>Logbook</h1>
        <p role="alert" style={{ color: '#f87171' }}>
          Could not load logbook data. Check that the local runtime is running.
        </p>
      </div>
    )
  }

  if (!profile || profile.total_sessions === 0) {
    return (
      <div>
        <h1>Logbook</h1>
        <section
          aria-label="No sessions yet"
          style={{
            marginTop: '1.5rem',
            padding: '1.5rem',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '8px',
            maxWidth: '36rem',
          }}
        >
          <p style={{ margin: '0 0 0.5rem', fontWeight: 600, fontSize: '1rem' }}>
            Your logbook is empty
          </p>
          <p style={{ margin: '0 0 1rem', fontSize: '0.875rem', color: '#a1a1aa' }}>
            Complete your first scenario to start tracking your progress. Every session
            builds your skill profile.
          </p>
          <Link
            to="/library"
            style={{
              fontSize: '0.85rem',
              padding: '0.35rem 0.8rem',
              borderRadius: '4px',
              border: '1px solid rgba(255,255,255,0.15)',
              color: '#e8e8ea',
              textDecoration: 'none',
              display: 'inline-block',
            }}
          >
            Start a scenario →
          </Link>
        </section>
      </div>
    )
  }

  const practiceTime = formatDuration(profile.total_practice_seconds)

  return (
    <div>
      <h1>Logbook</h1>
      <p style={{ color: '#a1a1aa', marginBottom: '2rem' }}>
        Your local training record — all data stays on this device.
      </p>

      {/* Summary stats */}
      <section aria-label="Training summary" style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>
          Summary
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(10rem, 1fr))',
            gap: '0.75rem',
          }}
        >
          {[
            { label: 'Sessions', value: String(profile.total_sessions) },
            { label: 'Practice time', value: practiceTime },
            {
              label: 'Streak',
              value: `${profile.streak_days} day${profile.streak_days !== 1 ? 's' : ''}`,
            },
            ...(profile.last_session_delta !== null
              ? [{ label: 'Last session', value: undefined, delta: profile.last_session_delta }]
              : []),
          ].map(({ label, value, delta }) => (
            <div
              key={label}
              style={{
                padding: '0.85rem 1rem',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '6px',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: '#71717a', marginBottom: '0.25rem' }}>
                {label}
              </div>
              {value !== undefined ? (
                <div style={{ fontWeight: 700, fontSize: '1.25rem' }}>{value}</div>
              ) : delta !== undefined ? (
                <div style={{ fontWeight: 700, fontSize: '1.25rem' }}>
                  <DeltaBadge delta={delta} />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      {/* Skill scores */}
      {profile.dimension_scores.length > 0 && (
        <section aria-label="Skill scores" style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>
            Skill profile
          </h2>
          <p style={{ fontSize: '0.8rem', color: '#71717a', marginBottom: '0.75rem' }}>
            Recency-weighted rolling average across all debriefs.
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {[...profile.dimension_scores]
              .sort((a, b) => b.rolling_score - a.rolling_score)
              .map((dim) => {
                const isStrongest = dim.dimension_id === profile.strongest_dimension
                const isWeakest = dim.dimension_id === profile.weakest_dimension && profile.dimension_scores.length > 1
                return (
                  <li
                    key={dim.dimension_id}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}
                  >
                    <span style={{ minWidth: '9rem', fontSize: '0.875rem', color: '#e8e8ea' }}>
                      {dim.dimension_id.replace(/_/g, ' ')}
                      {isStrongest && (
                        <span
                          title="Strongest skill"
                          style={{ marginLeft: '0.4rem', fontSize: '0.7rem', color: '#4ade80' }}
                        >
                          ▲
                        </span>
                      )}
                      {isWeakest && (
                        <span
                          title="Weakest skill"
                          style={{ marginLeft: '0.4rem', fontSize: '0.7rem', color: '#f87171' }}
                        >
                          ▼
                        </span>
                      )}
                    </span>
                    <div
                      style={{
                        flex: 1,
                        height: '6px',
                        background: 'rgba(255,255,255,0.07)',
                        borderRadius: '3px',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          height: '100%',
                          width: `${Math.min(100, Math.max(0, dim.rolling_score))}%`,
                          background: isStrongest
                            ? '#4ade80'
                            : isWeakest
                            ? '#f87171'
                            : '#6366f1',
                          borderRadius: '3px',
                          transition: 'width 0.4s ease',
                        }}
                      />
                    </div>
                    <span
                      style={{
                        minWidth: '2.5rem',
                        textAlign: 'right',
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        color: '#a1a1aa',
                      }}
                    >
                      {dim.rolling_score}
                    </span>
                    <SkillTrajectory
                      dimensionId={dim.dimension_id}
                      scores={dim.trajectory}
                      color={isStrongest ? '#4ade80' : isWeakest ? '#f87171' : '#6366f1'}
                    />
                    <span style={{ fontSize: '0.75rem', color: '#52525b', minWidth: '4rem' }}>
                      {dim.session_count} session{dim.session_count !== 1 ? 's' : ''}
                    </span>
                  </li>
                )
              })}
          </ul>
        </section>
      )}

      {/* Personal records */}
      {profile.personal_records.length > 0 && (
        <section aria-label="Personal records" style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>
            Personal records
          </h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {profile.personal_records.map((pr) => (
              <li
                key={`${pr.scenario_id}|${pr.difficulty}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.6rem 0.75rem',
                  border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: '6px',
                  fontSize: '0.875rem',
                }}
              >
                <span style={{ flex: 1, color: '#e8e8ea' }}>
                  {pr.scenario_id.replace(/_/g, ' ')}
                </span>
                <span style={{ color: '#71717a', fontSize: '0.8rem', minWidth: '3.5rem' }}>
                  {pr.difficulty}
                </span>
                <span style={{ fontWeight: 700, color: '#a3e635' }}>
                  {pr.best_score}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Export */}
      <section aria-label="Export" style={{ borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: '1.5rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>Export</h2>
        <p style={{ fontSize: '0.8rem', color: '#71717a', marginBottom: '0.75rem' }}>
          Download your logbook as JSON for backup or analysis.
        </p>
        <button
          onClick={() => void handleExport()}
          disabled={exporting}
          style={{
            fontSize: '0.85rem',
            padding: '0.35rem 0.8rem',
            borderRadius: '4px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'transparent',
            color: exporting ? '#52525b' : '#e8e8ea',
            cursor: exporting ? 'default' : 'pointer',
          }}
        >
          {exporting ? 'Exporting…' : 'Export logbook as JSON'}
        </button>
        {exportError && (
          <p role="alert" style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#f87171' }}>
            {exportError}
          </p>
        )}
      </section>
    </div>
  )
}
