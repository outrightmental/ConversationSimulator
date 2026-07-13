// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import FirstRunWizard from '../screens/FirstRunWizard'
import { SETUP_KEYS } from '../privacyPrefs'
import type { ModelsResponse, BenchmarkResponse, PreflightCheck } from '@convsim/shared'

vi.mock('../api/client', () => ({
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
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const REGISTRY_ENTRY = {
  id: 'qwen3-4b-instruct-q4_k_m',
  name: 'Qwen3 4B Instruct Q4_K_M',
  provider: 'huggingface',
  family: 'qwen3',
  role: 'starter',
  format: 'gguf',
  license_spdx: 'Apache-2.0',
  license_url: 'https://www.apache.org/licenses/LICENSE-2.0',
  source_type: 'registry',
  download_url: 'PENDING',
  sha256: 'PENDING',
  size_gb: 2.6,
  min_vram_gb: 4,
  recommended_vram_gb: 6,
  context_length: 8192,
  registered_at: '2026-01-01T00:00:00.000Z',
}

const DEFAULT_BENCHMARK: BenchmarkResponse = {
  model_id: 'qwen3-4b-instruct-q4_k_m',
  runtime_id: 'llama_cpp',
  tokens_per_sec: 14.2,
  context_length: 8192,
  warnings: [],
  output_tokens: 5,
  benchmarked_at: '2026-01-01T00:00:00.000Z',
}

function makeModelsResponse(overrides: Partial<ModelsResponse> = {}): ModelsResponse {
  return {
    registry: [REGISTRY_ENTRY],
    installed: [],
    ollama_models: [
      { id: 'llama3:latest', name: 'llama3:latest', size_category: 'medium' },
      { id: 'phi3:mini', name: 'phi3:mini', size_category: 'small' },
    ],
    active: { runtime_id: null, model_id: null },
    runtime_health: {
      runtime_id: 'none',
      runtime_name: 'llama.cpp',
      status: 'unavailable',
      model_id: null,
      latency_ms: null,
      message: 'No model configured',
      checked_at: '2026-01-01T00:00:00.000Z',
    },
    total: 1,
    last_benchmark: null,
    ...overrides,
  }
}

function renderWizard() {
  return render(
    <MemoryRouter
      initialEntries={['/first-run']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/first-run" element={<FirstRunWizard />} />
        <Route path="/" element={<div data-testid="home-page" />} />
        <Route path="/library" element={<div data-testid="library-page" />} />
        <Route path="/setup/*" element={<div data-testid="setup-page" />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  localStorage.clear()

  mockApi.getModels.mockResolvedValue({ ok: true, data: makeModelsResponse() })
  mockApi.preflight.mockResolvedValue({
    ok: true,
    data: {
      overall: 'pass',
      checks: [],
      ran_at: '2026-01-01T00:00:00.000+00:00',
    },
  })
  mockApi.useModel.mockResolvedValue({ ok: true, data: {
    runtime_id: 'ollama',
    model_id: 'llama3:latest',
    runtime_name: 'Ollama',
    status: 'ready',
    message: null,
  } })
  mockApi.installModel.mockResolvedValue({ ok: true, data: {
    install_id: 1,
    registry_id: 'qwen3-4b-instruct-q4_k_m',
    status: 'pending',
    message: 'Install queued.',
  } })
  mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
    id: 1,
    registry_id: 'qwen3-4b-instruct-q4_k_m',
    filename: 'qwen3-4b-instruct-q4_k_m.gguf',
    file_path: '',
    size_bytes: null,
    install_status: 'downloading',
    progress_bytes: null,
    error_message: null,
    verified_sha256: null,
    installed_at: '2026-01-01T00:00:00Z',
  } })
  mockApi.cancelInstall.mockResolvedValue({ ok: true, data: undefined })
  mockApi.registerGguf.mockResolvedValue({ ok: true, data: {
    profile_id: 1,
    file_path: '/home/user/models/my-model.gguf',
    display_name: 'my-model.gguf',
    filename: 'my-model.gguf',
    family_guess: null,
    context_length_default: null,
    warnings: [],
    active_runtime_id: 'llama_cpp',
    active_model_id: '/home/user/models/my-model.gguf',
  } })
  mockApi.startSidecar.mockResolvedValue({ ok: true, data: {
    state: 'running',
    pid: 1234,
    log_path: '/tmp/sidecar.log',
    host: '127.0.0.1',
    port: 7356,
  } })
  mockApi.benchmarkModel.mockResolvedValue({ ok: true, data: DEFAULT_BENCHMARK })
  mockApi.recordOnboardingOutcome.mockResolvedValue({ ok: true, data: undefined })
  mockApi.getSetupStatus.mockResolvedValue({ ok: true, data: { kind: 'ready' } })
})

// ── Welcome step ─────────────────────────────────────────────────────────────

describe('FirstRunWizard — welcome step', () => {
  it('shows a welcome heading', () => {
    renderWizard()
    expect(screen.getByRole('heading', { name: /welcome to conversation simulator/i })).toBeInTheDocument()
  })

  it('shows the privacy and offline-play guarantee note', () => {
    renderWizard()
    expect(
      screen.getByRole('note', { name: /privacy and offline-play guarantee/i }),
    ).toBeInTheDocument()
  })

  it('states conversations stay on this machine', () => {
    renderWizard()
    expect(screen.getByText(/your data stays on this machine/i)).toBeInTheDocument()
  })

  it('shows a Get started button', () => {
    renderWizard()
    expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument()
  })

  it('does not call the API on the welcome step', () => {
    renderWizard()
    expect(mockApi.getModels).not.toHaveBeenCalled()
  })

  it('advances to loading then choose step when Get started is clicked', async () => {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    expect(await screen.findByRole('heading', { name: /choose how to get started/i })).toBeInTheDocument()
    expect(mockApi.getModels).toHaveBeenCalledOnce()
  })

  it('redirects to home when setup is already complete', () => {
    localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true')
    renderWizard()
    expect(screen.getByTestId('home-page')).toBeInTheDocument()
  })

  it('shows a How it works section', () => {
    renderWizard()
    expect(screen.getByText(/how it works/i)).toBeInTheDocument()
  })

  it('explains that a local AI model powers conversations', () => {
    renderWizard()
    expect(
      screen.getByText(/a local ai model powers the conversations/i),
    ).toBeInTheDocument()
  })

  it('explains what scenario packs are', () => {
    renderWizard()
    expect(
      screen.getByText(/packs give you scenarios to practise/i),
    ).toBeInTheDocument()
  })

  it('mentions the text-only demo option', () => {
    renderWizard()
    expect(
      screen.getByText(/no download\? try the text-only demo/i),
    ).toBeInTheDocument()
  })

  it('explains that the model runs without internet after download', () => {
    renderWizard()
    expect(
      screen.getByText(/works without internet/i),
    ).toBeInTheDocument()
  })

  it('shows a Read setup docs link', () => {
    renderWizard()
    const link = screen.getByRole('link', { name: /read setup docs/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('target', '_blank')
  })
})

// ── Preflight step ────────────────────────────────────────────────────────────

describe('FirstRunWizard — preflight step', () => {
  const INFRA_FAIL_PREFLIGHT = {
    overall: 'fail' as const,
    ran_at: '2026-01-01T00:00:00.000+00:00',
    checks: [
      {
        id: 'llama-cpp-binary',
        name: 'Inference engine',
        status: 'fail' as const,
        message: 'llama-server binary not found.',
        fix_action: { kind: 'open-url' as const, href: 'https://example.com/setup', label: 'Setup guide' },
      },
    ],
  }

  async function goToPreflight() {
    mockApi.preflight.mockResolvedValue({ ok: true, data: INFRA_FAIL_PREFLIGHT })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /system check/i })
  }

  it('shows the system check heading when infra checks fail', async () => {
    await goToPreflight()
    expect(screen.getByRole('heading', { name: /system check/i })).toBeInTheDocument()
  })

  it('shows failing check details in the wizard', async () => {
    await goToPreflight()
    expect(screen.getByTestId('wizard-preflight-check-llama-cpp-binary')).toBeInTheDocument()
  })

  it('shows a fix action button for the failing check', async () => {
    await goToPreflight()
    expect(screen.getByTestId('wizard-preflight-fix-llama-cpp-binary')).toBeInTheDocument()
  })

  it('shows a Continue anyway button', async () => {
    await goToPreflight()
    expect(screen.getByRole('button', { name: /continue anyway/i })).toBeInTheDocument()
  })

  it('shows a Retry system check button', async () => {
    await goToPreflight()
    expect(screen.getByRole('button', { name: /retry system check/i })).toBeInTheDocument()
  })

  it('proceeds to choose step when Continue anyway is clicked', async () => {
    await goToPreflight()
    fireEvent.click(screen.getByRole('button', { name: /continue anyway/i }))
    await screen.findByRole('heading', { name: /choose how to get started/i })
  })

  it('skips preflight step when all infra checks pass', async () => {
    mockApi.preflight.mockResolvedValue({
      ok: true,
      data: { overall: 'pass', checks: [], ran_at: '2026-01-01T00:00:00.000+00:00' },
    })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /choose how to get started/i })
  })

  it('skips preflight step when preflight API call fails (graceful degradation)', async () => {
    mockApi.preflight.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'unavailable' } })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /choose how to get started/i })
  })
})

