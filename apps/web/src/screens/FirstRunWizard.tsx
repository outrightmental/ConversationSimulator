// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { api } from '../api/client'
import { SETUP_KEYS } from '../privacyPrefs'
import type {
  ModelsResponse,
  ModelRegistryEntry,
  DetectedOllamaModel,
  InstalledModelInfo,
  BenchmarkResponse,
} from '@convsim/shared'

export { SETUP_KEYS }

const SETUP_DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/wiki'

export function markFirstRunComplete(): void {
  try {
    localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true')
  } catch {
    // localStorage may be unavailable in some environments; proceed anyway.
  }
}

type WizardStep =
  | 'welcome'
  | 'loading'
  | 'choose'
  | 'confirm-install'
  | 'installing'
  | 'benchmark'
  | 'ollama-select'
  | 'gguf-path'
  | 'demo-warning'
  | 'load-error'

// ── Shared styled primitives ─────────────────────────────────────────────────

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '1rem' }}
    >
      {children}
    </div>
  )
}

function CardHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: '1rem', fontWeight: 600, marginTop: 0, marginBottom: '0.4rem' }}>
      {children}
    </h2>
  )
}

function CardDescription({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: '0.875rem', color: '#a1a1aa', margin: '0 0 0.75rem' }}>
      {children}
    </p>
  )
}

function ActionButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '0.45rem 1rem',
        borderRadius: '4px',
        border: '1px solid rgba(255,255,255,0.2)',
        background: 'rgba(255,255,255,0.06)',
        color: 'inherit',
        cursor: disabled ? 'wait' : 'pointer',
        fontSize: '0.875rem',
        fontWeight: 500,
      }}
    >
      {children}
    </button>
  )
}

function PrimaryButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '0.45rem 1rem',
        borderRadius: '4px',
        border: 'none',
        background: disabled ? 'rgba(99,102,241,0.4)' : 'rgba(99,102,241,0.85)',
        color: '#fff',
        cursor: disabled ? 'wait' : 'pointer',
        fontSize: '0.875rem',
        fontWeight: 500,
      }}
    >
      {children}
    </button>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <tr>
      <td
        style={{
          color: '#a1a1aa',
          paddingTop: '0.4rem',
          paddingBottom: '0.4rem',
          paddingRight: '1.5rem',
          whiteSpace: 'nowrap',
          verticalAlign: 'top',
        }}
      >
        {label}
      </td>
      <td style={{ paddingTop: '0.4rem', paddingBottom: '0.4rem' }}>{children}</td>
    </tr>
  )
}

// ── Component ────────────────────────────────────────────────────────────────

