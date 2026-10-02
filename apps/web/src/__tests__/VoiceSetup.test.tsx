// SPDX-License-Identifier: Apache-2.0
// Issue #487: Settings used to say "Not installed" and offer nothing. These
// tests pin the behaviour that replaced it — disclosure before download, a
// real download with progress and cancel, and honest guidance for the two
// engines the app will not fetch.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { VoiceInstallJob, VoiceSetupPlan } from '@convsim/shared'
import VoiceSetup from '../screens/VoiceSetup'

vi.mock('../api/client', () => ({
  api: {
    getVoiceSetupPlan: vi.fn(),
    startVoiceInstall: vi.fn(),
    getVoiceInstallStatus: vi.fn(),
    cancelVoiceInstall: vi.fn(),
    startVoiceEngine: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

function makeAsset(overrides: Partial<VoiceSetupPlan['assets'][number]> = {}) {
  return {
    id: 'whisper-base-en',
    capability: 'stt' as const,
    name: 'Whisper base.en',
    description: 'The recommended balance of accuracy and speed.',
    language_note: 'English only',
    recommended: true,
    selected: false,
    size_bytes: 147_964_211,
    license: 'MIT',
    license_url: 'https://opensource.org/licenses/MIT',
    source_url: 'https://huggingface.co/ggerganov/whisper.cpp/resolve/abc/ggml-base.en.bin',
    sha256: 'a'.repeat(64),
    install_path: '/home/p/.convsim/models/stt/ggml-base.en.bin',
    installed: false,
    ...overrides,
  }
}

function makePlan(overrides: Partial<VoiceSetupPlan> = {}): VoiceSetupPlan {
  return {
    capabilities: [
      { id: 'stt', label: 'Speak your turns', description: 'Transcribes what you say.', ready: false, required_engine_ids: ['whisper-cli'], asset_ids: ['whisper-base-en', 'whisper-small-en'] },
      { id: 'tts', label: 'Hear the NPC', description: 'Reads replies aloud.', ready: false, required_engine_ids: ['kokoro-server'], asset_ids: [] },
      { id: 'vad', label: 'Hands-free turn-taking', description: 'Detects when you stop.', ready: false, required_engine_ids: [], asset_ids: ['silero-vad'] },
    ],
    assets: [
      makeAsset(),
      makeAsset({
        id: 'whisper-small-en',
        name: 'Whisper small.en',
        recommended: false,
        size_bytes: 487_614_201,
        install_path: '/home/p/.convsim/models/stt/ggml-small.en.bin',
      }),
      makeAsset({
        id: 'silero-vad',
        capability: 'vad',
        name: 'Silero VAD',
        language_note: '',
        size_bytes: 2_327_524,
        install_path: '/home/p/.convsim/models/vad/silero_vad.onnx',
      }),
    ],
    engines: [
      {
        id: 'whisper-cli',
        capability: 'stt',
        name: 'whisper.cpp',
        why_manual: 'whisper.cpp publishes no checksummed binary for every platform.',
        docs_url: 'https://github.com/ggml-org/whisper.cpp#quick-start',
        command: 'brew install whisper-cpp',
        startable: false,
        installed: false,
        found_at: null,
      },
      {
        id: 'kokoro-server',
        capability: 'tts',
        name: 'Kokoro TTS server',
        why_manual: 'The NPC voice runs in a small local server.',
        docs_url: 'https://github.com/remsky/Kokoro-FastAPI#readme',
        command: 'docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest',
        startable: true,
        installed: false,
        found_at: null,
      },
    ],
    platform: 'darwin',
    kokoro_state: 'stopped',
    onnxruntime_installed: true,
    ffmpeg_installed: true,
    active_job_id: null,
    default_asset_ids: ['whisper-base-en', 'silero-vad'],
    default_download_bytes: 150_291_735,
    ...overrides,
  }
}

function makeJob(overrides: Partial<VoiceInstallJob> = {}): VoiceInstallJob {
  return {
    id: 7,
    status: 'running',
    asset_ids: ['whisper-base-en', 'silero-vad'],
    stages: [
      { id: 'whisper-base-en', label: 'Downloading Whisper base.en', state: 'running', bytes_downloaded: 50_000_000, bytes_total: 147_964_211, error: null },
      { id: 'silero-vad', label: 'Downloading Silero VAD', state: 'pending', bytes_downloaded: null, bytes_total: null, error: null },
    ],
    error_message: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:01Z',
    ...overrides,
  }
}

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={['/voice-setup']}>
      <Routes>
        <Route path="/voice-setup" element={<VoiceSetup />} />
        <Route path="/library" element={<div>Library page</div>} />
        <Route path="/settings" element={<div>Settings page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: makePlan() })
  mockApi.startVoiceInstall.mockResolvedValue({ ok: true, data: makeJob() })
  mockApi.getVoiceInstallStatus.mockResolvedValue({ ok: true, data: makeJob() })
  mockApi.cancelVoiceInstall.mockResolvedValue({ ok: true, data: undefined })
  mockApi.startVoiceEngine.mockResolvedValue({
    ok: true,
    data: { engine_id: 'kokoro-server', state: 'running', started: true, message: 'The voice server is running.' },
  })
})

describe('VoiceSetup — what is missing', () => {
  it('lists every capability with its readiness', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    for (const id of ['stt', 'tts', 'vad']) {
      expect(screen.getByTestId(`capability-${id}`)).toBeInTheDocument()
      expect(screen.getByTestId(`capability-${id}-state`)).toHaveTextContent('Not yet')
    }
  })

  it('shows the per-platform command for an engine it will not download', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    const row = screen.getByTestId('engine-row-whisper-cli')
    expect(row).toHaveTextContent('brew install whisper-cpp')
    expect(row).toHaveTextContent('publishes no checksummed binary')
    // Installing it happens outside the app, so the row must offer a re-check.
    expect(screen.getByTestId('engine-recheck-whisper-cli')).toBeInTheDocument()
  })

  it('re-reads the plan when the player comes back from a terminal', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    const callsBefore = mockApi.getVoiceSetupPlan.mock.calls.length

    fireEvent.click(screen.getByTestId('engine-recheck-whisper-cli'))

    await waitFor(() =>
      expect(mockApi.getVoiceSetupPlan.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('offers to start a Kokoro server that is installed but stopped', async () => {
    const plan = makePlan()
    plan.engines[1] = { ...plan.engines[1], installed: true, found_at: '/usr/local/bin/kokoro-server' }
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    fireEvent.click(await screen.findByTestId('engine-start-kokoro-server'))

    await waitFor(() => expect(mockApi.startVoiceEngine).toHaveBeenCalledWith('kokoro-server'))
    expect(await screen.findByTestId('engine-message')).toHaveTextContent('voice server is running')
  })

  it('does not offer to start an engine that is not installed', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('engine-start-kokoro-server')).toBeNull()
  })

  it('offers the onnxruntime command only when the extra is missing', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('vad-onnxruntime-row')).toBeNull()

    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ onnxruntime_installed: false }),
    })
    renderScreen()
    expect(await screen.findByTestId('vad-onnxruntime-row')).toHaveTextContent('pip install onnxruntime')
  })
})

