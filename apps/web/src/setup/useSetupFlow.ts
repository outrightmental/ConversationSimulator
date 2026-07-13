// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { SETUP_KEYS } from '../privacyPrefs'
import { useSetupInstall } from './useSetupInstall'
import type {
  ModelsResponse,
  ModelRegistryEntry,
  DetectedOllamaModel,
  InstalledModelInfo,
  BenchmarkResponse,
  PreflightResponse,
  SetupInstallJob,
} from '@convsim/shared'
import type { ApiError } from '../api/errors'

export type SetupFlowStep =
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

/**
 * Check IDs that represent genuine blockers requiring a human decision.
 * Auto-fixable checks (engine, model, packs) are resolved silently by the
 * setup pipeline and must never appear here.
 *
 * @deprecated Prefer checking `check.severity === 'needs-human'` from the API
 * response. This set is kept as a fallback for API responses that predate the
 * severity field.
 */
export const BLOCKING_CHECK_IDS = new Set(['disk-space', 'data-dir-writable'])

export interface UseSetupFlowReturn {
  step: SetupFlowStep
  setStep: (s: SetupFlowStep) => void

  modelsData: ModelsResponse | null
  loadError: ApiError | null
  selectedModel: ModelRegistryEntry | null
  setSelectedModel: (m: ModelRegistryEntry | null) => void
  ggufPath: string
  setGgufPath: (p: string) => void
  ggufPathError: string | null
  setGgufPathError: (e: string | null) => void
  actionError: ApiError | null
  setActionError: (e: ApiError | null) => void
  actionLoading: boolean
  setActionLoading: (b: boolean) => void
  /** ID of the active setup-install pipeline job (set by handleStartInstall). */
  installId: number | null
  /** Live snapshot of the active setup-install job; null until first poll. */
  setupInstallJob: SetupInstallJob | null
  /** @deprecated Legacy per-model install record; null in the pipeline path. */
  installRecord: InstalledModelInfo | null
  benchmarkRunning: boolean
  benchmarkResult: BenchmarkResponse | null
  benchmarkError: ApiError | null
  preflightResult: PreflightResponse | null

  stepHeadingRef: React.RefObject<HTMLHeadingElement>
  recommendedModel: ModelRegistryEntry | null
  resetAction: () => void
  navigate: ReturnType<typeof useNavigate>

  handleSetMeUp: () => void
  handleAdvancedOllama: () => void
  handleAdvancedGguf: () => void
  handleStartInstall: (registryId: string) => Promise<void>
  handleSelectOllama: (m: DetectedOllamaModel) => Promise<void>
  handleUseGguf: () => Promise<void>
  handleConfirmDemo: (markComplete?: boolean) => Promise<void>
  handleStartTutorial: () => Promise<void>
  handleCancelInstall: () => Promise<void>
  handleFinishBenchmark: () => void
  reloadModels: () => Promise<void>
}

