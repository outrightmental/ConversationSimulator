// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom'
import type { DebriefTurningPoint, DebriefMetrics, SessionDebriefResponse, SessionCreateRequest, LogbookProfile } from '@convsim/shared'
import { recommendNext } from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'
import { isDevModeEnabled, readVoiceInviteState, writeVoiceInviteState } from '../privacyPrefs'
import { useTranslation, formatNumber } from '../i18n'
import { useSteamAchievements, SteamAchievement, SteamStat } from '../hooks/useSteamAchievements'
import { useScenarios } from '../api/useScenarios'

type TranscriptEvent = {
  event_id: number
  event_type: string
  payload: Record<string, unknown>
}

export default function Debrief() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const { state: routeState } = useLocation()
  const { t, locale } = useTranslation()

  // Set when the user deferred the model-ready switch during a tutorial session;
  // the debrief becomes the upgrade moment.
  const modelReadyAfterTutorial = (routeState as { modelReadyAfterTutorial?: boolean } | null)?.modelReadyAfterTutorial ?? false

  // Set when the session was run with a scripted or demo runtime (not real AI).
  // Voice invite is only offered after a genuine AI conversation.
  const isScripted = (routeState as { isScripted?: boolean } | null)?.isScripted ?? false

  // Voice invite card: shown once after the first real AI conversation's debrief.
  // Reads localStorage so "Maybe later" persists across relaunches.
  const [voiceInviteVisible, setVoiceInviteVisible] = useState(
    () => !isScripted && readVoiceInviteState() === 'pending'
  )

  const [phase, setPhase] = useState<'loading' | 'loaded' | 'error' | 'transcript_only'>('loading')
  const [debrief, setDebrief] = useState<SessionDebriefResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [transcript, setTranscript] = useState<TranscriptEvent[]>([])
  const [exporting, setExporting] = useState(false)
  const [exportingText, setExportingText] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const [sessionSetup, setSessionSetup] = useState<SessionCreateRequest | null>(null)
  const [exportedScenarioId, setExportedScenarioId] = useState<string | null>(null)
  const [replayingSameSetup, setReplayingSameSetup] = useState(false)
  // Debrief-generation latency (ms), captured locally for the dev debug view. No telemetry.
  const [debriefMs, setDebriefMs] = useState<number | null>(null)
  const devMode = isDevModeEnabled()

  const turnRefs = useRef<Map<number, HTMLElement>>(new Map())
  const { unlock, incrementStat } = useSteamAchievements()
  const achievementsGranted = useRef(false)
  const scenariosResult = useScenarios()

  // Build a synthetic profile from the session scores so the recommender can
  // surface the next scenario without a separate logbook fetch.
  const sessionProfile: LogbookProfile | null = debrief
    ? {
        total_sessions: 1,
        total_practice_seconds: 0,
        streak_days: 0,
        last_session_date: null,
        dimension_scores: Object.entries(debrief.scores ?? {}).map(([id, score]) => ({
          dimension_id: id,
          rolling_score: score,
          session_count: 1,
          trajectory: [score],
        })),
        personal_records: [],
        strongest_dimension: null,
        weakest_dimension: null,
        last_session_delta: null,
      }
    : null

  // Exclude the scenario that was just completed so "Next up" always points
  // forward rather than recommending a repeat of the session just debriefed.
  const nextUpScenarios = debrief?.scenario_id
    ? scenariosResult.scenarios.filter((s) => s.scenario_id !== debrief.scenario_id)
    : scenariosResult.scenarios
  const nextUpRecommendations = recommendNext(sessionProfile, nextUpScenarios)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    async function run() {
      const debriefStart = performance.now()
      const r = await api.generateDebrief(sessionId!)
      if (cancelled) return
      if (!r.ok) {
        setError(r.error)
        setPhase('error')
        return
      }
      setDebriefMs(Math.round(performance.now() - debriefStart))
      const result = r.data
      setDebrief(result)
      setPhase('loaded')

      if (!achievementsGranted.current) {
        achievementsGranted.current = true
        void unlock(SteamAchievement.FIRST_DEBRIEF)
        void incrementStat(SteamStat.DEBRIEFS_GENERATED)
        // Reaching a debrief means the session ended. Per the shipped Steam
        // framework (#230), that is exactly the boundary for FIRST_SCENARIO
        // ("session ends normally or is manually ended") and the
        // SCENARIOS_COMPLETED stat ("session ends"). These fire for every
        // ending type — not only 'success' — so a player who ends a scenario
        // manually (player_exit) still gets credit; gating on 'success' would
        // never unlock FIRST_SCENARIO for the manual-end case the framework
        // explicitly names, and would stall the "10 scenarios" milestone.
        void unlock(SteamAchievement.FIRST_SCENARIO)
        // Count each completed scenario once, at the moment of completion —
        // this is the cumulative stat Steam maps the "10 scenarios" milestone
        // onto. (Incrementing it on the Logbook screen instead would inflate
        // it on every page visit; the achievementsGranted ref keeps it to
        // once per debrief.)
        void incrementStat(SteamStat.SCENARIOS_COMPLETED)
      }

      if (!result.transcript_saving_disabled) {
        const r2 = await api.exportSession(sessionId!)
        if (cancelled) return
        if (r2.ok) {
          const exportData = r2.data as {
            session?: { setup?: SessionCreateRequest; scenario_id?: string }
            events?: TranscriptEvent[]
          }
          if (exportData.session?.setup) {
            setSessionSetup(exportData.session.setup)
          }
          if (exportData.session?.scenario_id) {
            setExportedScenarioId(exportData.session.scenario_id)
          }
          const turns = (exportData.events ?? []).filter(
            (e) =>
              e.event_type === 'player_turn' ||
              e.event_type === 'npc_turn' ||
              e.event_type === 'npc_opening',
          )
          setTranscript(turns)
        }
        // silently ignore export error
      }
    }

    void run()

    return () => {
      cancelled = true
    }
    // unlock/incrementStat are stable useCallbacks from useSteamAchievements;
    // listed to satisfy exhaustive-deps without triggering re-runs.
  }, [sessionId, retryKey, unlock, incrementStat])

  // Persist "seen" the moment the invite is actually rendered (debrief loaded),
  // so it appears exactly once and never re-nags on later debriefs (issue #385).
  // Without this, ignoring the card — the common case, since the debrief action
  // buttons navigate away — leaves the state 'pending' and re-shows the card
  // after every subsequent real conversation. The explicit "Set up voice" /
  // "Maybe later" buttons overwrite this with 'setup'/'dismissed' when clicked.
  useEffect(() => {
    if (phase === 'loaded' && voiceInviteVisible) {
      writeVoiceInviteState('dismissed')
    }
  }, [phase, voiceInviteVisible])

  const scrollToTurn = useCallback((turnNumber: number) => {
    const el = turnRefs.current.get(turnNumber)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])

  function handleRetry() {
    setPhase('loading')
    setError(null)
    setDebrief(null)
    setRetryKey((k) => k + 1)
  }

  async function handleShowTranscriptOnly() {
    if (!sessionId) return
    setPhase('loading')
    const r = await api.exportSession(sessionId!)
    if (!r.ok) {
      // Surface the actual export failure — otherwise the error phase would show
      // a stale cause left over from the debrief-generation failure (or nothing
      // at all), with no Copy diagnostics for what really went wrong here.
      setError(r.error)
      setPhase('error')
      return
    }
    const exportData = r.data as {
      session?: { setup?: SessionCreateRequest; scenario_id?: string }
      events?: TranscriptEvent[]
    }
    if (exportData.session?.setup) setSessionSetup(exportData.session.setup)
    if (exportData.session?.scenario_id) setExportedScenarioId(exportData.session.scenario_id)
    const turns = (exportData.events ?? []).filter(
      (e) =>
        e.event_type === 'player_turn' ||
        e.event_type === 'npc_turn' ||
        e.event_type === 'npc_opening',
    )
    setTranscript(turns)
    setPhase('transcript_only')
  }

  async function handleReplaySameSetup() {
    if (!sessionSetup) {
      handleReplayVariation()
      return
    }
    setReplayingSameSetup(true)
    const r = await api.createSession(sessionSetup)
    setReplayingSameSetup(false)
    if (!r.ok) {
      handleReplayVariation()
      return
    }
    const newSession = r.data
    navigate(`/conversation/${newSession.session_id}`, {
      state: {
        language: newSession.setup.language,
        show_state_meters: newSession.setup.show_state_meters,
        scenario_id: newSession.scenario_id,
        input_mode: newSession.setup.input_mode,
        tts_enabled: newSession.setup.tts_enabled,
      },
    })
  }

  async function handleExport() {
    if (!sessionId) return
    setExporting(true)
    const r = await api.exportSession(sessionId!)
    if (r.ok) {
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `session-${sessionId}.json`
      a.click()
      URL.revokeObjectURL(url)
    }
    // silently ignore error (export is best-effort)
    setExporting(false)
  }

  async function handleExportText() {
    if (!sessionId) return
    setExportingText(true)
    const r = await api.exportTranscriptText(sessionId!)
    if (r.ok) {
      const blob = new Blob([r.data.text], { type: 'text/markdown; charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = r.data.filename
      a.click()
      URL.revokeObjectURL(url)
    }
    // silently ignore error (export is best-effort)
    setExportingText(false)
  }

  function handleReplayVariation() {
    const scenarioId = debrief?.scenario_id ?? exportedScenarioId
    if (!scenarioId) {
      navigate('/library')
      return
    }
    navigate(`/setup/${scenarioId}`)
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
          <h1 style={{ margin: 0 }}>{t('debrief.title')}</h1>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#71717a' }}>
            {t('debrief.sessionLabel')} <code>{sessionId}</code>
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
          {t('debrief.backToLibrary')}
        </button>
      </div>

      {phase === 'loading' && (
        <p aria-live="polite" aria-busy="true" style={{ color: '#71717a' }}>
          {t('debrief.generating')}
        </p>
      )}

      {phase === 'error' && (
        <>
          {error && (
            <ApiErrorView
              error={error}
              context="Debrief"
            />
          )}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              data-testid="retry-btn"
              onClick={handleRetry}
              style={{
                padding: '0.35rem 0.9rem',
                borderRadius: 5,
                border: 'none',
                background: '#4f46e5',
                color: '#fff',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '0.8rem',
              }}
            >
              Retry debrief
            </button>
            <button
              data-testid="transcript-only-btn"
              onClick={() => void handleShowTranscriptOnly()}
              style={{
                padding: '0.35rem 0.9rem',
                borderRadius: 5,
                border: '1px solid #7f1d1d',
                background: 'transparent',
                color: '#fca5a5',
                cursor: 'pointer',
                fontSize: '0.8rem',
              }}
            >
              {t('debrief.error.transcriptOnly')}
            </button>
          </div>
        </>
      )}

      {phase === 'transcript_only' && (
        <>
          <div
            data-testid="transcript-only-notice"
            style={{
              padding: '0.6rem 1rem',
              borderRadius: 6,
              border: '1px solid #78350f',
              background: '#1c0a00',
              color: '#fbbf24',
              fontSize: '0.8rem',
            }}
          >
            {t('debrief.transcript.transcriptOnlyNotice')}
          </div>

          {transcript.length > 0 ? (
            <section aria-labelledby="transcript-heading-fallback" data-testid="transcript-section">
              <h2
                id="transcript-heading-fallback"
                style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}
              >
                {t('debrief.transcript.heading')}
              </h2>
              <div
                role="log"
                aria-label={t('debrief.transcript.ariaLabel')}
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
          ) : (
            <p style={{ color: '#71717a', fontSize: '0.875rem' }}>
              {t('debrief.transcript.noSaved')}
            </p>
          )}

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              data-testid="retry-btn"
              onClick={handleRetry}
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
              {t('debrief.actions.retryDebrief')}
            </button>
            <button
              data-testid="replay-btn"
              onClick={handleReplayVariation}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 6,
                border: '1px solid #52525b',
                background: 'transparent',
                color: '#a1a1aa',
                cursor: 'pointer',
              }}
            >
              {t('debrief.actions.replayVariation')}
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
              {exportingText ? t('debrief.actions.exporting') : t('debrief.actions.exportMarkdown')}
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
              {t('debrief.actions.tryAnother')}
            </button>
          </div>
          <p
            data-testid="export-privacy-notice"
            style={{ fontSize: '0.75rem', color: '#52525b', margin: 0 }}
          >
            {t('debrief.actions.privacyNotice')}
          </p>
        </>
      )}

      {devMode && debriefMs !== null && (
        <div
          data-testid="debrief-latency"
          style={{ fontSize: '0.7rem', color: '#6ee7b7' }}
        >
          {t('debrief.latency', { ms: formatNumber(debriefMs, locale) })}
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
              {t('debrief.fallback')}
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
              {t('debrief.transcriptDisabled')}
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
                {t('debrief.scenario')}{' '}
                <strong style={{ color: '#f4f4f5' }}>{debrief.scenario_id ?? '—'}</strong>
              </span>
              <span style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
                {t('debrief.turns')} <strong style={{ color: '#f4f4f5' }}>{debrief.turn_count ?? 0}</strong>
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
              {t('debrief.summary')}
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
                {t('debrief.scorecard')}
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

          {/* Telemetry */}
          {debrief.metrics && (
            <TelemetryPanel metrics={debrief.metrics} />
          )}

          {/* Strengths */}
          {debrief.strengths && debrief.strengths.length > 0 && (
            <section aria-labelledby="strengths-heading">
              <h2 id="strengths-heading" style={{ marginBottom: '0.5rem', fontSize: '1.1rem' }}>
                {t('debrief.strengths')}
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
                {t('debrief.improvements')}
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
                {t('debrief.missedOpportunities')}
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
                {t('debrief.keyMoments')}
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
                {t('debrief.tryNextTime')}
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
                {t('debrief.transcript.heading')}
              </h2>
              <div
                role="log"
                aria-label={t('debrief.transcript.ariaLabel')}
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
              {t('debrief.debugJson')}
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

          {/* Voice invite card — shown once after the first real AI conversation */}
          {voiceInviteVisible && (
            <div
              data-testid="voice-invite-card"
              role="region"
              aria-label={t('debrief.voiceInvite.heading')}
              style={{
                padding: '1rem 1.25rem',
                borderRadius: 8,
                border: '1px solid rgba(99,102,241,0.35)',
                background: 'rgba(99,102,241,0.06)',
              }}
            >
              <p style={{ margin: '0 0 0.35rem', fontWeight: 600, fontSize: '0.975rem', color: '#e0e0ff' }}>
                🎙️ {t('debrief.voiceInvite.heading')}
              </p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.875rem', color: '#a1a1aa', lineHeight: 1.5 }}>
                {t('debrief.voiceInvite.description')}
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button
                  data-testid="voice-invite-setup-btn"
                  onClick={() => {
                    writeVoiceInviteState('setup')
                    setVoiceInviteVisible(false)
                    navigate('/settings')
                  }}
                  style={{
                    padding: '0.4rem 1rem',
                    borderRadius: 6,
                    border: 'none',
                    background: '#4f46e5',
                    color: '#fff',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                  }}
                >
                  {t('debrief.voiceInvite.setupButton')}
                </button>
                <button
                  data-testid="voice-invite-later-btn"
                  onClick={() => {
                    writeVoiceInviteState('dismissed')
                    setVoiceInviteVisible(false)
                  }}
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
                  {t('debrief.voiceInvite.laterButton')}
                </button>
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            {modelReadyAfterTutorial && (
              <button
                data-testid="try-real-ai-btn"
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
                {t('debrief.actions.tryWithRealAi')}
              </button>
            )}
            <button
              data-testid="replay-btn"
              onClick={handleReplayVariation}
              style={{
                padding: '0.5rem 1.5rem',
                borderRadius: 6,
                border: 'none',
                background: modelReadyAfterTutorial ? 'transparent' : '#4f46e5',
                color: modelReadyAfterTutorial ? '#a1a1aa' : '#fff',
                fontWeight: 600,
                cursor: 'pointer',
                ...(modelReadyAfterTutorial ? { border: '1px solid #52525b' } : {}),
              }}
            >
              {t('debrief.actions.replayVariation')}
            </button>
            <button
              data-testid="replay-same-btn"
              onClick={() => void handleReplaySameSetup()}
              disabled={replayingSameSetup}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 6,
                border: '1px solid #52525b',
                background: 'transparent',
                color: '#a1a1aa',
                cursor: replayingSameSetup ? 'default' : 'pointer',
              }}
            >
              {replayingSameSetup ? t('debrief.actions.starting') : t('debrief.actions.replaySameSetup')}
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
              {exporting ? t('debrief.actions.exporting') : t('debrief.actions.exportJSON')}
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
              {exportingText ? t('debrief.actions.exporting') : t('debrief.actions.exportMarkdown')}
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
              {t('debrief.actions.tryAnother')}
            </button>
          </div>

          {nextUpRecommendations.length > 0 && (
            <section
              aria-label={t('debrief.nextUp.heading')}
              data-testid="next-up-section"
              style={{
                marginTop: '1.5rem',
                padding: '0.85rem 1rem',
                border: '1px solid rgba(99,102,241,0.2)',
                borderRadius: '6px',
                background: 'rgba(99,102,241,0.04)',
              }}
            >
              <p style={{ margin: '0 0 0.6rem', fontWeight: 600, fontSize: '0.875rem', color: '#a5b4fc' }}>
                {t('debrief.nextUp.heading')}
              </p>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {nextUpRecommendations.map((rec) => (
                  <li key={`${rec.pack_id}/${rec.scenario_id}`} style={{ fontSize: '0.875rem' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', flexWrap: 'wrap' }}>
                      <Link
                        to={`/setup/${rec.scenario_id}`}
                        data-testid="next-up-link"
                        style={{ fontWeight: 600, color: '#e8e8ea', textDecoration: 'none' }}
                      >
                        {rec.title} →
                      </Link>
                      <span style={{ fontSize: '0.75rem', color: '#71717a', textTransform: 'capitalize' }}>
                        {rec.recommended_difficulty}
                      </span>
                    </div>
                    <p style={{ margin: '0.2rem 0 0', color: '#a1a1aa', fontSize: '0.8rem' }}>{rec.reason}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p
            data-testid="export-privacy-notice"
            style={{ fontSize: '0.75rem', color: '#52525b', margin: 0 }}
          >
            {t('debrief.actions.privacyNotice')}
          </p>
        </>
      )}
    </div>
  )
}

function OverallScore({ score }: { score: number }) {
  const { t } = useTranslation()
  const color = score >= 70 ? '#86efac' : score >= 40 ? '#fbbf24' : '#fca5a5'
  const rounded = Math.round(score)
  const grade =
    rounded >= 70
      ? t('debrief.score.gradeGood')
      : rounded >= 40
        ? t('debrief.score.gradeFair')
        : t('debrief.score.gradeNeedsImprovement')
  return (
    <div
      data-testid="overall-score"
      aria-label={t('debrief.score.overall', { score: rounded, grade })}
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
  const { t } = useTranslation()
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
        aria-label={t('debrief.score.dimension', { label, score: rounded })}
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
  const { t } = useTranslation()
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
          aria-label={t('debrief.transcript.goToTurn', { number: point.turn_number })}
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
            aria-label={t('debrief.keyMoment.impact', { impact: point.impact })}
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
  const { t } = useTranslation()
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
        <span>{t('debrief.transcript.turn', { number: turnNumber })}</span>
        {' · '}
        <span>{isPlayer ? t('debrief.transcript.you') : t('debrief.transcript.npc')}</span>
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

function StateArcSparkline({ arc, variable }: { arc: DebriefMetrics['state_arc']; variable: string }) {
  const { t } = useTranslation()
  const values = arc.map((e) => e.state[variable]).filter((v) => v !== undefined) as number[]
  if (values.length < 2) return null
  const W = 120
  const H = 32
  const min = 0
  const max = 100
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * W
    const y = H - ((v - min) / (max - min)) * H
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg
      width={W}
      height={H}
      aria-label={t('debrief.chart.ariaLabel', { variable })}
      style={{ overflow: 'visible', flexShrink: 0 }}
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="#6ee7b7"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

function TelemetryPanel({ metrics }: { metrics: DebriefMetrics }) {
  const playerPct = Math.round(metrics.talk_ratio * 100)
  const npcPct = 100 - playerPct

  const stateVarNames = metrics.state_arc.length > 0
    ? Object.keys(metrics.state_arc[metrics.state_arc.length - 1].state)
    : []

  return (
    <section
      aria-labelledby="telemetry-heading"
      data-testid="telemetry-panel"
      style={{
        padding: '0.75rem 1rem',
        borderRadius: 8,
        background: '#09090b',
        border: '1px solid #27272a',
      }}
    >
      <h2 id="telemetry-heading" style={{ margin: '0 0 0.75rem', fontSize: '1.1rem' }}>
        Telemetry
      </h2>

      {/* Headline numbers */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: '0.75rem',
          marginBottom: stateVarNames.length > 0 ? '1rem' : 0,
        }}
      >
        <TelemetryStat
          label="Talk ratio"
          value={`${playerPct}% / ${npcPct}%`}
          sub="player / NPC"
        />
        <TelemetryStat
          label="Words / turn"
          value={`${metrics.words_per_turn_player} / ${metrics.words_per_turn_npc}`}
          sub="player / NPC"
        />
        <TelemetryStat
          label="Questions"
          value={`${metrics.open_questions} open, ${metrics.closed_questions} closed`}
        />
        {metrics.filler_word_count > 0 && (
          <TelemetryStat
            label="Filler words"
            value={String(metrics.filler_word_count)}
          />
        )}
        {metrics.response_latency_p50_ms !== null && (
          <TelemetryStat
            label="Response latency"
            value={`p50 ${metrics.response_latency_p50_ms} ms`}
            sub={metrics.response_latency_p95_ms !== null ? `p95 ${metrics.response_latency_p95_ms} ms` : undefined}
          />
        )}
      </div>

      {/* State arc sparklines */}
      {stateVarNames.length > 0 && (
        <div>
          <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#71717a' }}>
            State meters across turns
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {stateVarNames.map((varName) => (
              <div
                key={varName}
                style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}
              >
                <span
                  style={{
                    flex: '0 0 110px',
                    fontSize: '0.75rem',
                    color: '#a1a1aa',
                    textTransform: 'capitalize',
                  }}
                >
                  {varName.replace(/_/g, ' ')}
                </span>
                <StateArcSparkline arc={metrics.state_arc} variable={varName} />
                <span style={{ fontSize: '0.7rem', color: '#6ee7b7', minWidth: 28, textAlign: 'right' }}>
                  {metrics.state_arc[metrics.state_arc.length - 1].state[varName] ?? '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function TelemetryStat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div
      style={{
        padding: '0.5rem 0.75rem',
        borderRadius: 6,
        background: '#18181b',
        border: '1px solid #27272a',
      }}
    >
      <div style={{ fontSize: '0.7rem', color: '#71717a', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f4f4f5' }}>{value}</div>
      {sub && <div style={{ fontSize: '0.7rem', color: '#71717a', marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

function OutcomeBadge({ outcome, testId }: { outcome?: string; testId?: string }) {
  const { t } = useTranslation()
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
      aria-label={t('debrief.outcomeBadge.ariaLabel', { outcome: outcome.replace(/_/g, ' ') })}
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
