// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'
import { usePackCount } from '../api/usePackCount'
import { useTranslation } from '../i18n'
import { useLogbookProfile } from '../api/useLogbookProfile'
import { api } from '../api/client'
import RuntimeRecoveryCard from '../components/RuntimeRecoveryCard'
import type { BadgeStatus } from '@convsim/ui'

const DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/wiki'
const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'
const TROUBLESHOOTING_BASE =
  'https://github.com/outrightmental/ConversationSimulator/blob/main/docs/troubleshooting.md'

export default function Home() {
  const health = useApiHealth()
  const packCount = usePackCount()
  const logbook = useLogbookProfile()
  const loading = health.state === 'loading'
  const { t } = useTranslation()
  const { update, dismiss, install } = useAppUpdate()

  const [isRestartingSidecar, setIsRestartingSidecar] = useState(false)

  const runtime = health.runtime
  const llmReady = runtime?.llm_ready ?? false
  const llmName = runtime?.llm_model_name ?? null
  const sttReady = runtime?.stt_ready ?? false
  const ttsReady = runtime?.tts_ready ?? false
  const networkRequired = runtime?.network_required ?? false
  const lastError = runtime?.last_error ?? null

  function runtimeBadge(
    isLoading: boolean,
    healthy: boolean,
  ): { status: BadgeStatus; label: string } {
    if (isLoading) return { status: 'loading', label: t('home.status.checking') }
    return healthy
      ? { status: 'online', label: t('home.status.ready') }
      : { status: 'offline', label: t('home.status.unavailable') }
  }

  function readinessBadge(
    isLoading: boolean,
    ready: boolean,
    offLabel = t('home.status.notInstalled'),
  ): { status: BadgeStatus; label: string } {
    if (isLoading) return { status: 'loading', label: t('home.status.checking') }
    return ready
      ? { status: 'online', label: t('home.status.ready') }
      : { status: 'offline', label: offLabel }
  }

  const runtimeBadgeProps = runtimeBadge(loading, health.healthy)
  const llmBadgeProps = loading
    ? { status: 'loading' as BadgeStatus, label: t('home.status.checking') }
    : llmReady
    ? { status: 'online' as BadgeStatus, label: llmName ?? t('home.status.ready') }
    : { status: 'offline' as BadgeStatus, label: t('home.status.notInstalled') }
  const sttBadgeProps = readinessBadge(loading, sttReady)
  const ttsBadgeProps = readinessBadge(loading, ttsReady)

  const showNoModelPrompt = !loading && health.healthy && !llmReady
  const showUnreachable = health.state === 'unavailable' && !health.runtime
  const showMissingPack = !loading && health.healthy && llmReady && packCount === 0
  const isPortConflict =
    lastError != null &&
    /eaddrinuse|address[\s_-]?already[\s_-]?in[\s_-]?use|port[\s_-]?\d+.*(?:busy|in[\s_-]?use)|port[\s_-]?conflict/i.test(
      lastError,
    )

  const packsBadgeStatus: BadgeStatus = packCount > 0 ? 'online' : 'offline'
  const packsBadgeLabel =
    packCount > 0
      ? t('home.status.packsInstalledCount', { count: packCount })
      : t('home.status.noneInstalled')

  async function handleRestartSidecar() {
    setIsRestartingSidecar(true)
    try {
      const statusResult = await api.getSidecarStatus()
      const modelPath = statusResult.ok ? statusResult.data.model_path : null
      await api.stopSidecar()
      if (modelPath) {
        await api.startSidecar(modelPath)
      }
      // The polling in useApiHealth will pick up the healthy state within 3 s.
      health.refetch()
    } finally {
      setIsRestartingSidecar(false)
    }
  }

  return (
    <div>
      {update.status === 'available' && update.version && update.releaseUrl && (
        <UpdateBanner
          version={update.version}
          releaseUrl={update.releaseUrl}
          onViewNotes={dismiss}
          onInstall={install}
          onDismiss={dismiss}
        />
      )}
      <h1>{t('home.title')}</h1>
      <p>{t('home.tagline')}</p>

      <nav
        aria-label={t('home.primaryActions')}
        style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: '20rem' }}
      >
        <Link to="/library">{t('home.startScenario')}</Link>
        <Link to="/workbench">{t('home.createEdit')}</Link>
        <Link to="/settings">{t('home.installModel')}</Link>
        <Link to="/settings">{t('home.importPack')}</Link>
        <a href="https://github.com/outrightmental/ConversationSimulator/blob/main/docs/scenario-authoring.md" target="_blank" rel="noreferrer">
          {t('home.creatorWorkbenchGuide')}
        </a>
        <a href="https://github.com/outrightmental/ConversationSimulator/wiki" target="_blank" rel="noreferrer">
          {t('home.readDocs')}
        </a>
      </nav>

      <section aria-label={t('home.yourTraining')} style={{ marginTop: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>{t('home.yourTraining')}</h2>
        {logbook.state === 'loading' && (
          <p style={{ color: '#71717a', fontSize: '0.875rem' }}>{t('home.training.loading')}</p>
        )}
        {logbook.state === 'ready' && logbook.profile && logbook.profile.total_sessions === 0 && (
          <div
            style={{
              padding: '0.85rem 1rem',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: '6px',
              fontSize: '0.875rem',
              color: '#a1a1aa',
            }}
          >
            <p style={{ margin: '0 0 0.4rem' }}>{t('home.training.empty')}</p>
            <p style={{ margin: 0, fontSize: '0.8rem' }}>
              {t('home.training.emptyCta')}{' '}
              <Link to="/library" style={{ color: '#6366f1' }}>
                {t('home.training.startNow')}
              </Link>
            </p>
          </div>
        )}
        {logbook.state === 'ready' && logbook.profile && logbook.profile.total_sessions > 0 && (
          <div
            style={{
              padding: '0.85rem 1rem',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: '6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            }}
          >
            <ul
              style={{
                listStyle: 'none',
                padding: 0,
                margin: 0,
                display: 'flex',
                flexWrap: 'wrap',
                gap: '0.75rem 1.5rem',
                fontSize: '0.875rem',
              }}
            >
              <li>
                <span style={{ color: '#71717a' }}>{t('home.training.sessions')}: </span>
                <strong>{logbook.profile.total_sessions}</strong>
              </li>
              <li>
                <span style={{ color: '#71717a' }}>{t('home.training.streak')}: </span>
                <strong>{logbook.profile.streak_days} {logbook.profile.streak_days !== 1 ? t('home.training.days') : t('home.training.day')}</strong>
              </li>
              {logbook.profile.strongest_dimension && (
                <li>
                  <span style={{ color: '#71717a' }}>{t('home.training.strongest')}: </span>
                  <strong style={{ color: '#4ade80' }}>
                    {logbook.profile.strongest_dimension.replace(/_/g, ' ')}
                  </strong>
                </li>
              )}
              {logbook.profile.weakest_dimension &&
                logbook.profile.weakest_dimension !== logbook.profile.strongest_dimension && (
                  <li>
                    <span style={{ color: '#71717a' }}>{t('home.training.needsWork')}: </span>
                    <strong style={{ color: '#f87171' }}>
                      {logbook.profile.weakest_dimension.replace(/_/g, ' ')}
                    </strong>
                  </li>
                )}
              {logbook.profile.last_session_delta !== null && (
                <li>
                  <span style={{ color: '#71717a' }}>{t('home.training.lastSession')}: </span>
                  <strong
                    style={{
                      color:
                        logbook.profile.last_session_delta > 0
                          ? '#4ade80'
                          : logbook.profile.last_session_delta < 0
                          ? '#f87171'
                          : '#a1a1aa',
                    }}
                  >
                    {logbook.profile.last_session_delta >= 0 ? '+' : ''}
                    {Math.round(logbook.profile.last_session_delta)}
                  </strong>
                </li>
              )}
            </ul>
            <Link to="/logbook" style={{ fontSize: '0.8rem', color: '#6366f1', alignSelf: 'flex-start' }}>
              {t('home.training.viewFull')}
            </Link>
          </div>
        )}
      </section>

      <section aria-label={t('home.readinessSection')} style={{ marginTop: '2rem' }}>
        <h2>{t('home.status.heading')}</h2>
        <ul style={{ listStyle: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <li>
            {t('home.status.localRuntime')}:{' '}
            {runtimeBadgeProps.status === 'offline' ? (
              <a href="#runtime-recovery" style={{ textDecoration: 'none' }}>
                <StatusBadge status={runtimeBadgeProps.status}>{runtimeBadgeProps.label}</StatusBadge>
              </a>
            ) : (
              <StatusBadge status={runtimeBadgeProps.status}>{runtimeBadgeProps.label}</StatusBadge>
            )}
          </li>
          <li>
            {t('home.status.llm')}:{' '}
            <Link to="/settings" style={{ textDecoration: 'none' }}>
              <StatusBadge status={llmBadgeProps.status}>{llmBadgeProps.label}</StatusBadge>
            </Link>
          </li>
          <li>
            {t('home.status.stt')}:{' '}
            <Link to="/settings" style={{ textDecoration: 'none' }}>
              <StatusBadge status={sttBadgeProps.status}>{sttBadgeProps.label}</StatusBadge>
            </Link>
          </li>
          <li>
            {t('home.status.tts')}:{' '}
            <Link to="/settings" style={{ textDecoration: 'none' }}>
              <StatusBadge status={ttsBadgeProps.status}>{ttsBadgeProps.label}</StatusBadge>
            </Link>
          </li>
          <li>
            {t('home.status.networkRequired')}:{' '}
            <StatusBadge status={networkRequired ? 'offline' : 'online'}>
              {networkRequired ? t('home.status.yes') : t('home.status.no')}
            </StatusBadge>
          </li>
          <li>
            {t('home.status.packs')}:{' '}
            <Link to="/library" style={{ textDecoration: 'none' }}>
              <StatusBadge status={packsBadgeStatus}>{packsBadgeLabel}</StatusBadge>
            </Link>
          </li>
        </ul>

        {/* Recovery cards — anchored so the status strip can jump to them */}
        <div id="runtime-recovery">
          {showUnreachable && (
            <RuntimeRecoveryCard
              title={t('home.unreachable.title')}
              description={t('home.unreachable.message')}
              troubleshootingHref={`${TROUBLESHOOTING_BASE}#engine-startup-failure`}
              troubleshootingLabel={t('home.unreachable.troubleshootingDocs')}
              primaryAction={{
                label: t('home.unreachable.restart'),
                onClick: () => window.location.reload(),
              }}
              secondaryAction={{
                label: t('home.unreachable.openSupport'),
                href: '/support',
              }}
            />
          )}
          {lastError && (
            isPortConflict ? (
              <RuntimeRecoveryCard
                title={t('home.portConflict.title')}
                description={t('home.portConflict.message')}
                errorDetail={t('home.portConflict.details', { error: lastError })}
                troubleshootingHref={`${TROUBLESHOOTING_BASE}#port-conflicts`}
                troubleshootingLabel={t('home.portConflict.portTroubleshooting')}
                primaryAction={{
                  label: t('home.recovery.restartEngine'),
                  loadingLabel: t('home.recovery.restarting'),
                  onClick: () => void handleRestartSidecar(),
                  loading: isRestartingSidecar,
                }}
                secondaryAction={{
                  label: t('home.recovery.openSupport'),
                  href: '/support',
                }}
              />
            ) : (
              <RuntimeRecoveryCard
                title={t('home.lastError.message', { error: lastError })}
                description=""
                troubleshootingHref={`${TROUBLESHOOTING_BASE}#engine-startup-failure`}
                troubleshootingLabel={t('home.recovery.troubleshootingDocs')}
                primaryAction={{
                  label: t('home.recovery.restartEngine'),
                  loadingLabel: t('home.recovery.restarting'),
                  onClick: () => void handleRestartSidecar(),
                  loading: isRestartingSidecar,
                }}
                secondaryAction={{
                  label: t('home.recovery.openSupport'),
                  href: '/support',
                }}
                tertiaryAction={{
                  label: t('home.lastError.reportIssue'),
                  href: ISSUES_URL,
                }}
              />
            )
          )}
        </div>
      </section>

      {showNoModelPrompt && (
        <section aria-label={t('home.getStartedSection')} style={{ marginTop: '2rem' }}>
          <h2>{t('home.noModel.heading')}</h2>
          <p style={{ color: '#a1a1aa', fontSize: '0.875rem', marginBottom: '1rem' }}>
            {t('home.noModel.description')}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div
              style={{
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '0.85rem 1rem',
              }}
            >
              <p style={{ margin: '0 0 0.25rem', fontWeight: 600, fontSize: '0.875rem' }}>
                {t('home.noModel.gguf.title')}
              </p>
              <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                {t('home.noModel.gguf.description')}
              </p>
              <Link
                to="/model-manager"
                style={{
                  fontSize: '0.8rem',
                  padding: '0.3rem 0.7rem',
                  borderRadius: '4px',
                  border: '1px solid rgba(255,255,255,0.15)',
                  color: '#e8e8ea',
                  textDecoration: 'none',
                  display: 'inline-block',
                }}
              >
                {t('home.noModel.gguf.action')}
              </Link>
            </div>

            <div
              style={{
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '0.85rem 1rem',
              }}
            >
              <p style={{ margin: '0 0 0.25rem', fontWeight: 600, fontSize: '0.875rem' }}>
                {t('home.noModel.ollama.title')}
              </p>
              <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                {t('home.noModel.ollama.description')}
              </p>
              <Link
                to="/model-manager"
                style={{
                  fontSize: '0.8rem',
                  padding: '0.3rem 0.7rem',
                  borderRadius: '4px',
                  border: '1px solid rgba(255,255,255,0.15)',
                  color: '#e8e8ea',
                  textDecoration: 'none',
                  display: 'inline-block',
                }}
              >
                {t('home.noModel.ollama.action')}
              </Link>
            </div>

            <div
              style={{
                border: '1px solid rgba(251,191,36,0.2)',
                borderRadius: '8px',
                padding: '0.85rem 1rem',
              }}
            >
              <p style={{ margin: '0 0 0.25rem', fontWeight: 600, fontSize: '0.875rem' }}>
                {t('home.noModel.demo.title')}
              </p>
              <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                {t('home.noModel.demo.description')}
              </p>
              <Link
                to="/library"
                style={{
                  fontSize: '0.8rem',
                  padding: '0.3rem 0.7rem',
                  borderRadius: '4px',
                  border: '1px solid rgba(251,191,36,0.3)',
                  color: '#fbbf24',
                  textDecoration: 'none',
                  display: 'inline-block',
                }}
              >
                {t('home.noModel.demo.action')}
              </Link>
            </div>
          </div>
        </section>
      )}

      {showMissingPack && (
        <section
          aria-label={t('home.missingPack.title')}
          role="status"
          style={{
            marginTop: '2rem',
            padding: '0.85rem 1rem',
            background: 'rgba(251,191,36,0.06)',
            border: '1px solid rgba(251,191,36,0.25)',
            borderRadius: '8px',
          }}
        >
          <p style={{ margin: '0 0 0.3rem', fontWeight: 600, color: '#fbbf24', fontSize: '0.875rem' }}>
            {t('home.missingPack.title')}
          </p>
          <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
            {t('home.missingPack.description')}
          </p>
          <Link
            to="/library"
            style={{
              fontSize: '0.8rem',
              padding: '0.3rem 0.7rem',
              borderRadius: '4px',
              border: '1px solid rgba(251,191,36,0.3)',
              color: '#fbbf24',
              textDecoration: 'none',
              display: 'inline-block',
            }}
          >
            {t('home.missingPack.action')}
          </Link>
        </section>
      )}

      <section aria-label={t('home.helpSection')} style={{ marginTop: '2.5rem', borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: '1.5rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          {t('home.help.heading')}
        </h2>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.875rem' }}>
          <li>
            <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              {t('home.help.documentation')}
            </a>
          </li>
          <li>
            <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              {t('home.help.reportIssue')}
            </a>
          </li>
          <li style={{ color: '#52525b' }}>
            {t('home.help.logsFolder')}{' '}
            <code style={{ fontSize: '0.8rem', color: '#71717a' }}>{t('home.help.logsPath')}</code>
            {' '}{t('home.help.logsContext')}
          </li>
          <li style={{ color: '#52525b' }}>
            {t('home.help.dataFolder')}{' '}
            <code style={{ fontSize: '0.8rem', color: '#71717a' }}>{t('home.help.dataPath')}</code>
            {' '}{t('home.help.dataContext')}
          </li>
        </ul>
      </section>
    </div>
  )
}
