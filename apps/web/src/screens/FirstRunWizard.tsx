// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { api } from '../api/client'
import { openExternal } from '../lib/openExternal'
import { SETUP_KEYS } from '../privacyPrefs'
import type {
  ModelsResponse,
  ModelRegistryEntry,
  DetectedOllamaModel,
  InstalledModelInfo,
  BenchmarkResponse,
  PreflightResponse,
  PreflightCheck,
} from '@convsim/shared'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'
const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'

// Marks the one-time setup wizard complete so the FirstRunGuard stops redirecting here.
// Used only within this module; kept unexported so the file exports only its component
// (satisfies react-refresh/only-export-components).
function markFirstRunComplete(): void {
  try {
    localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true')
  } catch {
    // localStorage may be unavailable in some environments; proceed anyway.
  }
}

function markTutorialComplete(): void {
  try {
    localStorage.setItem(SETUP_KEYS.tutorialComplete, 'true')
  } catch {
    // localStorage may be unavailable in some environments; proceed anyway.
  }
}

function isTutorialComplete(): boolean {
  try {
    return localStorage.getItem(SETUP_KEYS.tutorialComplete) === 'true'
  } catch {
    return false
  }
}

type WizardStep =
  | 'welcome'
  | 'loading'
  | 'preflight'
  | 'choose'
  | 'confirm-install'
  | 'installing'
  | 'tutorial-prompt'
  | 'benchmark'
  | 'ollama-select'
  | 'gguf-path'
  | 'demo-warning'
  | 'load-error'

