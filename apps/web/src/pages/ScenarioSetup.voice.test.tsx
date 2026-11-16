// SPDX-License-Identifier: Apache-2.0
//
// The brief's voice install: the greyed-out voice options used to be a dead
// end ("STT not loaded", and a click did nothing). These cases pin what they
// lead to now. The brief's other behaviour is covered in ScenarioSetup.test.tsx,
// whose engine double has no voice installer, which is the "older engine"
// case: there the screen reads as it did before.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import axe from 'axe-core'
import type { HealthResponse, ScenarioInfo } from '@convsim/shared'
import { ScenarioSetupPage } from './ScenarioSetup'
import { readyPlan, voiceJob, voicePlan } from '../__tests__/voiceFixtures'

const scenario: ScenarioInfo = {
  scenario_id: 'behavioral_interview',
  title: 'Behavioral Interview',
  summary: 'A mid-level job interview.',
  content_rating: 'PG',
  pack_id: 'official.job_interview_basic',
  pack_name: 'Job Interview Basics',
  player_role: { label: 'Candidate', brief: 'You are interviewing for a role.' },
  difficulty: {
    default: 'standard',
    options: { standard: { patience: 50, volatility: 50, disclosure: 50, time_pressure: 50 } },
  },
  supported_languages: ['en', 'ja'],
  duration: { max_turns: 18, soft_time_limit_minutes: 20 },
  state_meters_permitted: true,
  voice_supported: true,
  safety_summary: 'PG content only.',
  estimated_length_label: '15–20 minutes',
  player_visible_goals: ['Give one specific example of your own work'],
}

function health(stt: boolean, tts: boolean): HealthResponse {
  return {
    status: 'ok',
    version: '0.4.0',
    runtime: {
      llm_ready: true,
      llm_model_name: 'Qwen3 4B',
      stt_ready: stt,
      tts_ready: tts,
      tts_voice_name: null,
      network_required: false,
    },
  }
}

