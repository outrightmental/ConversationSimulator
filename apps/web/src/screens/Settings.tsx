// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type ImportPackResponse, type PackSummary } from '../api/client'
import { readPrivacyPref, writePrivacyPref, PRIVACY_KEYS, isDevModeEnabled } from '../privacyPrefs'
import RuntimeSettingsPanel from '../components/RuntimeSettingsPanel'
import VoiceSettingsPanel from '../components/VoiceSettingsPanel'

type ClearState = 'idle' | 'confirming' | 'clearing' | 'done' | 'error'
type PackImportState = 'idle' | 'uploading' | 'success' | 'error'

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

/** Returns true when running inside the Tauri desktop shell. */
function detectTauri(): boolean {
  return typeof (window as { __TAURI__?: unknown }).__TAURI__ !== 'undefined'
}

/**
 * Opens a local folder in the OS file manager via the Tauri shell.
 * Throws when the desktop shell is unavailable or the shell rejects the path
 * (e.g. the shell open scope is restricted), so callers can surface a fallback.
 */
async function openFolderInShell(folderPath: string): Promise<void> {
  const tauri = (window as { __TAURI__?: { core?: { invoke?: (cmd: string, args?: unknown) => Promise<void> } } }).__TAURI__
  const invoke = tauri?.core?.invoke
  if (!invoke) {
    throw new Error('Desktop shell is unavailable')
  }
  await invoke('plugin:shell|open', { path: folderPath })
}

