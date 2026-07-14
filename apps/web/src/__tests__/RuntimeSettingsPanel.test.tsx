// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RuntimeSettingsPanel from '../components/RuntimeSettingsPanel'
import { UPDATE_DOCS_URL } from '../setup/docsUrls'
import type { ModelsResponse, RuntimeSettingsResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    getModels: vi.fn(),
    getRuntimeSettings: vi.fn(),
    useModel: vi.fn(),
    updateRuntimeSettings: vi.fn(),
    resetRuntimeSettings: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

function makeModels(overrides: Partial<ModelsResponse> = {}): ModelsResponse {
  return {
    registry: [],
    installed: [],
    ollama_models: [],
    active: { runtime_id: 'llama_cpp', model_id: null },
    runtime_health: {
      runtime_id: 'llama_cpp',
      runtime_name: 'llama.cpp',
      status: 'unavailable',
      model_id: null,
      latency_ms: null,
      message: 'No model configured',
      checked_at: '2026-01-01T00:00:00.000Z',
    },
    total: 0,
    last_benchmark: null,
    ...overrides,
  }
}

function makeSettings(overrides: Partial<RuntimeSettingsResponse> = {}): RuntimeSettingsResponse {
  return {
    settings: {
      context_length: null,
      gpu_layers: null,
      threads: null,
      temperature: null,
      top_p: null,
      repeat_penalty: null,
    },
    recommended: {
      context_length: null,
      gpu_layers: null,
      threads: null,
      temperature: null,
      top_p: null,
      repeat_penalty: null,
    },
    requires_restart: false,
    ...overrides,
  }
}

async function renderPanel() {
  render(<RuntimeSettingsPanel />)
  await waitFor(() => {
    expect(mockApi.getModels).toHaveBeenCalled()
    expect(mockApi.getRuntimeSettings).toHaveBeenCalled()
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels() })
  mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings() })
  mockApi.useModel.mockResolvedValue({
    ok: true,
    data: {
      runtime_id: 'llama_cpp',
      model_id: null,
      runtime_name: 'llama.cpp',
      status: 'unavailable',
      message: null,
    },
  })
  mockApi.updateRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings() })
  mockApi.resetRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings() })
})

// ── Loading and error states ──────────────────────────────────────────────────

describe('RuntimeSettingsPanel — loading', () => {
  it('shows loading state while data is being fetched', () => {
    mockApi.getModels.mockReturnValue(new Promise(() => {}))
    render(<RuntimeSettingsPanel />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows error when load fails', async () => {
    mockApi.getModels.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'network error' } })
    await renderPanel()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Connection failed/i),
    )
  })

  // A 404 from /api/runtime/settings means the bundled runtime predates the
  // route (issue #429). The rest of the panel is served by /api/models and must
  // stay usable, with plain-language guidance in place of the advanced section.
  describe('when getRuntimeSettings returns 404', () => {
    beforeEach(() => {
      mockApi.getRuntimeSettings.mockResolvedValue({
        ok: false,
        error: { kind: 'http-error', status: 404, message: 'Not Found' },
      })
    })

    it('does not block the panel behind an error view', async () => {
      await renderPanel()
      await waitFor(() =>
        expect(screen.getByRole('combobox', { name: /provider/i })).toBeInTheDocument(),
      )
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /apply provider and model/i })).toBeInTheDocument()
    })

    it('explains that an update is needed and links to the instructions', async () => {
      await renderPanel()
      const notice = await screen.findByRole('status', {
        name: /runtime advanced settings unavailable/i,
      })
      expect(notice).toHaveTextContent(/not available in this version of ConversationSimulator/i)
      expect(notice).toHaveTextContent(/update to the latest version/i)
      // Deep-links to the "Updates and rollback" section, not the top of the long
      // install page — the user needs the update steps, not a fresh install.
      expect(screen.getByRole('link', { name: /how to update/i })).toHaveAttribute(
        'href',
        UPDATE_DOCS_URL,
      )
      expect(UPDATE_DOCS_URL).toContain('#updates-and-rollback')
    })

    it('hides the advanced settings toggle, which the missing endpoint backs', async () => {
      await renderPanel()
      await screen.findByRole('status', { name: /runtime advanced settings unavailable/i })
      expect(
        screen.queryByRole('button', { name: /show runtime advanced settings/i }),
      ).not.toBeInTheDocument()
    })
  })

  it('still shows a blocking error when getRuntimeSettings fails for a non-404 reason', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({
      ok: false,
      error: { kind: 'http-error', status: 500, message: 'settings store is corrupt' },
    })
    await renderPanel()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/settings store is corrupt/i),
    )
  })
})