describe('VoiceSetup — download disclosure', () => {
  it('shows source, licence, checksum and destination before the download button', async () => {
    renderScreen()
    const table = await screen.findByTestId('voice-disclosure')

    expect(table).toHaveTextContent('Whisper base.en')
    expect(table).toHaveTextContent('MIT')
    expect(table).toHaveTextContent('huggingface.co/ggerganov/whisper.cpp')
    expect(table).toHaveTextContent(`SHA-256 ${'a'.repeat(64)}`)
    expect(table).toHaveTextContent('/home/p/.convsim/models/stt/ggml-base.en.bin')
  })

  it('states the total download size on the button', async () => {
    renderScreen()
    expect(await screen.findByTestId('voice-install-start')).toHaveTextContent('Download 143 MB')
  })

  it('downloads the recommended assets by default', async () => {
    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))

    await waitFor(() =>
      expect(mockApi.startVoiceInstall).toHaveBeenCalledWith(['whisper-base-en', 'silero-vad']),
    )
  })

  it('downloads the model the player picked instead of the recommendation', async () => {
    renderScreen()
    await screen.findByTestId('voice-disclosure')

    fireEvent.change(screen.getByLabelText('Speech-to-text model'), {
      target: { value: 'whisper-small-en' },
    })
    fireEvent.click(screen.getByTestId('voice-install-start'))

    await waitFor(() =>
      expect(mockApi.startVoiceInstall).toHaveBeenCalledWith(['whisper-small-en', 'silero-vad']),
    )
  })

  it('leaves out an asset that is already on disk', async () => {
    const plan = makePlan()
    plan.assets = plan.assets.map((a) => (a.id === 'silero-vad' ? { ...a, installed: true } : a))
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))

    await waitFor(() =>
      expect(mockApi.startVoiceInstall).toHaveBeenCalledWith(['whisper-base-en']),
    )
  })

  it('offers to switch to a model that is installed but not in use', async () => {
    const plan = makePlan()
    plan.assets = plan.assets.map((a) =>
      a.id === 'whisper-base-en' ? { ...a, installed: true, selected: true } : { ...a, installed: true },
    )
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    fireEvent.change(screen.getByLabelText('Speech-to-text model'), {
      target: { value: 'whisper-small-en' },
    })

    const button = await screen.findByTestId('voice-install-start')
    expect(button).toHaveTextContent('Use Whisper small.en')
    // Nothing is fetched, so there is nothing to disclose.
    expect(screen.queryByTestId('voice-disclosure')).toBeNull()

    fireEvent.click(button)
    await waitFor(() =>
      expect(mockApi.startVoiceInstall).toHaveBeenCalledWith(['whisper-small-en']),
    )
  })

  it('offers nothing to download once every asset is installed and in use', async () => {
    const plan = makePlan()
    plan.assets = plan.assets.map((a) => ({
      ...a,
      installed: true,
      selected: a.id === 'whisper-base-en',
    }))
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('voice-install-start')).toBeNull()
  })
})

