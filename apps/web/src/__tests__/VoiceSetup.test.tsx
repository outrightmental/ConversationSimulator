// SPDX-License-Identifier: Apache-2.0
// Issue #487: Settings used to say "Not installed" and offer nothing. These
// tests pin the behaviour that replaced it — disclosure before download, a
// real download with progress and cancel, and honest guidance for the two
// engines the app will not fetch.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
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
  apiClient: {
    uploadAudio: vi.fn(),
  },
}))

// The real hook reports 'unsupported' under jsdom (no MediaRecorder), which
// would hide the whole microphone step. Driving it from the test lets each
// permission state be asserted.
vi.mock('../hooks/useMicCapture', () => ({
  useMicCapture: vi.fn(),
  MAX_RECORDING_SECONDS: 60,
}))

import { api, apiClient } from '../api/client'
import { useMicCapture } from '../hooks/useMicCapture'
import type { MicPermission } from '../hooks/useMicCapture'
const mockApi = vi.mocked(api)
const mockApiClient = vi.mocked(apiClient)

function makeMicState(overrides: Partial<ReturnType<typeof useMicCapture>> = {}) {
  return {
    permission: 'idle' as MicPermission,
    isRecording: false,
    recordingSeconds: 0,
    error: null,
    stream: null,
    requestPermission: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    releaseStream: vi.fn(),
    ...overrides,
  }
}

