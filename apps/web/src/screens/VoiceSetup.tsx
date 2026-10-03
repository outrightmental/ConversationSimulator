// SPDX-License-Identifier: Apache-2.0
/**
 * Voice setup — the guided flow that actually installs speech-to-text and the
 * NPC voice (issue #487).
 *
 * Settings previously reported "STT: not installed" and left the player there.
 * This screen is the rest of that sentence: it names every piece voice needs,
 * says which are present, downloads the weight files it can verify, and hands
 * over the exact one-line command for the two native engines it will not fetch
 * on the player's behalf. Each row re-checks itself, so a terminal install in
 * another window shows up here on the next focus without a reload.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  computeVoiceInstallPct,
  formatDownloadSize,
  type VoiceAsset,
  type VoiceCapability,
  type VoiceEngine,
} from '@convsim/shared'
import { ApiErrorView } from '../components/ApiErrorView'
import { apiClient } from '../api/client'
import { useVoiceSetup } from '../hooks/useVoiceSetup'
import { useMicCapture, type MicPermission } from '../hooks/useMicCapture'
import { VOICE_DOCS_URL } from '../setup/docsUrls'

const RUNNING_STATES = new Set(['pending', 'running'])

function StatusDot({ ok, muted = false }: { ok: boolean; muted?: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={{
        flexShrink: 0,
        width: '0.55rem',
        height: '0.55rem',
        borderRadius: '50%',
        marginTop: '0.4rem',
        background: ok ? '#22c55e' : muted ? '#71717a' : '#f59e0b',
      }}
    />
  )
}

function Card({ children, accent = false }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <div
      style={{
        border: accent ? '1px solid rgba(99,102,241,0.45)' : '1px solid rgba(255,255,255,0.1)',
        background: accent ? 'rgba(99,102,241,0.08)' : 'rgba(255,255,255,0.02)',
        borderRadius: '8px',
        padding: '1rem 1.15rem',
      }}
    >
      {children}
    </div>
  )
}

function PrimaryButton({
  onClick,
  disabled,
  children,
  testId,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
  testId?: string
}) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '0.5rem 1.1rem',
        borderRadius: '6px',
        border: 'none',
        background: disabled ? 'rgba(99,102,241,0.4)' : 'rgba(99,102,241,0.9)',
        color: '#fff',
        fontWeight: 600,
        fontSize: '0.875rem',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {children}
    </button>
  )
}

function SecondaryButton({
  onClick,
  disabled,
  children,
  testId,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
  testId?: string
}) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '0.4rem 0.9rem',
        borderRadius: '6px',
        border: '1px solid rgba(255,255,255,0.22)',
        background: 'rgba(255,255,255,0.06)',
        color: 'inherit',
        fontSize: '0.85rem',
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {children}
    </button>
  )
}

function CommandBlock({ command, label }: { command: string; label: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard is unavailable outside a secure context; the command is
      // selectable on screen either way, so there is nothing to recover from.
    }
  }

  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'stretch', marginTop: '0.5rem' }}>
      <code
        style={{
          flex: 1,
          padding: '0.45rem 0.6rem',
          background: 'rgba(0,0,0,0.35)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '4px',
          fontSize: '0.8rem',
          wordBreak: 'break-all',
          color: '#d4d4d8',
        }}
      >
        {command}
      </code>
      <button
        onClick={() => void copy()}
        aria-label={label}
        style={{
          padding: '0.35rem 0.7rem',
          borderRadius: '4px',
          border: '1px solid rgba(255,255,255,0.18)',
          background: 'rgba(255,255,255,0.06)',
          color: 'inherit',
          fontSize: '0.78rem',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

function EngineRow({
  engine,
  busy,
  kokoroState,
  onStart,
  onRecheck,
}: {
  engine: VoiceEngine
  busy: boolean
  kokoroState: string | null
  onStart: (engineId: string) => void
  onRecheck: () => void
}) {
  // "Installed but not running" is the common Steam-depot case and the only
  // one the app can resolve itself, so it gets a button rather than a command.
  const canStart = engine.installed && engine.startable && kokoroState !== 'running'

  return (
    <li
      data-testid={`engine-row-${engine.id}`}
      style={{ display: 'flex', gap: '0.6rem', padding: '0.6rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}
    >
      <StatusDot ok={engine.installed && !canStart} />
      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontSize: '0.875rem', fontWeight: 500 }}>
          {engine.name}{' '}
          <span style={{ fontWeight: 400, color: engine.installed ? '#86efac' : '#fbbf24' }}>
            — {engine.installed ? (canStart ? 'installed, not running' : 'installed') : 'not found'}
          </span>
        </p>
        {engine.installed && engine.found_at && (
          <p style={{ margin: '0.15rem 0 0', fontSize: '0.78rem', color: '#71717a', wordBreak: 'break-all' }}>
            {engine.found_at}
          </p>
        )}
        {!engine.installed && (
          <>
            <p style={{ margin: '0.2rem 0 0', fontSize: '0.82rem', color: '#a1a1aa', lineHeight: 1.5 }}>
              {engine.why_manual}
            </p>
            {engine.command && (
              <CommandBlock command={engine.command} label={`Copy the ${engine.name} install command`} />
            )}
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', alignItems: 'center' }}>
              <SecondaryButton onClick={onRecheck} testId={`engine-recheck-${engine.id}`}>
                Check again
              </SecondaryButton>
              <a
                href={engine.docs_url}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '0.8rem', color: '#a5b4fc' }}
              >
                Other ways to install it
              </a>
            </div>
          </>
        )}
        {canStart && (
          <div style={{ marginTop: '0.5rem' }}>
            <PrimaryButton
              onClick={() => onStart(engine.id)}
              disabled={busy}
              testId={`engine-start-${engine.id}`}
            >
              {busy ? 'Starting…' : 'Start the voice server'}
            </PrimaryButton>
          </div>
        )}
      </div>
    </li>
  )
}

function AssetRow({ asset }: { asset: VoiceAsset }) {
  return (
    <li
      data-testid={`asset-row-${asset.id}`}
      style={{ display: 'flex', gap: '0.6rem', padding: '0.6rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}
    >
      <StatusDot ok={asset.installed} />
      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontSize: '0.875rem', fontWeight: 500 }}>
          {asset.name}{' '}
          <span style={{ fontWeight: 400, color: asset.installed ? '#86efac' : '#fbbf24' }}>
            — {asset.installed ? (asset.selected ? 'installed, in use' : 'installed') : `not installed · ${formatDownloadSize(asset.size_bytes)}`}
          </span>
        </p>
        <p style={{ margin: '0.15rem 0 0', fontSize: '0.82rem', color: '#a1a1aa', lineHeight: 1.5 }}>
          {asset.description}
        </p>
      </div>
    </li>
  )
}

/** Outcome of the one real round trip through microphone → decoder → speech model. */
type MicTestResult =
  | { kind: 'heard'; transcript: string }
  | { kind: 'problem'; message: string }
  | null

