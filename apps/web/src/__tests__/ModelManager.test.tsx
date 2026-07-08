// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ModelManager from '../screens/ModelManager'
import type { ModelsResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    getModels: vi.fn(),
    useModel: vi.fn(),
    installModel: vi.fn(),
    benchmarkModel: vi.fn(),
  },
}))

import { api } from '../api/client'
import type { BenchmarkResponse } from '@convsim/shared'
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

function renderModelManager() {
  return render(
    <MemoryRouter
      initialEntries={['/model-manager']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/model-manager" element={<ModelManager />} />
        <Route path="/" element={<div data-testid="home-page" />} />
        <Route path="/library" element={<div data-testid="library-page" />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  mockApi.getModels.mockResolvedValue(makeModelsResponse())
  mockApi.useModel.mockResolvedValue({
    runtime_id: 'ollama',
    model_id: 'llama3:latest',
    runtime_name: 'Ollama',
    status: 'ready',
    message: null,
  })
  mockApi.installModel.mockResolvedValue({
    install_id: 1,
    registry_id: 'qwen3-4b-instruct-q4_k_m',
    status: 'pending',
    message: 'Install queued.',
  })
  mockApi.benchmarkModel.mockResolvedValue({
    model_id: 'llama3:latest',
    runtime_id: 'ollama',
    tokens_per_sec: 12.5,
    context_length: 4096,
    warnings: [],
    output_tokens: 5,
    benchmarked_at: '2026-01-01T00:00:00.000Z',
  })
})

// ── Loading state ────────────────────────────────────────────────────────────

describe('ModelManager — loading', () => {
  it('shows loading state while fetching model info', () => {
    mockApi.getModels.mockReturnValue(new Promise(() => {}))
    renderModelManager()
    expect(screen.getByText(/loading model information/i)).toBeInTheDocument()
  })
})

// ── Choose step ──────────────────────────────────────────────────────────────

describe('ModelManager — choose step', () => {
  it('shows the set up heading after loading', async () => {
    renderModelManager()
    expect(await screen.findByRole('heading', { name: /set up your model/i })).toBeInTheDocument()
  })

  it('shows the install recommended option with model name', async () => {
    renderModelManager()
    expect(
      await screen.findByRole('button', { name: /install qwen3 4b/i }),
    ).toBeInTheDocument()
  })

  it('shows the Browse Ollama models option', async () => {
    renderModelManager()
    expect(
      await screen.findByRole('button', { name: /browse ollama models/i }),
    ).toBeInTheDocument()
  })

  it('shows the Use a GGUF file option', async () => {
    renderModelManager()
    expect(
      await screen.findByRole('button', { name: /use a gguf file/i }),
    ).toBeInTheDocument()
  })

  it('shows the Try text-only demo option', async () => {
    renderModelManager()
    expect(
      await screen.findByRole('button', { name: /try text-only demo/i }),
    ).toBeInTheDocument()
  })

  it('does not start any download on page load', async () => {
    renderModelManager()
    await screen.findByRole('heading', { name: /set up your model/i })
    expect(mockApi.installModel).not.toHaveBeenCalled()
  })
})

// ── Confirm install branch ───────────────────────────────────────────────────

describe('ModelManager — confirm install', () => {
  async function goToConfirm() {
    renderModelManager()
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('heading', { name: /confirm model install/i })
  }

  it('shows the confirm model install heading', async () => {
    await goToConfirm()
    expect(screen.getByRole('heading', { name: /confirm model install/i })).toBeInTheDocument()
  })

  it('shows the model name in the details table', async () => {
    await goToConfirm()
    expect(screen.getByText('Qwen3 4B Instruct Q4_K_M')).toBeInTheDocument()
  })

  it('shows the model size', async () => {
    await goToConfirm()
    expect(screen.getByText(/2\.6 gb/i)).toBeInTheDocument()
  })

  it('shows the license', async () => {
    await goToConfirm()
    expect(screen.getByText(/apache-2\.0/i)).toBeInTheDocument()
  })

  it('shows the SHA-256 checksum (even when PENDING)', async () => {
    await goToConfirm()
    expect(screen.getByText('PENDING')).toBeInTheDocument()
  })

  it('shows the min VRAM requirement', async () => {
    await goToConfirm()
    expect(screen.getByText('4 GB')).toBeInTheDocument()
  })

  it('shows the recommended VRAM', async () => {
    await goToConfirm()
    expect(screen.getByText('6 GB')).toBeInTheDocument()
  })

  it('shows the expected storage path', async () => {
    await goToConfirm()
    expect(
      screen.getByText(/~\/.convsim\/models\/qwen3-4b-instruct-q4_k_m\.gguf/),
    ).toBeInTheDocument()
  })

  it('does not call installModel until Confirm is clicked', async () => {
    await goToConfirm()
    expect(mockApi.installModel).not.toHaveBeenCalled()
  })

  it('calls installModel with the registry ID after confirmation', async () => {
    await goToConfirm()
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await waitFor(() =>
      expect(mockApi.installModel).toHaveBeenCalledWith({
        registry_id: 'qwen3-4b-instruct-q4_k_m',
      }),
    )
  })

  it('shows the installing step after confirmation succeeds', async () => {
    await goToConfirm()
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
  })

  it('shows an error alert when installModel fails', async () => {
    mockApi.installModel.mockRejectedValue(new Error('insufficient VRAM'))
    await goToConfirm()
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/insufficient vram/i),
    )
  })

  it('suggests a smaller model and setup docs when an install fails', async () => {
    mockApi.installModel.mockRejectedValue(new Error('runtime unavailable'))
    await goToConfirm()
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/smaller model/i),
    )
    expect(screen.getByRole('link', { name: /setup docs/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/wiki'),
    )
  })

  it('returns to choose step when Cancel is clicked', async () => {
    await goToConfirm()
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await screen.findByRole('heading', { name: /set up your model/i })
  })
})