export default function Settings() {
  const [saveTranscripts, setSaveTranscripts] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveTranscripts, true))
  const [saveTtsCache, setSaveTtsCache] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveTtsCache, true))
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [saveRawAudio, setSaveRawAudio] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveRawAudio, false))
  const [devMode, setDevMode] = useState(() => isDevModeEnabled())
  const [isTauri] = useState(detectTauri)

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

  function handleDevModeChange(v: boolean) {
    setDevMode(v)
    writePrivacyPref(PRIVACY_KEYS.devMode, v)
  }

  // ── Folders ─────────────────────────────────────────────────────────────────

  const [folders, setFolders] = useState<{ data: string; logs: string; models: string; packs: string; exports: string; cache: string; crash_bundles: string } | null>(null)
  const [foldersError, setFoldersError] = useState(false)
  const [copiedFolder, setCopiedFolder] = useState<string | null>(null)
  const [openFolderError, setOpenFolderError] = useState<string | null>(null)

  useEffect(() => {
    api.getFolders()
      .then((r) => setFolders(r))
      .catch(() => setFoldersError(true))
  }, [])

  async function handleCopyFolder(folderPath: string, key: string) {
    try {
      await navigator.clipboard.writeText(folderPath)
      setCopiedFolder(key)
      setTimeout(() => setCopiedFolder((v) => (v === key ? null : v)), 1500)
    } catch {
      // ignore — clipboard may be unavailable in non-secure contexts
    }
  }

  async function handleOpenFolder(folderPath: string) {
    setOpenFolderError(null)
    try {
      await openFolderInShell(folderPath)
    } catch {
      // The shell open scope can reject local paths; fall back to the copyable path.
      setOpenFolderError('Could not open the folder automatically. Copy the path and open it manually.')
    }
  }

  // ── Pack management ──────────────────────────────────────────────────────────

  const packFileInputRef = useRef<HTMLInputElement>(null)
  const [packImportState, setPackImportState] = useState<PackImportState>('idle')
  const [packImportError, setPackImportError] = useState<string | null>(null)
  const [importedPack, setImportedPack] = useState<ImportPackResponse | null>(null)
  const [installedPacks, setInstalledPacks] = useState<PackSummary[] | null>(null)
  const [installedPacksError, setInstalledPacksError] = useState(false)

  const loadInstalledPacks = useCallback(() => {
    api.listPacks()
      .then((r) => { setInstalledPacks(r.packs); setInstalledPacksError(false) })
      .catch(() => setInstalledPacksError(true))
  }, [])

  useEffect(() => { loadInstalledPacks() }, [loadInstalledPacks])

  async function handleImportPack(file: File) {
    setPackImportState('uploading')
    setPackImportError(null)
    setImportedPack(null)
    try {
      const result = await api.importPack(file)
      setImportedPack(result)
      setPackImportState('success')
      loadInstalledPacks()
    } catch (err) {
      setPackImportError(err instanceof Error ? err.message : 'Import failed')
      setPackImportState('error')
    }
  }

  function handlePackFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) void handleImportPack(file)
    e.target.value = ''
  }

  // ── Session data ─────────────────────────────────────────────────────────────

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
        setSessions([])
        setDeleteConfirmId(null)
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
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
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

  type FolderKey = 'data' | 'logs' | 'models' | 'packs' | 'exports' | 'cache' | 'crash_bundles'
  const FOLDER_ROWS: { key: FolderKey; label: string }[] = [
    { key: 'data', label: 'Data' },
    { key: 'logs', label: 'Logs' },
    { key: 'models', label: 'Models' },
    { key: 'packs', label: 'Packs' },
    { key: 'exports', label: 'Exports' },
    { key: 'cache', label: 'Cache' },
    { key: 'crash_bundles', label: 'Crash bundles' },
  ]

  return (
    <div style={{ maxWidth: '640px' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>Settings</h1>

      {/* Local-first posture notice */}
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
        <strong>Local-first.</strong> Conversations are processed entirely on your device. No
        telemetry is collected, no transcript is uploaded automatically, and no model or pack is
        downloaded without an explicit action from you.
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

      {/* Runtime settings */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Runtime</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Select the active AI provider and model. Advanced knobs are hidden by default.{' '}
          <Link
            to="/model-manager"
            aria-label="Open model manager"
            style={{ color: '#71717a' }}
          >
            Open model manager →
          </Link>
        </p>
        <RuntimeSettingsPanel />
      </section>

      {/* Voice output */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Voice output</SectionHeading>
        <PrivacyToggle
          id="save-tts-cache"
          label="Cache TTS audio locally"
          checked={saveTtsCache}
          onChange={handleSaveTtsCacheChange}
          description="Caching generated speech speeds up repeated phrases. Cached audio stays on your device and is never shared."
        />
        <VoiceSettingsPanel />
      </section>

      {/* Pack management */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Pack management</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Packs add scenarios to your library. Import a pack zip file — no executable content is
          accepted. Packs are validated on import and stored only on this device.
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <input
            ref={packFileInputRef}
            type="file"
            accept=".zip,application/zip"
            style={{ display: 'none' }}
            aria-label="Select pack zip file"
            data-testid="settings-import-file-input"
            onChange={handlePackFileChange}
          />
          <button
            onClick={() => packFileInputRef.current?.click()}
            disabled={packImportState === 'uploading'}
            aria-label="Import pack"
            data-testid="settings-import-pack-button"
            style={{
              padding: '0.4rem 0.85rem',
              borderRadius: '6px',
              border: '1px solid rgba(255,255,255,0.15)',
              background: 'rgba(255,255,255,0.05)',
              color: '#e8e8ea',
              fontSize: '0.875rem',
              cursor: packImportState === 'uploading' ? 'wait' : 'pointer',
            }}
          >
            {packImportState === 'uploading' ? 'Importing…' : 'Import pack (.zip)'}
          </button>
          {packImportState === 'success' && importedPack && (
            <span
              data-testid="settings-import-success"
              style={{ fontSize: '0.85rem', color: '#86efac' }}
            >
              Imported &ldquo;{importedPack.name}&rdquo;
            </span>
          )}
          {packImportState === 'error' && packImportError && (
            <span
              role="alert"
              data-testid="settings-import-error"
              style={{ fontSize: '0.85rem', color: '#f87171' }}
            >
              {packImportError}
            </span>
          )}
        </div>

        {installedPacksError && (
          <p style={{ fontSize: '0.875rem', color: '#f87171' }}>Could not load installed packs.</p>
        )}
        {!installedPacksError && installedPacks !== null && installedPacks.length === 0 && (
          <p data-testid="no-packs" style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
            No packs installed yet.
          </p>
        )}
        {!installedPacksError && installedPacks !== null && installedPacks.length > 0 && (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {installedPacks.map((p) => (
              <li
                key={p.pack_id}
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
                  <span style={{ fontWeight: 500 }}>{p.name}</span>
                  <span style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.8rem' }}>
                    {p.pack_id}
                  </span>
                  <span style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.8rem' }}>
                    {p.scenario_count} scenario{p.scenario_count !== 1 ? 's' : ''}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Local folders */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Local folders</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          All data stays on this device. Use these paths for manual inspection or backup.
        </p>
        {foldersError ? (
          <p style={{ fontSize: '0.875rem', color: '#f87171' }}>Could not retrieve folder paths.</p>
        ) : folders === null ? (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Loading…</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {FOLDER_ROWS.map(({ key, label }) => {
              const folderPath = folders[key]
              return (
                <div key={key}>
                  <span style={{ fontSize: '0.8rem', color: '#71717a', marginBottom: '0.25rem', display: 'block' }}>
                    {label}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <code
                      data-testid={`folder-path-${key}`}
                      style={{
                        flex: 1,
                        padding: '0.4rem 0.6rem',
                        background: 'rgba(255,255,255,0.05)',
                        borderRadius: '4px',
                        fontSize: '0.8rem',
                        wordBreak: 'break-all',
                      }}
                    >
                      {folderPath}
                    </code>
                    <button
                      aria-label={`Copy ${label.toLowerCase()} folder path`}
                      onClick={() => void handleCopyFolder(folderPath, key)}
                      style={{
                        flexShrink: 0,
                        padding: '0.3rem 0.6rem',
                        borderRadius: '4px',
                        border: '1px solid rgba(255,255,255,0.15)',
                        background: 'transparent',
                        color: copiedFolder === key ? '#86efac' : '#a1a1aa',
                        fontSize: '0.75rem',
                        cursor: 'pointer',
                      }}
                    >
                      {copiedFolder === key ? 'Copied!' : 'Copy'}
                    </button>
                    {isTauri && (
                      <button
                        aria-label={`Open ${label.toLowerCase()} folder`}
                        onClick={() => void handleOpenFolder(folderPath)}
                        style={{
                          flexShrink: 0,
                          padding: '0.3rem 0.6rem',
                          borderRadius: '4px',
                          border: '1px solid rgba(255,255,255,0.15)',
                          background: 'transparent',
                          color: '#a1a1aa',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                        }}
                      >
                        Open
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {openFolderError && (
          <p
            role="alert"
            data-testid="folder-open-error"
            style={{ fontSize: '0.85rem', color: '#f87171', marginTop: '0.5rem' }}
          >
            {openFolderError}
          </p>
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
          aria-controls="settings-advanced-section"
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
          <span aria-hidden="true">{showAdvanced ? '▾ ' : '▸ '}</span>
          {showAdvanced ? 'Hide advanced' : 'Show advanced'}
        </button>

        {showAdvanced && (
          <div id="settings-advanced-section">
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
            <PrivacyToggle
              id="dev-mode"
              label="Developer debug mode"
              checked={devMode}
              onChange={handleDevModeChange}
              description="Shows a debug drawer in the conversation screen with raw model output, state deltas, event evaluations, and hidden NPC fields. For developers diagnosing model drift or scenario behaviour. Reload the conversation screen after toggling."
            />
            {devMode && (
              <p
                aria-live="polite"
                style={{ fontSize: '0.85rem', color: '#fbbf24', margin: '0 0 0 1.5rem' }}
              >
                Developer debug drawer is active. Internal model data is visible on the conversation screen. Disable before sharing your screen.
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
