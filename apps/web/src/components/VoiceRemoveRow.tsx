// SPDX-License-Identifier: Apache-2.0
//
// Remove the in-app voice install from Settings, and get the disk space back.
// Shown only when the in-app install has files on disk; a voice the player set
// up by hand (a whisper-cli on the PATH, a Kokoro server) is not the app's to
// remove and is never touched.
import { useState } from 'react'
import type { UseVoiceInstall } from '../hooks/useVoiceInstall'
import { formatDownloadSize } from '../lib/voiceInstall'
import { ApiErrorView } from './ApiErrorView'

export default function VoiceRemoveRow({ voice }: { voice: UseVoiceInstall }) {
  const [confirming, setConfirming] = useState(false)
  const [freed, setFreed] = useState<string | null>(null)
  const { status, busy, installing, error, remove } = voice
  const installedBytes = status?.installed_bytes ?? 0

  if (freed != null) {
    return (
      <p role="status" data-testid="voice-removed" style={{ fontSize: '0.85rem', color: '#a1a1aa' }}>
        Voice removed; {freed} freed. Text keeps working, and you can install voice again any time.
      </p>
    )
  }
  if (status == null || installedBytes <= 0 || installing) return null
  const size = formatDownloadSize(installedBytes)

  const buttonStyle = {
    padding: '0.4rem 0.9rem',
    borderRadius: '4px',
    border: '1px solid rgba(255,255,255,0.15)',
    background: 'rgba(255,255,255,0.05)',
    color: '#d4d4d8',
    fontSize: '0.85rem',
    cursor: busy ? 'progress' : 'pointer',
  } as const

  return (
    <div data-testid="voice-remove" style={{ marginBottom: '1.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '1rem' }}>
        <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>Built-in voice</span>
        <span style={{ fontSize: '0.8rem', color: '#a1a1aa' }}>{size} on disk</span>
      </div>
      {!confirming ? (
        <button type="button" onClick={() => setConfirming(true)} disabled={busy} style={{ ...buttonStyle, marginTop: '0.5rem' }}>
          Remove voice
        </button>
      ) : (
        <div style={{ marginTop: '0.5rem' }}>
          <p style={{ margin: '0 0 0.5rem', fontSize: '0.85rem', color: '#d4d4d8' }}>
            Remove voice from this computer? It frees {size}. Conversations continue in text,
            and you can install voice again any time.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              disabled={busy}
              style={{ ...buttonStyle, borderColor: 'rgba(239,68,68,0.5)', color: '#fca5a5' }}
              onClick={async () => {
                const ok = await remove()
                setConfirming(false)
                if (ok) setFreed(size)
              }}
            >
              {busy ? 'Removing…' : 'Remove'}
            </button>
            <button type="button" disabled={busy} style={buttonStyle} onClick={() => setConfirming(false)}>
              Keep voice
            </button>
          </div>
        </div>
      )}
      {error && <ApiErrorView error={error} compact context="VoiceRemove" />}
    </div>
  )
}