const MIC_STATE_LABEL: Record<MicPermission, string> = {
  unsupported: 'not available in this browser',
  idle: 'not allowed yet',
  requesting: 'waiting for your answer…',
  granted: 'allowed',
  denied: 'blocked',
}

/**
 * The step no download can satisfy: the browser has to be allowed to use the
 * microphone, and the whole chain has to come back with words. Installing the
 * models proves neither, so this row asks for permission and then runs one real
 * transcription — the player leaves the screen knowing rather than hoping.
 */
function MicCheckRow({ sttReady }: { sttReady: boolean }) {
  const [result, setResult] = useState<MicTestResult>(null)
  const [transcribing, setTranscribing] = useState(false)

  const handleAudio = useCallback(async (blob: Blob) => {
    setTranscribing(true)
    try {
      const r = await apiClient.uploadAudio(blob)
      if (!r.ok) {
        setResult({ kind: 'problem', message: r.error.message })
      } else if (r.data.status === 'unavailable') {
        setResult({
          kind: 'problem',
          message: 'Speech-to-text is not running yet — finish the steps above, then try again.',
        })
      } else if (r.data.status === 'error') {
        setResult({
          kind: 'problem',
          message:
            'The recording could not be transcribed. ffmpeg is the usual culprit — check its row below.',
        })
      } else if (r.data.transcript) {
        setResult({ kind: 'heard', transcript: r.data.transcript })
      } else {
        setResult({
          kind: 'problem',
          message: 'No speech was detected. Move closer to the microphone and try again.',
        })
      }
    } finally {
      setTranscribing(false)
    }
  }, [])

  const {
    permission,
    isRecording,
    recordingSeconds,
    error,
    requestPermission,
    startRecording,
    stopRecording,
  } = useMicCapture(handleAudio)

  const granted = permission === 'granted'

  return (
    <li
      data-testid="mic-check-row"
      style={{ display: 'flex', gap: '0.6rem', padding: '0.6rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}
    >
      <StatusDot ok={granted} muted={permission === 'unsupported'} />
      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontSize: '0.875rem', fontWeight: 500 }}>
          Microphone{' '}
          <span style={{ fontWeight: 400, color: granted ? '#86efac' : '#fbbf24' }}>
            — {MIC_STATE_LABEL[permission]}
          </span>
        </p>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.82rem', color: '#a1a1aa', lineHeight: 1.5 }}>
          {permission === 'unsupported'
            ? 'This browser cannot record audio. The desktop app can, as can a recent Chrome, Edge or Safari.'
            : permission === 'denied'
            ? 'Your browser is blocking the microphone for this app. Allow it in the site permissions — or your system privacy settings — then try again.'
            : permission === 'requesting'
            ? 'Answer the prompt your browser just raised.'
            : !granted
            ? 'The browser asks once. Nothing is recorded until you hold the talk key during a scenario.'
            : sttReady
            ? 'Say a few words to check the whole chain — microphone, decoder and speech model — before you start a scenario.'
            : 'Finish the speech-to-text steps above and you can test the whole chain from here.'}
        </p>

        {(permission === 'idle' || permission === 'denied' || permission === 'requesting') && (
          <div style={{ marginTop: '0.5rem' }}>
            <PrimaryButton
              onClick={() => void requestPermission()}
              disabled={permission === 'requesting'}
              testId="mic-allow"
            >
              {permission === 'denied' ? 'Try the microphone again' : 'Allow the microphone'}
            </PrimaryButton>
          </div>
        )}

        {granted && sttReady && (
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            {isRecording ? (
              <PrimaryButton onClick={stopRecording} testId="mic-test-stop">
                {`Stop and transcribe · ${recordingSeconds}s`}
              </PrimaryButton>
            ) : (
              <PrimaryButton
                onClick={startRecording}
                disabled={transcribing}
                testId="mic-test-start"
              >
                {transcribing ? 'Transcribing…' : 'Record a test phrase'}
              </PrimaryButton>
            )}
          </div>
        )}

        {error != null && (
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.82rem', color: '#f87171' }}>{error}</p>
        )}

        {result != null && (
          <p
            aria-live="polite"
            data-testid="mic-test-result"
            style={{
              margin: '0.4rem 0 0',
              fontSize: '0.82rem',
              lineHeight: 1.5,
              color: result.kind === 'heard' ? '#86efac' : '#fbbf24',
            }}
          >
            {result.kind === 'heard'
              ? `Heard: “${result.transcript}” — speaking your turns works.`
              : result.message}
          </p>
        )}
      </div>
    </li>
  )
}