// ── Issue-378 regression: preflight fix-action dead-loop ─────────────────────
// Covers the exact loop: preflight-fail → click fix → assert NOT on welcome step.

describe('FirstRunWizard — issue-378: preflight fix actions never loop back to welcome', () => {
  function makePreflightWith(checks: PreflightCheck[]) {
    return {
      ok: true as const,
      data: {
        overall: 'fail' as const,
        ran_at: '2026-01-01T00:00:00.000+00:00',
        checks,
      },
    }
  }

  it('wizard-step fix action (llm-present) advances to choose step, not welcome', async () => {
    // Reproduces the exact first-run loop from issue #378:
    // llama-cpp-binary blocks → preflight shown → click "Open Model Manager" → must NOT be welcome.
    mockApi.preflight.mockResolvedValue(makePreflightWith([
      {
        id: 'llama-cpp-binary',
        name: 'Inference engine',
        status: 'fail',
        message: 'llama-server binary not found.',
        fix_action: { kind: 'open-url', href: 'https://example.com/setup', label: 'Setup guide' },
      },
      {
        id: 'llm-present',
        name: 'Language model',
        status: 'fail',
        message: 'No language model installed.',
        fix_action: { kind: 'wizard-step', href: 'choose', label: 'Open Model Manager' },
      },
    ]))
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /system check/i })

    fireEvent.click(screen.getByTestId('wizard-preflight-fix-llm-present'))

    // Must land on the choose step — never the welcome screen.
    await screen.findByRole('heading', { name: /choose how to get started/i })
    expect(screen.queryByRole('heading', { name: /welcome to conversation simulator/i })).not.toBeInTheDocument()
  })

  it('legacy navigate /model-manager fix action also advances to choose step', async () => {
    // Backward-compat path for older backends that still emit navigate /model-manager.
    mockApi.preflight.mockResolvedValue(makePreflightWith([
      {
        id: 'llama-cpp-binary',
        name: 'Inference engine',
        status: 'fail',
        message: 'llama-server binary not found.',
        fix_action: { kind: 'open-url', href: 'https://example.com/setup', label: 'Setup guide' },
      },
      {
        id: 'llm-present',
        name: 'Language model',
        status: 'fail',
        message: 'No language model installed.',
        fix_action: { kind: 'navigate', href: '/model-manager', label: 'Open Model Manager' },
      },
    ]))
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /system check/i })

    fireEvent.click(screen.getByTestId('wizard-preflight-fix-llm-present'))

    await screen.findByRole('heading', { name: /choose how to get started/i })
    expect(screen.queryByRole('heading', { name: /welcome to conversation simulator/i })).not.toBeInTheDocument()
  })

  it('voice-ready navigate /settings fix action renders as informational only (no button)', async () => {
    // Voice check warns with a /settings navigate action; during first-run that
    // route is guarded, so the button must be suppressed entirely.
    mockApi.preflight.mockResolvedValue(makePreflightWith([
      {
        id: 'llama-cpp-binary',
        name: 'Inference engine',
        status: 'fail',
        message: 'llama-server binary not found.',
        fix_action: { kind: 'open-url', href: 'https://example.com/setup', label: 'Setup guide' },
      },
      {
        id: 'voice-ready',
        name: 'Voice features',
        status: 'warn',
        message: 'Some voice features are unavailable.',
        fix_action: { kind: 'navigate', href: '/settings', label: 'Voice Settings' },
      },
    ]))
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /system check/i })

    // The check is rendered but no fix button appears.
    expect(screen.getByTestId('wizard-preflight-check-voice-ready')).toBeInTheDocument()
    expect(screen.queryByTestId('wizard-preflight-fix-voice-ready')).not.toBeInTheDocument()
  })

  it('no fix-action button produced by the preflight step can trigger the FirstRunGuard redirect', async () => {
    // Exhaustively asserts that every fix_action the backend can emit is handled
    // inside the wizard without routing to a guarded path.
    // Mirrors every fix_action the backend can actually emit from preflight.py:
    // open-url (setup guide), wizard-step (llm-present), and navigate to
    // /model-manager, /settings, and /library. Any navigate target that isn't
    // resolvable inside the wizard must be suppressed (no button) rather than
    // rendered as a loop-inducing FirstRunGuard redirect.
    const ALL_POSSIBLE_FIX_ACTIONS: import('@convsim/shared').PreflightFixAction[] = [
      { kind: 'open-url', href: 'https://example.com', label: 'Docs' },
      { kind: 'wizard-step', href: 'choose', label: 'Choose model' },
      { kind: 'navigate', href: '/model-manager', label: 'Model Manager' },
      { kind: 'navigate', href: '/settings', label: 'Open Settings' },
      { kind: 'navigate', href: '/library', label: 'Browse Scenarios' },
    ]
    for (const fix_action of ALL_POSSIBLE_FIX_ACTIONS) {
      localStorage.clear()
      mockApi.preflight.mockResolvedValue(makePreflightWith([
        {
          id: 'llama-cpp-binary',
          name: 'Inference engine',
          status: 'fail',
          message: 'Binary missing.',
          fix_action,
        },
      ]))
      const { unmount } = renderWizard()
      fireEvent.click(screen.getByRole('button', { name: /get started/i }))
      await screen.findByRole('heading', { name: /system check/i })

      // After clicking the fix button (if rendered), the user must never see the
      // welcome screen again (which is what happens when FirstRunGuard sends them
      // back to /first-run and the wizard resets).
      const fixBtn = screen.queryByTestId('wizard-preflight-fix-llama-cpp-binary')
      const resolvableInWizard =
        fix_action.kind !== 'navigate' || fix_action.href === '/model-manager'
      if (resolvableInWizard) {
        // A button is rendered and clicking it must resolve inside the wizard.
        expect(fixBtn).not.toBeNull()
        fireEvent.click(fixBtn!)
        // Give React time to process; welcome heading must NOT appear.
        await new Promise((r) => setTimeout(r, 50))
        expect(screen.queryByRole('heading', { name: /welcome to conversation simulator/i })).not.toBeInTheDocument()
      } else {
        // A navigate to any other guarded route is suppressed entirely — no button,
        // no way to trigger the FirstRunGuard loop.
        expect(fixBtn).toBeNull()
      }
      unmount()
    }
  })
})