// ── Installing step ──────────────────────────────────────────────────────────

describe('ModelManager — installing step', () => {
  it('shows the installing model heading', async () => {
    renderModelManager()
    await screen.findByRole('button', { name: /install qwen3/i })
    fireEvent.click(screen.getByRole('button', { name: /install qwen3/i }))
    await screen.findByRole('button', { name: /confirm & install/i })
    fireEvent.click(screen.getByRole('button', { name: /confirm & install/i }))
    await screen.findByRole('heading', { name: /installing model/i })
    expect(screen.getByRole('heading', { name: /installing model/i })).toBeInTheDocument()
  })
})

// ── Ollama branch ─────────────────────────────────────────────────────────────

describe('ModelManager — Ollama branch', () => {
  async function goToOllama() {
    renderModelManager()
    await screen.findByRole('button', { name: /browse ollama models/i })
    fireEvent.click(screen.getByRole('button', { name: /browse ollama models/i }))
    await screen.findByRole('heading', { name: /use ollama model/i })
  }

  it('shows the use ollama model heading', async () => {
    await goToOllama()
    expect(screen.getByRole('heading', { name: /use ollama model/i })).toBeInTheDocument()
  })

  it('lists all detected Ollama model names', async () => {
    await goToOllama()
    expect(screen.getByText('llama3:latest')).toBeInTheDocument()
    expect(screen.getByText('phi3:mini')).toBeInTheDocument()
  })

  it('shows a "Use this model" button for each Ollama model', async () => {
    await goToOllama()
    const buttons = screen.getAllByRole('button', { name: /use this model/i })
    expect(buttons).toHaveLength(2)
  })

  it('calls useModel with ollama runtime when a model is selected', async () => {
    await goToOllama()
    const [firstButton] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(firstButton)
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({
        runtime_id: 'ollama',
        model_id: 'llama3:latest',
      }),
    )
  })

  it('shows the benchmark step after selecting an Ollama model', async () => {
    await goToOllama()
    const [firstButton] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(firstButton)
    await screen.findByRole('heading', { name: /model benchmark/i })
    expect(screen.getByRole('heading', { name: /model benchmark/i })).toBeInTheDocument()
  })

  it('shows an alert when useModel fails', async () => {
    mockApi.useModel.mockRejectedValue(new Error('Ollama not running'))
    await goToOllama()
    const [firstButton] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(firstButton)
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/ollama not running/i),
    )
  })

  it('shows "No Ollama models detected" when the list is empty', async () => {
    mockApi.getModels.mockResolvedValue(makeModelsResponse({ ollama_models: [] }))
    renderModelManager()
    await screen.findByRole('button', { name: /browse ollama models/i })
    fireEvent.click(screen.getByRole('button', { name: /browse ollama models/i }))
    await screen.findByText(/no ollama models detected/i)
    expect(screen.getByText(/no ollama models detected/i)).toBeInTheDocument()
  })

  it('back button returns to choose step', async () => {
    await goToOllama()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    await screen.findByRole('heading', { name: /set up your model/i })
  })
})