vi.mock('../api/client', () => ({
  api: {
    getScenario: vi.fn(),
    health: vi.fn(),
    createSession: vi.fn(),
    listVoices: vi.fn(),
    getVoiceSetup: vi.fn(),
    startVoiceInstall: vi.fn(),
    getVoiceInstallJob: vi.fn(),
    cancelVoiceInstall: vi.fn(),
  },
  getLogExcerptRaw: vi.fn().mockResolvedValue({ excerpt: '', sources: [], notice: '' }),
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)
const ok = <T,>(data: T) => ({ ok: true as const, data })

const VOICES = {
  voices: [
    { voice_id: 'af_heart', display_name: 'Heart (US female)', engine: 'kokoro', gender: 'female' as const, locale: 'en-US' },
  ],
}

function renderBrief() {
  const onSessionCreated = vi.fn()
  const view = render(
    <ScenarioSetupPage
      scenarioId="behavioral_interview"
      onSessionCreated={onSessionCreated}
      onBack={vi.fn()}
    />,
  )
  return { onSessionCreated, ...view }
}

async function loaded() {
  await waitFor(() => screen.getByText('Behavioral Interview'))
  await waitFor(() => expect(mockApi.getVoiceSetup).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.getScenario.mockResolvedValue(ok(scenario))
  mockApi.listVoices.mockResolvedValue(ok(VOICES))
  mockApi.health.mockResolvedValue(ok(health(false, false)))
  mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan()))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('conversation brief: voice not installed', () => {
  it('offers the install on the brief itself, with its size', async () => {
    renderBrief()
    await loaded()

    const card = await screen.findByTestId('voice-install')
    expect(within(card).getByText('Add voice')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /^install voice/i })).toHaveTextContent('559 MB')
  })

  it('gives each greyed-out input mode a way to install it', async () => {
    renderBrief()
    await loaded()
    await screen.findByTestId('voice-install')

    expect(screen.getByRole('radio', { name: /push-to-talk/i })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /hands-free/i })).toBeDisabled()
    // The stale engineering label is gone; the row says what is true.
    expect(screen.queryByText(/STT not loaded/i)).not.toBeInTheDocument()
    expect(screen.getAllByText('Not installed')).toHaveLength(2)

    expect(
      screen.getByRole('button', { name: 'Install voice to use Push-to-talk voice' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Install voice to use Hands-free voice (VAD)' }),
    ).toBeInTheDocument()
    // Text is installed, so it gets no install button.
    expect(screen.queryByRole('button', { name: /install voice to use text only/i })).not.toBeInTheDocument()
  })

  it('takes the player from a greyed-out option to the install button', async () => {
    renderBrief()
    await loaded()
    const card = await screen.findByTestId('voice-install')
    const install = within(card).getByRole('button', { name: /^install voice/i })

    fireEvent.click(screen.getByRole('button', { name: 'Install voice to use Push-to-talk voice' }))

    expect(install).toHaveFocus()
    expect(card).toHaveClass('is-highlighted')
    // Reaching for the option is not consent to a 559 MB download.
    expect(mockApi.startVoiceInstall).not.toHaveBeenCalled()
  })

  it('replaces the dead-end TTS hint with a link to the installer', async () => {
    renderBrief()
    await loaded()
    const card = await screen.findByTestId('voice-install')

    expect(screen.queryByText(/Install a TTS model to enable voice output/i)).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /npc voice/i })).toBeDisabled()
    const note = screen.getByText(/to hear replies out loud/i)
    fireEvent.click(within(note).getByRole('button', { name: 'Install voice' }))
    expect(within(card).getByRole('button', { name: /^install voice/i })).toHaveFocus()
  })

  it('links the runtime readiness rows to the installer', async () => {
    renderBrief()
    await loaded()
    const card = await screen.findByTestId('voice-install')
    const panel = within(screen.getByTestId('runtime-readiness'))

    const links = panel.getAllByRole('button', { name: 'Install' })
    expect(links).toHaveLength(2)
    fireEvent.click(links[0])
    expect(within(card).getByRole('button', { name: /^install voice/i })).toHaveFocus()
  })

  it('starts the install from the card and shows its progress', async () => {
    mockApi.startVoiceInstall.mockResolvedValue(ok(voiceJob()))
    mockApi.getVoiceInstallJob.mockResolvedValue(ok(voiceJob()))
    renderBrief()
    await loaded()
    const card = await screen.findByTestId('voice-install')

    fireEvent.click(within(card).getByRole('button', { name: /^install voice/i }))

    await waitFor(() => expect(screen.getByText('Installing voice')).toBeInTheDocument())
    expect(mockApi.startVoiceInstall).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('progressbar', { name: /voice install progress/i })).toBeInTheDocument()
    // The rows say so too, and the conversation can still be started in text.
    expect(screen.getAllByText('Installing…').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: /start conversation/i })).toBeEnabled()
  })

  it('switches voice on for this conversation when the install finishes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockApi.startVoiceInstall.mockResolvedValue(ok(voiceJob()))
    mockApi.getVoiceInstallJob.mockResolvedValue(ok(voiceJob({ status: 'complete' })))
    const { onSessionCreated } = renderBrief()
    await loaded()
    const card = await screen.findByTestId('voice-install')
    expect(screen.getByRole('radio', { name: /text only/i })).toBeChecked()

    // From here on the engine reports voice as ready.
    mockApi.health.mockResolvedValue(ok(health(true, true)))
    mockApi.getVoiceSetup.mockResolvedValue(ok({ ...readyPlan(), job: voiceJob({ status: 'complete' }) }))
    fireEvent.click(within(card).getByRole('button', { name: /^install voice/i }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })

    await waitFor(() => expect(screen.getByRole('radio', { name: /push-to-talk/i })).toBeChecked())
    expect(screen.getByRole('radio', { name: /push-to-talk/i })).toBeEnabled()
    expect(screen.getByRole('radio', { name: /hands-free/i })).toBeEnabled()
    expect(screen.getByRole('checkbox', { name: /npc voice/i })).toBeChecked()
    expect(screen.getByText('Voice is installed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /install voice to use/i })).not.toBeInTheDocument()

    // And the conversation that starts carries the choice.
    mockApi.createSession.mockResolvedValue(ok({
      session_id: 's1', scenario_id: 'behavioral_interview', state: 'ready',
      setup: {}, created_at: '2026-11-16T00:00:00Z',
    } as never))
    fireEvent.click(screen.getByRole('button', { name: /start conversation/i }))
    await waitFor(() => expect(onSessionCreated).toHaveBeenCalled())
    expect(mockApi.createSession).toHaveBeenCalledWith(
      expect.objectContaining({ input_mode: 'push-to-talk', tts_enabled: true }),
    )
  })

  it('has no axe violations with the installer on the page', async () => {
    const { container } = renderBrief()
    await loaded()
    await screen.findByTestId('voice-install')
    const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(results.violations.map((v) => `${v.id}: ${v.nodes[0]?.html ?? ''}`)).toEqual([])
  })
})

