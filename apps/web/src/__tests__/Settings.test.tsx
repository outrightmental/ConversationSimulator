// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { SessionCreateRequest } from '@convsim/shared'
import Settings from '../screens/Settings'

vi.mock('../api/client', () => ({
  api: {
    getDataFolder: vi.fn(),
    clearLocalData: vi.fn(),
    listSessions: vi.fn(),
    deleteSession: vi.fn(),
    exportSession: vi.fn(),
    getModels: vi.fn(),
    getRuntimeSettings: vi.fn(),
    useModel: vi.fn(),
    updateRuntimeSettings: vi.fn(),
    resetRuntimeSettings: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const STUB_MODELS = {
  registry: [],
  installed: [],
  ollama_models: [],
  active: { runtime_id: 'llama_cpp', model_id: null },
  runtime_health: {
    runtime_id: 'llama_cpp',
    runtime_name: 'llama.cpp',
    status: 'unavailable' as const,
    model_id: null,
    latency_ms: null,
    message: 'No model configured',
    checked_at: '2026-01-01T00:00:00.000Z',
  },
  total: 0,
  last_benchmark: null,
}

const STUB_RUNTIME_SETTINGS = {
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
}

const SESSION_A = {
  session_id: 'sess-aaa',
  scenario_id: 'behavioral_interview',
  state: 'Ended' as const,
  created_at: '2026-01-01T00:00:00.000Z',
  setup: {} as unknown as SessionCreateRequest,
}

const SESSION_B = {
  session_id: 'sess-bbb',
  scenario_id: 'sales_call',
  state: 'NotStarted' as const,
  created_at: '2026-01-02T00:00:00.000Z',
  setup: {} as unknown as SessionCreateRequest,
}

async function renderSettings() {
  render(<Settings />)
  // Wait for all mount effects to fire and flush state updates.
  await waitFor(() => {
    expect(mockApi.getDataFolder).toHaveBeenCalled()
    expect(mockApi.listSessions).toHaveBeenCalled()
    expect(mockApi.getModels).toHaveBeenCalled()
    expect(mockApi.getRuntimeSettings).toHaveBeenCalled()
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.getDataFolder.mockResolvedValue({ path: '/home/user/.convsim/db' })
  mockApi.listSessions.mockResolvedValue({ sessions: [] })
  mockApi.getModels.mockResolvedValue(STUB_MODELS)
  mockApi.getRuntimeSettings.mockResolvedValue(STUB_RUNTIME_SETTINGS)
  mockApi.useModel.mockResolvedValue({ runtime_id: 'llama_cpp', model_id: null, runtime_name: 'llama.cpp', status: 'unavailable', message: null })
  mockApi.updateRuntimeSettings.mockResolvedValue(STUB_RUNTIME_SETTINGS)
  mockApi.resetRuntimeSettings.mockResolvedValue(STUB_RUNTIME_SETTINGS)
})

// ---------------------------------------------------------------------------
// Privacy notice
// ---------------------------------------------------------------------------

describe('privacy notice', () => {
  it('states conversations are not sent to servers', async () => {
    await renderSettings()
    expect(
      screen.getByText(/conversations are processed entirely on your device/i),
    ).toBeInTheDocument()
  })

  it('states no conversation data is sent to external servers', async () => {
    await renderSettings()
    expect(
      screen.getByText(/no conversation data is ever sent to external servers/i),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Transcript toggle
// ---------------------------------------------------------------------------

describe('transcript saving toggle', () => {
  it('shows the save transcripts checkbox', async () => {
    await renderSettings()
    expect(
      screen.getByRole('checkbox', { name: /save transcripts locally/i }),
    ).toBeInTheDocument()
  })

  it('transcript saving is enabled by default', async () => {
    await renderSettings()
    const checkbox = screen.getByRole('checkbox', { name: /save transcripts locally/i })
    expect(checkbox).toBeChecked()
  })

  it('shows local-only note when transcript saving is on', async () => {
    await renderSettings()
    expect(screen.getByText(/saved to your local data folder only/i)).toBeInTheDocument()
  })

  it('shows not-saved note when transcript saving is toggled off', async () => {
    await renderSettings()
    const checkbox = screen.getByRole('checkbox', { name: /save transcripts locally/i })
    fireEvent.click(checkbox)
    expect(checkbox).not.toBeChecked()
    await waitFor(() => expect(screen.getByText(/not saved/i)).toBeInTheDocument())
  })

  it('can be toggled back on after being turned off', async () => {
    await renderSettings()
    const checkbox = screen.getByRole('checkbox', { name: /save transcripts locally/i })
    fireEvent.click(checkbox)
    fireEvent.click(checkbox)
    expect(checkbox).toBeChecked()
  })
})

// ---------------------------------------------------------------------------
// TTS cache toggle
// ---------------------------------------------------------------------------

describe('TTS cache toggle', () => {
  it('shows the cache TTS audio checkbox', async () => {
    await renderSettings()
    expect(
      screen.getByRole('checkbox', { name: /cache tts audio locally/i }),
    ).toBeInTheDocument()
  })

  it('TTS cache is enabled by default', async () => {
    await renderSettings()
    expect(screen.getByRole('checkbox', { name: /cache tts audio locally/i })).toBeChecked()
  })
})

// ---------------------------------------------------------------------------
// Data folder
// ---------------------------------------------------------------------------

describe('data folder', () => {
  it('displays the data folder path returned by the API', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('data-folder-path')).toHaveTextContent('/home/user/.convsim/db'),
    )
  })

  it('shows an error message when the API fails', async () => {
    mockApi.getDataFolder.mockRejectedValue(new Error('network error'))
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByText(/could not retrieve data folder path/i)).toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Clear local data — two-step confirmation
// ---------------------------------------------------------------------------

describe('clear local data', () => {
  it('shows the clear all local data button', async () => {
    await renderSettings()
    expect(
      screen.getByRole('button', { name: /clear all local data/i }),
    ).toBeInTheDocument()
  })

  it('shows a confirmation warning on first click', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/permanently delete all sessions/i),
    )
  })

  it('shows the confirm button after the first click', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /confirm.*delete everything/i }),
      ).toBeInTheDocument(),
    )
  })

  it('shows a cancel button during confirmation', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument(),
    )
  })

  it('cancel dismisses the confirmation without clearing', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /cancel/i }))
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(mockApi.clearLocalData).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('calls clearLocalData API on the second (confirm) click', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 3 })
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() => expect(mockApi.clearLocalData).toHaveBeenCalledOnce())
  })

  it('shows success message with deleted count after clear', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 3 })
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() =>
      expect(screen.getByText(/3 sessions deleted/i)).toBeInTheDocument(),
    )
  })

  it('shows singular "1 session deleted" when exactly one session is removed', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 1 })
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() =>
      expect(screen.getByText(/1 session deleted/i)).toBeInTheDocument(),
    )
  })

  it('shows an error when the clear API call fails', async () => {
    mockApi.clearLocalData.mockRejectedValue(new Error('disk full'))
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/disk full/i),
    )
  })

  it('clicking clear again after success re-enters the confirmation flow', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 1 })
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() => screen.getByText(/1 session deleted/i))

    // Second click should restart the two-step flow, not be a no-op
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm.*delete everything/i })).toBeInTheDocument(),
    )
  })

  it('clicking clear again after an error re-enters the confirmation flow', async () => {
    mockApi.clearLocalData.mockRejectedValue(new Error('disk full'))
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() => screen.getByRole('alert'))

    // Second click should restart the two-step flow, not be a no-op
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm.*delete everything/i })).toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Your sessions
// ---------------------------------------------------------------------------

