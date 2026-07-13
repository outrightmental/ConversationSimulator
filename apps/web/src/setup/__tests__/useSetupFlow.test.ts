// SPDX-License-Identifier: Apache-2.0
/**
 * Tests for the step-machine transitions encoded in useSetupFlow.
 *
 * Covers the pure logic of the state machine table — which API calls fire,
 * which step each result routes to, and the error paths.  We test the hook
 * via renderHook so we exercise the real React state/effect machinery rather
 * than mocking internals.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import React from 'react'
import { useSetupFlow } from '../useSetupFlow'

vi.mock('../../api/client', () => ({
  api: {
    getModels: vi.fn(),
    preflight: vi.fn(),
    useModel: vi.fn(),
    installModel: vi.fn(),
    getInstallStatus: vi.fn(),
    cancelInstall: vi.fn(),
    registerGguf: vi.fn(),
    startSidecar: vi.fn(),
    benchmarkModel: vi.fn(),
    recordOnboardingOutcome: vi.fn().mockResolvedValue({ ok: true, data: undefined }),
    getSetupStatus: vi.fn().mockResolvedValue({ ok: true, data: { kind: 'ready' } }),
    startSetupInstall: vi.fn(),
    getSetupInstallStatus: vi.fn(),
    cancelSetupInstall: vi.fn(),
  },
}))

import { api } from '../../api/client'
const mockApi = vi.mocked(api)

import type { ModelsResponse, PreflightResponse } from '@convsim/shared'

const MODELS_DATA: ModelsResponse = {
  registry: [
    {
      id: 'qwen3-4b-q4',
      name: 'Qwen3 4B Q4',
      provider: 'hf',
      family: 'qwen3',
      role: 'starter',
      format: 'gguf',
      license_spdx: 'Apache-2.0',
      license_url: '',
      source_type: 'registry',
      download_url: 'https://example.com/model.gguf',
      sha256: 'abc123',
      size_gb: 2.6,
      min_vram_gb: 4,
      recommended_vram_gb: 6,
      context_length: 8192,
      registered_at: '2026-01-01T00:00:00Z',
    },
  ],
  installed: [],
  ollama_models: [{ id: 'llama3:latest', name: 'llama3:latest', size_category: 'medium' as const }],
  active: { runtime_id: null, model_id: null },
  runtime_health: { runtime_id: 'none', runtime_name: 'llama.cpp', status: 'unavailable' as const, model_id: null, latency_ms: null, message: '', checked_at: '2026-01-01T00:00:00Z' },
  total: 1,
  last_benchmark: null,
}

const PREFLIGHT_PASS: PreflightResponse = {
  overall: 'pass',
  checks: [],
  ran_at: '2026-01-01T00:00:00Z',
}

const DISK_SPACE_FAIL_CHECK: PreflightResponse = {
  overall: 'fail',
  checks: [{
    id: 'disk-space',
    name: 'Not enough disk space',
    status: 'fail',
    message: 'The AI model needs 5.0 GB and this disk has 1.0 GB free.',
    severity: 'needs-human',
    autofix: false,
    fix_action: { kind: 'navigate', href: '/settings', label: 'Choose another location' },
  }],
  ran_at: '2026-01-01T00:00:00Z',
}

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(MemoryRouter, { future: { v7_startTransition: true, v7_relativeSplatPath: true } }, children)
}

const RUNNING_JOB = {
  id: 42,
  status: 'running' as const,
  registry_id: 'qwen3-4b-q4',
  stages: [],
  error_message: null,
  created_at: '',
  updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_DATA })
  mockApi.preflight.mockResolvedValue({ ok: true, data: PREFLIGHT_PASS })
  mockApi.startSetupInstall.mockResolvedValue({ ok: true, data: RUNNING_JOB })
  mockApi.getSetupInstallStatus.mockResolvedValue({ ok: true, data: RUNNING_JOB })
  mockApi.cancelSetupInstall.mockResolvedValue({ ok: true, data: undefined })
})

describe('useSetupFlow step machine', () => {
  it('starts at the given initial step', () => {
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })
    expect(result.current.step).toBe('welcome')
  })

  it('starts at loading when initialStep is loading', () => {
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    expect(result.current.step).toBe('loading')
  })

  // loading → choose (happy path, no blocking preflight fails)
  it('transitions loading → choose when preflight passes', async () => {
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))
  })

  // loading → preflight when a needs-human check fails
  it('transitions loading → preflight when a needs-human check fails', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: DISK_SPACE_FAIL_CHECK })
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('preflight'))
  })

  // loading → does NOT route to preflight when an auto-fixable check fails
  it('does not route to preflight when an auto-fixable check fails', async () => {
    mockApi.preflight.mockResolvedValue({
      ok: true,
      data: {
        overall: 'fail' as const,
        checks: [{
          id: 'llama-cpp-binary',
          name: 'AI engine',
          status: 'fail' as const,
          message: 'The AI engine is not installed.',
          severity: 'auto-fixable' as const,
          autofix: true,
          fix_action: { kind: 'install-engine' as const, href: '/settings/install-engine', label: 'Install engine' },
        }],
        ran_at: '2026-01-01T00:00:00Z',
      },
    })
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    // Should proceed past loading without hitting the preflight step
    await waitFor(() => expect(result.current.step).not.toBe('loading'))
    expect(result.current.step).not.toBe('preflight')
  })

  // loading → load-error when getModels fails
  it('transitions loading → load-error when getModels fails', async () => {
    mockApi.getModels.mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'Server error', status: 500 } })
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('load-error'))
    expect(result.current.loadError).not.toBeNull()
  })

  // choose → confirm-install via setSelectedModel + setStep
  it('exposes setSelectedModel and setStep for wizard navigation', async () => {
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))

    act(() => {
      result.current.setSelectedModel(MODELS_DATA.registry[0])
      result.current.setStep('confirm-install')
    })

    expect(result.current.step).toBe('confirm-install')
    expect(result.current.selectedModel?.id).toBe('qwen3-4b-q4')
  })

  // confirm-install → installing via handleStartInstall
  it('transitions confirm-install → installing via handleStartInstall', async () => {
    mockApi.startSetupInstall.mockResolvedValue({ ok: true, data: { id: 42, status: 'running' as const, registry_id: 'qwen3-4b-q4', stages: [], error_message: null, created_at: '', updated_at: '' } })
    // Polling should keep returning 'running' so we stay on installing
    mockApi.getSetupInstallStatus.mockResolvedValue({
      ok: true, data: { id: 42, status: 'running' as const, registry_id: 'qwen3-4b-q4', stages: [], error_message: null, created_at: '', updated_at: '' },
    })

    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))

    act(() => {
      result.current.setSelectedModel(MODELS_DATA.registry[0])
      result.current.setStep('confirm-install')
    })

    await act(async () => {
      await result.current.handleStartInstall('qwen3-4b-q4')
    })

    expect(result.current.step).toBe('installing')
    expect(result.current.installId).toBe(42)
    expect(mockApi.startSetupInstall).toHaveBeenCalledWith('qwen3-4b-q4')
  })

  // handleStartInstall error → stays on confirm-install with actionError set
  it('handleStartInstall failure sets actionError and stays on confirm-install', async () => {
    mockApi.startSetupInstall.mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'No space left', status: 500 } })
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))

    act(() => {
      result.current.setSelectedModel(MODELS_DATA.registry[0])
      result.current.setStep('confirm-install')
    })

    await act(async () => {
      await result.current.handleStartInstall('qwen3-4b-q4')
    })

    expect(result.current.step).toBe('confirm-install')
    expect(result.current.actionError).not.toBeNull()
  })

  // ollama-select → benchmark via handleSelectOllama
  it('transitions ollama-select → benchmark via handleSelectOllama', async () => {
    mockApi.useModel.mockResolvedValue({ ok: true, data: { runtime_id: 'ollama', model_id: 'llama3:latest', runtime_name: 'Ollama', status: 'ready', message: null } })
    mockApi.benchmarkModel.mockResolvedValue({ ok: true, data: { model_id: 'llama3:latest', runtime_id: 'ollama', tokens_per_sec: 12.5, context_length: 4096, warnings: [], output_tokens: 5, benchmarked_at: '' } })

    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))

    act(() => { result.current.setStep('ollama-select') })

    await act(async () => {
      await result.current.handleSelectOllama({ id: 'llama3:latest', name: 'llama3:latest', size_category: 'medium' })
    })

    expect(result.current.step).toBe('benchmark')
    expect(mockApi.useModel).toHaveBeenCalledWith({ runtime_id: 'ollama', model_id: 'llama3:latest' })
  })

  // gguf-path → benchmark via handleUseGguf
  it('transitions gguf-path → benchmark via handleUseGguf', async () => {
    mockApi.registerGguf.mockResolvedValue({ ok: true, data: { profile_id: 1, file_path: '/m.gguf', display_name: 'm.gguf', filename: 'm.gguf', family_guess: null, context_length_default: null, warnings: [], active_runtime_id: 'llama_cpp', active_model_id: '/m.gguf' } })
    mockApi.startSidecar.mockResolvedValue({ ok: true, data: { state: 'running', pid: 1, log_path: '', host: 'localhost', port: 8080 } })
    mockApi.benchmarkModel.mockResolvedValue({ ok: true, data: { model_id: '/m.gguf', runtime_id: 'llama_cpp', tokens_per_sec: 8.0, context_length: 4096, warnings: [], output_tokens: 5, benchmarked_at: '' } })

    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))

    act(() => {
      result.current.setStep('gguf-path')
      result.current.setGgufPath('/path/to/model.gguf')
    })

    await act(async () => {
      await result.current.handleUseGguf()
    })

    expect(result.current.step).toBe('benchmark')
    expect(mockApi.registerGguf).toHaveBeenCalledWith({ path: '/path/to/model.gguf' })
  })

  it('handleUseGguf validates empty path', async () => {
    const { result } = renderHook(() => useSetupFlow('gguf-path'), { wrapper })
    act(() => { result.current.setGgufPath('') })
    await act(async () => { await result.current.handleUseGguf() })
    expect(result.current.ggufPathError).toBeTruthy()
    expect(result.current.step).toBe('gguf-path')
  })

  it('handleUseGguf validates non-.gguf extension', async () => {
    const { result } = renderHook(() => useSetupFlow('gguf-path'), { wrapper })
    act(() => { result.current.setGgufPath('/path/model.bin') })
    await act(async () => { await result.current.handleUseGguf() })
    expect(result.current.ggufPathError).toBeTruthy()
    expect(result.current.step).toBe('gguf-path')
  })

  it('resetAction clears actionError and actionLoading', async () => {
    mockApi.startSetupInstall.mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'err', status: 500 } })
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))

    act(() => { result.current.setStep('confirm-install') })
    await act(async () => { await result.current.handleStartInstall('qwen3-4b-q4') })

    expect(result.current.actionError).not.toBeNull()
    act(() => { result.current.resetAction() })
    expect(result.current.actionError).toBeNull()
    expect(result.current.actionLoading).toBe(false)
  })

  it('exposes recommendedModel from registry', async () => {
    const { result } = renderHook(() => useSetupFlow('loading'), { wrapper })
    await waitFor(() => expect(result.current.step).toBe('choose'))
    expect(result.current.recommendedModel?.id).toBe('qwen3-4b-q4')
  })

  // Resume mid-install: opening the wizard at 'installing' with a seeded install
  // id lands on the progress step (bound to that record) instead of a fresh
  // Welcome. The polling of the record is covered by the ModelManager tests.
  it('resumes into installing when seeded with an install id', () => {
    const { result } = renderHook(() => useSetupFlow('installing', 7), { wrapper })
    expect(result.current.step).toBe('installing')
    expect(result.current.installId).toBe(7)
  })

  it('starts at welcome with no install id when not resuming', () => {
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })
    expect(result.current.step).toBe('welcome')
    expect(result.current.installId).toBeNull()
  })

  // Completing via the benchmark (Ollama/GGUF paths) must persist the server
  // outcome, not just the localStorage mirror.
  it('handleFinishBenchmark records the onboarding outcome server-side', async () => {
    const { result } = renderHook(() => useSetupFlow('benchmark'), { wrapper })
    act(() => { result.current.handleFinishBenchmark() })
    expect(mockApi.recordOnboardingOutcome).toHaveBeenCalledWith('completed-with-model')
  })

  // New welcome-screen handlers (#381)

  it('pre-fetches models registry on welcome step', async () => {
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })
    await waitFor(() => expect(mockApi.getModels).toHaveBeenCalledOnce())
    expect(result.current.recommendedModel?.id).toBe('qwen3-4b-q4')
  })

  it('handleSetMeUp transitions welcome → loading → installing via auto-install', async () => {
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })
    expect(result.current.step).toBe('welcome')

    act(() => { result.current.handleSetMeUp() })

    await waitFor(() => expect(result.current.step).toBe('installing'))
    expect(result.current.installId).toBe(42)
    expect(mockApi.startSetupInstall).toHaveBeenCalledWith('qwen3-4b-q4')
  })

  it('handleSetMeUp falls back to confirm-install when startSetupInstall fails', async () => {
    mockApi.startSetupInstall.mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'disk full', status: 507 } })
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    act(() => { result.current.handleSetMeUp() })

    await waitFor(() => expect(result.current.step).toBe('confirm-install'))
    expect(result.current.actionError).not.toBeNull()
    expect(result.current.selectedModel?.id).toBe('qwen3-4b-q4')
  })

  it('handleAdvancedOllama transitions welcome → loading → ollama-select', async () => {
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })
    expect(result.current.step).toBe('welcome')

    act(() => { result.current.handleAdvancedOllama() })

    await waitFor(() => expect(result.current.step).toBe('ollama-select'))
    expect(mockApi.getModels).toHaveBeenCalled()
    expect(mockApi.preflight).toHaveBeenCalled()
  })

  it('handleAdvancedGguf transitions welcome → loading → gguf-path and runs preflight', async () => {
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })
    expect(result.current.step).toBe('welcome')

    act(() => { result.current.handleAdvancedGguf() })

    await waitFor(() => expect(result.current.step).toBe('gguf-path'))
    // Preflight must run silently on the GGUF path too, so genuine blockers surface.
    expect(mockApi.preflight).toHaveBeenCalled()
  })

  it('handleAdvancedGguf surfaces needs-human preflight failures before gguf-path', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: DISK_SPACE_FAIL_CHECK })
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    act(() => { result.current.handleAdvancedGguf() })

    await waitFor(() => expect(result.current.step).toBe('preflight'))
  })

  // handleStartTutorial — issue #383 "play while it downloads" paths

  const SCRIPTED_RUNTIME_RESPONSE = {
    ok: true as const,
    data: { runtime_id: 'scripted', model_id: null, runtime_name: 'Scripted tutorial', status: 'ready' as const, message: null },
  }

  const FAKE_RUNTIME_RESPONSE = {
    ok: true as const,
    data: { runtime_id: 'fake', model_id: null, runtime_name: 'Fake (deterministic)', status: 'ready' as const, message: null },
  }

  it('handleStartTutorial writes activeRuntimeHint=scripted to localStorage', async () => {
    mockApi.useModel.mockResolvedValue(SCRIPTED_RUNTIME_RESPONSE)
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    await act(async () => { await result.current.handleStartTutorial() })

    expect(localStorage.getItem('convsim.active_runtime_hint')).toBe('scripted')
  })

  it('handleStartTutorial without an active install records demo outcome (try-now path)', async () => {
    mockApi.useModel.mockResolvedValue(SCRIPTED_RUNTIME_RESPONSE)
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    await act(async () => { await result.current.handleStartTutorial() })

    expect(mockApi.recordOnboardingOutcome).toHaveBeenCalledWith('demo')
    expect(localStorage.getItem('convsim.tutorial.install_id')).toBeNull()
  })

  it('handleStartTutorial with an active install writes tutorialInstallId and records completed-with-model', async () => {
    mockApi.useModel.mockResolvedValue(SCRIPTED_RUNTIME_RESPONSE)
    mockApi.getSetupInstallStatus.mockResolvedValue({
      ok: true, data: { id: 42, status: 'running' as const, registry_id: 'qwen3-4b-q4', stages: [], error_message: null, created_at: '', updated_at: '' },
    })

    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    // Trigger auto-install so installId is set
    act(() => { result.current.handleSetMeUp() })
    await waitFor(() => expect(result.current.installId).toBe(42))

    await act(async () => { await result.current.handleStartTutorial() })

    expect(localStorage.getItem('convsim.tutorial.install_id')).toBe('42')
    expect(mockApi.recordOnboardingOutcome).toHaveBeenCalledWith('completed-with-model')
  })

  it('handleConfirmDemo writes activeRuntimeHint=fake to localStorage', async () => {
    mockApi.useModel.mockResolvedValue(FAKE_RUNTIME_RESPONSE)
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    await act(async () => { await result.current.handleConfirmDemo() })

    expect(localStorage.getItem('convsim.active_runtime_hint')).toBe('fake')
  })

  it('WelcomeStep "Try it right now" is wired to handleStartTutorial not handleConfirmDemo (spot-check via tutorial-complete flag)', async () => {
    mockApi.useModel.mockResolvedValue(SCRIPTED_RUNTIME_RESPONSE)
    const { result } = renderHook(() => useSetupFlow('welcome'), { wrapper })

    // handleStartTutorial marks tutorialComplete; handleConfirmDemo does not.
    await act(async () => { await result.current.handleStartTutorial() })

    expect(localStorage.getItem('convsim.tutorial.complete')).toBe('true')
  })

  it('install-complete effect clears runtime hint keys so real-model sessions are not mislabeled', async () => {
    // Seed localStorage with stale keys that would have been written by handleStartTutorial
    localStorage.setItem('convsim.active_runtime_hint', 'scripted')
    localStorage.setItem('convsim.tutorial.install_id', '42')

    const completeJob = {
      id: 42,
      status: 'complete' as const,
      registry_id: 'qwen3-4b-q4',
      stages: [],
      error_message: null,
      created_at: '',
      updated_at: '',
    }
    mockApi.startSetupInstall.mockResolvedValue({ ok: true, data: { id: 42, status: 'running' as const, registry_id: 'qwen3-4b-q4', stages: [], error_message: null, created_at: '', updated_at: '' } })
    mockApi.getSetupInstallStatus.mockResolvedValue({ ok: true, data: completeJob })

    const { result } = renderHook(() => useSetupFlow('installing', 42), { wrapper })
    await waitFor(() => expect(result.current.setupInstallJob?.status).toBe('complete'))

    expect(localStorage.getItem('convsim.active_runtime_hint')).toBeNull()
    expect(localStorage.getItem('convsim.tutorial.install_id')).toBeNull()
  })
})