// ── Basic settings — provider and model ──────────────────────────────────────

describe('RuntimeSettingsPanel — basic settings', () => {
  it('shows a provider selector', async () => {
    await renderPanel()
    expect(screen.getByRole('combobox', { name: /provider/i })).toBeInTheDocument()
  })

  it('shows the active provider selected by default', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels({ active: { runtime_id: 'ollama', model_id: 'llama3:latest' } }) })
    await renderPanel()
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: /provider/i })).toHaveValue('ollama'),
    )
  })

  it('shows llama.cpp, Ollama, and Fake options in the provider dropdown', async () => {
    await renderPanel()
    const select = screen.getByRole('combobox', { name: /provider/i })
    expect(select).toContainHTML('llama.cpp')
    expect(select).toContainHTML('Ollama')
    expect(select).toContainHTML('Fake')
  })

  it('shows a model selector when provider is not fake', async () => {
    await renderPanel()
    await waitFor(() => expect(screen.getByRole('combobox', { name: /model/i })).toBeInTheDocument())
  })

  it('hides the model selector when fake provider is selected', async () => {
    await renderPanel()
    fireEvent.change(screen.getByRole('combobox', { name: /provider/i }), { target: { value: 'fake' } })
    await waitFor(() =>
      expect(screen.queryByRole('combobox', { name: /model/i })).not.toBeInTheDocument(),
    )
  })

  it('populates model dropdown with installed llama.cpp models', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels({
      installed: [{
        id: 1,
        registry_id: 'qwen3-4b-instruct-q4_k_m',
        filename: 'qwen3-4b.gguf',
        file_path: '/home/user/.convsim/models/llm/qwen3-4b.gguf',
        size_bytes: 2_800_000_000,
        install_status: 'ready',
        progress_bytes: null,
        error_message: null,
        verified_sha256: null,
        installed_at: '2026-01-01T00:00:00.000Z',
      }],
    }) })
    await renderPanel()
    const modelSelect = await screen.findByRole('combobox', { name: /model/i })
    expect(modelSelect).toContainHTML('qwen3-4b.gguf')
  })

  it('populates model dropdown with Ollama models when Ollama is selected', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels({
      ollama_models: [{ id: 'llama3:latest', name: 'llama3:latest', size_category: 'medium' }],
    }) })
    await renderPanel()
    fireEvent.change(screen.getByRole('combobox', { name: /provider/i }), { target: { value: 'ollama' } })
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: /model/i })).toContainHTML('llama3:latest'),
    )
  })

  it('shows an Apply button for basic settings', async () => {
    await renderPanel()
    expect(screen.getByRole('button', { name: /apply provider and model/i })).toBeInTheDocument()
  })

  it('calls useModel when Apply is clicked', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /apply provider and model/i }))
    await waitFor(() =>
      expect(mockApi.useModel).toHaveBeenCalledWith({ runtime_id: 'llama_cpp', model_id: null }),
    )
  })

  it('shows success message after provider/model is applied', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /apply provider and model/i }))
    await waitFor(() =>
      expect(screen.getByText(/provider and model updated/i)).toBeInTheDocument(),
    )
  })

  it('shows error when useModel fails', async () => {
    mockApi.useModel.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'runtime not available' } })
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /apply provider and model/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Connection failed/i),
    )
  })
})

// ── Health status display ─────────────────────────────────────────────────────

