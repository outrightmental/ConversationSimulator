// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import VoiceSettingsPanel from '../components/VoiceSettingsPanel'

vi.mock('../api/client', () => ({
  api: {
    listVoices: vi.fn(),
    getTtsCacheSize: vi.fn(),
    clearTtsCache: vi.fn(),
    health: vi.fn(),
    vadHealth: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const STUB_VOICES = {
  voices: [
    { voice_id: 'af_heart', display_name: 'Heart (US female)', engine: 'kokoro', gender: 'female' as const, locale: 'en-US' },
    { voice_id: 'am_adam', display_name: 'Adam (US male)', engine: 'kokoro', gender: 'male' as const, locale: 'en-US' },
    { voice_id: 'bf_emma', display_name: 'Emma (UK female)', engine: 'kokoro', gender: 'female' as const, locale: 'en-GB' },
  ],
}

const STUB_HEALTH_READY = {
  status: 'ok' as const,
  version: '0.1.0',
  runtime: {
    llm_ready: true,
    llm_model_name: 'Qwen3 8B',
    stt_ready: true,
    tts_ready: true,
    tts_voice_name: 'af_heart',
    network_required: false,
  },
}

const STUB_HEALTH_NO_VOICE = {
  status: 'degraded' as const,
  version: '0.1.0',
  runtime: {
    llm_ready: true,
    llm_model_name: 'Qwen3 8B',
    stt_ready: false,
    tts_ready: false,
    tts_voice_name: null,
    network_required: false,
  },
}

const STUB_VAD_READY = {
  worker_id: 'silero',
  worker_name: 'Silero VAD',
  status: 'ready' as const,
  model_path: '/models/silero.onnx',
  message: null,
  checked_at: '2026-01-01T00:00:00.000Z',
}

const STUB_VAD_UNAVAILABLE = {
  worker_id: 'silero',
  worker_name: 'Silero VAD',
  status: 'unavailable' as const,
  model_path: null,
  message: 'VAD not loaded',
  checked_at: '2026-01-01T00:00:00.000Z',
}

const STUB_CACHE_SIZE = { files: 4, size_bytes: 8192 }
const STUB_CACHE_EMPTY = { files: 0, size_bytes: 0 }

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  localStorage.clear()

  // Default: all ready
  mockApi.listVoices.mockResolvedValue(STUB_VOICES)
  mockApi.getTtsCacheSize.mockResolvedValue(STUB_CACHE_SIZE)
  mockApi.clearTtsCache.mockResolvedValue({ deleted_files: 4 })
  mockApi.health.mockResolvedValue(STUB_HEALTH_READY)
  mockApi.vadHealth.mockResolvedValue(STUB_VAD_READY)

  // Stub navigator.permissions so tests don't depend on browser
  Object.defineProperty(navigator, 'permissions', {
    value: {
      query: vi.fn().mockResolvedValue({ state: 'granted', addEventListener: vi.fn() }),
    },
    writable: true,
    configurable: true,
  })
})

afterEach(() => {
  localStorage.clear()
})

// ---------------------------------------------------------------------------
// Voice readiness cards
// ---------------------------------------------------------------------------

describe('voice readiness cards', () => {
  it('shows the voice readiness section', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('voice-readiness')).toBeInTheDocument())
  })

  it('shows STT as ready when health reports stt_ready', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-stt')).toBeInTheDocument())
    expect(screen.getByTestId('readiness-stt')).toHaveTextContent('model loaded')
  })

  it('shows TTS as ready when health reports tts_ready', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-tts')).toHaveTextContent('model loaded'))
  })

  it('shows VAD as ready when vadHealth returns ready', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-vad')).toBeInTheDocument())
    expect(screen.getByTestId('readiness-vad')).toHaveTextContent('ready')
  })

  it('shows Microphone as ready when permission is granted', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-mic')).toBeInTheDocument())
    expect(screen.getByTestId('readiness-mic')).toHaveTextContent('permission granted')
  })

  it('shows STT as unavailable when health reports stt_ready=false', async () => {
    mockApi.health.mockResolvedValue(STUB_HEALTH_NO_VOICE)
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-stt')).toBeInTheDocument())
    expect(screen.getByTestId('readiness-stt')).toHaveTextContent('no model loaded')
  })

  it('shows TTS as unavailable when health reports tts_ready=false', async () => {
    mockApi.health.mockResolvedValue(STUB_HEALTH_NO_VOICE)
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-tts')).toBeInTheDocument())
    expect(screen.getByTestId('readiness-tts')).toHaveTextContent('no model loaded')
    // Should show setup/fallback guidance
    expect(screen.getByText(/Install a text-to-speech model/i)).toBeInTheDocument()
  })

  it('shows VAD as unavailable when vadHealth returns unavailable', async () => {
    mockApi.vadHealth.mockResolvedValue(STUB_VAD_UNAVAILABLE)
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-vad')).toHaveTextContent('not available'))
  })

  it('shows mic denied guidance when permission is denied', async () => {
    Object.defineProperty(navigator, 'permissions', {
      value: {
        query: vi.fn().mockResolvedValue({ state: 'denied', addEventListener: vi.fn() }),
      },
      writable: true,
      configurable: true,
    })
    render(<VoiceSettingsPanel />)
    await waitFor(() => expect(screen.getByTestId('readiness-mic')).toHaveTextContent('permission denied'))
    expect(screen.getByText(/Allow microphone access/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Voice selection
// ---------------------------------------------------------------------------

describe('voice selection', () => {
  it('shows the voice selection dropdown', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: /default npc voice/i })).toBeInTheDocument(),
    )
  })

  it('populates dropdown with voices from the API', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('combobox', { name: /default npc voice/i }))
    expect(screen.getByRole('option', { name: /Heart \(US female\)/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Adam \(US male\)/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Emma \(UK female\)/i })).toBeInTheDocument()
  })

  it('defaults to the first voice when no preference is stored', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('combobox', { name: /default npc voice/i }))
    const select = screen.getByRole('combobox', { name: /default npc voice/i }) as HTMLSelectElement
    expect(select.value).toBe('af_heart')
  })

  it('restores stored preference when a valid voice_id is in localStorage', async () => {
    localStorage.setItem('convsim.voice.preferredVoiceId', 'am_adam')
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('combobox', { name: /default npc voice/i }))
    const select = screen.getByRole('combobox', { name: /default npc voice/i }) as HTMLSelectElement
    expect(select.value).toBe('am_adam')
  })

  it('updates localStorage when the user changes the voice selection', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('combobox', { name: /default npc voice/i }))
    fireEvent.change(screen.getByRole('combobox', { name: /default npc voice/i }), {
      target: { value: 'bf_emma' },
    })
    expect(localStorage.getItem('convsim.voice.preferredVoiceId')).toBe('bf_emma')
  })

  it('shows an error when voice list fails to load', async () => {
    mockApi.listVoices.mockRejectedValue(new Error('network error'))
    render(<VoiceSettingsPanel />)
    await waitFor(() =>
      expect(screen.getByText(/could not load voice list/i)).toBeInTheDocument(),
    )
  })

  it('shows a note that voice selection is limited to approved voices', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('combobox', { name: /default npc voice/i }))
    expect(screen.getByText(/approved built-in voices/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// TTS cache display and clear
// ---------------------------------------------------------------------------

describe('TTS cache', () => {
  it('displays the current cache size', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() =>
      expect(screen.getByTestId('cache-size-label')).toHaveTextContent('4 files · 8.0 KB'),
    )
  })

  it('shows "Empty" when cache has zero files', async () => {
    mockApi.getTtsCacheSize.mockResolvedValue(STUB_CACHE_EMPTY)
    render(<VoiceSettingsPanel />)
    await waitFor(() =>
      expect(screen.getByTestId('cache-size-label')).toHaveTextContent('Empty'),
    )
  })

  it('disables clear button when cache is empty', async () => {
    mockApi.getTtsCacheSize.mockResolvedValue(STUB_CACHE_EMPTY)
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /clear tts cache/i }))
    expect(screen.getByRole('button', { name: /clear tts cache/i })).toBeDisabled()
  })

  it('clear button is enabled when cache has files', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /clear tts cache/i }))
    expect(screen.getByRole('button', { name: /clear tts cache/i })).not.toBeDisabled()
  })

  it('calls clearTtsCache API when clear button is clicked', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /clear tts cache/i }))
    fireEvent.click(screen.getByRole('button', { name: /clear tts cache/i }))
    await waitFor(() => expect(mockApi.clearTtsCache).toHaveBeenCalledOnce())
  })

  it('updates cache size display to empty after clearing', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /clear tts cache/i }))
    fireEvent.click(screen.getByRole('button', { name: /clear tts cache/i }))
    await waitFor(() =>
      expect(screen.getByTestId('cache-size-label')).toHaveTextContent('Empty'),
    )
  })

  it('shows success message after clearing', async () => {
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /clear tts cache/i }))
    fireEvent.click(screen.getByRole('button', { name: /clear tts cache/i }))
    await waitFor(() =>
      expect(screen.getByText(/cache cleared/i)).toBeInTheDocument(),
    )
  })

  it('shows error message when clear fails', async () => {
    mockApi.clearTtsCache.mockRejectedValue(new Error('disk full'))
    render(<VoiceSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /clear tts cache/i }))
    fireEvent.click(screen.getByRole('button', { name: /clear tts cache/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/disk full/i),
    )
  })
})
