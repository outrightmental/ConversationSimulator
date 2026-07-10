// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { SessionCreateRequest } from '@convsim/shared'
import type { ImportPackResponse } from '../api/client'
import Settings from '../screens/Settings'

vi.mock('../api/client', () => ({
  api: {
    getDataFolder: vi.fn(),
    getFolders: vi.fn(),
    clearLocalData: vi.fn(),
    listSessions: vi.fn(),
    deleteSession: vi.fn(),
    exportSession: vi.fn(),
    getModels: vi.fn(),
    getRuntimeSettings: vi.fn(),
    useModel: vi.fn(),
    updateRuntimeSettings: vi.fn(),
    resetRuntimeSettings: vi.fn(),
    // VoiceSettingsPanel methods
    listVoices: vi.fn(),
    getTtsCacheSize: vi.fn(),
    clearTtsCache: vi.fn(),
    health: vi.fn(),
    vadHealth: vi.fn(),
    // Pack management
    listPacks: vi.fn(),
    importPack: vi.fn(),
    validatePack: vi.fn(),
    // Diagnostics
    createCrashBundle: vi.fn(),
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

const STUB_FOLDERS = {
  data: '/home/user/.convsim/db',
  logs: '/home/user/.convsim/logs',
  models: '/home/user/.convsim/models/llm',
  packs: '/home/user/.convsim/db/packs',
  exports: '/home/user/.convsim/exports',
  cache: '/home/user/.convsim/cache',
  crash_bundles: '/home/user/.convsim/crashes',
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

const STUB_PACK_A = {
  pack_id: 'pack-alpha',
  name: 'Alpha Scenarios',
  scenario_count: 3,
  pack_root: '/home/user/.convsim/db/packs/pack-alpha',
}

async function renderSettings() {
  render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>,
  )
  // Wait for all mount effects to fire and flush state updates.
  await waitFor(() => {
    expect(mockApi.getFolders).toHaveBeenCalled()
    expect(mockApi.listSessions).toHaveBeenCalled()
    expect(mockApi.listPacks).toHaveBeenCalled()
    expect(mockApi.getModels).toHaveBeenCalled()
    expect(mockApi.getRuntimeSettings).toHaveBeenCalled()
    expect(mockApi.listVoices).toHaveBeenCalled()
  })
}

const STUB_VOICES = {
  voices: [
    { voice_id: 'af_heart', display_name: 'Heart (US female)', engine: 'kokoro', gender: 'female' as const, locale: 'en-US' },
  ],
}

const STUB_HEALTH = {
  status: 'ok' as const,
  version: '0.1.0',
  runtime: { llm_ready: true, llm_model_name: null, stt_ready: false, tts_ready: false, tts_voice_name: null, network_required: false },
}

const STUB_VAD = {
  worker_id: 'silero', worker_name: 'Silero VAD', status: 'unavailable' as const,
  model_path: null, message: null, checked_at: '2026-01-01T00:00:00.000Z',
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.getDataFolder.mockResolvedValue({ path: '/home/user/.convsim/db' })
  mockApi.getFolders.mockResolvedValue(STUB_FOLDERS)
  mockApi.listSessions.mockResolvedValue({ sessions: [] })
  mockApi.listPacks.mockResolvedValue({ packs: [], total: 0 })
  mockApi.importPack.mockResolvedValue({ pack_id: 'pack-alpha', name: 'Alpha Scenarios', version: '1.0.0', dest: '/tmp/pack-alpha' })
  mockApi.validatePack.mockResolvedValue({ pack_id: 'pack-alpha', valid: true, errors: [] })
  mockApi.getModels.mockResolvedValue(STUB_MODELS)
  mockApi.getRuntimeSettings.mockResolvedValue(STUB_RUNTIME_SETTINGS)
  mockApi.useModel.mockResolvedValue({ runtime_id: 'llama_cpp', model_id: null, runtime_name: 'llama.cpp', status: 'unavailable', message: null })
  mockApi.updateRuntimeSettings.mockResolvedValue(STUB_RUNTIME_SETTINGS)
  mockApi.resetRuntimeSettings.mockResolvedValue(STUB_RUNTIME_SETTINGS)
  // VoiceSettingsPanel stubs
  mockApi.listVoices.mockResolvedValue(STUB_VOICES)
  mockApi.getTtsCacheSize.mockResolvedValue({ files: 0, size_bytes: 0 })
  mockApi.clearTtsCache.mockResolvedValue({ deleted_files: 0 })
  mockApi.health.mockResolvedValue(STUB_HEALTH)
  mockApi.vadHealth.mockResolvedValue(STUB_VAD)
  // Stub navigator.permissions so tests don't hang on browser API
  Object.defineProperty(navigator, 'permissions', {
    value: { query: vi.fn().mockResolvedValue({ state: 'granted', addEventListener: vi.fn() }) },
    writable: true, configurable: true,
  })
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
      screen.getByText(/no telemetry is collected/i),
    ).toBeInTheDocument()
  })

  it('states no transcript is uploaded automatically', async () => {
    await renderSettings()
    expect(
      screen.getByText(/no transcript is uploaded automatically/i),
    ).toBeInTheDocument()
  })

  it('states no model or pack is downloaded without explicit action', async () => {
    await renderSettings()
    expect(
      screen.getByText(/no model or pack is downloaded without an explicit action/i),
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
// Model manager link
// ---------------------------------------------------------------------------

describe('model manager link', () => {
  it('shows a link to the model manager', async () => {
    await renderSettings()
    expect(
      screen.getByRole('link', { name: /open model manager/i }),
    ).toBeInTheDocument()
  })

  it('model manager link points to /model-manager', async () => {
    await renderSettings()
    const link = screen.getByRole('link', { name: /open model manager/i })
    expect(link).toHaveAttribute('href', '/model-manager')
  })
})

// ---------------------------------------------------------------------------
// Pack management — import
// ---------------------------------------------------------------------------

describe('pack management: import', () => {
  it('shows the import pack button', async () => {
    await renderSettings()
    expect(
      screen.getByRole('button', { name: /import pack/i }),
    ).toBeInTheDocument()
  })

  it('shows "No packs installed yet." when the list is empty', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('no-packs')).toBeInTheDocument(),
    )
  })

  it('renders a row for each installed pack', async () => {
    mockApi.listPacks.mockResolvedValue({ packs: [STUB_PACK_A], total: 1 })
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByText('Alpha Scenarios')).toBeInTheDocument(),
    )
    expect(screen.getByText('pack-alpha')).toBeInTheDocument()
  })

  it('shows an error when listPacks fails', async () => {
    mockApi.listPacks.mockRejectedValue(new Error('network'))
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByText(/could not load installed packs/i)).toBeInTheDocument(),
    )
  })

  it('shows importing state while uploading', async () => {
    let resolveImport!: (v: ImportPackResponse) => void
    mockApi.importPack.mockReturnValue(new Promise<ImportPackResponse>((r) => { resolveImport = r }))
    await renderSettings()
    const button = screen.getByRole('button', { name: /import pack/i })
    const fileInput = screen.getByTestId('settings-import-file-input')
    const file = new File(['PK'], 'pack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /import pack/i })).toHaveTextContent(/importing/i),
    )
    expect(button).toBeDisabled()
    resolveImport({ pack_id: 'pack-alpha', name: 'Alpha Scenarios', version: '1.0.0', dest: '/tmp/pack-alpha' })
  })

  it('shows success message after a successful import', async () => {
    await renderSettings()
    const fileInput = screen.getByTestId('settings-import-file-input')
    const file = new File(['PK'], 'pack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() =>
      expect(screen.getByTestId('settings-import-success')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('settings-import-success')).toHaveTextContent(/alpha scenarios/i)
  })

  it('shows an error message when import fails', async () => {
    mockApi.importPack.mockRejectedValue(new Error('Invalid pack format'))
    await renderSettings()
    const fileInput = screen.getByTestId('settings-import-file-input')
    const file = new File(['bad'], 'pack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() =>
      expect(screen.getByTestId('settings-import-error')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('settings-import-error')).toHaveTextContent(/invalid pack format/i)
  })

  it('calls importPack with the selected file', async () => {
    await renderSettings()
    const fileInput = screen.getByTestId('settings-import-file-input')
    const file = new File(['PK'], 'mypack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => expect(mockApi.importPack).toHaveBeenCalledWith(file))
  })

  it('reloads the pack list after a successful import', async () => {
    mockApi.importPack.mockResolvedValue({ pack_id: 'pack-alpha', name: 'Alpha Scenarios', version: '1.0.0', dest: '/tmp/pack-alpha' })
    mockApi.listPacks
      .mockResolvedValueOnce({ packs: [], total: 0 })
      .mockResolvedValueOnce({ packs: [STUB_PACK_A], total: 1 })
    await renderSettings()
    const fileInput = screen.getByTestId('settings-import-file-input')
    const file = new File(['PK'], 'pack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() =>
      expect(screen.getByText('Alpha Scenarios')).toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Local folders
// ---------------------------------------------------------------------------

describe('local folders', () => {
  it('displays the data folder path', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('folder-path-data')).toHaveTextContent('/home/user/.convsim/db'),
    )
  })

  it('displays the logs folder path', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('folder-path-logs')).toHaveTextContent('/home/user/.convsim/logs'),
    )
  })

  it('displays the models folder path', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('folder-path-models')).toHaveTextContent('/home/user/.convsim/models/llm'),
    )
  })

  it('displays the packs folder path', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('folder-path-packs')).toHaveTextContent('/home/user/.convsim/db/packs'),
    )
  })

  it('displays the exports folder path', async () => {
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('folder-path-exports')).toHaveTextContent('/home/user/.convsim/exports'),
    )
  })

  it('shows copy buttons for each folder', async () => {
    await renderSettings()
    await waitFor(() => screen.getByTestId('folder-path-data'))
    expect(screen.getByRole('button', { name: /copy data folder path/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy logs folder path/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy models folder path/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy packs folder path/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy exports folder path/i })).toBeInTheDocument()
  })

  it('shows an error message when getFolders fails', async () => {
    mockApi.getFolders.mockRejectedValue(new Error('network error'))
    await renderSettings()
    await waitFor(() =>
      expect(screen.getByText(/could not retrieve folder paths/i)).toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Local folders — desktop "Open" integration (Tauri shell)
// ---------------------------------------------------------------------------

describe('local folders: open in desktop shell', () => {
  const win = window as unknown as { __TAURI__?: unknown }

  afterEach(() => {
    delete win.__TAURI__
  })

  it('does not render Open buttons outside the desktop shell', async () => {
    await renderSettings()
    await waitFor(() => screen.getByTestId('folder-path-data'))
    expect(screen.queryByRole('button', { name: /open data folder/i })).not.toBeInTheDocument()
  })

  it('invokes the shell with the folder path when Open is clicked', async () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    win.__TAURI__ = { core: { invoke } }
    await renderSettings()
    await waitFor(() => screen.getByTestId('folder-path-data'))
    fireEvent.click(screen.getByRole('button', { name: /open logs folder/i }))
    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith('plugin:shell|open', { path: '/home/user/.convsim/logs' }),
    )
  })

  it('shows a fallback message when the shell rejects the path', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('not allowed'))
    win.__TAURI__ = { core: { invoke } }
    await renderSettings()
    await waitFor(() => screen.getByTestId('folder-path-data'))
    fireEvent.click(screen.getByRole('button', { name: /open data folder/i }))
    await waitFor(() =>
      expect(screen.getByTestId('folder-open-error')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('folder-open-error')).toHaveTextContent(/copy the path/i)
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
