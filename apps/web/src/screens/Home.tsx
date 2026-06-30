// SPDX-License-Identifier: Apache-2.0
import { Link } from 'react-router-dom'
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'

export default function Home() {
  const { state, healthy } = useApiHealth()

  return (
    <div>
      <h1>Conversation Simulator</h1>
      <p>Flight Simulator for conversations.</p>

      <section style={{ marginTop: '2rem' }}>
        <h2>Status</h2>
        <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '0.25rem 1rem' }}>
          <dt>Local runtime</dt>
          <dd>
            <StatusBadge status={state === 'loading' ? 'loading' : healthy ? 'online' : 'offline'}>
              {state === 'loading' ? 'Checking…' : healthy ? 'Ready' : 'Unavailable'}
            </StatusBadge>
          </dd>
          <dt>LLM</dt>
          <dd><StatusBadge status="offline">Not installed</StatusBadge></dd>
          <dt>STT</dt>
          <dd><StatusBadge status="offline">Not installed</StatusBadge></dd>
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