// Infrastructure checks that block the wizard if they fail (binary missing,
// disk full, data dir unwritable).  LLM-presence and packs are handled by the
// wizard itself and therefore excluded from this list.
const BLOCKING_CHECK_IDS = new Set(['llama-cpp-binary', 'disk-space', 'data-dir-writable'])

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

  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null)

  // Focus management: move focus to each step's heading on step change so that keyboard
  // and screen-reader users are announced the new context without a full page reload.
  const stepHeadingRef = useRef<HTMLHeadingElement>(null)
  const isInitialStep = useRef(true)
  useEffect(() => {
    if (isInitialStep.current) {
      isInitialStep.current = false
      return
    }
    stepHeadingRef.current?.focus()
  }, [step])
  const benchmarkStartedRef = useRef(false)
  // Capture the "already done" state once at mount so that calling markFirstRunComplete()
  // mid-wizard (before the navigate() fires) doesn't cause a spurious redirect to "/".
  const alreadyCompleteRef = useRef(localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true')

  // Fetch model data and run preflight when the user advances past the welcome step.
  useEffect(() => {
    if (step !== 'loading') return
    Promise.all([api.getModels(), api.preflight()]).then(([modelsResult, preflightResult]) => {
      if (!modelsResult.ok) {
        setLoadError(modelsResult.error.message)
        setStep('load-error')
        return
      }
      setModelsData(modelsResult.data)

      if (preflightResult.ok) {
        setPreflightResult(preflightResult.data)
        const blockingFails = preflightResult.data.checks.filter(
          (c: PreflightCheck) => c.status === 'fail' && BLOCKING_CHECK_IDS.has(c.id),
        )
        if (blockingFails.length > 0) {
          setStep('preflight')
          return
        }
      }
      setStep('choose')
    }).catch((err: unknown) => {
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
        .then((r) => {
          if (!r.ok) { /* Ignore transient polling errors; keep polling. */ return }
          const record = r.data
          setInstallRecord(record)
          const terminal = ['ready', 'complete', 'failed', 'cancelled', 'checksum_mismatch']
          if (terminal.includes(record.install_status)) {
            stopPoll()
            if (record.install_status === 'ready' || record.install_status === 'complete') {
              markFirstRunComplete()
              // If the player finished the tutorial while waiting, offer the library
              // so they can jump straight into a real scenario.
              navigate(isTutorialComplete() ? '/library' : '/')
            } else {
              // Stay on the installing step and surface the error with recovery options.
              setActionError(record.error_message ?? 'Download failed. Please try again.')
            }
          }
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
      .then((r) => {
        if (r.ok) {
          setBenchmarkResult(r.data)
        } else {
          setBenchmarkError(r.error.message)
        }
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
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Welcome to Conversation Simulator</h1>
        <p style={{ fontSize: '1rem', lineHeight: 1.6, color: '#d4d4d8' }}>
          Conversation Simulator is the private, local-first practice tool for conversations that
          matter — interviews, negotiations, language practice, and difficult discussions at your
          own pace.
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

        <div style={{ marginTop: '1.5rem' }}>
          <p style={{ fontWeight: 600, color: '#e8e8ea', margin: '0 0 0.75rem' }}>How it works</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            <div
              aria-label="local model explanation"
              style={{
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '0.85rem 1rem',
              }}
            >
              <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem' }}>
                A local AI model powers the conversations
              </p>
              <p style={{ margin: '0.35rem 0 0', fontSize: '0.825rem', color: '#a1a1aa' }}>
                The app uses a small language model that runs entirely on your machine. After a
                one-time download it works without internet — and nothing is ever sent to a server.
              </p>
            </div>
            <div
              aria-label="packs explanation"
              style={{
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '0.85rem 1rem',
              }}
            >
              <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem' }}>
                Packs give you scenarios to practise
              </p>
              <p style={{ margin: '0.35rem 0 0', fontSize: '0.825rem', color: '#a1a1aa' }}>
                Scenario packs are collections of practice conversations. A starter pack is already
                installed. You can download more from the library or create your own in the Creator
                Workbench.
              </p>
            </div>
            <div
              aria-label="text-only demo explanation"
              style={{
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '0.85rem 1rem',
              }}
            >
              <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem' }}>
                No download? Try the text-only demo
              </p>
              <p style={{ margin: '0.35rem 0 0', fontSize: '0.825rem', color: '#a1a1aa' }}>
                Want to explore the interface first? Choose{' '}
                <strong>Continue without a model</strong> in the next step. NPC responses are
                scripted, not AI-generated, but you can try every screen immediately.
              </p>
            </div>
          </div>
        </div>

        <p style={{ marginTop: '1.25rem', color: '#a1a1aa', fontSize: '0.875rem' }}>
          This one-time setup wizard helps you choose a local AI model and get ready to play. It
          takes about a minute plus download time. You can change your model at any time from{' '}
          <strong>Settings → Runtime</strong>.
        </p>

        <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <PrimaryButton onClick={() => setStep('loading')}>Get started</PrimaryButton>
          <a
            href={SETUP_DOCS_URL}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: '0.825rem', color: '#71717a' }}
          >
            Read setup docs
          </a>
        </div>
      </div>
    )
  }

  // ── Loading ───────────────────────────────────────────────────────────────────

  if (step === 'loading') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Model Setup</h1>
        <p aria-live="polite" aria-busy="true">Checking your system…</p>
      </div>
    )
  }

  // ── Preflight ─────────────────────────────────────────────────────────────────

  if (step === 'preflight' && preflightResult) {
    const blockingFails = preflightResult.checks.filter(
      (c) => c.status === 'fail' && BLOCKING_CHECK_IDS.has(c.id),
    )
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>System Check</h1>
        <p style={{ color: '#f87171', marginBottom: '1rem' }}>
          {blockingFails.length === 1
            ? 'One issue needs your attention before setup can continue.'
            : `${blockingFails.length} issues need your attention before setup can continue.`}
        </p>

        <div
          role="list"
          aria-label="Preflight check results"
          style={{ marginBottom: '1.25rem' }}
          data-testid="wizard-preflight-results"
        >
          {preflightResult.checks
            .filter((c) => c.status !== 'pass')
            .map((check) => (
              <div
                key={check.id}
                role="listitem"
                data-testid={`wizard-preflight-check-${check.id}`}
                style={{
                  padding: '0.75rem',
                  marginBottom: '0.5rem',
                  background: check.status === 'fail'
                    ? 'rgba(239,68,68,0.08)'
                    : 'rgba(251,191,36,0.08)',
                  border: `1px solid ${check.status === 'fail' ? 'rgba(239,68,68,0.3)' : 'rgba(251,191,36,0.25)'}`,
                  borderRadius: '6px',
                }}
              >
                <p style={{ margin: '0 0 0.25rem', fontWeight: 600, fontSize: '0.875rem',
                  color: check.status === 'fail' ? '#f87171' : '#fde68a' }}>
                  {check.name}
                </p>
                <p style={{ margin: 0, fontSize: '0.825rem', color: '#a1a1aa' }}>{check.message}</p>
                {check.fix_action && !(check.fix_action.kind === 'navigate' && check.fix_action.href === '/settings') && (
                  <button
                    onClick={() => {
                      const { kind, href } = check.fix_action!
                      if (kind === 'open-url') {
                        void openExternal(href)
                      } else if (kind === 'wizard-step') {
                        // Backend-signalled in-wizard step: navigate without leaving the wizard.
                        setStep(href as WizardStep)
                      } else if (href === '/model-manager') {
                        // Backward-compat for older backends: /model-manager is behind
                        // FirstRunGuard, so map it to the in-wizard model-selection step.
                        setStep('choose')
                      } else {
                        navigate(href)
                      }
                    }}
                    data-testid={`wizard-preflight-fix-${check.id}`}
                    style={{
                      marginTop: '0.5rem',
                      padding: '0.25rem 0.65rem',
                      borderRadius: '4px',
                      border: '1px solid rgba(255,255,255,0.15)',
                      background: 'rgba(255,255,255,0.06)',
                      color: '#93c5fd',
                      fontSize: '0.8rem',
                      cursor: 'pointer',
                    }}
                  >
                    {check.fix_action.label} →
                  </button>
                )}
              </div>
            ))}
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <ActionButton onClick={() => setStep('loading')}>Retry system check</ActionButton>
          <ActionButton onClick={() => setStep('choose')}>Continue anyway</ActionButton>
        </div>
      </div>
    )
  }

  // ── Load error ────────────────────────────────────────────────────────────────

  if (step === 'load-error') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Model Setup</h1>
        <p role="alert" style={{ color: '#f87171' }}>
          {loadError ?? 'Something went wrong loading model information. Please try again.'}
        </p>
        <div
          style={{
            marginTop: '0.5rem',
            padding: '0.85rem 1rem',
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: '6px',
          }}
        >
          <p style={{ margin: '0 0 0.4rem', fontWeight: 600, color: '#f87171', fontSize: '0.875rem' }}>
            Could not connect to the local runtime
          </p>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
            The API server may not be running. Make sure you launched the app correctly, then try
            again. If your hardware cannot run a full model, the text-only demo works without one.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <a
              href={SETUP_DOCS_URL}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: '0.825rem', color: '#a1a1aa' }}
            >
              Troubleshooting docs
            </a>
            <span style={{ color: '#52525b', fontSize: '0.825rem' }}>·</span>
            <a
              href={ISSUES_URL}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: '0.825rem', color: '#a1a1aa' }}
            >
              Report an issue
            </a>
          </div>
          <ActionButton onClick={() => setStep('welcome')}>Back to welcome</ActionButton>
        </div>
      </div>
    )
  }

  // ── Choose ────────────────────────────────────────────────────────────────────

  if (step === 'choose') {
    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Choose how to get started</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Pick an option below. You can change it later in Settings.
        </p>

        <ul
          role="list"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            marginTop: '1.5rem',
            listStyle: 'none',
            padding: 0,
            margin: '1.5rem 0 0',
          }}
        >
          {recommendedModel && (
            <li>
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
            </li>
          )}

          <li>
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
          </li>

          <li>
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
          </li>

          <li>
            <SectionCard>
              <CardHeading>Continue without a model</CardHeading>
              <CardDescription>
                Try the interface without a model. NPC responses will be scripted — not AI-generated.
                Response quality is limited compared to a real local model.
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
          </li>
        </ul>
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
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Confirm model install</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          Review the details below before starting the download. No download begins until you click{' '}
          <strong>Confirm &amp; install</strong>.
        </p>

        <table style={{ marginTop: '1rem', borderCollapse: 'collapse', width: '100%' }}>
          <caption
            style={{
              textAlign: 'left',
              fontSize: '0.8rem',
              color: '#71717a',
              paddingBottom: '0.4rem',
              captionSide: 'top',
            }}
          >
            Model details
          </caption>
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
            <DetailRow label="Integrity checksum">
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
              {sha256IsPending ? (
                <span
                  style={{
                    display: 'block',
                    fontSize: '0.8rem',
                    color: '#fbbf24',
                    marginTop: '0.2rem',
                  }}
                >
                  Checksum not yet confirmed — the download will be rejected if verification fails.
                </span>
              ) : (
                <span
                  style={{
                    display: 'block',
                    fontSize: '0.75rem',
                    color: '#71717a',
                    marginTop: '0.2rem',
                  }}
                >
                  SHA-256 — the app checks this after download to confirm the file was not corrupted.
                </span>
              )}
            </DetailRow>
            <DetailRow label="Saves to">
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
                if (!resp.ok) {
                  setActionError(resp.error.message)
                } else {
                  setInstallId(resp.data.install_id)
                  setInstallRecord(null)
                  setStep('installing')
                }
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
          <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Installing model</h1>

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
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Installing model</h1>
        <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
          {statusLabel[status] ?? 'Downloading…'} Download time depends on your internet speed.
          The app will be ready as soon as the download completes.
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

        <p aria-live="polite" style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.4rem' }}>
          {pct != null
            ? `${pct}% — ${(progressBytes / 1_073_741_824).toFixed(2)} GB`
            : 'Waiting for progress data…'}
        </p>

        <div
          role="note"
          aria-label="play tutorial while downloading"
          style={{
            background: 'rgba(99,102,241,0.08)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: '8px',
            padding: '1rem 1.25rem',
            marginTop: '1.5rem',
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: '#a5b4fc', fontSize: '0.9rem' }}>
            No need to wait — try the tutorial now
          </p>
          <p style={{ margin: '0.4rem 0 0.75rem', fontSize: '0.825rem', color: '#c7d2fe' }}>
            Play the 3–5 minute First Words tutorial while your model downloads.
            It uses scripted (not AI) responses and teaches state meters, scenario
            events, and the debrief rubric — no model needed.
          </p>
          <PrimaryButton onClick={() => setStep('tutorial-prompt')}>
            Play the tutorial while you wait
          </PrimaryButton>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
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

  // ── Tutorial prompt ───────────────────────────────────────────────────────────
  // Shown when the player clicks "Play the tutorial while you wait" during install.
  // After acknowledging, mark setup complete and navigate to the tutorial scenario.

  if (step === 'tutorial-prompt') {
    async function handleStartTutorial() {
      setActionLoading(true)
      try {
        await api.useModel({ runtime_id: 'scripted', model_id: null })
      } catch {
        // Activating the scripted runtime is best-effort; proceed regardless.
      } finally {
        setActionLoading(false)
      }
      markTutorialComplete()
      markFirstRunComplete()
      // Enter the tutorial through the normal scenario-setup flow, which resolves
      // the seeded scenario by id and creates a session against the active
      // (scripted) runtime.  There is no dedicated /play route.
      navigate('/setup/first_words_tutorial')
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>
          First Words tutorial
        </h1>

        <div
          role="note"
          aria-label="scripted tutorial disclaimer"
          style={{
            background: 'rgba(251,191,36,0.08)',
            border: '1px solid rgba(251,191,36,0.35)',
            borderRadius: '6px',
            padding: '1rem 1.25rem',
            marginTop: '1rem',
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: '#fbbf24', fontSize: '0.875rem' }}>
            Scripted tutorial — not AI-generated
          </p>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.825rem', color: '#fde68a' }}>
            Alex Chen's responses are pre-authored, not generated by a language model.
            The tutorial teaches how the app works — once your model finishes
            downloading you'll switch to real AI-powered conversations automatically.
          </p>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <p style={{ fontSize: '0.875rem', color: '#d4d4d8', marginBottom: '0.5rem', fontWeight: 500 }}>
            What you'll learn in 3–5 minutes:
          </p>
          <ul
            style={{
              margin: 0,
              paddingLeft: '1.25rem',
              fontSize: '0.875rem',
              color: '#a1a1aa',
              lineHeight: 1.7,
            }}
          >
            <li>How state meters track conversation dynamics turn by turn</li>
            <li>How scenario events fire at threshold crossings and change NPC behaviour</li>
            <li>The three ways a session can end: success, failure, or timeout</li>
            <li>What each rubric dimension measures and how the debrief scores you</li>
          </ul>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
          <PrimaryButton disabled={actionLoading} onClick={handleStartTutorial}>
            {actionLoading ? 'Starting…' : 'Start the tutorial'}
          </PrimaryButton>
          <ActionButton
            onClick={() => {
              resetAction()
              setStep('installing')
            }}
          >
            Back
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
      if (!r.ok) {
        setActionError(r.error.message)
        setActionLoading(false)
        return
      }
      benchmarkStartedRef.current = false
      setStep('benchmark')
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Use Ollama model</h1>

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
      const reg = await api.registerGguf({ path: trimmed })
      if (!reg.ok) {
        setActionError(reg.error.message)
        setActionLoading(false)
        return
      }
      const sidecar = await api.startSidecar(trimmed)
      if (!sidecar.ok) {
        console.warn('GGUF registered, but the llama.cpp sidecar failed to start:', sidecar.error.message)
      }
      benchmarkStartedRef.current = false
      setStep('benchmark')
    }

    return (
      <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Use a GGUF file</h1>

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
            Full file path including the filename, e.g.{' '}
            <code style={{ fontFamily: 'monospace' }}>/home/you/Downloads/model.gguf</code> —
            must be compatible with llama.cpp.
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
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Text-only demo</h1>

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
        <h1 ref={stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Model benchmark</h1>
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
