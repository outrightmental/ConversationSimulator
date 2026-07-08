// SPDX-License-Identifier: Apache-2.0
import { Link } from 'react-router-dom'
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'

function sttBadgeStatus(sttStatus: string | undefined): 'online' | 'offline' | 'loading' {
  if (!sttStatus) return 'offline'
  if (sttStatus === 'ready') return 'online'
  if (sttStatus === 'starting') return 'loading'
  return 'offline'
}

function sttBadgeLabel(sttStatus: string | undefined, loading: boolean): string {
  if (loading) return 'Checking…'
  if (!sttStatus || sttStatus === 'unavailable') return 'Not installed'
  if (sttStatus === 'ready') return 'Ready'
  if (sttStatus === 'starting') return 'Starting…'
  return 'Unavailable'
}

export default function Home() {
  const { state, healthy, stt } = useApiHealth()
  const loading = state === 'loading'

  return (
    <div>
      <h1>Conversation Simulator</h1>
      <p>Flight Simulator for conversations.</p>

      <section style={{ marginTop: '2rem' }}>
        <h2>Status</h2>
        <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '0.25rem 1rem' }}>
          <dt>Local runtime</dt>
          <dd>
            <StatusBadge status={loading ? 'loading' : healthy ? 'online' : 'offline'}>
              {loading ? 'Checking…' : healthy ? 'Ready' : 'Unavailable'}
            </StatusBadge>
          </dd>
          <dt>LLM</dt>
          <dd><StatusBadge status="offline">Not installed</StatusBadge></dd>
          <dt>STT</dt>
          <dd>
            <StatusBadge status={loading ? 'loading' : sttBadgeStatus(stt?.status)}>
              {sttBadgeLabel(stt?.status, loading)}
            </StatusBadge>
          </dd>
          <dt>TTS</dt>
          <dd><StatusBadge status="offline">Not installed</StatusBadge></dd>
          <dt>Network required to play</dt>
          <dd>No</dd>
        </dl>
      </section>

      <nav style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: '20rem' }}>
        <Link to="/library">Start a scenario</Link>
        <Link to="/workbench">Create / edit a scenario</Link>
        <Link to="/settings">Install model</Link>
        <Link to="/settings">Import pack</Link>
      </nav>
    </div>
  )
}
