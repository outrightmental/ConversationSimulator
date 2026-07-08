// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'

export interface DebugTurnEntry {
  turnId: number
  role: 'npc_opening' | 'npc'
  rawPayload: Record<string, unknown>
  appliedDelta: Record<string, number>
}

// Fields that may contain hidden NPC agenda — highlighted so they can't be missed
const AGENDA_FIELDS = new Set([
  'agenda',
  'npc_agenda',
  'hidden_state',
  'private_notes',
  'internal_notes',
  'prompt_metadata',
])

// Fields stripped before copying to clipboard (never copy raw audio or secrets)
const REDACT_FIELDS = new Set(['audio', 'audio_data', 'tts_audio', 'raw_audio', 'secret'])

function redactForCopy(payload: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(payload).filter(([k]) => !REDACT_FIELDS.has(k)))
}

function JsonBlock({ data }: { data: unknown }) {
  let text: string
  try {
    text = JSON.stringify(data, null, 2)
  } catch {
    text = String(data)
  }
  return (
    <pre
      data-testid="debug-json-block"
      style={{
        margin: 0,
        padding: '0.5rem',
        background: '#0a0a0a',
        borderRadius: 4,
        fontSize: '0.7rem',
        color: '#d4d4d8',
        overflowX: 'auto',
        maxHeight: 200,
        overflowY: 'auto',
        wordBreak: 'break-all',
        whiteSpace: 'pre-wrap',
      }}
    >
      {text}
    </pre>
  )
}

function CopyButton({ payload }: { payload: Record<string, unknown> }) {
  const [label, setLabel] = useState('Copy JSON')

  function handleCopy() {
    let text: string
    try {
      text = JSON.stringify(redactForCopy(payload), null, 2)
    } catch {
      text = String(payload)
    }
    navigator.clipboard.writeText(text).then(
      () => {
        setLabel('Copied!')
        setTimeout(() => setLabel('Copy JSON'), 2000)
      },
      () => {
        setLabel('Copy failed')
        setTimeout(() => setLabel('Copy JSON'), 2000)
      },
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
      <button
        onClick={handleCopy}
        aria-label="Copy turn JSON to clipboard"
        style={{
          padding: '0.2rem 0.5rem',
          borderRadius: 4,
          border: '1px solid #3f3f46',
          background: '#18181b',
          color: '#a1a1aa',
          fontSize: '0.7rem',
          cursor: 'pointer',
        }}
      >
        {label}
      </button>
      <span aria-live="polite" style={{ fontSize: '0.65rem', color: '#fbbf24' }}>
        Raw audio and secrets redacted from copy
      </span>
    </div>
  )
}

function DebugTurnItem({ entry, index }: { entry: DebugTurnEntry; index: number }) {
  const agendaFields = Object.keys(entry.rawPayload).filter((k) => AGENDA_FIELDS.has(k))
  const hasDelta = Object.keys(entry.appliedDelta).length > 0

  return (
    <details style={{ borderBottom: '1px solid #1c1c1e', padding: '0.4rem 0' }}>
      <summary
        style={{
          cursor: 'pointer',
          fontSize: '0.75rem',
          color: '#a1a1aa',
          userSelect: 'none',
          listStyle: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
        }}
      >
        <span style={{ color: '#71717a' }}>▶</span>
        <span>Turn {index + 1}</span>
        <span style={{ color: '#52525b' }}>({entry.role})</span>
        {agendaFields.length > 0 && (
          <span
            aria-label="Contains hidden NPC agenda fields"
            style={{
              fontSize: '0.6rem',
              padding: '0 0.3rem',
              background: 'rgba(245,158,11,0.15)',
              border: '1px solid rgba(245,158,11,0.4)',
              borderRadius: 3,
              color: '#fbbf24',
            }}
          >
            agenda
          </span>
        )}
        {hasDelta && (
          <span
            style={{
              fontSize: '0.6rem',
              padding: '0 0.3rem',
              background: 'rgba(110,231,183,0.1)',
              border: '1px solid rgba(110,231,183,0.3)',
              borderRadius: 3,
              color: '#6ee7b7',
            }}
          >
            Δ state
          </span>
        )}
      </summary>

      <div style={{ marginTop: '0.4rem', display: 'flex', flexDirection: 'column', gap: '0.4rem', paddingLeft: '0.5rem' }}>
        {agendaFields.length > 0 && (
          <div
            role="note"
            aria-label="Hidden NPC agenda fields"
            style={{
              padding: '0.3rem 0.5rem',
              background: 'rgba(245,158,11,0.08)',
              border: '1px solid rgba(245,158,11,0.3)',
              borderRadius: 4,
              fontSize: '0.7rem',
              color: '#fbbf24',
            }}
          >
            Hidden NPC fields (dev only): {agendaFields.join(', ')}
          </div>
        )}

        <div>
          <div style={{ fontSize: '0.65rem', color: '#52525b', marginBottom: 2 }}>Raw payload</div>
          <JsonBlock data={entry.rawPayload} />
        </div>

        {hasDelta && (
          <div>
            <div style={{ fontSize: '0.65rem', color: '#52525b', marginBottom: 2 }}>
              Applied state delta
            </div>
            <JsonBlock data={entry.appliedDelta} />
          </div>
        )}

        <CopyButton payload={entry.rawPayload} />
      </div>
    </details>
  )
}

interface DebugDrawerProps {
  entries: DebugTurnEntry[]
}

export default function DebugDrawer({ entries }: DebugDrawerProps) {
  return (
    <details data-testid="debug-drawer">
      <summary
        style={{
          cursor: 'pointer',
          fontSize: '0.8rem',
          color: '#f59e0b',
          userSelect: 'none',
          listStyle: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <span>▶</span>
        <span>Developer debug</span>
        <span
          style={{
            fontSize: '0.6rem',
            padding: '0.1rem 0.4rem',
            background: 'rgba(245,158,11,0.15)',
            border: '1px solid rgba(245,158,11,0.4)',
            borderRadius: 4,
            color: '#fbbf24',
          }}
        >
          DEV
        </span>
        <span style={{ color: '#52525b', fontSize: '0.7rem' }}>
          {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
        </span>
      </summary>

      <div
        data-testid="debug-drawer-content"
        style={{
          marginTop: '0.5rem',
          padding: '0.5rem',
          borderRadius: 6,
          border: '1px solid rgba(245,158,11,0.25)',
          background: '#0c0c0e',
          maxHeight: 420,
          overflowY: 'auto',
        }}
      >
        <div
          role="note"
          style={{
            padding: '0.3rem 0.5rem',
            marginBottom: '0.5rem',
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 4,
            fontSize: '0.7rem',
            color: '#fca5a5',
          }}
        >
          Developer mode — internal model data is visible here. Hidden NPC fields (agenda,
          prompt metadata) never appear in the normal player view.
        </div>

        {entries.length === 0 ? (
          <p style={{ fontSize: '0.75rem', color: '#52525b', margin: 0 }}>
            No debug entries yet.
          </p>
        ) : (
          entries.map((entry, i) => (
            <DebugTurnItem key={entry.turnId} entry={entry} index={i} />
          ))
        )}
      </div>
    </details>
  )
}