// ── GGUF branch ───────────────────────────────────────────────────────────────

describe('ModelManager — GGUF branch', () => {
  async function goToGguf() {
    renderModelManager()
    await screen.findByRole('button', { name: /use a gguf file/i })
    fireEvent.click(screen.getByRole('button', { name: /use a gguf file/i }))
    await screen.findByRole('heading', { name: /use a gguf file/i })
  }

  it('shows the file path input', async () => {
    await goToGguf()
    expect(screen.getByRole('textbox', { name: /file path/i })).toBeInTheDocument()
  })

  it('shows the Use this file button', async () => {
    await goToGguf()
    expect(screen.getByRole('button', { name: /use this file/i })).toBeInTheDocument()
  })

  it('shows a license responsibility notice', async () => {
    await goToGguf()
    expect(screen.getByRole('note', { name: /license responsibility notice/i })).toBeInTheDocument()
  })

  it('states user is responsible for license and hardware fit', async () => {
    await goToGguf()
    expect(screen.getByText(/responsible for this model.*license/i)).toBeInTheDocument()
  })

  it('states the app does not claim the model is official or redistributable', async () => {
    await goToGguf()
    expect(screen.getByText(/does not claim/i)).toBeInTheDocument()
  })

  it('states the file will not be copied', async () => {
    await goToGguf()
    expect(screen.getByText(/file will not be copied/i)).toBeInTheDocument()
  })

  it('shows a validation error when path is empty', async () => {
    await goToGguf()
    fireEvent.click(screen.getByRole('button', { name: /use this file/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/please enter a file path/i),
    )
  })

  it('shows a validation error when path lacks .gguf extension', async () => {
    await goToGguf()
    fireEvent.change(screen.getByRole('textbox', { name: /file path/i }), {
      target: { value: '/home/user/model.bin' },
    })
    fireEvent.click(screen.getByRole('button', { name: /use this file/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/\.gguf extension/i),
    )
  })

  it('calls useModel with llama_cpp runtime and the provided path', async () => {
    await goToGguf()
    fireEvent.change(screen.getByRole('textbox', { name: /file path/i }), {
      target: { value: '/home/user/models/my-model.gguf' },
    })
    fireEvent.click(screen.getByRole('button', { name: /use this file/i }))
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({
        runtime_id: 'llama_cpp',
        model_id: '/home/user/models/my-model.gguf',
      }),
    )
  })

  it('shows the benchmark step after a valid GGUF path is submitted', async () => {
    await goToGguf()
    fireEvent.change(screen.getByRole('textbox', { name: /file path/i }), {
      target: { value: '/home/user/models/my-model.gguf' },
    })
    fireEvent.click(screen.getByRole('button', { name: /use this file/i }))
    await screen.findByRole('heading', { name: /model benchmark/i })
    expect(screen.getByRole('heading', { name: /model benchmark/i })).toBeInTheDocument()
  })

  it('shows an error when useModel fails for the GGUF path', async () => {
    mockApi.useModel.mockRejectedValue(new Error('GGUF_FILE_NOT_FOUND: file not found'))
    await goToGguf()
    fireEvent.change(screen.getByRole('textbox', { name: /file path/i }), {
      target: { value: '/home/user/models/missing.gguf' },
    })
    fireEvent.click(screen.getByRole('button', { name: /use this file/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/file not found/i),
    )
  })

  it('back button returns to choose step', async () => {
    await goToGguf()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    await screen.findByRole('heading', { name: /set up your model/i })
  })
})

// ── Text-only demo branch ─────────────────────────────────────────────────────

describe('ModelManager — text-only demo branch', () => {
  async function goToDemo() {
    renderModelManager()
    await screen.findByRole('button', { name: /try text-only demo/i })
    fireEvent.click(screen.getByRole('button', { name: /try text-only demo/i }))
    await screen.findByRole('heading', { name: /text-only demo/i })
  }

  it('shows the text-only demo heading', async () => {
    await goToDemo()
    expect(screen.getByRole('heading', { name: /text-only demo/i })).toBeInTheDocument()
  })

  it('shows a disclaimer that this is not production quality', async () => {
    await goToDemo()
    expect(screen.getByText(/this is a demo, not production quality/i)).toBeInTheDocument()
  })

  it('mentions scripted responses in the disclaimer', async () => {
    await goToDemo()
    expect(screen.getByText(/scripted responses/i)).toBeInTheDocument()
  })

  it('shows the I understand confirm button', async () => {
    await goToDemo()
    expect(screen.getByRole('button', { name: /i understand/i })).toBeInTheDocument()
  })

  it('shows a cancel button on the demo warning', async () => {
    await goToDemo()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('cancel returns to choose step', async () => {
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await screen.findByRole('heading', { name: /set up your model/i })
  })

  it('calls useModel with the fake runtime when confirmed', async () => {
    mockApi.useModel.mockResolvedValue({
      runtime_id: 'fake',
      model_id: null,
      runtime_name: 'Fake (deterministic)',
      status: 'ready',
      message: null,
    })
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({
        runtime_id: 'fake',
        model_id: null,
      }),
    )
  })

  it('navigates to the library after confirming demo mode', async () => {
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    await waitFor(() => expect(screen.getByTestId('library-page')).toBeInTheDocument())
  })

  it('still navigates to library even when useModel fails for demo', async () => {
    mockApi.useModel.mockRejectedValue(new Error('runtime unavailable'))
    await goToDemo()
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }))
    await waitFor(() => expect(screen.getByTestId('library-page')).toBeInTheDocument())
  })
})

