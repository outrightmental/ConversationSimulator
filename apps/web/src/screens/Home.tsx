// SPDX-License-Identifier: Apache-2.0
import { Link } from 'react-router-dom'
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'
import { usePackCount } from '../api/usePackCount'
import type { BadgeStatus } from '@convsim/ui'

const DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/wiki'
const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'

function runtimeBadge(loading: boolean, healthy: boolean): { status: BadgeStatus; label: string } {
  if (loading) return { status: 'loading', label: 'Checking…' }
  return healthy
    ? { status: 'online', label: 'Ready' }
    : { status: 'offline', label: 'Unavailable' }
}

function readinessBadge(loading: boolean, ready: boolean, offLabel = 'Not installed'): { status: BadgeStatus; label: string } {
  if (loading) return { status: 'loading', label: 'Checking…' }
  return ready ? { status: 'online', label: 'Ready' } : { status: 'offline', label: offLabel }
}

export default function Home() {
  const health = useApiHealth()
  const packCount = usePackCount()
  const loading = health.state === 'loading'

  const runtime = health.runtime
  const llmReady = runtime?.llm_ready ?? false
  const llmName = runtime?.llm_model_name ?? null
  const sttReady = runtime?.stt_ready ?? false
  const ttsReady = runtime?.tts_ready ?? false
  const networkRequired = runtime?.network_required ?? false
  const lastError = runtime?.last_error ?? null

  const runtimeBadgeProps = runtimeBadge(loading, health.healthy)
  const llmBadgeProps = loading
    ? { status: 'loading' as BadgeStatus, label: 'Checking…' }
    : llmReady
    ? { status: 'online' as BadgeStatus, label: llmName ?? 'Ready' }
    : { status: 'offline' as BadgeStatus, label: 'Not installed' }
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

  return (
    <div>
      <h1>Conversation Simulator</h1>
      <p>Practice interviews, negotiations, language, and difficult conversations.</p>

      <nav
        aria-label="Primary actions"
        style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: '20rem' }}
      >
        <Link to="/library">Start a scenario</Link>
        <Link to="/workbench">Create / edit a scenario</Link>
        <Link to="/settings">Install model</Link>
        <Link to="/settings">Import pack</Link>
        <a href="https://github.com/outrightmental/ConversationSimulator/blob/main/docs/scenario-authoring.md" target="_blank" rel="noreferrer">
          Creator workbench guide
        </a>
        <a href="https://github.com/outrightmental/ConversationSimulator/wiki" target="_blank" rel="noreferrer">
          Read docs
        </a>
      </nav>

      <section aria-label="System readiness" style={{ marginTop: '2rem' }}>
        <h2>Status</h2>
        <ul style={{ listStyle: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <li>
            Local runtime:{' '}
            <StatusBadge status={runtimeBadgeProps.status}>{runtimeBadgeProps.label}</StatusBadge>
          </li>
          <li>
            LLM:{' '}
            <Link to="/settings" style={{ textDecoration: 'none' }}>
              <StatusBadge status={llmBadgeProps.status}>{llmBadgeProps.label}</StatusBadge>
            </Link>
          </li>
          <li>
            STT:{' '}
            <Link to="/settings" style={{ textDecoration: 'none' }}>
              <StatusBadge status={sttBadgeProps.status}>{sttBadgeProps.label}</StatusBadge>
            </Link>
          </li>
          <li>
            TTS:{' '}
            <Link to="/settings" style={{ textDecoration: 'none' }}>
              <StatusBadge status={ttsBadgeProps.status}>{ttsBadgeProps.label}</StatusBadge>
            </Link>
          </li>
          <li>
            Network required to play:{' '}
            <StatusBadge status={networkRequired ? 'offline' : 'online'}>
              {networkRequired ? 'Yes' : 'No'}
            </StatusBadge>
          </li>
          <li>
            Packs:{' '}
            <Link to="/library" style={{ textDecoration: 'none' }}>
              <StatusBadge status={packCount > 0 ? 'online' : 'offline'}>
                {packCount > 0 ? `${packCount} installed` : 'None installed'}
              </StatusBadge>
            </Link>
          </li>
        </ul>

        {showUnreachable && (
          <div
            role="alert"
            style={{
              marginTop: '0.75rem',
              padding: '0.85rem 1rem',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '6px',
            }}
          >
            <p style={{ margin: '0 0 0.3rem', fontWeight: 600, color: '#f87171', fontSize: '0.875rem' }}>
              Cannot reach the local runtime
            </p>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
              Ensure the API server is running. If this persists, check the logs folder or report
              an issue.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.8rem' }}>
              <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
                Troubleshooting docs
              </a>
              <span style={{ color: '#52525b' }}>·</span>
              <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
                Report an issue
              </a>
            </div>
          </div>
        )}
        {lastError && (
          <div
            role="alert"
            style={{
              marginTop: '0.75rem',
              padding: '0.85rem 1rem',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '6px',
            }}
          >
            {isPortConflict ? (
              <>
                <p style={{ margin: '0 0 0.3rem', fontWeight: 600, color: '#f87171', fontSize: '0.875rem' }}>
                  Port conflict
                </p>
                <p style={{ margin: '0 0 0.4rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                  A required port is already in use by another process. Try closing other apps,
                  then restart Conversation Simulator.
                </p>
                <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: '#71717a' }}>
                  Details: {lastError}
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.8rem' }}>
                  <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
                    Port troubleshooting
                  </a>
                  <span style={{ color: '#52525b' }}>·</span>
                  <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
                    Report an issue
                  </a>
                </div>
              </>
            ) : (
              <>
                <p style={{ margin: '0 0 0.3rem', fontSize: '0.875rem', color: '#f87171' }}>
                  Last error: {lastError}
                </p>
                <a
                  href={ISSUES_URL}
                  target="_blank"
                  rel="noreferrer"
                  style={{ fontSize: '0.8rem', color: '#71717a' }}
                >
                  Report an issue
                </a>
              </>
            )}
          </div>
        )}
      </section>

      {showNoModelPrompt && (
        <section aria-label="Get started without a model" style={{ marginTop: '2rem' }}>
          <h2>No model configured</h2>
          <p style={{ color: '#a1a1aa', fontSize: '0.875rem', marginBottom: '1rem' }}>
            Choose how to get started. You can change this at any time from{' '}
            <Link to="/settings" style={{ color: '#71717a' }}>Settings</Link>.
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
                Install a GGUF model
              </p>
              <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                Download a local model file. Works offline after the initial download.
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
                Install a GGUF model →
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
                Connect Ollama
              </p>
              <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                Use an existing Ollama installation. No additional download required.
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
                Connect Ollama →
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
                Try text-only demo
              </p>
              <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                Explore the interface now using scripted NPC responses — no model needed.
                Response quality is limited compared to a real AI model.
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
                Try text-only demo →
              </Link>
            </div>
          </div>
        </section>
      )}

      {showMissingPack && (
        <section
          aria-label="No scenario packs installed"
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
            No scenario packs installed
          </p>
          <p style={{ margin: '0 0 0.6rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
            Your model is ready but there are no packs to play. Import a pack or browse the
            scenario library.
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
            Go to library →
          </Link>
        </section>
      )}

      <section aria-label="Help and resources" style={{ marginTop: '2.5rem', borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: '1.5rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>Help</h2>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.875rem' }}>
          <li>
            <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              Documentation
            </a>
          </li>
          <li>
            <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              Report an issue
            </a>
          </li>
          <li style={{ color: '#52525b' }}>
            Logs folder:{' '}
            <code style={{ fontSize: '0.8rem', color: '#71717a' }}>~/.convsim/logs</code>
            {' (exact path shown in the local folders panel)'}
          </li>
          <li style={{ color: '#52525b' }}>
            Data folder:{' '}
            <code style={{ fontSize: '0.8rem', color: '#71717a' }}>~/.convsim</code>
            {' (exact path shown in the local folders panel)'}
          </li>
        </ul>
      </section>
    </div>
  )
}