describe('your sessions', () => {
  it('shows "No sessions yet." when the list is empty', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [] })
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('no-sessions')).toBeInTheDocument(),
    )
  })

  it('renders a row for each session', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A, SESSION_B] })
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /export session sess-aaa/i })).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /export session sess-bbb/i })).toBeInTheDocument()
  })

  it('shows an error message when listSessions fails', async () => {
    mockApi.listSessions.mockRejectedValue(new Error('network'))
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByText(/could not load sessions/i)).toBeInTheDocument(),
    )
  })

  it('clears the sessions error when a subsequent load succeeds', async () => {
    mockApi.listSessions
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ sessions: [SESSION_A] })
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 1 })
    await renderSettings()
    await waitFor(() => expect(screen.getByText(/could not load sessions/i)).toBeInTheDocument())

    // Trigger a reload via clear-all (success path calls loadSessions internally)
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))

    await waitFor(() =>
      expect(screen.queryByText(/could not load sessions/i)).not.toBeInTheDocument(),
    )
  })

  it('clicking Delete shows a confirm button', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A] })
    await renderSettings()
    await waitFor(() => screen.getByRole('button', { name: /delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /delete session sess-aaa/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm delete session sess-aaa/i })).toBeInTheDocument(),
    )
  })

  it('clicking Cancel after Delete dismisses without calling API', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A] })
    await renderSettings()
    await waitFor(() => screen.getByRole('button', { name: /delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /delete session sess-aaa/i }))
    await waitFor(() => screen.getByRole('button', { name: /cancel delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /cancel delete session sess-aaa/i }))
    expect(mockApi.deleteSession).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /confirm delete session sess-aaa/i })).not.toBeInTheDocument()
  })

  it('clicking Confirm delete calls deleteSession and removes the row', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A, SESSION_B] })
    mockApi.deleteSession.mockResolvedValue(undefined)
    await renderSettings()
    await waitFor(() => screen.getByRole('button', { name: /delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /delete session sess-aaa/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm delete session sess-aaa/i }))
    await waitFor(() => expect(mockApi.deleteSession).toHaveBeenCalledWith('sess-aaa'))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /delete session sess-aaa/i })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /delete session sess-bbb/i })).toBeInTheDocument()
  })

  it('clicking Export calls exportSession', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A] })
    mockApi.exportSession.mockResolvedValue({ session: { ...SESSION_A, ending_type: null, state_vars: {}, turn_count: 0 }, events: [] })
    // Stub URL.createObjectURL/revokeObjectURL which jsdom does not implement.
    const origURL = globalThis.URL
    Object.defineProperty(globalThis, 'URL', {
      value: Object.assign(Object.create(origURL), {
        createObjectURL: vi.fn().mockReturnValue('blob:mock'),
        revokeObjectURL: vi.fn(),
      }),
      writable: true,
      configurable: true,
    })
    await renderSettings()
    await waitFor(() => screen.getByRole('button', { name: /export session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /export session sess-aaa/i }))
    await waitFor(() => expect(mockApi.exportSession).toHaveBeenCalledWith('sess-aaa'))
    Object.defineProperty(globalThis, 'URL', { value: origURL, writable: true, configurable: true })
  })

  it('shows an error when deleteSession API fails', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A] })
    mockApi.deleteSession.mockRejectedValue(new Error('network error'))
    await renderSettings()
    await waitFor(() => screen.getByRole('button', { name: /delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /delete session sess-aaa/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm delete session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm delete session sess-aaa/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/network error/i),
    )
    // Session row should still be present after a failed delete
    expect(screen.getByRole('button', { name: /delete session sess-aaa/i })).toBeInTheDocument()
  })

  it('shows an error when exportSession API fails', async () => {
    mockApi.listSessions.mockResolvedValue({ sessions: [SESSION_A] })
    mockApi.exportSession.mockRejectedValue(new Error('export failed'))
    await renderSettings()
    await waitFor(() => screen.getByRole('button', { name: /export session sess-aaa/i }))
    fireEvent.click(screen.getByRole('button', { name: /export session sess-aaa/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/export failed/i),
    )
  })
})