// ── Choose step ───────────────────────────────────────────────────────────────

describe('FirstRunWizard — choose step', () => {
  async function goToChoose() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('heading', { name: /choose how to get started/i })
  }

  it('shows Install recommended model option', async () => {
    await goToChoose()
    expect(screen.getByRole('button', { name: /install qwen3/i })).toBeInTheDocument()
  })

  it('shows Browse Ollama models option', async () => {
    await goToChoose()
    expect(screen.getByRole('button', { name: /browse ollama models/i })).toBeInTheDocument()
  })

  it('shows Use a GGUF file option', async () => {
    await goToChoose()
    expect(screen.getByRole('button', { name: /use a gguf file/i })).toBeInTheDocument()
  })

  it('shows Continue without a model option', async () => {
    await goToChoose()
    expect(screen.getByRole('button', { name: /continue in text-only demo/i })).toBeInTheDocument()
  })
})

// ── Confirm install step ──────────────────────────────────────────────────────

describe('FirstRunWizard — confirm install step', () => {
  async function goToConfirm() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('heading', { name: /confirm model install/i })
  }

  it('shows the confirm heading', async () => {
    await goToConfirm()
    expect(screen.getByRole('heading', { name: /confirm model install/i })).toBeInTheDocument()
  })

  it('shows the model size', async () => {
    await goToConfirm()
    expect(screen.getByText(/2\.6 gb/i)).toBeInTheDocument()
  })

  it('shows the license', async () => {
    await goToConfirm()
    expect(screen.getByText(/apache-2\.0/i)).toBeInTheDocument()
  })

  it('shows the destination path', async () => {
    await goToConfirm()
    expect(
      screen.getByText(/~\/.convsim\/models\/llm\/qwen3-4b-instruct-q4_k_m\.gguf/),
    ).toBeInTheDocument()
  })

  it('shows the min VRAM requirement', async () => {
    await goToConfirm()
    expect(screen.getByText('4 GB')).toBeInTheDocument()
  })

  it('shows the offline-play explanation note', async () => {
    await goToConfirm()
    expect(
      screen.getByRole('note', { name: /offline-play explanation/i }),
    ).toBeInTheDocument()
  })

  it('states the model plays offline after install', async () => {
    await goToConfirm()
    expect(screen.getByText(/plays offline after install/i)).toBeInTheDocument()
  })

  it('states no data is sent to any server', async () => {
    await goToConfirm()
    expect(screen.getByText(/no data is sent to any server/i)).toBeInTheDocument()
  })

  it('does not start the download until Confirm is clicked', async () => {
    await goToConfirm()
    expect(mockApi.installModel).not.toHaveBeenCalled()
  })

})

