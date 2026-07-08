// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { readPrivacyPref, writePrivacyPref, PRIVACY_KEYS } from '../privacyPrefs'

type ClearState = 'idle' | 'confirming' | 'clearing' | 'done' | 'error'

interface PrivacyToggleProps {
  id: string
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  description: string
}

function PrivacyToggle({ id, label, checked, onChange, description }: PrivacyToggleProps) {
  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          style={{ width: '1rem', height: '1rem' }}
          aria-describedby={`${id}-desc`}
        />
        <span style={{ fontWeight: 500 }}>{label}</span>
      </label>
      <p id={`${id}-desc`} style={{ margin: '0.25rem 0 0 1.5rem', fontSize: '0.85rem', color: '#a1a1aa' }}>
        {description}
      </p>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.4rem' }}>
      {children}
    </h2>
  )
}

export default function Settings() {
  const [saveTranscripts, setSaveTranscripts] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveTranscripts, true))
  const [saveTtsCache, setSaveTtsCache] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveTtsCache, true))
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [saveRawAudio, setSaveRawAudio] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveRawAudio, false))

  function handleSaveTranscriptsChange(v: boolean) {
    setSaveTranscripts(v)
    writePrivacyPref(PRIVACY_KEYS.saveTranscripts, v)
  }

  function handleSaveTtsCacheChange(v: boolean) {
    setSaveTtsCache(v)
    writePrivacyPref(PRIVACY_KEYS.saveTtsCache, v)
  }

  function handleSaveRawAudioChange(v: boolean) {
    setSaveRawAudio(v)
    writePrivacyPref(PRIVACY_KEYS.saveRawAudio, v)
  }

  const [dataFolder, setDataFolder] = useState<string | null>(null)
  const [dataFolderError, setDataFolderError] = useState(false)

  const [clearState, setClearState] = useState<ClearState>('idle')
  const [clearError, setClearError] = useState<string | null>(null)
  const [deletedCount, setDeletedCount] = useState<number | null>(null)

  useEffect(() => {
    api.getDataFolder()
      .then((r) => setDataFolder(r.path))
      .catch(() => setDataFolderError(true))
  }, [])

  async function handleClearLocalData() {
    if (clearState === 'idle' || clearState === 'done' || clearState === 'error') {
      setClearState('confirming')
      return
    }
    if (clearState === 'confirming') {
      setClearState('clearing')
      setClearError(null)
      try {
        const result = await api.clearLocalData()
        setDeletedCount(result.deleted_sessions)
        setClearState('done')
      } catch (err) {
        setClearError(err instanceof Error ? err.message : 'Unknown error')
        setClearState('error')
      }
    }
  }

  function cancelClear() {
    setClearState('idle')
    setClearError(null)
  }

  const clearButtonLabel =
    clearState === 'confirming'
      ? 'Confirm — delete everything'
      : clearState === 'clearing'
        ? 'Clearing…'
        : 'Clear all local data'

  return (
    <div style={{ maxWidth: '640px' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>Settings</h1>

      {/* Privacy notice */}
      <div
        role="note"
        aria-label="local-only notice"
        style={{
          background: 'rgba(34,197,94,0.08)',
          border: '1px solid rgba(34,197,94,0.25)',
          borderRadius: '6px',
          padding: '0.75rem 1rem',
          marginBottom: '2rem',
          fontSize: '0.9rem',
          color: '#86efac',
        }}
      >
        Conversations are processed entirely on your device. No conversation data is ever sent to
        external servers.
      </div>

      {/* Transcript saving */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Transcript</SectionHeading>
        <PrivacyToggle
          id="save-transcripts"
          label="Save transcripts locally"
          checked={saveTranscripts}
          onChange={handleSaveTranscriptsChange}
          description={
            saveTranscripts
              ? 'Conversation transcripts are saved to your local data folder only — never uploaded anywhere.'
              : 'Transcripts will not be saved. This session\'s conversation cannot be exported or searched after it ends.'
          }
        />
        {!saveTranscripts && (
          <p
            aria-live="polite"
            style={{ fontSize: '0.85rem', color: '#fbbf24', margin: '0 0 0 1.5rem' }}
          >
            Not saved — transcript will be lost when this session ends.
          </p>
        )}
      </section>

      {/* TTS cache */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Voice output</SectionHeading>
        <PrivacyToggle
          id="save-tts-cache"
          label="Cache TTS audio locally"
          checked={saveTtsCache}
          onChange={handleSaveTtsCacheChange}
          description="Caching generated speech speeds up repeated phrases. Cached audio stays on your device and is never shared."
        />
      </section>

      {/* Data folder */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Data folder</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.5rem' }}>
          All local data (sessions, transcripts, caches) is stored in:
        </p>
        {dataFolderError ? (
          <p style={{ fontSize: '0.875rem', color: '#f87171' }}>Could not retrieve data folder path.</p>
        ) : dataFolder === null ? (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Loading…</p>
        ) : (
          <code
            data-testid="data-folder-path"
            style={{
              display: 'block',
              padding: '0.5rem 0.75rem',
              background: 'rgba(255,255,255,0.05)',
              borderRadius: '4px',
              fontSize: '0.8rem',
              wordBreak: 'break-all',
            }}
          >
            {dataFolder}
          </code>
        )}
      </section>

      {/* Clear all local data */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Clear local data</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Permanently deletes all sessions, transcripts, and cached data from your device. Installed
          models are not removed.
        </p>

        {clearState === 'confirming' && (
          <div
            role="alert"
            style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.4)',
              borderRadius: '6px',
              padding: '0.75rem 1rem',
              marginBottom: '0.75rem',
              fontSize: '0.875rem',
              color: '#fca5a5',
            }}
          >
            This will permanently delete all sessions and transcripts from this device. This cannot
            be undone.
          </div>
        )}

        {clearState === 'done' && (
          <p style={{ fontSize: '0.875rem', color: '#86efac', marginBottom: '0.5rem' }}>
            {deletedCount === 1
              ? '1 session deleted.'
              : `${deletedCount ?? 0} sessions deleted.`}{' '}
            Local data has been cleared.
          </p>
        )}

        {clearState === 'error' && (
          <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', marginBottom: '0.5rem' }}>
            {clearError ?? 'Failed to clear data. Please try again.'}
          </p>
        )}

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handleClearLocalData}
            disabled={clearState === 'clearing'}
            aria-label={clearButtonLabel}
            style={{
              padding: '0.4rem 0.9rem',
              borderRadius: '4px',
              border: 'none',
              cursor: clearState === 'clearing' ? 'wait' : 'pointer',
              background: clearState === 'confirming' ? '#dc2626' : 'rgba(239,68,68,0.15)',
              color: clearState === 'confirming' ? '#fff' : '#f87171',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            {clearButtonLabel}
          </button>

          {clearState === 'confirming' && (
            <button
              onClick={cancelClear}
              style={{
                padding: '0.4rem 0.9rem',
                borderRadius: '4px',
                border: '1px solid rgba(255,255,255,0.15)',
                cursor: 'pointer',
                background: 'transparent',
                color: '#a1a1aa',
                fontSize: '0.875rem',
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </section>

      {/* Advanced */}
      <section>
        <button
          onClick={() => setShowAdvanced((v) => !v)}
          aria-expanded={showAdvanced}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: '#71717a',
            fontSize: '0.85rem',
            padding: 0,
            marginBottom: '0.75rem',
          }}
        >
          {showAdvanced ? '▾ Hide advanced' : '▸ Show advanced'}
        </button>

        {showAdvanced && (
          <div>
            <SectionHeading>Advanced</SectionHeading>
            <PrivacyToggle
              id="save-raw-audio"
              label="Save raw audio recordings (advanced)"
              checked={saveRawAudio}
              onChange={handleSaveRawAudioChange}
              description="Off by default. When enabled, unprocessed microphone recordings are saved to your data folder for debugging voice input. Enable only if you are diagnosing STT accuracy issues."
            />
            {saveRawAudio && (
              <p
                aria-live="polite"
                style={{ fontSize: '0.85rem', color: '#fbbf24', margin: '0 0 0 1.5rem' }}
              >
                Raw audio saving is on. Recordings will be stored locally until you clear local data.
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