/** The blob callback VoiceSetup handed the mic hook, i.e. "recording finished". */
async function finishRecording(blob = new Blob(['audio'])) {
  const onAudioReady = vi.mocked(useMicCapture).mock.calls[0][0]
  await act(async () => {
    await onAudioReady?.(blob)
  })
}

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
        command: 'brew install whisper.cpp',
        command_note: null,
        startable: false,
        installed: false,
        found_at: null,
        serving: false,
      },
      {
        id: 'kokoro-server',
        capability: 'tts',
        name: 'Kokoro TTS server',
        why_manual: 'The NPC voice runs in a small local server.',
        docs_url: 'https://github.com/remsky/Kokoro-FastAPI#readme',
        command: 'docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest',
        command_note: null,
        startable: true,
        installed: false,
        found_at: null,
        serving: false,
      },
    ],
    platform: 'darwin',
    kokoro_state: 'stopped',
    onnxruntime_installed: true,
    onnxruntime_installable: true,
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
  mockApiClient.uploadAudio.mockResolvedValue({
    ok: true,
    data: { transcript: 'Thanks for seeing me today.', status: 'ok' },
  })
  vi.mocked(useMicCapture).mockReturnValue(makeMicState())
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

  it('counts one speech model as one step, not four', async () => {
    // Exactly one whisper model is needed. Giving every option a checklist row
    // would put three amber "not installed" lines above a button offering to
    // download 143 MB, and leave three of them under a green "Ready" heading
    // once one model was installed — the screen restating a problem that is
    // not there, which is the dead end issue #487 was filed about.
    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    expect(screen.getByTestId('asset-row-whisper-base-en')).toBeInTheDocument()
    expect(screen.queryByTestId('asset-row-whisper-small-en')).not.toBeInTheDocument()

    // Nothing is hidden: the picker still names every option with its size.
    const picker = screen.getByLabelText('Speech-to-text model')
    expect(picker).toHaveTextContent('Whisper base.en')
    expect(picker).toHaveTextContent('Whisper small.en')
  })

  it('keeps a row for a model on disk that is not the one in use', async () => {
    // Two models installed is a real state — the player downloaded one, then
    // switched — and both are honestly "installed", so both stay visible.
    const plan = makePlan()
    plan.assets = plan.assets.map((a) =>
      a.id === 'whisper-base-en' ? { ...a, installed: true, selected: true } : { ...a, installed: true },
    )
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    expect(screen.getByTestId('asset-row-whisper-base-en')).toHaveTextContent('installed, in use')
    expect(screen.getByTestId('asset-row-whisper-small-en')).toHaveTextContent('installed')
  })

  it('renders a multi-line install command as separate lines', async () => {
    // Windows PowerShell 5.1 has no `&&`, so the source build arrives
    // newline-separated. Collapsing it on screen would show one line nobody
    // can run.
    const plan = makePlan({ platform: 'win32' })
    plan.engines[0] = {
      ...plan.engines[0],
      command: 'git clone https://github.com/ggml-org/whisper.cpp\ncmake --build build',
    }
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    const row = await screen.findByTestId('engine-row-whisper-cli')
    const code = row.querySelector('code')
    expect(code).not.toBeNull()
    expect(code!.textContent).toContain('\n')
    expect(getComputedStyle(code!).whiteSpace).toBe('pre-wrap')
  })

  it('shows the per-platform command for an engine it will not download', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    const row = screen.getByTestId('engine-row-whisper-cli')
    expect(row).toHaveTextContent('brew install whisper.cpp')
    expect(row).toHaveTextContent('publishes no checksummed binary')
    // Installing it happens outside the app, so the row must offer a re-check.
    expect(screen.getByTestId('engine-recheck-whisper-cli')).toBeInTheDocument()
    // No follow-up step on this platform, so no note should be invented.
    expect(screen.queryByTestId('engine-note-whisper-cli')).not.toBeInTheDocument()
  })

  it('shows the follow-up step when the command alone does not finish the job', async () => {
    // The Windows route builds from source, which leaves the binary in the
    // build tree — without the note the player runs a command and nothing
    // changes, which is the dead end this whole screen exists to remove.
    const plan = makePlan()
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({
        platform: 'win32',
        engines: plan.engines.map((e) =>
          e.id === 'whisper-cli'
            ? {
                ...e,
                command: 'git clone https://github.com/ggml-org/whisper.cpp && cmake -B build -S whisper.cpp',
                command_note:
                  'The build leaves whisper-cli.exe in build\\bin\\Release. Add that folder to your PATH.',
              }
            : e,
        ),
      }),
    })
    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    expect(screen.getByTestId('engine-note-whisper-cli')).toHaveTextContent('Add that folder to your PATH')
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

  it('reports a start that did not work as a problem, not a success', async () => {
    // The endpoint answers 200 with started:false and the reason — a missing
    // binary, a taken port, a start that timed out — rather than 500ing, so
    // `ok` alone says nothing about whether the server came up. Announcing it
    // in success green would leave the banner contradicting the amber row
    // directly beneath it, on the screen built to stop exactly that.
    mockApi.startVoiceEngine.mockResolvedValue({
      ok: true,
      data: {
        engine_id: 'kokoro-server',
        state: 'stopped',
        started: false,
        message: 'Port 7358 is already in use.',
      },
    })
    const plan = makePlan()
    plan.engines[1] = { ...plan.engines[1], installed: true, found_at: '/usr/local/bin/kokoro-server' }
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    fireEvent.click(await screen.findByTestId('engine-start-kokoro-server'))

    const message = await screen.findByTestId('engine-message')
    expect(message).toHaveTextContent('Port 7358 is already in use.')
    expect(message).toHaveAttribute('role', 'alert')
  })

  it('leaves "already running" as information rather than a failure', async () => {
    // started:false with the server up is the one benign case: nothing was
    // launched because nothing needed to be.
    mockApi.startVoiceEngine.mockResolvedValue({
      ok: true,
      data: {
        engine_id: 'kokoro-server',
        state: 'running',
        started: false,
        message: 'The voice server is already running.',
      },
    })
    const plan = makePlan()
    plan.engines[1] = { ...plan.engines[1], installed: true, found_at: '/usr/local/bin/kokoro-server' }
    plan.kokoro_state = 'stopped'
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    fireEvent.click(await screen.findByTestId('engine-start-kokoro-server'))

    const message = await screen.findByTestId('engine-message')
    expect(message).toHaveTextContent('already running')
    expect(message).toHaveAttribute('role', 'status')
  })

  it('does not offer to start an engine that is not installed', async () => {
    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('engine-start-kokoro-server')).toBeNull()
  })

  it('stops nagging about an engine that is already answering from outside the app', async () => {
    // The Kokoro command this screen hands out runs the server in Docker, which
    // puts no binary on PATH. Re-offering that command — behind a re-check that
    // can never turn green — beside a capability reported Ready is the dead end
    // issue #487 was filed about, just one screen later.
    const plan = makePlan()
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({
        capabilities: plan.capabilities.map((c) => (c.id === 'tts' ? { ...c, ready: true } : c)),
        engines: plan.engines.map((e) =>
          e.id === 'kokoro-server' ? { ...e, installed: true, serving: true } : e,
        ),
      }),
    })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    const row = screen.getByTestId('engine-row-kokoro-server')
    expect(row).toHaveTextContent('already running')
    expect(screen.getByTestId('engine-serving-kokoro-server')).toBeInTheDocument()
    // Neither a command to run nor a server to start: both would be wrong.
    expect(row).not.toHaveTextContent('docker run')
    expect(screen.queryByTestId('engine-recheck-kokoro-server')).toBeNull()
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

  it('puts the ffmpeg gap inside the section whose badge it explains', async () => {
    // WhisperCppWorker.health reports speech-to-text unavailable without
    // ffmpeg, so this is the state where the badge reads "Not yet" while the
    // engine and the model rows above it are both green. As a card below all
    // three capability sections, the one row that explained the badge was off
    // the bottom of the page.
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ ffmpeg_installed: false }),
    })

    renderScreen()
    const row = await screen.findByTestId('ffmpeg-row')

    expect(screen.getByTestId('capability-stt')).toContainElement(row)
    expect(row).toHaveTextContent('not found')
    expect(screen.getByLabelText('Copy the ffmpeg install command')).toBeInTheDocument()
  })

  it('drops the ffmpeg row once ffmpeg is there', async () => {
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ ffmpeg_installed: true }),
    })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('ffmpeg-row')).toBeNull()
  })

  it('tells Windows to restart after the ffmpeg command, and nobody else', async () => {
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ ffmpeg_installed: false, platform: 'win32' }),
    })
    renderScreen()
    expect(await screen.findByTestId('ffmpeg-restart-note')).toHaveTextContent('Restart the app')

  })

  it('does not ask for a restart where the command lands on the existing PATH', async () => {
    // brew and apt land in a directory the running process already has on
    // PATH, so asking for a restart there would be noise.
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ ffmpeg_installed: false, platform: 'darwin' }),
    })
    renderScreen()

    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('ffmpeg-restart-note')).toBeNull()
  })

  it('explains instead of printing a pip command a packaged build cannot run', async () => {
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ onnxruntime_installed: false, onnxruntime_installable: false }),
    })
    renderScreen()

    const row = await screen.findByTestId('vad-onnxruntime-row')
    // A command with no interpreter to install into is the dead end this
    // screen exists to remove, so it must not appear at all.
    expect(row).not.toHaveTextContent('pip install onnxruntime')
    expect(screen.getByTestId('vad-onnxruntime-packaged')).toHaveTextContent('Push-to-talk')
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

  it('re-points at a model already on disk instead of re-downloading the recommendation', async () => {
    // The state a cancelled job leaves behind: the speech model the player
    // chose finished downloading, the stage after it was cancelled, so nothing
    // was persisted and no asset comes back selected. Quoting a fresh download
    // for the recommendation here would charge the player twice for a model
    // they already have.
    const plan = makePlan()
    plan.assets = plan.assets.map((a) =>
      a.id === 'whisper-base-en' ? a : { ...a, installed: true },
    )
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })

    renderScreen()
    const button = await screen.findByTestId('voice-install-start')

    expect(button).toHaveTextContent('Use Whisper small.en')
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

  it('says a cancel is under way instead of leaving the card looking frozen', async () => {
    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))
    fireEvent.click(await screen.findByTestId('voice-install-cancel'))

    // The DELETE only signals the downloader; the job row still reads
    // 'running' until the next poll, so the button has to speak for itself.
    const button = await screen.findByTestId('voice-install-cancel')
    await waitFor(() => expect(button).toHaveTextContent('Cancelling'))
    expect(button).toBeDisabled()
  })

  it('does not report a cancel that arrived a moment too late as a failure', async () => {
    // The player clicks while the job is still 'running' on screen, but it has
    // already settled server-side, so the endpoint answers 409. The download
    // has stopped either way — the one thing they asked for.
    mockApi.cancelVoiceInstall.mockResolvedValue({
      ok: false,
      error: {
        kind: 'http-error',
        status: 409,
        message: "Voice install job 7 is already in terminal state 'cancelled'.",
      },
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('voice-install-start'))
    fireEvent.click(await screen.findByTestId('voice-install-cancel'))

    await waitFor(() => expect(mockApi.cancelVoiceInstall).toHaveBeenCalledWith(7))
    expect(screen.queryByText(/Request failed/i)).toBeNull()
    expect(screen.queryByText(/terminal state/i)).toBeNull()
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

  it('does not celebrate a plan that lists no capabilities at all', async () => {
    // `[].every(...)` is true, so a plan that arrives without capabilities —
    // a trimmed-down edition, a contract drift — would otherwise announce
    // voice ready on a screen with nothing on it.
    mockApi.getVoiceSetupPlan.mockResolvedValue({
      ok: true,
      data: makePlan({ capabilities: [] }),
    })

    renderScreen()
    await screen.findByTestId('voice-setup-screen')
    expect(screen.queryByTestId('voice-ready-panel')).toBeNull()
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


describe('VoiceSetup — the microphone', () => {
  /** STT ready on the server: models installed, engine found. */
  function readyPlan() {
    const plan = makePlan()
    plan.capabilities = plan.capabilities.map((c) => (c.id === 'stt' ? { ...c, ready: true } : c))
    plan.assets = plan.assets.map((a) => ({ ...a, installed: true, selected: a.recommended }))
    return plan
  }

  it('asks for permission, because no download can grant it', async () => {
    const requestPermission = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ requestPermission }))

    renderScreen()
    await screen.findByTestId('voice-setup-screen')

    expect(screen.getByTestId('mic-check-row')).toHaveTextContent('not allowed yet')
    fireEvent.click(screen.getByTestId('mic-allow'))
    expect(requestPermission).toHaveBeenCalledOnce()
  })

  it('says how to recover a microphone the browser has blocked', async () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'denied' }))

    renderScreen()
    const row = await screen.findByTestId('mic-check-row')

    expect(row).toHaveTextContent('blocked')
    expect(row).toHaveTextContent('site permissions')
    expect(screen.getByTestId('mic-allow')).toHaveTextContent('Try the microphone again')
  })

  it('explains that this browser cannot record at all', async () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'unsupported' }))

    renderScreen()
    const row = await screen.findByTestId('mic-check-row')

    expect(row).toHaveTextContent('not available in this browser')
    // Nothing to ask for: the browser, not the player, is the blocker.
    expect(screen.queryByTestId('mic-allow')).toBeNull()
  })

  it('withholds the test until speech-to-text is actually ready', async () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))

    renderScreen()
    const row = await screen.findByTestId('mic-check-row')

    expect(row).toHaveTextContent('Finish the speech-to-text steps above')
    expect(screen.queryByTestId('mic-test-start')).toBeNull()
  })

  it('runs one real round trip and repeats back what it heard', async () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted', startRecording }))
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: readyPlan() })

    renderScreen()
    fireEvent.click(await screen.findByTestId('mic-test-start'))
    expect(startRecording).toHaveBeenCalledOnce()

    await finishRecording()

    expect(mockApiClient.uploadAudio).toHaveBeenCalledOnce()
    expect(await screen.findByTestId('mic-test-result')).toHaveTextContent(
      'Thanks for seeing me today.',
    )
  })

  it('stops a recording that is in progress', async () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(
      makeMicState({ permission: 'granted', isRecording: true, recordingSeconds: 3, stopRecording }),
    )
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: readyPlan() })

    renderScreen()
    const stop = await screen.findByTestId('mic-test-stop')
    expect(stop).toHaveTextContent('3s')

    fireEvent.click(stop)
    expect(stopRecording).toHaveBeenCalledOnce()
  })

  it('reports a transcription that produced no words', async () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: readyPlan() })
    mockApiClient.uploadAudio.mockResolvedValue({
      ok: true,
      data: { transcript: null, status: 'ok' },
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('mic-test-start'))
    await finishRecording()

    expect(await screen.findByTestId('mic-test-result')).toHaveTextContent('No speech was detected')
  })

  it('names ffmpeg rather than "finish the steps above" when ffmpeg is the gap', async () => {
    // A missing ffmpeg reports 'unavailable', the same status as a missing
    // binary or model, because it is the same kind of gap. Naming it is still
    // worth its own sentence: it is the one piece whose absence fails every
    // utterance however green the rest of the list is.
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    const plan = readyPlan()
    plan.ffmpeg_installed = false
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })
    mockApiClient.uploadAudio.mockResolvedValue({
      ok: true,
      data: { transcript: null, status: 'unavailable' },
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('mic-test-start'))
    await finishRecording()

    const result = await screen.findByTestId('mic-test-result')
    expect(result).toHaveTextContent('ffmpeg is missing')
    expect(result).not.toHaveTextContent('finish the steps above')
    // The card it sends the player to has to actually be on the screen.
    expect(screen.getByText(/browser records WebM/)).toBeInTheDocument()
  })

  it('still says "finish the steps above" when ffmpeg is not the gap', async () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    const plan = readyPlan()
    plan.ffmpeg_installed = true
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })
    mockApiClient.uploadAudio.mockResolvedValue({
      ok: true,
      data: { transcript: null, status: 'unavailable' },
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('mic-test-start'))
    await finishRecording()

    expect(await screen.findByTestId('mic-test-result')).toHaveTextContent(
      'finish the steps above',
    )
  })

  it('points at ffmpeg when the worker refuses the audio and ffmpeg is missing', async () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    const plan = readyPlan()
    plan.ffmpeg_installed = false
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })
    mockApiClient.uploadAudio.mockResolvedValue({
      ok: true,
      data: { transcript: null, status: 'error' },
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('mic-test-start'))
    await finishRecording()

    const result = await screen.findByTestId('mic-test-result')
    expect(result).toHaveTextContent('ffmpeg is the usual culprit')
    // The row it sends the player to has to actually be on the screen.
    expect(screen.getByText(/browser records WebM/)).toBeInTheDocument()
  })

  it('does not send the player to an ffmpeg row that is not rendered', async () => {
    // The ffmpeg card only exists while ffmpeg is missing, so blaming it
    // unconditionally would have the screen name a row it is not showing —
    // on the screen whose whole job is telling the player the truth about
    // what is installed.
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    const plan = readyPlan()
    plan.ffmpeg_installed = true
    mockApi.getVoiceSetupPlan.mockResolvedValue({ ok: true, data: plan })
    mockApiClient.uploadAudio.mockResolvedValue({
      ok: true,
      data: { transcript: null, status: 'error' },
    })

    renderScreen()
    fireEvent.click(await screen.findByTestId('mic-test-start'))
    await finishRecording()

    const result = await screen.findByTestId('mic-test-result')
    expect(result).not.toHaveTextContent('check its row above')
    expect(result).toHaveTextContent('speech model is the likely culprit')
  })
})