// ── Successful install ────────────────────────────────────────────────────────

describe('FirstRunWizard — successful install', () => {
  async function goToInstalling() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  }

  it('shows the installing heading after confirmation', async () => {
    await goToInstalling()
    expect(screen.getByRole('heading', { name: /installing model/i })).toBeInTheDocument()
  })

  it('shows a download progress bar', async () => {
    await goToInstalling()
    expect(screen.getByRole('progressbar', { name: /download progress/i })).toBeInTheDocument()
  })

  it('shows percentage and GB when progress data is available', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: 2_000_000_000,
        install_status: 'downloading',
        progress_bytes: 1_000_000_000,
        error_message: null,
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      const bar = screen.getByRole('progressbar')
      expect(bar.getAttribute('aria-valuenow')).toBe('50')
      expect(screen.getByText(/50%/)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('navigates home when install reaches ready status', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '/home/user/.convsim/models/llm/qwen3-4b-instruct-q4_k_m.gguf',
        size_bytes: 2_000_000_000,
        install_status: 'ready',
        progress_bytes: 2_000_000_000,
        error_message: null,
        verified_sha256: 'a'.repeat(64),
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
    } finally {
      vi.useRealTimers()
    }
  })

  it('marks first-run complete in localStorage on successful install', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '/home/user/.convsim/models/llm/qwen3-4b-instruct-q4_k_m.gguf',
        size_bytes: 2_000_000_000,
        install_status: 'ready',
        progress_bytes: 2_000_000_000,
        error_message: null,
        verified_sha256: 'a'.repeat(64),
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)
      await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())

      expect(localStorage.getItem(SETUP_KEYS.firstRunComplete)).toBe('true')
    } finally {
      vi.useRealTimers()
    }
  })
})