export default function VoiceSetup() {
  const navigate = useNavigate()
  const {
    plan,
    planError,
    loading,
    job,
    actionError,
    engineMessage,
    busy,
    refresh,
    startInstall,
    cancelInstall,
    startEngine,
  } = useVoiceSetup()

  const [sttChoice, setSttChoice] = useState<string | null>(null)

  const sttAssets = useMemo(
    () => (plan?.assets ?? []).filter((a) => a.capability === 'stt'),
    [plan],
  )

  // Default the picker to what is already in use, else the recommendation.
  useEffect(() => {
    if (sttChoice != null || sttAssets.length === 0) return
    const inUse = sttAssets.find((a) => a.selected)
    const recommended = sttAssets.find((a) => a.recommended)
    setSttChoice((inUse ?? recommended ?? sttAssets[0]).id)
  }, [sttAssets, sttChoice])

  const installing = job != null && RUNNING_STATES.has(job.status)

  // What the Download button would fetch: the chosen STT model plus every
  // other recommended asset that is still missing (today, the VAD model).
  const pendingAssets = useMemo(() => {
    if (plan == null) return []
    const wanted = new Set<string>(plan.default_asset_ids)
    if (sttChoice != null) {
      for (const a of sttAssets) wanted.delete(a.id)
      wanted.add(sttChoice)
    }
    return plan.assets.filter((a) => wanted.has(a.id) && !a.installed)
  }, [plan, sttAssets, sttChoice])

  const pendingBytes = pendingAssets.reduce((sum, a) => sum + a.size_bytes, 0)

  // Already on disk but not the file the engine reads: the player installed
  // several models and is switching between them. Posting the install re-points
  // the worker without fetching anything, so the same button does both jobs.
  const switchTo = useMemo(() => {
    if (sttChoice == null) return null
    const chosen = sttAssets.find((a) => a.id === sttChoice)
    return chosen != null && chosen.installed && !chosen.selected ? chosen : null
  }, [sttAssets, sttChoice])

  const requestedAssetIds = useMemo(() => {
    const ids = pendingAssets.map((a) => a.id)
    return switchTo != null && !ids.includes(switchTo.id) ? [switchTo.id, ...ids] : ids
  }, [pendingAssets, switchTo])

  const capabilities = plan?.capabilities ?? []
  const readyCount = capabilities.filter((c) => c.ready).length
  const essential = capabilities.filter((c) => c.id !== 'vad')
  const essentialReady = essential.length > 0 && essential.every((c) => c.ready)

  function assetsFor(capability: VoiceCapability): VoiceAsset[] {
    return (plan?.assets ?? []).filter((a) => capability.asset_ids.includes(a.id))
  }

  function enginesFor(capability: VoiceCapability): VoiceEngine[] {
    return (plan?.engines ?? []).filter((e) => capability.required_engine_ids.includes(e.id))
  }

  if (loading) {
    return (
      <div style={{ maxWidth: 720 }}>
        <h1>Set up voice</h1>
        <p style={{ color: '#a1a1aa' }}>Checking what this machine already has…</p>
      </div>
    )
  }

  if (planError != null || plan == null) {
    return (
      <div style={{ maxWidth: 720 }}>
        <h1>Set up voice</h1>
        {planError != null && (
          <ApiErrorView error={planError} onRetry={refresh} context="VoiceSetup-Plan" />
        )}
      </div>
    )
  }

  return (
    <div data-testid="voice-setup-screen" style={{ maxWidth: 720, display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div>
        <Link to="/settings" style={{ fontSize: '0.8rem', color: '#a5b4fc', textDecoration: 'none' }}>
          ← Settings
        </Link>
        <h1 style={{ margin: '0.4rem 0 0.35rem' }}>Set up voice</h1>
        <p style={{ margin: 0, color: '#a1a1aa', fontSize: '0.9rem', lineHeight: 1.6 }}>
          Speaking your side out loud is the part of practice that transfers. Everything
          below runs on this machine — no account, no audio leaves your computer — and
          the app stays fully playable in text while you set it up.{' '}
          <a
            href={VOICE_DOCS_URL}
            target="_blank"
            rel="noreferrer"
            data-testid="voice-docs-link"
            style={{ color: '#a5b4fc' }}
          >
            Read the voice guide
          </a>
          .
        </p>
      </div>

      {essentialReady && !installing && (
        <div data-testid="voice-ready-panel">
          <Card accent>
            <p style={{ margin: '0 0 0.3rem', fontWeight: 600, fontSize: '0.975rem', color: '#e0e0ff' }}>
              🎙️ Voice is ready
            </p>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', color: '#c7d2fe', lineHeight: 1.55 }}>
              Pick a scenario and choose a voice input mode on the setup screen. You can
              change the NPC voice and timing in Settings at any time.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <PrimaryButton onClick={() => navigate('/library')} testId="voice-ready-library">
                Pick a scenario
              </PrimaryButton>
              <SecondaryButton onClick={() => navigate('/settings')}>
                Back to Settings
              </SecondaryButton>
            </div>
          </Card>
        </div>
      )}

      <p aria-live="polite" style={{ margin: 0, fontSize: '0.82rem', color: '#a1a1aa' }}>
        {readyCount} of {capabilities.length} voice features ready
      </p>

      {engineMessage != null && (
        <p
          role="status"
          data-testid="engine-message"
          style={{ margin: 0, fontSize: '0.85rem', color: '#86efac' }}
        >
          {engineMessage}
        </p>
      )}

      {actionError != null && <ApiErrorView error={actionError} context="VoiceSetup-Action" />}

      {installing && (
        <div data-testid="voice-install-progress">
          <Card accent>
            <p style={{ margin: '0 0 0.6rem', fontWeight: 600, fontSize: '0.9rem' }}>
              Downloading voice models
            </p>
            <div
              role="progressbar"
              aria-valuenow={computeVoiceInstallPct(job) ?? 0}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Voice download progress"
              style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${computeVoiceInstallPct(job) ?? 0}%`,
                  background: 'rgba(99,102,241,0.85)',
                  transition: 'width 0.4s ease',
                }}
              />
            </div>
            <ol
              aria-label="Download stages"
              style={{ listStyle: 'none', margin: '0.75rem 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: '0.3rem' }}
            >
              {job?.stages.map((s) => (
                <li key={s.id} style={{ fontSize: '0.82rem', color: s.state === 'running' ? '#e4e4e7' : '#a1a1aa' }}>
                  {s.state === 'complete' ? '✓' : s.state === 'skipped' ? '–' : s.state === 'running' ? '▸' : '○'}{' '}
                  {s.label}
                  {s.state === 'running' && s.bytes_total != null && s.bytes_total > 0 && (
                    <span style={{ color: '#71717a' }}>
                      {' '}
                      {formatDownloadSize(s.bytes_downloaded ?? 0)} / {formatDownloadSize(s.bytes_total)}
                    </span>
                  )}
                </li>
              ))}
            </ol>
            <div style={{ marginTop: '0.75rem' }}>
              <SecondaryButton onClick={() => void cancelInstall()} disabled={busy} testId="voice-install-cancel">
                Cancel download
              </SecondaryButton>
            </div>
          </Card>
        </div>
      )}

      {job != null && job.status === 'failed' && (
        <Card>
          <p role="alert" style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: '#f87171' }}>
            {job.error_message ?? 'The download did not finish.'}
          </p>
          <PrimaryButton
            onClick={() => void startInstall(requestedAssetIds)}
            disabled={busy || requestedAssetIds.length === 0}
            testId="voice-install-retry"
          >
            Try again
          </PrimaryButton>
        </Card>
      )}

      {capabilities.map((capability) => {
        const engines = enginesFor(capability)
        const assets = assetsFor(capability)
        return (
          <section
            key={capability.id}
            data-testid={`capability-${capability.id}`}
            aria-label={capability.label}
          >
            <Card>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '0.75rem' }}>
                <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>{capability.label}</h2>
                <span
                  data-testid={`capability-${capability.id}-state`}
                  style={{ fontSize: '0.8rem', color: capability.ready ? '#86efac' : '#fbbf24', whiteSpace: 'nowrap' }}
                >
                  {capability.ready ? 'Ready' : 'Not yet'}
                </span>
              </div>
              <p style={{ margin: '0.25rem 0 0.4rem', fontSize: '0.85rem', color: '#a1a1aa', lineHeight: 1.55 }}>
                {capability.description}
              </p>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {engines.map((engine) => (
                  <EngineRow
                    key={engine.id}
                    engine={engine}
                    busy={busy}
                    kokoroState={plan.kokoro_state}
                    onStart={(id) => void startEngine(id)}
                    onRecheck={refresh}
                  />
                ))}
                {assets.map((asset) => (
                  <AssetRow key={asset.id} asset={asset} />
                ))}
                {capability.id === 'stt' && sttAssets.length > 1 && (
                  <li style={{ padding: '0.6rem 0 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <label
                      htmlFor="stt-model-choice"
                      style={{ display: 'block', fontSize: '0.82rem', fontWeight: 500, marginBottom: '0.3rem' }}
                    >
                      Speech-to-text model
                    </label>
                    <select
                      id="stt-model-choice"
                      value={sttChoice ?? ''}
                      onChange={(e) => setSttChoice(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '0.4rem 0.6rem',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(255,255,255,0.15)',
                        borderRadius: '4px',
                        color: '#d4d4d8',
                        fontSize: '0.85rem',
                      }}
                    >
                      {sttAssets.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name} — {formatDownloadSize(a.size_bytes)}
                          {a.language_note ? ` · ${a.language_note}` : ''}
                          {a.installed ? ' · already installed' : ''}
                        </option>
                      ))}
                    </select>
                  </li>
                )}
                {capability.id === 'stt' && <MicCheckRow sttReady={capability.ready} />}
                {capability.id === 'vad' && !plan.onnxruntime_installed && (
                  <li
                    data-testid="vad-onnxruntime-row"
                    style={{ display: 'flex', gap: '0.6rem', padding: '0.6rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <StatusDot ok={false} />
                    <div style={{ flex: 1 }}>
                      <p style={{ margin: 0, fontSize: '0.875rem', fontWeight: 500 }}>
                        onnxruntime <span style={{ fontWeight: 400, color: '#fbbf24' }}>— not installed</span>
                      </p>
                      <p style={{ margin: '0.2rem 0 0', fontSize: '0.82rem', color: '#a1a1aa', lineHeight: 1.5 }}>
                        Hands-free turn-taking runs the voice-activity model through onnxruntime.
                        Push-to-talk works without it.
                      </p>
                      <CommandBlock command="pip install onnxruntime" label="Copy the onnxruntime install command" />
                    </div>
                  </li>
                )}
              </ul>
            </Card>
          </section>
        )
      })}

      {!plan.ffmpeg_installed && (
        <Card>
          <p style={{ margin: 0, fontSize: '0.875rem', fontWeight: 500 }}>
            ffmpeg <span style={{ fontWeight: 400, color: '#fbbf24' }}>— not found</span>
          </p>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.82rem', color: '#a1a1aa', lineHeight: 1.5 }}>
            The browser records WebM/Opus audio and whisper.cpp reads WAV. Without ffmpeg on
            your PATH some recordings are rejected and the app falls back to text input.
          </p>
          <CommandBlock
            command={
              plan.platform === 'darwin'
                ? 'brew install ffmpeg'
                : plan.platform === 'win32'
                ? 'winget install --id Gyan.FFmpeg'
                : 'sudo apt install ffmpeg'
            }
            label="Copy the ffmpeg install command"
          />
        </Card>
      )}

      {(pendingAssets.length > 0 || switchTo != null) && !installing && (
        <section aria-label="Download the voice models">
          <Card accent>
            <h2 style={{ margin: '0 0 0.3rem', fontSize: '1rem', fontWeight: 600 }}>
              {pendingAssets.length > 0 ? 'Download the voice models' : 'Switch speech-to-text model'}
            </h2>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', color: '#c7d2fe', lineHeight: 1.55 }}>
              {pendingAssets.length > 0
                ? 'These are fetched from their original publishers and checked against a known SHA-256 before anything is installed. Nothing downloads until you press the button.'
                : 'This model is already on disk. Switching points the speech engine at it — nothing is downloaded.'}
            </p>

            {pendingAssets.length > 0 && (
            <table data-testid="voice-disclosure" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
              <caption style={{ captionSide: 'top', textAlign: 'left', color: '#a1a1aa', paddingBottom: '0.4rem' }}>
                What will be downloaded
              </caption>
              <tbody>
                {pendingAssets.map((a) => (
                  <tr key={a.id} style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                    <td style={{ padding: '0.5rem 0.5rem 0.5rem 0', verticalAlign: 'top' }}>
                      <strong style={{ fontSize: '0.85rem' }}>{a.name}</strong>
                      <span style={{ display: 'block', color: '#a1a1aa' }}>
                        {formatDownloadSize(a.size_bytes)} ·{' '}
                        <a href={a.license_url} target="_blank" rel="noreferrer" style={{ color: '#a5b4fc' }}>
                          {a.license}
                        </a>
                      </span>
                      <span style={{ display: 'block', color: '#71717a', wordBreak: 'break-all' }}>
                        {a.source_url}
                      </span>
                      <span style={{ display: 'block', color: '#71717a', wordBreak: 'break-all' }}>
                        SHA-256 {a.sha256}
                      </span>
                      <span style={{ display: 'block', color: '#71717a', wordBreak: 'break-all' }}>
                        → {a.install_path}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            )}

            <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', marginTop: '0.85rem', flexWrap: 'wrap' }}>
              <PrimaryButton
                onClick={() => void startInstall(requestedAssetIds)}
                disabled={busy}
                testId="voice-install-start"
              >
                {busy
                  ? 'Starting…'
                  : pendingAssets.length > 0
                  ? `Download ${formatDownloadSize(pendingBytes)}`
                  : `Use ${switchTo?.name}`}
              </PrimaryButton>
              {pendingAssets.length > 0 && (
                <span style={{ fontSize: '0.78rem', color: '#a1a1aa' }}>
                  You can cancel at any time; partial files are removed.
                </span>
              )}
            </div>
          </Card>
        </section>
      )}
    </div>
  )
}
