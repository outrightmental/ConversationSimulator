// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { api } from '../api/client'
import { readPrivacyPref, writePrivacyPref, PRIVACY_KEYS } from '../privacyPrefs'

type ClearState = 'idle' | 'confirming' | 'clearing' | 'done' | 'error'

interface SessionSummary {
  session_id: string
  scenario_id: string
  state: string
  created_at: string
}

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

function SectionHeading({ children }: { children: ReactNode }) {
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

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [sessionsError, setSessionsError] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const loadSessions = useCallback(() => {
    api.listSessions()
      .then((r) => { setSessions(r.sessions); setSessionsError(false) })
      .catch(() => setSessionsError(true))
  }, [])

  useEffect(() => {
    api.getDataFolder()
      .then((r) => setDataFolder(r.path))
      .catch(() => setDataFolderError(true))
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

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
        setDeleteError(null)
        setExportError(null)
        setClearState('done')
        loadSessions()
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

  async function handleDeleteSession(sessionId: string) {
    setDeletingId(sessionId)
    setDeleteError(null)
    try {
      await api.deleteSession(sessionId)
      setSessions((prev) => prev?.filter((s) => s.session_id !== sessionId) ?? null)
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete session')
    } finally {
      setDeletingId(null)
      setDeleteConfirmId(null)
    }
  }

  async function handleExportSession(sessionId: string) {
    setExportError(null)
    try {
      const data = await api.exportSession(sessionId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `session-${sessionId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Failed to export session')
    }
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

      {/* Your sessions */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Your sessions</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Export a session as JSON or delete it permanently.
        </p>
        {sessionsError && (
          <p style={{ fontSize: '0.875rem', color: '#f87171' }}>Could not load sessions.</p>
        )}
        {deleteError && (
          <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', marginBottom: '0.5rem' }}>
            {deleteError}
          </p>
        )}
        {exportError && (
          <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', marginBottom: '0.5rem' }}>
            {exportError}
          </p>
        )}
        {!sessionsError && sessions === null && (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Loading…</p>
        )}
        {!sessionsError && sessions !== null && sessions.length === 0 && (
          <p data-testid="no-sessions" style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
            No sessions yet.
          </p>
        )}
        {!sessionsError && sessions !== null && sessions.length > 0 && (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {sessions.map((s) => (
              <li
                key={s.session_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.5rem',
                  padding: '0.5rem 0',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  fontSize: '0.875rem',
                }}
              >
                <span style={{ color: '#d4d4d8', flex: 1, minWidth: 0 }}>
                  <span style={{ fontWeight: 500 }}>{s.scenario_id}</span>
                  <span style={{ color: '#71717a', marginLeft: '0.5rem' }}>
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                  <span
                    style={{
                      marginLeft: '0.5rem',
                      fontSize: '0.75rem',
                      color: s.state === 'Ended' ? '#86efac' : '#fbbf24',
                    }}
                  >
                    {s.state}
                  </span>
                </span>
                <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
                  <button
                    aria-label={`Export session ${s.session_id}`}
                    onClick={() => handleExportSession(s.session_id)}
                    style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                      border: '1px solid rgba(255,255,255,0.15)',
                      cursor: 'pointer',
                      background: 'transparent',
                      color: '#a1a1aa',
                      fontSize: '0.8rem',
                    }}
                  >
                    Export
                  </button>
                  {deleteConfirmId === s.session_id ? (
                    <>
                      <button
                        aria-label={`Confirm delete session ${s.session_id}`}
                        onClick={() => handleDeleteSession(s.session_id)}
                        disabled={deletingId === s.session_id}
                        style={{
                          padding: '0.2rem 0.6rem',
                          borderRadius: '4px',
                          border: 'none',
                          cursor: deletingId === s.session_id ? 'wait' : 'pointer',
                          background: '#dc2626',
                          color: '#fff',
                          fontSize: '0.8rem',
                        }}
                      >
                        Confirm delete
                      </button>
                      <button
                        aria-label={`Cancel delete session ${s.session_id}`}
                        onClick={() => setDeleteConfirmId(null)}
                        style={{
                          padding: '0.2rem 0.6rem',
                          borderRadius: '4px',
                          border: '1px solid rgba(255,255,255,0.15)',
                          cursor: 'pointer',
                          background: 'transparent',
                          color: '#a1a1aa',
                          fontSize: '0.8rem',
                        }}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      aria-label={`Delete session ${s.session_id}`}
                      onClick={() => setDeleteConfirmId(s.session_id)}
                      style={{
                        padding: '0.2rem 0.6rem',
                        borderRadius: '4px',
                        border: '1px solid rgba(239,68,68,0.4)',
                        cursor: 'pointer',
                        background: 'transparent',
                        color: '#f87171',
                        fontSize: '0.8rem',
                      }}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
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