// ── No network error ──────────────────────────────────────────────────────────

describe('FirstRunWizard — no network error', () => {
  async function goToInstalling() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  }

  it('shows a network error alert when download fails with a network error', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: null,
        install_status: 'failed',
        progress_bytes: 0,
        error_message: 'no network connection available',
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() =>
        expect(screen.getByRole('alert', { name: /network error/i })).toBeInTheDocument(),
      )
      expect(screen.getByText(/network connection lost/i)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('stays on the installing step when a network error occurs', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: null,
        install_status: 'failed',
        progress_bytes: 0,
        error_message: 'network error: connection refused',
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() =>
        expect(screen.getByRole('alert', { name: /network error/i })).toBeInTheDocument(),
      )
      expect(screen.getByRole('heading', { name: /installing model/i })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows a Retry download button after a network error', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: null,
        install_status: 'failed',
        progress_bytes: 0,
        error_message: 'no network connection',
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /retry download/i })).toBeInTheDocument(),
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows a Choose a different option button after a network error', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: null,
        install_status: 'failed',
        progress_bytes: 0,
        error_message: 'no network connection',
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() =>
        expect(
          screen.getByRole('button', { name: /choose a different option/i }),
        ).toBeInTheDocument(),
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('returns to the confirm step when Retry download is clicked', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: null,
        install_status: 'failed',
        progress_bytes: 0,
        error_message: 'no network connection',
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /retry download/i })).toBeInTheDocument(),
      )

      fireEvent.click(screen.getByRole('button', { name: /retry download/i }))
      await screen.findByRole('heading', { name: /confirm model install/i })
    } finally {
      vi.useRealTimers()
    }
  })

  it('returns to the choose step when Choose a different option is clicked', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '',
        size_bytes: null,
        install_status: 'failed',
        progress_bytes: 0,
        error_message: 'no network connection',
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)
      await waitFor(() =>
        expect(
          screen.getByRole('button', { name: /choose a different option/i }),
        ).toBeInTheDocument(),
      )

      fireEvent.click(screen.getByRole('button', { name: /choose a different option/i }))
      await screen.findByRole('heading', { name: /choose how to get started/i })
    } finally {
      vi.useRealTimers()
    }
  })
})

// ── Insufficient disk error ───────────────────────────────────────────────────

