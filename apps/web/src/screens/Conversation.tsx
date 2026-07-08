// SPDX-License-Identifier: Apache-2.0
import { useLocation, useParams } from 'react-router-dom'
import VoiceInput from '../components/VoiceInput'

export default function Conversation() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const { state } = useLocation()
  const language = (state as { language?: string } | null)?.language

  const handleSubmit = (text: string) => {
    // Conversation turn submission — LLM integration will be wired here.
    console.debug('[Conversation] player turn:', text)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: 700 }}>
      <h1>Conversation</h1>
      <p style={{ color: '#71717a', fontSize: '0.875rem' }}>
        Session: <code>{sessionId}</code>
      </p>

      <div
        role="log"
        aria-label="Conversation transcript"
        aria-live="polite"
        style={{
          minHeight: 200,
          padding: '1rem',
          borderRadius: '8px',
          border: '1px solid #27272a',
          color: '#a1a1aa',
          fontSize: '0.9rem',
        }}
      >
        <em>Conversation transcript will appear here.</em>
      </div>

      <VoiceInput onSubmit={handleSubmit} language={language} />
    </div>
  )
}