// Persist the onboarding outcome server-side BEFORE navigating into a guarded
// route. The write must be awaited: FirstRunGuard mounts on the destination and
// immediately revalidates via GET /setup/status. If that GET is served before
// this POST commits, the server still reports 'never-run' and the guard would
// clear the mirror and bounce the user straight back to the wizard's Welcome —
// right after they finished installing a model. Awaiting the commit closes that
// race; the localStorage mirror still covers the offline case (a failed write
// leaves the guard's fast-path 'ready' intact rather than downgrading it).
async function markFirstRunComplete(): Promise<void> {
  try { localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true') } catch { /* ignore */ }
  try { await api.recordOnboardingOutcome('completed-with-model') } catch { /* best-effort */ }
}

async function markDemoComplete(): Promise<void> {
  try { localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true') } catch { /* ignore */ }
  try { await api.recordOnboardingOutcome('demo') } catch { /* best-effort */ }
}

function markTutorialComplete(): void {
  try { localStorage.setItem(SETUP_KEYS.tutorialComplete, 'true') } catch { /* ignore */ }
}

function isTutorialComplete(): boolean {
  try { return localStorage.getItem(SETUP_KEYS.tutorialComplete) === 'true' } catch { return false }
}

export function useSetupFlow(
  initialStep: SetupFlowStep,
  initialInstallId?: number,
): UseSetupFlowReturn {
  const navigate = useNavigate()
  const [step, setStep] = useState<SetupFlowStep>(initialStep)
  const [modelsData, setModelsData] = useState<ModelsResponse | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)

  const [selectedModel, setSelectedModel] = useState<ModelRegistryEntry | null>(null)
  const [ggufPath, setGgufPath] = useState('')
  const [ggufPathError, setGgufPathError] = useState<string | null>(null)

  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  // installId now refers to the setup-install pipeline job ID.
  // Seeded from initialInstallId so resuming mid-install (forwarded via URL
  // by FirstRunGuard) opens straight to the installing step.
  const [installId, setInstallId] = useState<number | null>(initialInstallId ?? null)
  const setupInstallJob = useSetupInstall(installId)
  // installRecord kept for backwards-compat (Ollama/GGUF paths never use it now).
  const [installRecord] = useState<InstalledModelInfo | null>(null)

  const [benchmarkRunning, setBenchmarkRunning] = useState(false)
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResponse | null>(null)
  const [benchmarkError, setBenchmarkError] = useState<ApiError | null>(null)
  const benchmarkStartedRef = useRef(false)

  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null)

  // Tracks what the user chose on the welcome screen so the loading step can
  // route to the right destination without exposing the detail as UI state.
  const intentRef = useRef<'set-me-up' | 'ollama' | 'gguf' | null>(null)

  const stepHeadingRef = useRef<HTMLHeadingElement>(null)
  const isInitialStep = useRef(true)
  useEffect(() => {
    if (isInitialStep.current) { isInitialStep.current = false; return }
    stepHeadingRef.current?.focus()
  }, [step])

  // Pre-fetch the model registry when on the welcome step so the WelcomeStep
  // can render model size + license before any user action, satisfying the
  // acceptance criterion that these values come from the registry, not
  // hardcoded strings.
  useEffect(() => {
    if (step !== 'welcome') return
    let cancelled = false
    void api.getModels().then((r) => {
      if (!cancelled && r.ok) setModelsData(r.data)
    })
    return () => { cancelled = true }
  }, [step])

  // Fetch models + preflight when entering loading step, then route based on intent
  useEffect(() => {
    if (step !== 'loading') return
    void Promise.all([api.getModels(), api.preflight()]).then(async ([modelsResult, preflightRes]) => {
      if (!modelsResult.ok) {
        setLoadError(modelsResult.error)
        setStep('load-error')
        return
      }
      setModelsData(modelsResult.data)
      if (preflightRes.ok) {
        setPreflightResult(preflightRes.data)
        // Only block on checks that genuinely require human intervention.
        // Auto-fixable failures (engine, model, packs) are handled silently by
        // the setup pipeline and must never route to the preflight step.
        const blockingFails = preflightRes.data.checks.filter(
          (c) =>
            c.status === 'fail' &&
            (c.severity
              ? c.severity === 'needs-human'
              : BLOCKING_CHECK_IDS.has(c.id)), // fallback for older API
        )
        if (blockingFails.length > 0) { setStep('preflight'); return }
      }

      const intent = intentRef.current
      intentRef.current = null

      if (intent === 'set-me-up') {
        const rec = modelsResult.data.registry.find((m) => m.role === 'starter') ?? null
        if (!rec) { setStep('choose'); return }
        setSelectedModel(rec)
        setActionLoading(true)
        setActionError(null)
        try {
          const resp = await api.startSetupInstall(rec.id)
          if (!resp.ok) {
            setActionError(resp.error)
            setStep('confirm-install')
          } else {
            setInstallId(resp.data.id)
            setStep('installing')
          }
        } catch (err: unknown) {
          setActionError({ kind: 'network', message: err instanceof Error ? err.message : 'Install failed. Please try again.' })
          setStep('confirm-install')
        } finally {
          setActionLoading(false)
        }
        return
      }

      if (intent === 'ollama') {
        setStep('ollama-select')
        return
      }

      if (intent === 'gguf') {
        setStep('gguf-path')
        return
      }

      setStep('choose')
    }).catch((err: unknown) => {
      setLoadError({ kind: 'network', message: err instanceof Error ? err.message : 'Failed to load model information.' })
      setStep('load-error')
    })
  }, [step])

  // React to pipeline job terminal states while on the 'installing' step.
  useEffect(() => {
    if (step !== 'installing' || setupInstallJob == null) return
    const { status } = setupInstallJob
    if (status === 'complete') {
      void markFirstRunComplete().then(() => {
        navigate(isTutorialComplete() ? '/library' : '/')
      })
    } else if (status === 'failed' || status === 'cancelled') {
      setActionError({
        kind: 'http-error',
        message: setupInstallJob.error_message ?? 'Install failed. Please try again.',
      })
    }
  }, [step, setupInstallJob, navigate])

  // Auto-run benchmark once on entering the 'benchmark' step
  useEffect(() => {
    if (step !== 'benchmark' || benchmarkStartedRef.current) return
    benchmarkStartedRef.current = true
    setBenchmarkRunning(true)
    setBenchmarkResult(null)
    setBenchmarkError(null)
    void api.benchmarkModel({}).then((r) => {
      if (r.ok) setBenchmarkResult(r.data)
      else setBenchmarkError(r.error)
    }).finally(() => { setBenchmarkRunning(false) })
  }, [step])

  const recommendedModel = modelsData?.registry.find((m) => m.role === 'starter') ?? null

  function resetAction() {
    setActionError(null)
    setActionLoading(false)
  }

  async function reloadModels() {
    setStep('loading')
  }

  function handleSetMeUp() {
    intentRef.current = 'set-me-up'
    setStep('loading')
  }

  function handleAdvancedOllama() {
    intentRef.current = 'ollama'
    setStep('loading')
  }

  function handleAdvancedGguf() {
    // Route through 'loading' (like the Ollama path) so preflight runs silently
    // and any genuine blocker surfaces before the user picks a .gguf file.
    setGgufPath('')
    setGgufPathError(null)
    resetAction()
    intentRef.current = 'gguf'
    setStep('loading')
  }

  async function handleStartInstall(registryId: string) {
    setActionLoading(true)
    setActionError(null)
    try {
      const resp = await api.startSetupInstall(registryId)
      if (!resp.ok) {
        setActionError(resp.error)
      } else {
        setInstallId(resp.data.id)
        setStep('installing')
      }
    } catch (err: unknown) {
      setActionError({ kind: 'network', message: err instanceof Error ? err.message : 'Install failed. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  async function handleSelectOllama(m: DetectedOllamaModel) {
    setActionLoading(true)
    setActionError(null)
    const r = await api.useModel({ runtime_id: 'ollama', model_id: m.id })
    if (!r.ok) { setActionError(r.error); setActionLoading(false); return }
    benchmarkStartedRef.current = false
    setStep('benchmark')
    setActionLoading(false)
  }

  async function handleUseGguf() {
    const trimmed = ggufPath.trim()
    if (!trimmed) { setGgufPathError('Please enter a file path.'); return }
    if (!trimmed.toLowerCase().endsWith('.gguf')) { setGgufPathError('The file must have a .gguf extension.'); return }
    setGgufPathError(null)
    setActionLoading(true)
    setActionError(null)
    const reg = await api.registerGguf({ path: trimmed })
    if (!reg.ok) { setActionError(reg.error); setActionLoading(false); return }
    void api.startSidecar(trimmed)
    benchmarkStartedRef.current = false
    setStep('benchmark')
    setActionLoading(false)
  }

  async function handleConfirmDemo(markComplete = false) {
    setActionLoading(true)
    try { await api.useModel({ runtime_id: 'fake', model_id: null }) } catch { /* best-effort */ }
    finally { setActionLoading(false) }
    if (markComplete) await markDemoComplete()
    navigate('/library')
  }

  async function handleStartTutorial() {
    setActionLoading(true)
    try { await api.useModel({ runtime_id: 'scripted', model_id: null }) } catch { /* best-effort */ }
    finally { setActionLoading(false) }
    markTutorialComplete()
    await markFirstRunComplete()
    navigate('/setup/first_words_tutorial')
  }

  async function handleCancelInstall() {
    if (installId != null) {
      try { await api.cancelSetupInstall(installId) } catch { /* best-effort */ }
    }
    await markFirstRunComplete()
    navigate('/')
  }

  // Completing the benchmark (reached via the Ollama and GGUF paths) is a valid
  // way to finish onboarding, so it must persist the server-side outcome — not
  // just the localStorage mirror — otherwise clearing the cache resurrects the
  // wizard for a working install (issue #380).
  async function handleFinishBenchmark() {
    await markFirstRunComplete()
    navigate('/')
  }

  return {
    step, setStep,
    modelsData, loadError,
    selectedModel, setSelectedModel,
    ggufPath, setGgufPath,
    ggufPathError, setGgufPathError,
    actionError, setActionError,
    actionLoading, setActionLoading,
    installId, installRecord, setupInstallJob,
    benchmarkRunning, benchmarkResult, benchmarkError,
    preflightResult,
    stepHeadingRef,
    recommendedModel,
    resetAction,
    navigate,
    handleSetMeUp,
    handleAdvancedOllama,
    handleAdvancedGguf,
    handleStartInstall,
    handleSelectOllama,
    handleUseGguf,
    handleConfirmDemo,
    handleStartTutorial,
    handleCancelInstall,
    handleFinishBenchmark,
    reloadModels,
  }
}