describe('FirstRunWizard — insufficient disk error', () => {
  async function triggerDiskError() {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })

    mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
      id: 1,
      registry_id: 'qwen3-4b-instruct-q4_k_m',
      filename: 'qwen3-4b-instruct-q4_k_m.gguf',
      file_path: '',
      size_bytes: 2_000_000_000,
      install_status: 'failed',
      progress_bytes: 0,
      error_message: 'insufficient disk space',
      verified_sha256: null,
      installed_at: '2026-01-01T00:00:00Z',
    } })
    await vi.advanceTimersByTimeAsync(2000)

    await waitFor(() =>
      expect(screen.getByRole('alert', { name: /insufficient disk space/i })).toBeInTheDocument(),
    )
  }

  it('shows a disk space alert when download fails with an insufficient disk error', async () => {
    try {
      await triggerDiskError()
      expect(screen.getByText(/not enough disk space/i)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('mentions the approximate disk space required', async () => {
    try {
      await triggerDiskError()
      expect(screen.getByText(/2\.6 gb/i)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('stays on the installing step when a disk error occurs', async () => {
    try {
      await triggerDiskError()
      expect(screen.getByRole('heading', { name: /installing model/i })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows a Try again button after a disk error', async () => {
    try {
      await triggerDiskError()
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('returns to the confirm step when Try again is clicked', async () => {
    try {
      await triggerDiskError()
      fireEvent.click(screen.getByRole('button', { name: /try again/i }))
      await screen.findByRole('heading', { name: /confirm model install/i })
    } finally {
      vi.useRealTimers()
    }
  })

  it('returns to the choose step when Choose a different option is clicked', async () => {
    try {
      await triggerDiskError()
      fireEvent.click(screen.getByRole('button', { name: /choose a different option/i }))
      await screen.findByRole('heading', { name: /choose how to get started/i })
    } finally {
      vi.useRealTimers()
    }
  })
})

// ── Cancelled download ────────────────────────────────────────────────────────

describe('FirstRunWizard — cancelled download', () => {
  async function goToInstalling() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  }

  it('shows a Cancel and go home button while downloading', async () => {
    await goToInstalling()
    expect(screen.getByRole('button', { name: /cancel and go home/i })).toBeInTheDocument()
  })

  it('calls cancelInstall when Cancel and go home is clicked', async () => {
    await goToInstalling()
    fireEvent.click(screen.getByRole('button', { name: /cancel and go home/i }))
    await waitFor(() => expect(mockApi.cancelInstall).toHaveBeenCalledWith(1))
  })

  it('navigates home after cancelling the download', async () => {
    await goToInstalling()
    fireEvent.click(screen.getByRole('button', { name: /cancel and go home/i }))
    await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
  })

  it('marks first-run complete in localStorage after cancelling', async () => {
    await goToInstalling()
    fireEvent.click(screen.getByRole('button', { name: /cancel and go home/i }))
    await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
    expect(localStorage.getItem(SETUP_KEYS.firstRunComplete)).toBe('true')
  })

  it('navigates home even when cancelInstall API call fails', async () => {
    mockApi.cancelInstall.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'server error' } })
    await goToInstalling()
    fireEvent.click(screen.getByRole('button', { name: /cancel and go home/i }))
    await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
  })

  it('keeps polling through transient status errors', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValueOnce({ ok: false, error: { kind: 'network', message: 'network blip' } })

      await vi.advanceTimersByTimeAsync(2000)
      expect(screen.getByRole('heading', { name: /installing model/i })).toBeInTheDocument()

      await vi.advanceTimersByTimeAsync(2000)
      expect(mockApi.getInstallStatus.mock.calls.length).toBeGreaterThanOrEqual(2)
    } finally {
      vi.useRealTimers()
    }
  })
})

// ── Existing Ollama path ──────────────────────────────────────────────────────

describe('FirstRunWizard — existing Ollama path', () => {
  async function goToOllama() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /browse ollama models/i })
    fireEvent.click(screen.getByRole('button', { name: /browse ollama models/i }))
    await screen.findByRole('heading', { name: /use ollama model/i })
  }

  it('shows the Ollama model list', async () => {
    await goToOllama()
    expect(screen.getByText('llama3:latest')).toBeInTheDocument()
    expect(screen.getByText('phi3:mini')).toBeInTheDocument()
  })

  it('shows a Use this model button for each Ollama model', async () => {
    await goToOllama()
    expect(screen.getAllByRole('button', { name: /use this model/i })).toHaveLength(2)
  })

  it('calls useModel with the ollama runtime when a model is selected', async () => {
    await goToOllama()
    const [first] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(first)
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({
        runtime_id: 'ollama',
        model_id: 'llama3:latest',
      }),
    )
  })

  it('advances to the benchmark step after selecting an Ollama model', async () => {
    await goToOllama()
    const [first] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(first)
    await screen.findByRole('heading', { name: /model benchmark/i })
    expect(screen.getByRole('heading', { name: /model benchmark/i })).toBeInTheDocument()
  })

  it('shows tokens per second after benchmark completes', async () => {
    await goToOllama()
    const [first] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(first)
    await screen.findByRole('heading', { name: /model benchmark/i })
    await waitFor(() => expect(screen.getByText(/14\.2 tokens\/sec/i)).toBeInTheDocument())
  })

  it('shows a Continue to Home button after benchmark', async () => {
    await goToOllama()
    const [first] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(first)
    const btn = await screen.findByRole('button', { name: /continue to home/i })
    expect(btn).toBeInTheDocument()
  })

  it('navigates home and marks setup complete when Continue is clicked', async () => {
    await goToOllama()
    const [first] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(first)
    const btn = await screen.findByRole('button', { name: /continue to home/i })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
    expect(localStorage.getItem(SETUP_KEYS.firstRunComplete)).toBe('true')
  })

  it('shows an error alert when useModel fails', async () => {
    mockApi.useModel.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Ollama not running' } })
    await goToOllama()
    const [first] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(first)
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/ollama not running/i),
    )
  })

  it('shows "No Ollama models detected" when the list is empty', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModelsResponse({ ollama_models: [] }) })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /browse ollama models/i })
    fireEvent.click(screen.getByRole('button', { name: /browse ollama models/i }))
    await screen.findByText(/no ollama models detected/i)
    expect(screen.getByText(/no ollama models detected/i)).toBeInTheDocument()
  })

  it('back button returns to the choose step', async () => {
    await goToOllama()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    await screen.findByRole('heading', { name: /choose how to get started/i })
  })
})

