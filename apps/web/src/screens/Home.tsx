// SPDX-License-Identifier: Apache-2.0
import { Link } from 'react-router-dom'
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'
import { usePackCount } from '../api/usePackCount'
import type { BadgeStatus } from '@convsim/ui'

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

  const runtimeBadgeProps = runtimeBadge(loading, health.healthy)
  const llmBadgeProps = loading
    ? { status: 'loading' as BadgeStatus, label: 'Checking…' }
    : llmReady
    ? { status: 'online' as BadgeStatus, label: llmName ?? 'Ready' }
    : { status: 'offline' as BadgeStatus, label: 'Not installed' }
  const sttBadgeProps = readinessBadge(loading, sttReady)
  const ttsBadgeProps = readinessBadge(loading, ttsReady)

  const showNoModelPrompt = !loading && health.healthy && !llmReady
  const showError = health.state === 'unavailable'

  return (
    <div>
      <h1>Conversation Simulator</h1>
      <p>Flight Simulator for conversations.</p>

      <nav
        aria-label="Primary actions"
        style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: '20rem' }}
      >
        <Link to="/library">Start a scenario</Link>
        <Link to="/workbench">Create / edit a scenario</Link>
        <Link to="/settings">Install model</Link>
        <Link to="/settings">Import pack</Link>
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

        {showError && (
          <p role="alert" style={{ color: '#cc4444', marginTop: '0.75rem' }}>
            Cannot reach the local runtime. Ensure the API server is running.
          </p>
        )}
      </section>

      {showNoModelPrompt && (
        <section aria-label="Get started without a model" style={{ marginTop: '2rem' }}>
          <h2>No model configured</h2>
          <p>Choose how to get started:</p>
          <ul style={{ listStyle: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <li>
              <Link to="/settings">Install a GGUF model</Link>
              {' — download a local model file'}
            </li>
            <li>
              <Link to="/settings">Connect Ollama</Link>
              {' — use an existing Ollama installation'}
            </li>
            <li>
              <Link to="/settings">Try text-only demo</Link>
              {' — run without a model using the fake runtime'}
            </li>
          </ul>
        </section>
      )}
    </div>
  )
}
