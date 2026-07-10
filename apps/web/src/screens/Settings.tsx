// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type ImportPackResponse, type PackSummary, type RelationshipRecapSummary } from '../api/client'
import type { ApiError } from '../api/errors'
import { errorHeadline } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'
import { readPrivacyPref, writePrivacyPref, PRIVACY_KEYS, isDevModeEnabled } from '../privacyPrefs'
import { useSteamStatus } from '../hooks/useSteamStatus'
import RuntimeSettingsPanel from '../components/RuntimeSettingsPanel'
import VoiceSettingsPanel from '../components/VoiceSettingsPanel'
import { useTranslation, formatDate, SUPPORTED_LOCALES } from '../i18n'

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

// Display names shown in the locale selector — always in the native language.
const LOCALE_DISPLAY_NAMES: Record<string, string> = {
  en: 'English',
  de: 'Deutsch',
}

export default function Settings() {
  const { t, locale, setLocale } = useTranslation()

  const [saveTranscripts, setSaveTranscripts] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveTranscripts, true))
  const [saveTtsCache, setSaveTtsCache] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveTtsCache, true))
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [saveRawAudio, setSaveRawAudio] = useState(() => readPrivacyPref(PRIVACY_KEYS.saveRawAudio, false))
  const [devMode, setDevMode] = useState(() => isDevModeEnabled())
  const [isTauri] = useState(detectTauri)
  const steamStatus = useSteamStatus()

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
  const [foldersError, setFoldersError] = useState<ApiError | false>(false)
  const [copiedFolder, setCopiedFolder] = useState<string | null>(null)
  const [openFolderError, setOpenFolderError] = useState<string | null>(null)

  useEffect(() => {
    void api.getFolders().then((r) => {
      if (r.ok) { setFolders(r.data); setFoldersError(false) }
      else setFoldersError(r.error)
    })
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
      setOpenFolderError(t('settings.folders.openError'))
    }
  }

  // ── Pack management ──────────────────────────────────────────────────────────

  const packFileInputRef = useRef<HTMLInputElement>(null)
  const [packImportState, setPackImportState] = useState<PackImportState>('idle')
  const [packImportError, setPackImportError] = useState<ApiError | null>(null)
  const [importedPack, setImportedPack] = useState<ImportPackResponse | null>(null)
  const [installedPacks, setInstalledPacks] = useState<PackSummary[] | null>(null)
  const [installedPacksError, setInstalledPacksError] = useState<ApiError | null>(null)

  const loadInstalledPacks = useCallback(() => {
    void api.listPacks().then((r) => {
      if (r.ok) { setInstalledPacks(r.data.packs); setInstalledPacksError(null) }
      else setInstalledPacksError(r.error)
    })
  }, [])

  useEffect(() => { loadInstalledPacks() }, [loadInstalledPacks])

  async function handleImportPack(file: File) {
    setPackImportState('uploading')
    setPackImportError(null)
    setImportedPack(null)
    const r = await api.importPack(file)
    if (r.ok) {
      setImportedPack(r.data)
      setPackImportState('success')
      loadInstalledPacks()
    } else {
      setPackImportError(r.error)
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
  const [clearError, setClearError] = useState<ApiError | null>(null)
  const [deletedCount, setDeletedCount] = useState<number | null>(null)

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [sessionsError, setSessionsError] = useState<ApiError | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<ApiError | null>(null)
  const [exportError, setExportError] = useState<ApiError | null>(null)

  const loadSessions = useCallback(() => {
    void api.listSessions().then((r) => {
      if (r.ok) { setSessions(r.data.sessions); setSessionsError(null) }
      else setSessionsError(r.error)
    })
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
      const r = await api.clearLocalData()
      if (r.ok) {
        setDeletedCount(r.data.deleted_sessions)
        setDeleteError(null)
        setExportError(null)
        setSessions([])
        setDeleteConfirmId(null)
        setClearState('done')
        loadSessions()
      } else {
        setClearError(r.error)
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
    const r = await api.deleteSession(sessionId)
    if (r.ok) {
      setSessions((prev) => prev?.filter((s) => s.session_id !== sessionId) ?? null)
    } else {
      setDeleteError(r.error)
    }
    setDeletingId(null)
    setDeleteConfirmId(null)
  }

  // ── NPC relationship memory ──────────────────────────────────────────────────

  const [recaps, setRecaps] = useState<RelationshipRecapSummary[] | null>(null)
  const [recapsError, setRecapsError] = useState<ApiError | null>(null)
  const [deletingRecap, setDeletingRecap] = useState<string | null>(null)
  const [clearingRecaps, setClearingRecaps] = useState(false)

  const loadRecaps = useCallback(() => {
    void api.listRelationshipMemory().then((r) => {
      if (r.ok) { setRecaps(r.data.recaps); setRecapsError(null) }
      else setRecapsError(r.error)
    })
  }, [])

  useEffect(() => { loadRecaps() }, [loadRecaps])

  async function handleDeleteRecap(npcId: string, packId: string) {
    const key = `${npcId}:${packId}`
    setDeletingRecap(key)
    const r = await api.deleteRelationshipMemory(npcId, packId)
    if (r.ok) {
      setRecaps((prev) => prev?.filter((x) => !(x.npc_id === npcId && x.pack_id === packId)) ?? null)
    }
    setDeletingRecap(null)
  }

  async function handleClearAllRecaps() {
    setClearingRecaps(true)
    const r = await api.clearAllRelationshipMemory()
    if (r.ok) { setRecaps([]) }
    setClearingRecaps(false)
  }

  async function handleExportSession(sessionId: string) {
    setExportError(null)
    const r = await api.exportSession(sessionId)
    if (r.ok) {
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `session-${sessionId}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } else {
      setExportError(r.error)
    }
  }

  const clearButtonLabel =
    clearState === 'confirming'
      ? t('settings.clearData.confirm')
      : clearState === 'clearing'
        ? t('settings.clearData.clearing')
        : t('settings.clearData.clear')

  type FolderKey = 'data' | 'logs' | 'models' | 'packs' | 'exports' | 'cache' | 'crash_bundles'
  const FOLDER_ROWS: { key: FolderKey; label: string }[] = [
    { key: 'data', label: t('settings.folders.data') },
    { key: 'logs', label: t('settings.folders.logs') },
    { key: 'models', label: t('settings.folders.models') },
    { key: 'packs', label: t('settings.folders.packs') },
    { key: 'exports', label: t('settings.folders.exports') },
    { key: 'cache', label: t('settings.folders.cache') },
    { key: 'crash_bundles', label: t('settings.folders.crash_bundles') },
  ]

  return (
    <div style={{ maxWidth: '640px' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>{t('settings.title')}</h1>

      {/* Local-first posture notice */}
      <div
        role="note"
        aria-label={t('settings.localFirst.ariaLabel')}
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
        <strong>{t('settings.localFirst.label')}</strong>{' '}
        {t('settings.localFirst.description')}
      </div>

      {/* Language / locale switcher */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.language.heading')}</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.language.description')}
        </p>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem' }}>
          <span>{t('settings.language.label')}:</span>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            aria-label={t('settings.language.label')}
            data-testid="settings-locale-select"
            style={{
              padding: '0.3rem 0.6rem',
              borderRadius: '4px',
              border: '1px solid rgba(255,255,255,0.15)',
              background: 'rgba(255,255,255,0.05)',
              color: '#e8e8ea',
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            {SUPPORTED_LOCALES.map((loc) => (
              <option key={loc} value={loc}>
                {LOCALE_DISPLAY_NAMES[loc] ?? loc}
              </option>
            ))}
          </select>
        </label>
      </section>

      {/* Transcript saving */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.transcript.heading')}</SectionHeading>
        <PrivacyToggle
          id="save-transcripts"
          label={t('settings.transcript.saveLabel')}
          checked={saveTranscripts}
          onChange={handleSaveTranscriptsChange}
          description={
            saveTranscripts
              ? t('settings.transcript.saveOn')
              : t('settings.transcript.saveOff')
          }
        />
        {!saveTranscripts && (
          <p
            aria-live="polite"
            style={{ fontSize: '0.85rem', color: '#fbbf24', margin: '0 0 0 1.5rem' }}
          >
            {t('settings.transcript.notSavedWarning')}
          </p>
        )}
      </section>

      {/* Runtime settings */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.runtime.heading')}</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.runtime.description')}{' '}
          <Link
            to="/model-manager"
            aria-label={t('settings.runtime.openModelManagerLabel')}
            style={{ color: '#71717a' }}
          >
            {t('settings.runtime.openModelManagerLink')}
          </Link>
        </p>
        <RuntimeSettingsPanel />
      </section>

      {/* Voice output */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.voice.heading')}</SectionHeading>
        <PrivacyToggle
          id="save-tts-cache"
          label={t('settings.voice.cacheLabel')}
          checked={saveTtsCache}
          onChange={handleSaveTtsCacheChange}
          description={t('settings.voice.cacheDescription')}
        />
        <VoiceSettingsPanel />
      </section>

      {/* Steam Cloud sync */}
      <section
        aria-label={t('settings.steamCloud.heading')}
        data-testid="steam-cloud-section"
        style={{ marginBottom: '2rem' }}
      >
        <SectionHeading>{t('settings.steamCloud.heading')}</SectionHeading>

        {/* Active indicator: shown only when the app is running under Steam */}
        {steamStatus?.launched_by_steam && (
          <div
            aria-label="steam-cloud-active"
            style={{
              background: 'rgba(103,193,245,0.08)',
              border: '1px solid rgba(103,193,245,0.25)',
              borderRadius: '6px',
              padding: '0.5rem 0.875rem',
              marginBottom: '0.75rem',
              fontSize: '0.85rem',
              color: '#7dd3fc',
            }}
          >
            {t('settings.steamCloud.active')}
          </div>
        )}

        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.steamCloud.description')}
        </p>

        <div aria-label="steam-cloud-synced-items" style={{ marginBottom: '0.75rem' }}>
          <p style={{ fontSize: '0.875rem', color: '#d4d4d8', marginBottom: '0.4rem', fontWeight: 500 }}>
            {t('settings.steamCloud.syncedHeading')}
          </p>
          <ul style={{ margin: '0 0 0 1.25rem', padding: 0, fontSize: '0.85rem', color: '#a1a1aa' }}>
            <li>{t('settings.steamCloud.syncedModel')}</li>
          </ul>
        </div>

        <div aria-label="steam-cloud-excluded-items">
          <p style={{ fontSize: '0.875rem', color: '#d4d4d8', marginBottom: '0.4rem', fontWeight: 500 }}>
            {t('settings.steamCloud.excludedHeading')}
          </p>
          <ul style={{ margin: '0 0 0 1.25rem', padding: 0, fontSize: '0.85rem', color: '#a1a1aa' }}>
            <li>{t('settings.steamCloud.excludedTranscripts')}</li>
            <li>{t('settings.steamCloud.excludedPrompts')}</li>
            <li>{t('settings.steamCloud.excludedAudio')}</li>
            <li>{t('settings.steamCloud.excludedModels')}</li>
            <li>{t('settings.steamCloud.excludedCrashLogs')}</li>
            <li>{t('settings.steamCloud.excludedPacks')}</li>
          </ul>
        </div>
      </section>

      {/* Pack management */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.packs.heading')}</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.packs.description')}
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <input
            ref={packFileInputRef}
            type="file"
            accept=".zip,application/zip"
            style={{ display: 'none' }}
            aria-label={t('settings.packs.importFileLabel')}
            data-testid="settings-import-file-input"
            onChange={handlePackFileChange}
          />
          <button
            onClick={() => packFileInputRef.current?.click()}
            disabled={packImportState === 'uploading'}
            aria-label={t('settings.packs.importButton')}
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
            {packImportState === 'uploading' ? t('settings.packs.importing') : t('settings.packs.importButton')}
          </button>
          {packImportState === 'success' && importedPack && (
            <span
              data-testid="settings-import-success"
              style={{ fontSize: '0.85rem', color: '#86efac' }}
            >
              {t('settings.packs.importedSuccess', { name: importedPack.name })}
            </span>
          )}
          {packImportState === 'error' && packImportError && (
            <span
              role="alert"
              data-testid="settings-import-error"
              style={{ fontSize: '0.85rem', color: '#f87171' }}
            >
              {errorHeadline(packImportError)}
            </span>
          )}
        </div>

        {installedPacksError && (
          <ApiErrorView error={installedPacksError} onRetry={loadInstalledPacks} context="Settings-Packs" />
        )}
        {!installedPacksError && installedPacks !== null && installedPacks.length === 0 && (
          <p data-testid="no-packs" style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
            {t('settings.packs.noPacks')}
          </p>
        )}
        {installedPacksError === null && installedPacks !== null && installedPacks.length > 0 && (
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
                    {p.scenario_count === 1
                      ? t('settings.packs.scenarioCount_one', { count: 1 })
                      : t('settings.packs.scenarioCount_other', { count: p.scenario_count })}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Local folders */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.folders.heading')}</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.folders.description')}
        </p>
        {foldersError ? (
          <ApiErrorView error={foldersError} onRetry={() => { void api.getFolders().then((r) => { if (r.ok) { setFolders(r.data); setFoldersError(false) } else setFoldersError(r.error) }) }} context="Settings-Folders" />
        ) : folders === null ? (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>{t('settings.folders.loading')}</p>
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
                      aria-label={t('settings.folders.copyLabel', { folder: label.toLowerCase() })}
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
                      {copiedFolder === key ? t('settings.folders.copied') : t('settings.folders.copy')}
                    </button>
                    {isTauri && (
                      <button
                        aria-label={t('settings.folders.openLabel', { folder: label.toLowerCase() })}
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
                        {t('settings.folders.open')}
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
        <SectionHeading>{t('settings.clearData.heading')}</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.clearData.description')}
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
            {t('settings.clearData.confirmMessage')}
          </div>
        )}

        {clearState === 'done' && (
          <p style={{ fontSize: '0.875rem', color: '#86efac', marginBottom: '0.5rem' }}>
            {deletedCount === 1
              ? t('settings.clearData.done_one')
              : t('settings.clearData.done_other', { count: deletedCount ?? 0 })}{' '}
            {t('settings.clearData.doneLocal')}
          </p>
        )}

        {clearState === 'error' && clearError && (
          <div style={{ marginBottom: '0.5rem' }}>
            <ApiErrorView error={clearError} onRetry={handleClearLocalData} context="Settings-Clear" />
          </div>
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
              {t('settings.clearData.cancel')}
            </button>
          )}
        </div>
      </section>

      {/* Your sessions */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>{t('settings.sessions.heading')}</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          {t('settings.sessions.description')}
        </p>
        {sessionsError && (
          <ApiErrorView error={sessionsError} onRetry={loadSessions} context="Settings-Sessions" />
        )}
        {deleteError && (
          <div style={{ marginBottom: '0.5rem' }}>
            <ApiErrorView error={deleteError} compact context="Settings-Delete" />
          </div>
        )}
        {exportError && (
          <div style={{ marginBottom: '0.5rem' }}>
            <ApiErrorView error={exportError} compact context="Settings-Export" />
          </div>
        )}
        {sessionsError === null && sessions === null && (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>{t('settings.sessions.loading')}</p>
        )}
        {sessionsError === null && sessions !== null && sessions.length === 0 && (
          <p data-testid="no-sessions" style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
            {t('settings.sessions.noSessions')}
          </p>
        )}
        {sessionsError === null && sessions !== null && sessions.length > 0 && (
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
                    {formatDate(s.created_at, locale)}
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
                    aria-label={t('settings.sessions.exportLabel', { id: s.session_id })}
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
                    {t('settings.sessions.export')}
                  </button>
                  {deleteConfirmId === s.session_id ? (
                    <>
                      <button
                        aria-label={t('settings.sessions.confirmDeleteLabel', { id: s.session_id })}
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
                        {t('settings.sessions.confirmDelete')}
                      </button>
                      <button
                        aria-label={t('settings.sessions.cancelDeleteLabel', { id: s.session_id })}
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
                        {t('settings.sessions.cancelDelete')}
                      </button>
                    </>
                  ) : (
                    <button
                      aria-label={t('settings.sessions.deleteLabel', { id: s.session_id })}
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
                      {t('settings.sessions.delete')}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* NPC relationship memory */}
      <section style={{ marginBottom: '2rem' }} data-testid="relationship-memory-section">
        <SectionHeading>NPC relationship memory</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          After each completed session the app stores a short summary of your practice patterns for each NPC. This
          allows NPCs to exhibit subtle continuity across sessions. The summary never contains raw transcript text
          and you can delete any entry here.
        </p>
        {recapsError && (
          <ApiErrorView error={recapsError} onRetry={loadRecaps} context="Settings-RelationshipMemory" />
        )}
        {!recapsError && recaps === null && (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Loading&hellip;</p>
        )}
        {!recapsError && recaps !== null && recaps.length === 0 && (
          <p data-testid="no-recaps" style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
            No NPC memories stored yet. Memories are created after completing a session and generating a debrief.
          </p>
        )}
        {!recapsError && recaps !== null && recaps.length > 0 && (
          <>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.75rem 0' }}>
              {recaps.map((r) => {
                const key = `${r.npc_id}:${r.pack_id}`
                const isDeleting = deletingRecap === key
                return (
                  <li
                    key={key}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      gap: '0.5rem',
                      padding: '0.6rem 0',
                      borderBottom: '1px solid rgba(255,255,255,0.06)',
                      fontSize: '0.875rem',
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ fontWeight: 500, color: '#d4d4d8' }}>{r.npc_id}</span>
                      <span style={{ color: '#71717a', marginLeft: '0.4rem', fontSize: '0.8rem' }}>{r.pack_id}</span>
                      <span style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.75rem' }}>
                        {r.session_count} session{r.session_count !== 1 ? 's' : ''}
                      </span>
                      {r.key_observations.length > 0 && (
                        <ul style={{ margin: '0.25rem 0 0 0', padding: '0 0 0 1rem', fontSize: '0.8rem', color: '#a1a1aa' }}>
                          {r.key_observations.slice(0, 3).map((obs, i) => (
                            <li key={i}>{obs}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <button
                      aria-label={`Delete memory for ${r.npc_id}`}
                      onClick={() => void handleDeleteRecap(r.npc_id, r.pack_id)}
                      disabled={isDeleting}
                      style={{
                        flexShrink: 0,
                        padding: '0.2rem 0.6rem',
                        borderRadius: '4px',
                        border: '1px solid rgba(239,68,68,0.4)',
                        cursor: isDeleting ? 'wait' : 'pointer',
                        background: 'transparent',
                        color: '#f87171',
                        fontSize: '0.8rem',
                      }}
                    >
                      {isDeleting ? 'Deleting…' : 'Delete'}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button
              data-testid="clear-all-recaps-button"
              onClick={() => void handleClearAllRecaps()}
              disabled={clearingRecaps}
              style={{
                padding: '0.4rem 0.85rem',
                borderRadius: '4px',
                border: 'none',
                cursor: clearingRecaps ? 'wait' : 'pointer',
                background: 'rgba(239,68,68,0.15)',
                color: '#f87171',
                fontWeight: 500,
                fontSize: '0.875rem',
              }}
            >
              {clearingRecaps ? 'Clearing…' : 'Clear all NPC memories'}
            </button>
          </>
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
          {showAdvanced ? t('settings.advanced.hideAdvanced') : t('settings.advanced.showAdvanced')}
        </button>

        {showAdvanced && (
          <div id="settings-advanced-section">
            <SectionHeading>{t('settings.advanced.heading')}</SectionHeading>
            <PrivacyToggle
              id="save-raw-audio"
              label={t('settings.advanced.rawAudioLabel')}
              checked={saveRawAudio}
              onChange={handleSaveRawAudioChange}
              description={t('settings.advanced.rawAudioDescription')}
            />
            {saveRawAudio && (
              <p
                aria-live="polite"
                style={{ fontSize: '0.85rem', color: '#fbbf24', margin: '0 0 0 1.5rem' }}
              >
                {t('settings.advanced.rawAudioWarning')}
              </p>
            )}
            <PrivacyToggle
              id="dev-mode"
              label={t('settings.advanced.devModeLabel')}
              checked={devMode}
              onChange={handleDevModeChange}
              description={t('settings.advanced.devModeDescription')}
            />
            {devMode && (
              <p
                aria-live="polite"
                style={{ fontSize: '0.85rem', color: '#fbbf24', margin: '0 0 0 1.5rem' }}
              >
                {t('settings.advanced.devModeWarning')}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