// ── Demo / text-only path ─────────────────────────────────────────────────────

describe('FirstRunWizard — text-only demo path', () => {
  async function goToDemo() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /continue in text-only demo/i })
    fireEvent.click(screen.getByRole('button', { name: /continue in text-only demo/i }))
    await screen.findByRole('heading', { name: /text-only demo/i })
  }

  it('shows a disclaimer that this is not production quality', async () => {
    await goToDemo()
    expect(screen.getByText(/this is a demo, not production quality/i)).toBeInTheDocument()
  })

  it('mentions scripted responses in the disclaimer', async () => {
    await goToDemo()
    expect(screen.getByText(/scripted responses/i)).toBeInTheDocument()
  })

  it('calls useModel with the fake runtime when confirmed', async () => {
    mockApi.useModel.mockResolvedValue({ ok: true, data: {
      runtime_id: 'fake',
      model_id: null,
      runtime_name: 'Fake (deterministic)',
      status: 'ready',
      message: null,
    } })
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({ runtime_id: 'fake', model_id: null }),
    )
  })

  it('navigates to the library and marks setup complete after confirming demo', async () => {
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    await waitFor(() => expect(screen.getByTestId('library-page')).toBeInTheDocument())
    expect(localStorage.getItem(SETUP_KEYS.firstRunComplete)).toBe('true')
  })

  it('still navigates to library even when useModel fails in demo mode', async () => {
    mockApi.useModel.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'runtime unavailable' } })
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    await waitFor(() => expect(screen.getByTestId('library-page')).toBeInTheDocument())
  })
})

// ── Tutorial CTA on installing step ──────────────────────────────────────────

describe('FirstRunWizard — tutorial CTA during install', () => {
  async function goToInstalling() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  }

  it('shows the play tutorial note while downloading', async () => {
    await goToInstalling()
    expect(
      screen.getByRole('note', { name: /play tutorial while downloading/i }),
    ).toBeInTheDocument()
  })

  it('shows the Play the tutorial while you wait button', async () => {
    await goToInstalling()
    expect(
      screen.getByRole('button', { name: /play the tutorial while you wait/i }),
    ).toBeInTheDocument()
  })

  it('still shows the download progress bar alongside the tutorial CTA', async () => {
    await goToInstalling()
    expect(screen.getByRole('progressbar', { name: /download progress/i })).toBeInTheDocument()
  })

  it('still shows the Cancel and go home button alongside the tutorial CTA', async () => {
    await goToInstalling()
    expect(screen.getByRole('button', { name: /cancel and go home/i })).toBeInTheDocument()
  })

  it('advances to the tutorial-prompt step when the CTA is clicked', async () => {
    await goToInstalling()
    fireEvent.click(screen.getByRole('button', { name: /play the tutorial while you wait/i }))
    await screen.findByRole('heading', { name: /first words tutorial/i })
  })
})

// ── Tutorial prompt step ──────────────────────────────────────────────────────