describe('conversation brief: voice installed', () => {
  beforeEach(() => {
    mockApi.health.mockResolvedValue(ok(health(true, true)))
    mockApi.getVoiceSetup.mockResolvedValue(ok(readyPlan()))
  })

  it('shows no installer and no install buttons', async () => {
    renderBrief()
    await loaded()
    await waitFor(() => expect(screen.getByRole('radio', { name: /push-to-talk/i })).toBeEnabled())

    expect(screen.queryByTestId('voice-install')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /install/i })).not.toBeInTheDocument()
  })

  it('keeps the reply in text for a language the voices cannot speak, and says so', async () => {
    const { onSessionCreated } = renderBrief()
    await loaded()
    const toggle = screen.getByRole('checkbox', { name: /npc voice/i })
    await waitFor(() => expect(toggle).toBeChecked())

    fireEvent.change(screen.getByRole('combobox', { name: /conversation language/i }), {
      target: { value: 'ja' },
    })

    expect(toggle).not.toBeChecked()
    expect(toggle).toBeDisabled()
    expect(screen.getByText(/cannot speak .* yet, so replies in this conversation are text/i)).toBeInTheDocument()

    mockApi.createSession.mockResolvedValue(ok({
      session_id: 's1', scenario_id: 'behavioral_interview', state: 'ready',
      setup: {}, created_at: '2026-11-16T00:00:00Z',
    } as never))
    fireEvent.click(screen.getByRole('button', { name: /start conversation/i }))
    await waitFor(() => expect(onSessionCreated).toHaveBeenCalled())
    expect(mockApi.createSession).toHaveBeenCalledWith(
      expect.objectContaining({ language: 'ja', tts_enabled: false }),
    )

    // Back in a language the voices speak, the choice the player made returns.
    fireEvent.change(screen.getByRole('combobox', { name: /conversation language/i }), {
      target: { value: 'en' },
    })
    expect(toggle).toBeChecked()
  })

  it('does not second-guess a voice server the player runs themselves', async () => {
    // Ready, but not through the in-app install: no language list applies.
    const own = readyPlan()
    own.components = own.components.map((c) => ({ ...c, installed: false }))
    mockApi.getVoiceSetup.mockResolvedValue(ok(own))
    renderBrief()
    await loaded()
    const toggle = screen.getByRole('checkbox', { name: /npc voice/i })
    await waitFor(() => expect(toggle).toBeChecked())

    fireEvent.change(screen.getByRole('combobox', { name: /conversation language/i }), {
      target: { value: 'ja' },
    })
    expect(toggle).toBeChecked()
    expect(toggle).toBeEnabled()
  })
})

describe('conversation brief: voice cannot be installed here', () => {
  it('says so once and offers no download', async () => {
    mockApi.getVoiceSetup.mockResolvedValue(ok(voicePlan({
      supported: false,
      unsupported_reason: 'Voice is not available for this kind of computer yet.',
      download_bytes: 0,
    })))
    renderBrief()
    await loaded()

    const card = await screen.findByTestId('voice-install')
    expect(card).toHaveTextContent('not available for this kind of computer yet')
    expect(screen.queryByRole('button', { name: /install/i })).not.toBeInTheDocument()
    // With no installer the rows keep their plain "not loaded" wording.
    expect(screen.getAllByText(/STT not loaded/i)).toHaveLength(2)
  })
})