describe('RuntimeSettingsPanel — health display', () => {
  it('shows the runtime health status', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels({
      runtime_health: {
        runtime_id: 'ollama',
        runtime_name: 'Ollama',
        status: 'ready',
        model_id: 'llama3:latest',
        latency_ms: 150,
        message: null,
        checked_at: '2026-01-01T00:00:00.000Z',
      },
    }) })
    await renderPanel()
    await waitFor(() =>
      expect(screen.getByLabelText(/runtime health/i)).toHaveTextContent(/Ollama/),
    )
  })

  it('shows the model ID in the health status', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels({
      active: { runtime_id: 'ollama', model_id: 'llama3:latest' },
      runtime_health: {
        runtime_id: 'ollama',
        runtime_name: 'Ollama',
        status: 'ready',
        model_id: 'llama3:latest',
        latency_ms: null,
        message: null,
        checked_at: '2026-01-01T00:00:00.000Z',
      },
    }) })
    await renderPanel()
    await waitFor(() =>
      expect(screen.getByLabelText(/runtime health/i)).toHaveTextContent(/llama3:latest/),
    )
  })

  it('shows the last benchmark result when available', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: makeModels({
      last_benchmark: {
        model_id: 'llama3:latest',
        runtime_id: 'ollama',
        tokens_per_sec: 18.7,
        context_length: 4096,
        warnings: [],
        output_tokens: 5,
        benchmarked_at: '2026-01-01T00:00:00.000Z',
      },
    }) })
    await renderPanel()
    await waitFor(() =>
      expect(screen.getByLabelText(/last benchmark result/i)).toHaveTextContent(/18.7/),
    )
  })

  it('does not show the benchmark section when last_benchmark is null', async () => {
    await renderPanel()
    await waitFor(() => expect(mockApi.getModels).toHaveBeenCalled())
    expect(screen.queryByLabelText(/last benchmark result/i)).not.toBeInTheDocument()
  })
})

// ── Advanced settings — hidden by default ────────────────────────────────────

describe('RuntimeSettingsPanel — advanced settings (hidden by default)', () => {
  it('advanced runtime settings are hidden by default', async () => {
    await renderPanel()
    await waitFor(() => expect(mockApi.getModels).toHaveBeenCalled())
    expect(screen.queryByRole('spinbutton', { name: /context length/i })).not.toBeInTheDocument()
  })

  it('shows a "Show advanced runtime settings" button', async () => {
    await renderPanel()
    expect(
      screen.getByRole('button', { name: /show runtime advanced settings/i }),
    ).toBeInTheDocument()
  })

  it('reveals advanced inputs after clicking show advanced', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /show runtime advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('spinbutton', { name: /context length/i })).toBeInTheDocument(),
    )
  })

  it('collapses advanced section when hide advanced is clicked', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /show runtime advanced settings/i }))
    await waitFor(() => screen.getByRole('spinbutton', { name: /context length/i }))
    fireEvent.click(screen.getByRole('button', { name: /hide runtime advanced settings/i }))
    expect(
      screen.queryByRole('spinbutton', { name: /context length/i }),
    ).not.toBeInTheDocument()
  })
})

// ── Advanced settings — inputs and validation ─────────────────────────────────

describe('RuntimeSettingsPanel — advanced settings inputs', () => {
  async function openAdvanced() {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /show runtime advanced settings/i }))
    await waitFor(() => screen.getByRole('spinbutton', { name: /context length/i }))
  }

  it('shows context length, GPU layers, threads, temperature, top-p, and repeat penalty inputs', async () => {
    await openAdvanced()
    expect(screen.getByRole('spinbutton', { name: /context length/i })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /gpu layers/i })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /cpu threads/i })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /temperature/i })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /top-p/i })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /repeat penalty/i })).toBeInTheDocument()
  })

  it('pre-fills inputs from saved settings', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings({
      settings: {
        context_length: 4096,
        gpu_layers: -1,
        threads: 8,
        temperature: 0.7,
        top_p: 0.9,
        repeat_penalty: 1.1,
      },
    }) })
    await openAdvanced()
    expect(screen.getByRole('spinbutton', { name: /context length/i })).toHaveValue(4096)
    expect(screen.getByRole('spinbutton', { name: /gpu layers/i })).toHaveValue(-1)
    expect(screen.getByRole('spinbutton', { name: /cpu threads/i })).toHaveValue(8)
  })

  it('shows Apply and Reset to defaults buttons in advanced section', async () => {
    await openAdvanced()
    expect(screen.getByRole('button', { name: /apply advanced settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reset to defaults/i })).toBeInTheDocument()
  })

  it('links to troubleshooting docs in the advanced section', async () => {
    await openAdvanced()
    expect(screen.getByRole('link', { name: /troubleshooting docs/i })).toBeInTheDocument()
  })
})

// ── Client-side validation ────────────────────────────────────────────────────