describe('FirstRunWizard — tutorial prompt step', () => {
  async function goToTutorialPrompt() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
    fireEvent.click(screen.getByRole('button', { name: /play the tutorial while you wait/i }))
    await screen.findByRole('heading', { name: /first words tutorial/i })
  }

  it('shows the scripted tutorial disclaimer', async () => {
    await goToTutorialPrompt()
    expect(
      screen.getByRole('note', { name: /scripted tutorial disclaimer/i }),
    ).toBeInTheDocument()
  })

  it('labels the tutorial as scripted and not AI-generated', async () => {
    await goToTutorialPrompt()
    expect(screen.getByText(/scripted tutorial — not ai-generated/i)).toBeInTheDocument()
  })

  it('lists what the player will learn', async () => {
    await goToTutorialPrompt()
    expect(screen.getByText(/state meters/i)).toBeInTheDocument()
    expect(screen.getByText(/scenario events/i)).toBeInTheDocument()
  })

  it('shows a Start the tutorial button', async () => {
    await goToTutorialPrompt()
    expect(screen.getByRole('button', { name: /start the tutorial/i })).toBeInTheDocument()
  })

  it('shows a Back button to return to the installing step', async () => {
    await goToTutorialPrompt()
    expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument()
  })

  it('back button returns to the installing step', async () => {
    await goToTutorialPrompt()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  })

  it('calls useModel with scripted runtime when Start the tutorial is clicked', async () => {
    mockApi.useModel.mockResolvedValue({ ok: true, data: {
      runtime_id: 'scripted',
      model_id: null,
      runtime_name: 'Scripted tutorial',
      status: 'ready',
      message: null,
    } })
    await goToTutorialPrompt()
    fireEvent.click(screen.getByRole('button', { name: /start the tutorial/i }))
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({ runtime_id: 'scripted', model_id: null }),
    )
  })

  it('marks tutorial complete in localStorage when starting the tutorial', async () => {
    await goToTutorialPrompt()
    fireEvent.click(screen.getByRole('button', { name: /start the tutorial/i }))
    await waitFor(() =>
      expect(localStorage.getItem(SETUP_KEYS.tutorialComplete)).toBe('true'),
    )
  })

  it('marks first-run complete in localStorage when starting the tutorial', async () => {
    await goToTutorialPrompt()
    fireEvent.click(screen.getByRole('button', { name: /start the tutorial/i }))
    await waitFor(() =>
      expect(localStorage.getItem(SETUP_KEYS.firstRunComplete)).toBe('true'),
    )
  })

  it('proceeds even when useModel fails for the scripted runtime', async () => {
    mockApi.useModel.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'scripted unavailable' } })
    await goToTutorialPrompt()
    fireEvent.click(screen.getByRole('button', { name: /start the tutorial/i }))
    await waitFor(() =>
      expect(localStorage.getItem(SETUP_KEYS.tutorialComplete)).toBe('true'),
    )
  })

  it('navigates to the tutorial scenario setup route (a real, mounted route)', async () => {
    await goToTutorialPrompt()
    fireEvent.click(screen.getByRole('button', { name: /start the tutorial/i }))
    // The setup route resolves the seeded scenario by id; there is no /play route.
    await screen.findByTestId('setup-page')
  })
})

// ── Tutorial completion affects post-install navigation ───────────────────────

describe('FirstRunWizard — post-install navigation with tutorial completed', () => {
  async function goToInstalling() {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  }

  it('navigates to /library (not home) when install completes and tutorial was completed', async () => {
    localStorage.setItem(SETUP_KEYS.tutorialComplete, 'true')
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '/home/user/.convsim/models/llm/qwen3-4b-instruct-q4_k_m.gguf',
        size_bytes: 2_000_000_000,
        install_status: 'ready',
        progress_bytes: 2_000_000_000,
        error_message: null,
        verified_sha256: 'a'.repeat(64),
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() => expect(screen.getByTestId('library-page')).toBeInTheDocument())
    } finally {
      vi.useRealTimers()
    }
  })

  it('navigates to / (home) when install completes and tutorial was NOT completed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await goToInstalling()
      mockApi.getInstallStatus.mockResolvedValue({ ok: true, data: {
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b-instruct-q4_k_m.gguf',
        file_path: '/home/user/.convsim/models/llm/qwen3-4b-instruct-q4_k_m.gguf',
        size_bytes: 2_000_000_000,
        install_status: 'ready',
        progress_bytes: 2_000_000_000,
        error_message: null,
        verified_sha256: 'a'.repeat(64),
        installed_at: '2026-01-01T00:00:00Z',
      } })
      await vi.advanceTimersByTimeAsync(2000)

      await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
    } finally {
      vi.useRealTimers()
    }
  })
})

// ── Load error state ──────────────────────────────────────────────────────────

describe('FirstRunWizard — load error state', () => {
  it('shows an error alert when getModels fails', async () => {
    mockApi.getModels.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'service unavailable' } })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/service unavailable/i),
    )
  })

  it('mentions the text-only demo as a fallback when the runtime is unavailable', async () => {
    mockApi.getModels.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'runtime unreachable' } })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument(),
    )
    expect(screen.getByText(/text-only demo works without one/i)).toBeInTheDocument()
  })

  it('back button from load error returns to the welcome step', async () => {
    mockApi.getModels.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'network error' } })
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /back to welcome/i }))
    await screen.findByRole('heading', { name: /welcome to conversation simulator/i })
  })
})