// ---------------------------------------------------------------------------
// Advanced — raw audio saving
// ---------------------------------------------------------------------------

describe('advanced: raw audio saving', () => {
  it('advanced section is hidden by default', async () => {
    await renderSettings()
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalled())
    expect(
      screen.queryByRole('checkbox', { name: /save raw audio/i }),
    ).not.toBeInTheDocument()
  })

  it('advanced section appears after clicking show advanced', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: /save raw audio recordings/i }),
      ).toBeInTheDocument(),
    )
  })

  it('raw audio saving is off by default', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    expect(screen.getByRole('checkbox', { name: /save raw audio recordings/i })).not.toBeChecked()
  })

  it('shows a warning when raw audio saving is enabled', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    await waitFor(() =>
      expect(screen.getByText(/raw audio saving is on/i)).toBeInTheDocument(),
    )
  })

  it('advanced section collapses when hide advanced is clicked', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    fireEvent.click(screen.getByRole('button', { name: /hide advanced/i }))
    expect(
      screen.queryByRole('checkbox', { name: /save raw audio recordings/i }),
    ).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Advanced — developer debug mode
// ---------------------------------------------------------------------------

describe('advanced: developer debug mode', () => {
  afterEach(() => {
    localStorage.removeItem('convsim.devMode')
  })

  it('developer debug toggle is hidden behind Show advanced', async () => {
    await renderSettings()
    expect(
      screen.queryByRole('checkbox', { name: /developer debug mode/i }),
    ).not.toBeInTheDocument()
  })

  it('developer debug toggle appears after clicking Show advanced', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: /developer debug mode/i }),
      ).toBeInTheDocument(),
    )
  })

  it('developer debug mode is off by default', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /developer debug mode/i }))
    expect(screen.getByRole('checkbox', { name: /developer debug mode/i })).not.toBeChecked()
  })

  it('shows a warning when developer debug mode is enabled', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /developer debug mode/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /developer debug mode/i }))
    await waitFor(() =>
      expect(screen.getByText(/developer debug drawer is active/i)).toBeInTheDocument(),
    )
  })

  it('writes devMode to localStorage when toggled on', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /developer debug mode/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /developer debug mode/i }))
    expect(localStorage.getItem('convsim.devMode')).toBe('true')
  })

  it('initialises as checked when convsim.devMode is set in localStorage', async () => {
    localStorage.setItem('convsim.devMode', 'true')
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /developer debug mode/i }))
    expect(screen.getByRole('checkbox', { name: /developer debug mode/i })).toBeChecked()
  })
})