describe('RuntimeSettingsPanel — client-side validation', () => {
  async function openAdvanced() {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /show runtime advanced settings/i }))
    await waitFor(() => screen.getByRole('spinbutton', { name: /context length/i }))
  }

  it('shows error for context length below 512', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /context length/i }), {
      target: { value: '256' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/512/),
    )
    expect(mockApi.updateRuntimeSettings).not.toHaveBeenCalled()
  })

  it('shows error for context length above 131072', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /context length/i }), {
      target: { value: '200000' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/131072/),
    )
  })

  it('shows error for GPU layers below -1', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /gpu layers/i }), {
      target: { value: '-5' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/-1/),
    )
  })

  it('shows error for temperature above 2.0', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /temperature/i }), {
      target: { value: '3.0' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/2\.0/),
    )
  })

  it('shows error for top-p above 1.0', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /top-p/i }), {
      target: { value: '1.5' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/1\.0/),
    )
  })

  it('shows error for repeat penalty below 1.0', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /repeat penalty/i }), {
      target: { value: '0.5' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/1\.0/),
    )
  })

  it('calls updateRuntimeSettings when all fields are valid', async () => {
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /context length/i }), {
      target: { value: '8192' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(mockApi.updateRuntimeSettings).toHaveBeenCalledWith(
        expect.objectContaining({ context_length: 8192 }),
      ),
    )
  })

  it('sends null for empty fields', async () => {
    await openAdvanced()
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(mockApi.updateRuntimeSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          context_length: null,
          gpu_layers: null,
          temperature: null,
        }),
      ),
    )
  })
})

// ── Restart required warning ──────────────────────────────────────────────────

describe('RuntimeSettingsPanel — restart required warning', () => {
  async function openAdvanced() {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /show runtime advanced settings/i }))
    await waitFor(() => screen.getByRole('spinbutton', { name: /context length/i }))
  }

  it('shows restart warning after applying context length change', async () => {
    mockApi.updateRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings({ requires_restart: true }) })
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /context length/i }), {
      target: { value: '4096' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('status', { name: /restart required/i })).toBeInTheDocument(),
    )
  })

  it('does not show restart warning when non-restart fields change', async () => {
    mockApi.updateRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings({ requires_restart: false }) })
    await openAdvanced()
    fireEvent.change(screen.getByRole('spinbutton', { name: /temperature/i }), {
      target: { value: '0.7' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() => expect(mockApi.updateRuntimeSettings).toHaveBeenCalled())
    expect(screen.queryByRole('status', { name: /restart required/i })).not.toBeInTheDocument()
  })

  it('shows restart warning after reset', async () => {
    mockApi.resetRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings({ requires_restart: true }) })
    await openAdvanced()
    fireEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))
    await waitFor(() =>
      expect(screen.getByRole('status', { name: /restart required/i })).toBeInTheDocument(),
    )
  })
})

// ── Apply advanced and reset ──────────────────────────────────────────────────

describe('RuntimeSettingsPanel — apply advanced and reset', () => {
  async function openAdvanced() {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /show runtime advanced settings/i }))
    await waitFor(() => screen.getByRole('spinbutton', { name: /context length/i }))
  }

  it('shows error when updateRuntimeSettings API fails', async () => {
    mockApi.updateRuntimeSettings.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'server error' } })
    await openAdvanced()
    fireEvent.click(screen.getByRole('button', { name: /apply advanced settings/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Connection failed/i),
    )
  })

  it('calls resetRuntimeSettings when Reset to defaults is clicked', async () => {
    await openAdvanced()
    fireEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))
    await waitFor(() => expect(mockApi.resetRuntimeSettings).toHaveBeenCalledOnce())
  })

  it('clears form fields after reset', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: makeSettings({
      settings: { context_length: 4096, gpu_layers: null, threads: null, temperature: null, top_p: null, repeat_penalty: null },
    }) })
    await openAdvanced()
    await waitFor(() => expect(screen.getByRole('spinbutton', { name: /context length/i })).toHaveValue(4096))
    fireEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))
    await waitFor(() =>
      expect(screen.getByRole('spinbutton', { name: /context length/i })).toHaveValue(null),
    )
  })

  it('shows error when resetRuntimeSettings API fails', async () => {
    mockApi.resetRuntimeSettings.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'reset failed' } })
    await openAdvanced()
    fireEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Connection failed/i),
    )
  })
})