export default function FirstRunWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState<WizardStep>('welcome')
  const [modelsData, setModelsData] = useState<ModelsResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedModel, setSelectedModel] = useState<ModelRegistryEntry | null>(null)
  const [ggufPath, setGgufPath] = useState('')
  const [ggufPathError, setGgufPathError] = useState<string | null>(null)

  const [actionError, setActionError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const [installId, setInstallId] = useState<number | null>(null)
  const [installRecord, setInstallRecord] = useState<InstalledModelInfo | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [benchmarkRunning, setBenchmarkRunning] = useState(false)
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResponse | null>(null)
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null)
  const benchmarkStartedRef = useRef(false)
  // Capture the "already done" state once at mount so that calling markFirstRunComplete()
  // mid-wizard (before the navigate() fires) doesn't cause a spurious redirect to "/".
  const alreadyCompleteRef = useRef(localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true')

  // Fetch model data when the user advances past the welcome step.
  useEffect(() => {
    if (step !== 'loading') return
    api
      .getModels()
      .then((data) => {
        setModelsData(data)
        setStep('choose')
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : 'Failed to load model information.')
        setStep('load-error')
      })
  }, [step])

  // Poll install progress while on the 'installing' step.
  useEffect(() => {
    if (step !== 'installing' || installId == null) return

    function stopPoll() {
      if (pollRef.current != null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }

    pollRef.current = setInterval(() => {
      api
        .getInstallStatus(installId)
        .then((record) => {
          setInstallRecord(record)
          const terminal = ['ready', 'complete', 'failed', 'cancelled', 'checksum_mismatch']
          if (terminal.includes(record.install_status)) {
            stopPoll()
            if (record.install_status === 'ready' || record.install_status === 'complete') {
              markFirstRunComplete()
              navigate('/')
            } else {
              // Stay on the installing step and surface the error with recovery options.
              setActionError(record.error_message ?? 'Download failed. Please try again.')
            }
          }
        })
        .catch(() => {
          // Ignore transient polling errors; keep polling.
        })
    }, 2000)

    return stopPoll
  }, [step, installId, navigate])

  // Auto-run the benchmark once when entering the 'benchmark' step.
  useEffect(() => {
    if (step !== 'benchmark' || benchmarkStartedRef.current) return
    benchmarkStartedRef.current = true
    setBenchmarkRunning(true)
    setBenchmarkResult(null)
    setBenchmarkError(null)
    api
      .benchmarkModel({})
      .then((result) => {
        setBenchmarkResult(result)
      })
      .catch((err: unknown) => {
        setBenchmarkError(err instanceof Error ? err.message : 'Benchmark failed.')
      })
      .finally(() => {
        setBenchmarkRunning(false)
      })
  }, [step])

  const recommendedModel = modelsData?.registry.find((m) => m.role === 'starter') ?? null

  function resetAction() {
    setActionError(null)
    setActionLoading(false)
  }

  // If setup was already completed when this component mounted, skip the wizard entirely.
  if (alreadyCompleteRef.current) {
    return <Navigate to="/" replace />
  }

  // ── Welcome ──────────────────────────────────────────────────────────────────

  if (step === 'welcome') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Welcome to Conversation Simulator</h1>
        <p style={{ fontSize: '1rem', lineHeight: 1.6, color: '#d4d4d8' }}>
          Conversation Simulator is a flight simulator for real-life conversations — a private,
          local-first tool for practising difficult discussions at your own pace.
        </p>

        <div
          role="note"
          aria-label="privacy and offline-play guarantee"
          style={{
            background: 'rgba(99,102,241,0.08)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: '8px',
            padding: '1rem 1.25rem',
            marginTop: '1.25rem',
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: '#a5b4fc' }}>
            Your data stays on this machine
          </p>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: '#c7d2fe' }}>
            Conversations, transcripts, audio recordings, and AI responses are processed locally
            and never leave your computer unless you choose to export or share them. You can play
            without an internet connection once the model is installed.
          </p>
        </div>

        <p style={{ marginTop: '1.5rem', color: '#a1a1aa', fontSize: '0.9rem' }}>
          This one-time setup wizard will help you choose a local AI model and get ready to play.
          It takes about a minute plus download time.
        </p>

        <div style={{ marginTop: '1.5rem' }}>
          <PrimaryButton onClick={() => setStep('loading')}>Get started</PrimaryButton>
        </div>
      </div>
    )
  }

  // ── Loading ───────────────────────────────────────────────────────────────────

  if (step === 'loading') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Model Setup</h1>
        <p>Loading model information…</p>
      </div>
    )
  }

  // ── Load error ────────────────────────────────────────────────────────────────

  if (step === 'load-error') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Model Setup</h1>
        <p role="alert" style={{ color: '#f87171' }}>
          {loadError ?? 'Something went wrong loading model information. Please try again.'}
        </p>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
          The local runtime may be unavailable. Check that it is running, then reload this page.
          If your hardware cannot run a full model, the text-only demo works without one — or see
          the{' '}
          <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">
            setup docs
          </a>{' '}
          for smaller-model and troubleshooting guidance.
        </p>
        <ActionButton onClick={() => setStep('welcome')}>Back to welcome</ActionButton>
      </div>
    )
  }

  // ── Choose ────────────────────────────────────────────────────────────────────

  if (step === 'choose') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Choose how to get started</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Pick an option below. You can change it later in Settings.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1.5rem' }}>
          {recommendedModel && (
            <SectionCard>
              <CardHeading>Install recommended model</CardHeading>
              <CardDescription>
                {recommendedModel.name} · {recommendedModel.size_gb} GB ·{' '}
                {recommendedModel.license_spdx} · Requires {recommendedModel.min_vram_gb} GB VRAM
              </CardDescription>
              <ActionButton
                onClick={() => {
                  setSelectedModel(recommendedModel)
                  resetAction()
                  setStep('confirm-install')
                }}
              >
                Install {recommendedModel.name}
              </ActionButton>
            </SectionCard>
          )}

          <SectionCard>
            <CardHeading>Use existing Ollama model</CardHeading>
            <CardDescription>
              Select from models already installed in your local Ollama instance.
            </CardDescription>
            <ActionButton
              onClick={() => {
                resetAction()
                setStep('ollama-select')
              }}
            >
              Browse Ollama models
            </ActionButton>
          </SectionCard>

          <SectionCard>
            <CardHeading>Use a local GGUF file</CardHeading>
            <CardDescription>
              Point to a GGUF model file already on your machine. Compatible with llama.cpp.
            </CardDescription>
            <ActionButton
              onClick={() => {
                setGgufPath('')
                setGgufPathError(null)
                resetAction()
                setStep('gguf-path')
              }}
            >
              Use a GGUF file
            </ActionButton>
          </SectionCard>

          <SectionCard>
            <CardHeading>Continue without a model</CardHeading>
            <CardDescription>
              Try the interface without a model. NPC responses are scripted — not real AI quality.
            </CardDescription>
            <ActionButton
              onClick={() => {
                resetAction()
                setStep('demo-warning')
              }}
            >
              Continue in text-only demo
            </ActionButton>
          </SectionCard>
        </div>
      </div>
    )
  }

  // ── Confirm install ───────────────────────────────────────────────────────────

  if (step === 'confirm-install' && selectedModel) {
    const sha256Display = selectedModel.sha256 ?? 'Not available'
    const sha256IsPending = sha256Display.toUpperCase() === 'PENDING'
    const needsMoreVram = selectedModel.min_vram_gb != null && selectedModel.min_vram_gb > 4

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Confirm model install</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Review the details below before starting the download. No download begins until you click{' '}
          <strong>Confirm &amp; install</strong>.
        </p>

        <table style={{ marginTop: '1rem', borderCollapse: 'collapse', width: '100%' }}>
          <tbody>
            <DetailRow label="Model">{selectedModel.name}</DetailRow>
            <DetailRow label="Size">
              {selectedModel.size_gb != null ? `${selectedModel.size_gb} GB` : 'Unknown'}
            </DetailRow>
            <DetailRow label="License">
              {selectedModel.license_url ? (
                <a href={selectedModel.license_url} target="_blank" rel="noreferrer">
                  {selectedModel.license_spdx ?? 'View license'}
                </a>
              ) : (
                selectedModel.license_spdx ?? 'Unknown'
              )}
            </DetailRow>
            <DetailRow label="Min VRAM">
              {selectedModel.min_vram_gb != null ? `${selectedModel.min_vram_gb} GB` : 'Unknown'}
            </DetailRow>
            <DetailRow label="Recommended VRAM">
              {selectedModel.recommended_vram_gb != null
                ? `${selectedModel.recommended_vram_gb} GB`
                : 'Unknown'}
            </DetailRow>
            <DetailRow label="SHA-256 checksum">
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.8rem',
                  wordBreak: 'break-all',
                  color: sha256IsPending ? '#fbbf24' : 'inherit',
                }}
              >
                {sha256Display}
              </span>
              {sha256IsPending && (
                <span
                  style={{
                    display: 'block',
                    fontSize: '0.8rem',
                    color: '#fbbf24',
                    marginTop: '0.2rem',
                  }}
                >
                  Checksum not yet confirmed — install may be rejected by the runtime.
                </span>
              )}
            </DetailRow>
            <DetailRow label="Saved to">
              <code style={{ fontSize: '0.8rem' }}>
                ~/.convsim/models/llm/{selectedModel.id}.gguf
              </code>
            </DetailRow>
          </tbody>
        </table>

        <div
          role="note"
          aria-label="offline-play explanation"
          style={{
            background: 'rgba(99,102,241,0.08)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: '6px',
            padding: '0.85rem 1rem',
            marginTop: '1rem',
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: '#a5b4fc', fontSize: '0.875rem' }}>
            Plays offline after install
          </p>
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.825rem', color: '#c7d2fe' }}>
            Once downloaded, this model runs entirely on your machine. You can disconnect from the
            internet and the game will work exactly the same. No data is sent to any server.
          </p>
        </div>

        {actionError && (
          <div role="alert" style={{ marginTop: '1rem' }}>
            <p style={{ color: '#f87171', margin: 0 }}>{actionError}</p>
            <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginTop: '0.4rem' }}>
              {needsMoreVram
                ? `This model requires ${selectedModel.min_vram_gb} GB VRAM. If your hardware is limited, try a smaller model or `
                : 'If your hardware or runtime cannot install this model, try a smaller model or '}
              check the{' '}
              <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">
                setup docs
              </a>
              .
            </p>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
          <PrimaryButton
            disabled={actionLoading}
            onClick={async () => {
              setActionLoading(true)
              setActionError(null)
              try {
                const resp = await api.installModel({ registry_id: selectedModel.id })
                setInstallId(resp.install_id)
                setInstallRecord(null)
                setStep('installing')
              } catch (err: unknown) {
                setActionError(
                  err instanceof Error ? err.message : 'Install failed. Please try again.',
                )
              } finally {
                setActionLoading(false)
              }
            }}
          >
            {actionLoading ? 'Starting…' : 'Confirm & install'}
          </PrimaryButton>
          <ActionButton
            onClick={() => {
              setSelectedModel(null)
              resetAction()
              setStep('choose')
            }}
          >
            Cancel
          </ActionButton>
        </div>
      </div>
    )
  }

  // ── Installing ────────────────────────────────────────────────────────────────

  if (step === 'installing') {
    const status = installRecord?.install_status ?? 'pending'
    const progressBytes = installRecord?.progress_bytes ?? 0
    const totalBytes = installRecord?.size_bytes ?? null
    const pct =
      totalBytes != null && totalBytes > 0
        ? Math.min(100, Math.round((progressBytes / totalBytes) * 100))
        : null

    const statusLabel: Record<string, string> = {
      pending: 'Queued…',
      downloading: 'Downloading…',
    }

    // When the download has failed, show specific recovery paths inline.
    if (actionError != null) {
      const isNetworkError =
        /no[\s_-]?network|network[\s_-]?unavailable|network[\s_-]?error|connection[\s_-]?refused|failed[\s_-]?to[\s_-]?connect|offline|timed[\s_-]?out/i.test(
          actionError,
        )
      const isDiskError =
        /insufficient[\s_-]?disk|not[\s_-]?enough[\s_-]?disk|disk[\s_-]?space|no[\s_-]?space[\s_-]?left|storage[\s_-]?full/i.test(
          actionError,
        )

      return (
        <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
          <h1>Installing model</h1>

          {isNetworkError && (
            <div
              role="alert"
              aria-label="network error"
              style={{
                marginTop: '1rem',
                padding: '0.85rem 1rem',
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: '6px',
              }}
            >
              <p
                style={{
                  margin: '0 0 0.4rem',
                  color: '#f87171',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                }}
              >
                Network connection lost
              </p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                The download could not complete. Check your internet connection and try again, or
                choose a different option that does not require a download.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton
                  onClick={() => {
                    resetAction()
                    setStep('confirm-install')
                  }}
                >
                  Retry download
                </PrimaryButton>
                <ActionButton
                  onClick={() => {
                    resetAction()
                    setStep('choose')
                  }}
                >
                  Choose a different option
                </ActionButton>
              </div>
            </div>
          )}

          {isDiskError && (
            <div
              role="alert"
              aria-label="insufficient disk space"
              style={{
                marginTop: '1rem',
                padding: '0.85rem 1rem',
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: '6px',
              }}
            >
              <p
                style={{
                  margin: '0 0 0.4rem',
                  color: '#f87171',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                }}
              >
                Not enough disk space
              </p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                {selectedModel != null
                  ? `This model requires approximately ${selectedModel.size_gb} GB of free disk space. `
                  : ''}
                Free up space on your drive and try again, or use a smaller model or Ollama
                instead.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton
                  onClick={() => {
                    resetAction()
                    setStep('confirm-install')
                  }}
                >
                  Try again
                </PrimaryButton>
                <ActionButton
                  onClick={() => {
                    resetAction()
                    setStep('choose')
                  }}
                >
                  Choose a different option
                </ActionButton>
              </div>
            </div>
          )}

          {!isNetworkError && !isDiskError && (
            <div
              role="alert"
              style={{
                marginTop: '1rem',
                padding: '0.85rem 1rem',
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: '6px',
              }}
            >
              <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontSize: '0.875rem' }}>
                {actionError}
              </p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: '#a1a1aa' }}>
                Check the{' '}
                <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">
                  setup docs
                </a>{' '}
                if the problem persists.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton
                  onClick={() => {
                    resetAction()
                    setStep('confirm-install')
                  }}
                >
                  Try again
                </PrimaryButton>
                <ActionButton
                  onClick={() => {
                    resetAction()
                    setStep('choose')
                  }}
                >
                  Choose a different option
                </ActionButton>
              </div>
            </div>
          )}
        </div>
      )
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Installing model</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          {statusLabel[status] ?? 'Downloading…'} Download time depends on your connection speed.
        </p>

        <div
          role="progressbar"
          aria-valuenow={pct ?? 0}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Download progress"
          style={{
            marginTop: '1rem',
            height: '8px',
            borderRadius: '4px',
            background: 'rgba(255,255,255,0.1)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: pct != null ? `${pct}%` : '0%',
              background: 'rgba(99,102,241,0.85)',
              borderRadius: '4px',
              transition: 'width 0.4s ease',
            }}
          />
        </div>

        <p style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.4rem' }}>
          {pct != null
            ? `${pct}% — ${(progressBytes / 1_073_741_824).toFixed(2)} GB`
            : 'Waiting for progress data…'}
        </p>

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
          <ActionButton
            onClick={async () => {
              if (installId != null) {
                try {
                  await api.cancelInstall(installId)
                } catch {
                  // Cancel is best-effort; navigate home regardless.
                }
              }
              markFirstRunComplete()
              navigate('/')
            }}
          >
            Cancel and go home
          </ActionButton>
        </div>
      </div>
    )
  }

  // ── Ollama select ─────────────────────────────────────────────────────────────

  if (step === 'ollama-select') {
    const ollamaModels = modelsData?.ollama_models ?? []

    async function handleSelectOllama(m: DetectedOllamaModel) {
      setActionLoading(true)
      setActionError(null)
      try {
        await api.useModel({ runtime_id: 'ollama', model_id: m.id })
        benchmarkStartedRef.current = false
        setStep('benchmark')
      } catch (err: unknown) {
        setActionError(err instanceof Error ? err.message : 'Failed to activate Ollama model.')
        setActionLoading(false)
      }
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Use Ollama model</h1>

        {ollamaModels.length === 0 ? (
          <div>
            <p role="status">No Ollama models detected.</p>
            <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
              Install Ollama and pull at least one model, then return here.{' '}
              <a href="https://ollama.com" target="_blank" rel="noreferrer">
                ollama.com
              </a>
            </p>
          </div>
        ) : (
          <div>
            <p style={{ color: '#a1a1aa', fontSize: '0.9rem', marginBottom: '1rem' }}>
              Select a model from your local Ollama installation.
            </p>
            <ul
              style={{
                listStyle: 'none',
                padding: 0,
                margin: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
              }}
            >
              {ollamaModels.map((m) => (
                <li
                  key={m.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                    padding: '0.75rem',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '6px',
                  }}
                >
                  <span>
                    <strong>{m.name}</strong>
                    {m.size_category && (
                      <span
                        style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.8rem' }}
                      >
                        {m.size_category}
                      </span>
                    )}
                  </span>
                  <ActionButton disabled={actionLoading} onClick={() => handleSelectOllama(m)}>
                    Use this model
                  </ActionButton>
                </li>
              ))}
            </ul>
          </div>
        )}

        {actionError && (
          <p
            role="alert"
            style={{ color: '#f87171', marginTop: '0.75rem', fontSize: '0.875rem' }}
          >
            {actionError}
          </p>
        )}

        <div style={{ marginTop: '1.5rem' }}>
          <ActionButton
            onClick={() => {
              resetAction()
              setStep('choose')
            }}
          >
            Back
          </ActionButton>
        </div>
      </div>
    )
  }

  // ── GGUF path ─────────────────────────────────────────────────────────────────

  if (step === 'gguf-path') {
    async function handleUseGguf() {
      const trimmed = ggufPath.trim()
      if (!trimmed) {
        setGgufPathError('Please enter a file path.')
        return
      }
      if (!trimmed.toLowerCase().endsWith('.gguf')) {
        setGgufPathError('The file must have a .gguf extension.')
        return
      }
      setGgufPathError(null)
      setActionLoading(true)
      setActionError(null)
      try {
        await api.registerGguf({ path: trimmed })
        try {
          await api.startSidecar(trimmed)
        } catch (sidecarErr) {
          console.warn('GGUF registered, but the llama.cpp sidecar failed to start:', sidecarErr)
        }
        benchmarkStartedRef.current = false
        setStep('benchmark')
      } catch (err: unknown) {
        setActionError(err instanceof Error ? err.message : 'Failed to activate the GGUF file.')
        setActionLoading(false)
      }
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Use a GGUF file</h1>

        <div
          role="note"
          aria-label="license responsibility notice"
          style={{
            background: 'rgba(251,191,36,0.08)',
            border: '1px solid rgba(251,191,36,0.35)',
            borderRadius: '6px',
            padding: '0.85rem 1rem',
            marginTop: '1rem',
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: '#fbbf24', fontSize: '0.875rem' }}>
            You are responsible for this model's license and hardware fit.
          </p>
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.825rem', color: '#fde68a' }}>
            This app does not claim the model you provide is official, licensed for redistribution,
            or suitable for your hardware. Review the model's license before use. The file will not
            be copied — only its path is stored.
          </p>
        </div>

        <div style={{ marginTop: '1.25rem' }}>
          <label
            htmlFor="gguf-path"
            style={{ display: 'block', marginBottom: '0.4rem', fontSize: '0.875rem' }}
          >
            File path
          </label>
          <input
            id="gguf-path"
            type="text"
            value={ggufPath}
            onChange={(e) => {
              setGgufPath(e.target.value)
              setGgufPathError(null)
            }}
            placeholder="/path/to/model.gguf"
            aria-describedby="gguf-path-hint"
            aria-invalid={ggufPathError != null}
            style={{
              width: '100%',
              padding: '0.5rem 0.75rem',
              borderRadius: '4px',
              background: 'rgba(255,255,255,0.05)',
              border: ggufPathError
                ? '1px solid rgba(239,68,68,0.6)'
                : '1px solid rgba(255,255,255,0.15)',
              color: 'inherit',
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              boxSizing: 'border-box',
            }}
          />
          <p
            id="gguf-path-hint"
            style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.3rem' }}
          >
            Absolute path to a GGUF model file compatible with llama.cpp.
          </p>
          {ggufPathError && (
            <p
              role="alert"
              style={{ fontSize: '0.875rem', color: '#f87171', margin: '0.3rem 0 0' }}
            >
              {ggufPathError}
            </p>
          )}
        </div>

        {actionError && (
          <p
            role="alert"
            style={{ color: '#f87171', marginTop: '0.75rem', fontSize: '0.875rem' }}
          >
            {actionError}
          </p>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
          <PrimaryButton disabled={actionLoading} onClick={handleUseGguf}>
            {actionLoading ? 'Activating…' : 'Use this file'}
          </PrimaryButton>
          <ActionButton
            onClick={() => {
              resetAction()
              setStep('choose')
            }}
          >
            Back
          </ActionButton>
        </div>
      </div>
    )
  }

  // ── Demo warning ──────────────────────────────────────────────────────────────

  if (step === 'demo-warning') {
    async function handleConfirmDemo() {
      setActionLoading(true)
      try {
        await api.useModel({ runtime_id: 'fake', model_id: null })
      } catch {
        // Demo mode activation is best-effort; proceed regardless.
      } finally {
        setActionLoading(false)
      }
      markFirstRunComplete()
      navigate('/library')
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Text-only demo</h1>

        <div
          role="note"
          aria-label="demo mode disclaimer"
          style={{
            background: 'rgba(251,191,36,0.08)',
            border: '1px solid rgba(251,191,36,0.35)',
            borderRadius: '6px',
            padding: '1rem 1.25rem',
            marginTop: '1rem',
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: '#fbbf24' }}>
            This is a demo, not production quality.
          </p>
          <p style={{ margin: '0.6rem 0 0', fontSize: '0.875rem', color: '#fde68a' }}>
            Text-only demo mode uses scripted responses instead of a real AI model. NPC behaviour
            is hard-coded and does not represent the response quality you will experience with a
            local model installed. It is intended only to explore the interface before committing
            to a model download.
          </p>
        </div>

        <p style={{ marginTop: '1rem', fontSize: '0.875rem', color: '#a1a1aa' }}>
          You can return to model setup at any time from <strong>Settings → Model</strong>.
        </p>

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
          <PrimaryButton disabled={actionLoading} onClick={handleConfirmDemo}>
            {actionLoading ? 'Starting…' : 'I understand — continue with text-only demo'}
          </PrimaryButton>
          <ActionButton
            onClick={() => {
              resetAction()
              setStep('choose')
            }}
          >
            Cancel
          </ActionButton>
        </div>
      </div>
    )
  }

  // ── Benchmark ─────────────────────────────────────────────────────────────────

  if (step === 'benchmark') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Model benchmark</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Running a short benchmark to measure generation speed and check hardware compatibility.
        </p>

        {benchmarkRunning && (
          <p role="status" style={{ marginTop: '1rem' }}>
            Running benchmark…
          </p>
        )}

        {benchmarkResult && !benchmarkRunning && (
          <div>
            <table style={{ marginTop: '1rem', borderCollapse: 'collapse' }}>
              <tbody>
                <DetailRow label="Speed">
                  {benchmarkResult.tokens_per_sec.toFixed(1)} tokens/sec
                </DetailRow>
                {benchmarkResult.context_length != null && (
                  <DetailRow label="Context window">
                    {benchmarkResult.context_length.toLocaleString()} tokens
                  </DetailRow>
                )}
                <DetailRow label="Runtime">{benchmarkResult.runtime_id}</DetailRow>
              </tbody>
            </table>

            {benchmarkResult.warnings.length > 0 && (
              <div
                role="alert"
                aria-label="benchmark warnings"
                style={{
                  marginTop: '1rem',
                  background: 'rgba(251,191,36,0.08)',
                  border: '1px solid rgba(251,191,36,0.35)',
                  borderRadius: '6px',
                  padding: '0.75rem 1rem',
                }}
              >
                <p
                  style={{
                    margin: '0 0 0.5rem',
                    fontWeight: 600,
                    color: '#fbbf24',
                    fontSize: '0.875rem',
                  }}
                >
                  Performance warnings
                </p>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: '1.25rem',
                    fontSize: '0.875rem',
                    color: '#fde68a',
                  }}
                >
                  {benchmarkResult.warnings.map((w, i) => (
                    <li key={i} style={{ marginBottom: '0.3rem' }}>
                      {w}
                    </li>
                  ))}
                </ul>
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: '#a1a1aa' }}>
                  If generation is slow, try a smaller model or check that GPU acceleration is
                  enabled in your runtime settings.{' '}
                  <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">
                    Setup docs
                  </a>
                </p>
              </div>
            )}
          </div>
        )}

        {benchmarkError && !benchmarkRunning && (
          <div
            role="alert"
            style={{
              marginTop: '1rem',
              padding: '0.75rem 1rem',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '6px',
            }}
          >
            <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontSize: '0.875rem' }}>
              Benchmark failed: {benchmarkError}
            </p>
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#a1a1aa' }}>
              Your model is still selected and ready to use. The benchmark is optional.
            </p>
          </div>
        )}

        <div style={{ marginTop: '1.5rem' }}>
          <PrimaryButton
            disabled={benchmarkRunning}
            onClick={() => {
              markFirstRunComplete()
              navigate('/')
            }}
          >
            {benchmarkRunning ? 'Running…' : 'Continue to Home'}
          </PrimaryButton>
        </div>
      </div>
    )
  }

  return null
}