describe('VoiceSetup — download progress', () => {
  it('shows per-asset progress and a cancel button while downloading', async () => {
    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))

    const panel = await screen.findByTestId('voice-install-progress')
    expect(panel).toHaveTextContent('Downloading Whisper base.en')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '17')
    expect(screen.getByTestId('voice-install-cancel')).toBeInTheDocument()
  })

  it('cancels the running job', async () => {
    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))
    fireEvent.click(await screen.findByTestId('voice-install-cancel'))

    await waitFor(() => expect(mockApi.cancelVoiceInstall).toHaveBeenCalledWith(7))
  })

  it('reattaches to a job that was already running when the screen opened', async () => {
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ active_job_id: 7 }),
    })

    renderScreen()

    expect(await screen.findByTestId('voice-install-progress')).toBeInTheDocument()
    await waitFor(() => expect(mockApi.getVoiceInstallStatus).toHaveBeenCalledWith(7))
  })

  it('reports a failed download with a retry', async () => {
    mockApi.startVoiceInstall.mockResolvedValue({
      ok: true,
      data: makeJob({
        status: 'failed',
        error_message: 'SHA-256 of ggml-base.en.bin did not match the registry value.',
      }),
    })
    mockApi.getVoiceInstallStatus.mockResolvedValue({
      ok: true,
      data: makeJob({
        status: 'failed',
        error_message: 'SHA-256 of ggml-base.en.bin did not match the registry value.',
      }),
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))

    expect(await screen.findByRole('alert')).toHaveTextContent('SHA-256')
    expect(screen.getByTestId('voice-install-retry')).toBeInTheDocument()
  })
})

describe('VoiceSetup — finished', () => {
  it('celebrates and points at a scenario once speech and voice both work', async () => {
    const plan = makePlan()
    plan.capabilities = plan.capabilities.map((c) =>
      c.id === 'vad' ? c : { ...c, ready: true },
    )
    plan.assets = plan.assets.map((a) => ({ ...a, installed: true }))
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()

    expect(await screen.findByTestId('voice-ready-panel')).toHaveTextContent('Voice is ready')
    fireEvent.click(screen.getByTestId('voice-ready-library'))
    expect(await screen.findByText('Library page')).toBeInTheDocument()
  })

  it('does not celebrate while the NPC voice is still missing', async () => {
    const plan = makePlan()
    plan.capabilities = plan.capabilities.map((c) =>
      c.id === 'stt' ? { ...c, ready: true } : c,
    )
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('voice-ready-panel')).toBeNull()
  })
})
