// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ModelsResponse, ModelRegistryEntry, DetectedOllamaModel, InstalledModelInfo, BenchmarkResponse } from '@convsim/shared'
import type { ApiError } from '../api/errors'
import { errorHeadline } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'

const SETUP_DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/wiki'

type WizardStep =
  | 'loading'
  | 'choose'
  | 'confirm-install'
  | 'installing'
  | 'ollama-select'
  | 'gguf-path'
  | 'demo-warning'
  | 'benchmark'
  | 'load-error'

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: '8px',
        padding: '1rem',
      }}
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

export default function ModelManager() {
  const navigate = useNavigate()
  const [step, setStep] = useState<WizardStep>('loading')
  const [modelsData, setModelsData] = useState<ModelsResponse | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)

  const [selectedModel, setSelectedModel] = useState<ModelRegistryEntry | null>(null)
  const [ggufPath, setGgufPath] = useState('')
  const [ggufPathError, setGgufPathError] = useState<string | null>(null)

  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const [installId, setInstallId] = useState<number | null>(null)
  const [installRecord, setInstallRecord] = useState<InstalledModelInfo | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [benchmarkRunning, setBenchmarkRunning] = useState(false)
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResponse | null>(null)
  const [benchmarkError, setBenchmarkError] = useState<ApiError | null>(null)
  const benchmarkStartedRef = useRef(false)

  async function loadData() {
    setStep('loading')
    const r = await api.getModels()
    if (!r.ok) { setLoadError(r.error); setStep('load-error'); return }
    setModelsData(r.data)
    setStep('choose')
  }

  useEffect(() => { void loadData() }, [])

  // Poll install progress while in the 'installing' step.
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
        .then((r) => {
          if (!r.ok) { /* Ignore transient polling errors; keep polling. */ return }
          const record = r.data
          setInstallRecord(record)
          const terminal = ['ready', 'complete', 'failed', 'cancelled', 'checksum_mismatch']
          if (terminal.includes(record.install_status)) {
            stopPoll()
            if (record.install_status === 'ready' || record.install_status === 'complete') {
              navigate('/')
            } else {
              setActionError({ kind: 'http-error', message: record.error_message ?? 'Download failed. Please try again.' })
              setStep('confirm-install')
            }
          }
        })
    }, 2000)

    return stopPoll
  }, [step, installId, navigate])

  // Auto-run the benchmark once when entering the 'benchmark' step. The prompt is
  // fixed server-side and contains no user transcript. A failure is non-fatal —
  // the model is already active, so we surface the error and still allow Continue.
  useEffect(() => {
    if (step !== 'benchmark' || benchmarkStartedRef.current) return
    benchmarkStartedRef.current = true
    setBenchmarkRunning(true)
    setBenchmarkResult(null)
    setBenchmarkError(null)
    api
      .benchmarkModel({})
      .then((r) => {
        if (r.ok) setBenchmarkResult(r.data)
        else setBenchmarkError(r.error)
      })
      .finally(() => {
        setBenchmarkRunning(false)
      })
  }, [step])

  const recommendedModel =
    modelsData?.registry.find((m) => m.role === 'starter') ??
    null

  function resetAction() {
    setActionError(null)
    setActionLoading(false)
  }

  // ── Loading ─────────────────────────────────────────────────────────────────

  if (step === 'loading') {
    return (
      <div>
        <h1>Model Setup</h1>
        <p>Loading model information…</p>
      </div>
    )
  }

  // ── Load error ───────────────────────────────────────────────────────────────

  if (step === 'load-error') {
    return (
      <div style={{ maxWidth: '640px' }}>
        <h1>Model Setup</h1>
        {loadError && <ApiErrorView error={loadError} onRetry={loadData} context="ModelManager" />}
        <ActionButton onClick={() => navigate('/')}>Back to Home</ActionButton>
      </div>
    )
  }

  // ── Choose ───────────────────────────────────────────────────────────────────

  if (step === 'choose') {
    const lb = modelsData?.last_benchmark ?? null
    return (
      <div style={{ maxWidth: '640px' }}>
        <h1>Set up your model</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Choose how to get started. You can change this later in Settings.
        </p>

        {lb && (
          <div
            aria-label="last benchmark result"
            style={{
              marginTop: '1rem',
              padding: '0.6rem 0.9rem',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '6px',
              fontSize: '0.85rem',
              color: '#a1a1aa',
            }}
          >
            Last benchmark:{' '}
            <span style={{ color: 'inherit', fontWeight: 500 }}>
              {lb.tokens_per_sec.toFixed(1)} tok/s
            </span>
            {lb.context_length != null && (
              <span style={{ marginLeft: '0.75rem' }}>
                · context {lb.context_length.toLocaleString()} tokens
              </span>
            )}
            {lb.warnings.length > 0 && (
              <span style={{ color: '#fbbf24', marginLeft: '0.75rem' }}>
                · {lb.warnings.length} warning{lb.warnings.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        )}

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
            <CardHeading>Text-only demo</CardHeading>
            <CardDescription>
              Try the interface without a model. NPC responses are scripted — not real AI quality.
            </CardDescription>
            <ActionButton
              onClick={() => {
                resetAction()
                setStep('demo-warning')
              }}
            >
              Try text-only demo
            </ActionButton>
          </SectionCard>
        </div>

        <div style={{ marginTop: '1.5rem' }}>
          <ActionButton onClick={() => navigate('/')}>Back to Home</ActionButton>
        </div>
      </div>
    )
  }

  // ── Confirm install ──────────────────────────────────────────────────────────

  if (step === 'confirm-install' && selectedModel) {
    const sha256Display = selectedModel.sha256 ?? 'Not available'
    const sha256IsPending = sha256Display.toUpperCase() === 'PENDING'

    return (
      <div style={{ maxWidth: '640px' }}>
        <h1>Confirm model install</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Review the details below before starting the download. No download begins until you
          click <strong>Confirm &amp; install</strong>.
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
              {selectedModel.min_vram_gb != null
                ? `${selectedModel.min_vram_gb} GB`
                : 'Unknown'}
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
                  style={{ display: 'block', fontSize: '0.8rem', color: '#fbbf24', marginTop: '0.2rem' }}
                >
                  Checksum not yet confirmed — install may be rejected by the runtime.
                </span>
              )}
            </DetailRow>
            <DetailRow label="Storage path">
              <code style={{ fontSize: '0.8rem' }}>
                ~/.convsim/models/llm/{selectedModel.id}.gguf
              </code>
            </DetailRow>
            <DetailRow label="Source">
              {selectedModel.source_type === 'registry' ? 'Official registry' : selectedModel.source_type ?? 'Unknown'}
            </DetailRow>
          </tbody>
        </table>

        {actionError && <ApiErrorView error={actionError} compact context="ModelManager-Action" />}

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
          <PrimaryButton
            disabled={actionLoading}
            onClick={async () => {
              setActionLoading(true)
              setActionError(null)
              const r = await api.installModel({ registry_id: selectedModel.id })
              if (!r.ok) { setActionError(r.error); setActionLoading(false); return }
              setInstallId(r.data.install_id)
              setInstallRecord(null)
              setStep('installing')
              setActionLoading(false)
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

  // ── Installing ───────────────────────────────────────────────────────────────

  if (step === 'installing') {
    const status = installRecord?.install_status ?? 'pending'
    const progressBytes = installRecord?.progress_bytes ?? 0
    const totalBytes = installRecord?.size_bytes ?? null
    const pct = totalBytes != null && totalBytes > 0
      ? Math.min(100, Math.round((progressBytes / totalBytes) * 100))
      : null

    const statusLabel: Record<string, string> = {
      pending: 'Queued…',
      downloading: 'Downloading…',
    }

    return (
      <div style={{ maxWidth: '640px' }}>
        <h1>Installing model</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          {statusLabel[status] ?? 'Downloading…'} Download time depends on your connection speed.
        </p>

        {/* Progress bar */}
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
            onClick={() => {
              if (installId != null) {
                void api.cancelInstall(installId)
              }
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
      const r = await api.useModel({ runtime_id: 'ollama', model_id: m.id })
      if (!r.ok) { setActionError(r.error); setActionLoading(false); return }
      setStep('benchmark')
    }

    return (
      <div style={{ maxWidth: '640px' }}>
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
                      <span style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.8rem' }}>
                        {m.size_category}
                      </span>
                    )}
                  </span>
                  <ActionButton
                    disabled={actionLoading}
                    onClick={() => handleSelectOllama(m)}
                  >
                    Use this model
                  </ActionButton>
                </li>
              ))}
            </ul>
          </div>
        )}

        {actionError && <ApiErrorView error={actionError} compact context="ModelManager-Action" />}

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

  // ── GGUF path ────────────────────────────────────────────────────────────────

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
      const r = await api.registerGguf({ path: trimmed })
      if (!r.ok) { setActionError(r.error); setActionLoading(false); return }
      // Best-effort sidecar launch. Registration already made the model the
      // active config, so a failed auto-start is non-fatal — proceed to the
      // benchmark step and let the user start the server manually if needed.
      void api.startSidecar(trimmed)
      setStep('benchmark')
    }

    return (
      <div style={{ maxWidth: '640px' }}>
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
            or suitable for your hardware. Review the model's license before use. The file will
            not be copied — only its path is stored.
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
          <p id="gguf-path-hint" style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.3rem' }}>
            Absolute path to a GGUF model file compatible with llama.cpp. Paths with spaces are
            supported.
          </p>
          {ggufPathError && (
            <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', margin: '0.3rem 0 0' }}>
              {ggufPathError}
            </p>
          )}
        </div>

        {actionError && <ApiErrorView error={actionError} compact context="ModelManager-Action" />}

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
      // The text-only demo is served by the deterministic "fake" runtime, which
      // always reports ready and streams scripted responses. There is no separate
      // "demo" runtime registered in the backend. Activation is best-effort.
      void api.useModel({ runtime_id: 'fake', model_id: null })
      setActionLoading(false)
      navigate('/library')
    }

    return (
      <div style={{ maxWidth: '640px' }}>
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

  // ── Benchmark ────────────────────────────────────────────────────────────────

  if (step === 'benchmark') {
    return (
      <div style={{ maxWidth: '640px' }}>
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
                <p style={{ margin: '0 0 0.5rem', fontWeight: 600, color: '#fbbf24', fontSize: '0.875rem' }}>
                  Performance warnings
                </p>
                <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.875rem', color: '#fde68a' }}>
                  {benchmarkResult.warnings.map((w, i) => (
                    <li key={i} style={{ marginBottom: '0.3rem' }}>{w}</li>
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
              Benchmark failed: {errorHeadline(benchmarkError)}
            </p>
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#a1a1aa' }}>
              Your model is still selected and ready to use. The benchmark is optional.
            </p>
          </div>
        )}

        <div style={{ marginTop: '1.5rem' }}>
          <PrimaryButton disabled={benchmarkRunning} onClick={() => navigate('/')}>
            {benchmarkRunning ? 'Running…' : 'Continue to Home'}
          </PrimaryButton>
        </div>
      </div>
    )
  }

  return null
}
