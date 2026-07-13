// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { SETUP_KEYS } from '../privacyPrefs'
import type {
  ModelsResponse,
  ModelRegistryEntry,
  DetectedOllamaModel,
  InstalledModelInfo,
  BenchmarkResponse,
  PreflightResponse,
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

export const BLOCKING_CHECK_IDS = new Set(['llama-cpp-binary', 'disk-space', 'data-dir-writable'])

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
  installId: number | null
  installRecord: InstalledModelInfo | null
  benchmarkRunning: boolean
  benchmarkResult: BenchmarkResponse | null
  benchmarkError: ApiError | null
  preflightResult: PreflightResponse | null

  stepHeadingRef: React.RefObject<HTMLHeadingElement>
  recommendedModel: ModelRegistryEntry | null
  resetAction: () => void
  navigate: ReturnType<typeof useNavigate>

  handleStartInstall: (registryId: string) => Promise<void>
  handleSelectOllama: (m: DetectedOllamaModel) => Promise<void>
  handleUseGguf: () => Promise<void>
  handleConfirmDemo: (markComplete?: boolean) => Promise<void>
  handleStartTutorial: () => Promise<void>
  handleCancelInstall: () => Promise<void>
  reloadModels: () => Promise<void>
}

function markFirstRunComplete(): void {
  try { localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true') } catch { /* ignore */ }
  void api.recordOnboardingOutcome('completed-with-model').catch(() => { /* best-effort */ })
}

function markDemoComplete(): void {
  try { localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true') } catch { /* ignore */ }
  void api.recordOnboardingOutcome('demo').catch(() => { /* best-effort */ })
}

function markTutorialComplete(): void {
  try { localStorage.setItem(SETUP_KEYS.tutorialComplete, 'true') } catch { /* ignore */ }
}

function isTutorialComplete(): boolean {
  try { return localStorage.getItem(SETUP_KEYS.tutorialComplete) === 'true' } catch { return false }
}

export function useSetupFlow(initialStep: SetupFlowStep): UseSetupFlowReturn {
  const navigate = useNavigate()
  const [step, setStep] = useState<SetupFlowStep>(initialStep)
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

  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null)

  const stepHeadingRef = useRef<HTMLHeadingElement>(null)
  const isInitialStep = useRef(true)
  useEffect(() => {
    if (isInitialStep.current) { isInitialStep.current = false; return }
    stepHeadingRef.current?.focus()
  }, [step])

  // Fetch models + preflight when entering loading step
  useEffect(() => {
    if (step !== 'loading') return
    void Promise.all([api.getModels(), api.preflight()]).then(([modelsResult, preflightRes]) => {
      if (!modelsResult.ok) {
        setLoadError(modelsResult.error)
        setStep('load-error')
        return
      }
      setModelsData(modelsResult.data)
      if (preflightRes.ok) {
        setPreflightResult(preflightRes.data)
        const blockingFails = preflightRes.data.checks.filter(
          (c) => c.status === 'fail' && BLOCKING_CHECK_IDS.has(c.id),
        )
        if (blockingFails.length > 0) { setStep('preflight'); return }
      }
      setStep('choose')
    }).catch((err: unknown) => {
      setLoadError({ kind: 'network', message: err instanceof Error ? err.message : 'Failed to load model information.' })
      setStep('load-error')
    })
  }, [step])

  // Poll install status while on the 'installing' step
  useEffect(() => {
    if (step !== 'installing' || installId == null) return

    function stopPoll() {
      if (pollRef.current != null) { clearInterval(pollRef.current); pollRef.current = null }
    }

    pollRef.current = setInterval(() => {
      void api.getInstallStatus(installId).then((r) => {
        if (!r.ok) return
        const record = r.data
        setInstallRecord(record)
        const terminal = ['ready', 'complete', 'failed', 'cancelled', 'checksum_mismatch']
        if (terminal.includes(record.install_status)) {
          stopPoll()
          if (record.install_status === 'ready' || record.install_status === 'complete') {
            markFirstRunComplete()
            navigate(isTutorialComplete() ? '/library' : '/')
          } else {
            setActionError({ kind: 'http-error', message: record.error_message ?? 'Download failed. Please try again.' })
          }
        }
      })
    }, 2000)

    return stopPoll
  }, [step, installId, navigate])

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

  async function handleStartInstall(registryId: string) {
    setActionLoading(true)
    setActionError(null)
    try {
      const resp = await api.installModel({ registry_id: registryId })
      if (!resp.ok) {
        setActionError(resp.error)
      } else {
        setInstallId(resp.data.install_id)
        setInstallRecord(null)
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
    if (markComplete) markDemoComplete()
    navigate('/library')
  }

  async function handleStartTutorial() {
    setActionLoading(true)
    try { await api.useModel({ runtime_id: 'scripted', model_id: null }) } catch { /* best-effort */ }
    finally { setActionLoading(false) }
    markTutorialComplete()
    markFirstRunComplete()
    navigate('/setup/first_words_tutorial')
  }

  async function handleCancelInstall() {
    if (installId != null) {
      try { await api.cancelInstall(installId) } catch { /* best-effort */ }
    }
    markFirstRunComplete()
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
    installId, installRecord,
    benchmarkRunning, benchmarkResult, benchmarkError,
    preflightResult,
    stepHeadingRef,
    recommendedModel,
    resetAction,
    navigate,
    handleStartInstall,
    handleSelectOllama,
    handleUseGguf,
    handleConfirmDemo,
    handleStartTutorial,
    handleCancelInstall,
    reloadModels,
  }
}