// ── Benchmark step ────────────────────────────────────────────────────────────

describe('ModelManager — benchmark step', () => {
  async function goToBenchmarkViaOllama() {
    renderModelManager()
    await screen.findByRole('button', { name: /browse ollama models/i })
    fireEvent.click(screen.getByRole('button', { name: /browse ollama models/i }))
    await screen.findByRole('heading', { name: /use ollama model/i })
    const [firstButton] = screen.getAllByRole('button', { name: /use this model/i })
    fireEvent.click(firstButton)
    await screen.findByRole('heading', { name: /model benchmark/i })
  }

  it('shows the model benchmark heading after Ollama model selection', async () => {
    await goToBenchmarkViaOllama()
    expect(screen.getByRole('heading', { name: /model benchmark/i })).toBeInTheDocument()
  })

  it('automatically runs the benchmark on entering the step', async () => {
    await goToBenchmarkViaOllama()
    await waitFor(() => expect(mockApi.benchmarkModel).toHaveBeenCalledWith({}))
  })

  it('shows tokens per second after benchmark completes', async () => {
    await goToBenchmarkViaOllama()
    await waitFor(() => expect(screen.getByText(/12\.5 tokens\/sec/i)).toBeInTheDocument())
  })

  it('shows context window size after benchmark completes', async () => {
    await goToBenchmarkViaOllama()
    await waitFor(() => expect(screen.getByText(/4,096/)).toBeInTheDocument())
  })

  it('shows continue to home button', async () => {
    await goToBenchmarkViaOllama()
    const btn = await screen.findByRole('button', { name: /continue to home/i })
    expect(btn).toBeInTheDocument()
  })

  it('navigates to home when continue button is clicked', async () => {
    await goToBenchmarkViaOllama()
    const btn = await screen.findByRole('button', { name: /continue to home/i })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
  })

  it('shows benchmark warnings when returned by the API', async () => {
    mockApi.benchmarkModel.mockResolvedValue({
      model_id: 'llama3:latest',
      runtime_id: 'ollama',
      tokens_per_sec: 0.8,
      context_length: null,
      warnings: ['Very slow generation (0.8 tok/s). The model may be running on CPU only.'],
      output_tokens: 5,
      benchmarked_at: '2026-01-01T00:00:00.000Z',
    } satisfies BenchmarkResponse)
    await goToBenchmarkViaOllama()
    const alertEl = await screen.findByRole('alert', { name: /benchmark warnings/i })
    expect(alertEl).toBeInTheDocument()
    expect(alertEl).toHaveTextContent(/very slow/i)
  })

  it('shows error message when benchmark fails but still allows continuing', async () => {
    mockApi.benchmarkModel.mockRejectedValue(new Error('runtime unavailable'))
    await goToBenchmarkViaOllama()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/benchmark failed/i),
    )
    expect(screen.getByRole('button', { name: /continue to home/i })).toBeInTheDocument()
  })

  it('allows navigating home even after benchmark failure', async () => {
    mockApi.benchmarkModel.mockRejectedValue(new Error('runtime unavailable'))
    await goToBenchmarkViaOllama()
    const btn = await screen.findByRole('button', { name: /continue to home/i })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByTestId('home-page')).toBeInTheDocument())
  })
})

// ── Choose step — last benchmark display ─────────────────────────────────────

describe('ModelManager — last benchmark in choose step', () => {
  it('shows last benchmark speed when available', async () => {
    mockApi.getModels.mockResolvedValue(
      makeModelsResponse({
        last_benchmark: {
          model_id: 'llama3:latest',
          runtime_id: 'ollama',
          tokens_per_sec: 18.3,
          context_length: 8192,
          warnings: [],
          output_tokens: 5,
          benchmarked_at: '2026-01-01T00:00:00.000Z',
        },
      }),
    )
    renderModelManager()
    expect(await screen.findByLabelText(/last benchmark result/i)).toBeInTheDocument()
    expect(screen.getByText(/18\.3 tok\/s/i)).toBeInTheDocument()
  })

  it('shows warning count when last benchmark has warnings', async () => {
    mockApi.getModels.mockResolvedValue(
      makeModelsResponse({
        last_benchmark: {
          model_id: 'llama3:latest',
          runtime_id: 'ollama',
          tokens_per_sec: 1.2,
          context_length: null,
          warnings: ['Slow generation (1.2 tok/s).'],
          output_tokens: 2,
          benchmarked_at: '2026-01-01T00:00:00.000Z',
        },
      }),
    )
    renderModelManager()
    await screen.findByRole('heading', { name: /set up your model/i })
    expect(screen.getByText(/1 warning/i)).toBeInTheDocument()
  })

  it('does not show the last benchmark section when last_benchmark is null', async () => {
    renderModelManager()
    await screen.findByRole('heading', { name: /set up your model/i })
    expect(screen.queryByLabelText(/last benchmark result/i)).not.toBeInTheDocument()
  })
})

// ── Error state ───────────────────────────────────────────────────────────────

describe('ModelManager — load error state', () => {
  it('shows an error alert when getModels fails', async () => {
    mockApi.getModels.mockRejectedValue(new Error('network error'))
    renderModelManager()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  it('shows the error message text', async () => {
    mockApi.getModels.mockRejectedValue(new Error('connection refused'))
    renderModelManager()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/connection refused/i),
    )
  })

  it('suggests setup docs and the demo when the runtime is unavailable', async () => {
    mockApi.getModels.mockRejectedValue(new Error('runtime unavailable'))
    renderModelManager()
    const link = await screen.findByRole('link', { name: /setup docs/i })
    expect(link).toHaveAttribute('href', expect.stringContaining('/wiki'))
    expect(screen.getByText(/text-only demo works without one/i)).toBeInTheDocument()
  })
})
