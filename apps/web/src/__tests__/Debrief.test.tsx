// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import Debrief from '../screens/Debrief'
import type { SessionDebriefResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    generateDebrief: vi.fn(),
    exportSession: vi.fn(),
    exportTranscriptText: vi.fn(),
    createSession: vi.fn(),
    listScenarios: vi.fn(() => Promise.resolve({ ok: true, data: [] })),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const { mockReadVoiceInviteState, mockWriteVoiceInviteState } = vi.hoisted(() => ({
  mockReadVoiceInviteState: vi.fn(() => 'pending'),
  mockWriteVoiceInviteState: vi.fn(),
}))
vi.mock('../privacyPrefs', () => ({
  isDevModeEnabled: vi.fn(() => false),
  readVoiceInviteState: mockReadVoiceInviteState,
  writeVoiceInviteState: mockWriteVoiceInviteState,
}))
import { isDevModeEnabled } from '../privacyPrefs'
const mockIsDevModeEnabled = vi.mocked(isDevModeEnabled)

const mockUnlock = vi.fn(() => Promise.resolve(false))
const mockIncrementStat = vi.fn(() => Promise.resolve(false))
vi.mock('../hooks/useSteamAchievements', () => ({
  useSteamAchievements: () => ({ unlock: mockUnlock, incrementStat: mockIncrementStat }),
  SteamAchievement: {
    FIRST_SCENARIO: 'ACH_FIRST_SCENARIO',
    FIRST_DEBRIEF: 'ACH_FIRST_DEBRIEF',
    PRACTICE_STREAK: 'ACH_PRACTICE_STREAK',
  },
  SteamStat: {
    SCENARIOS_COMPLETED: 'STAT_SCENARIOS_COMPLETED',
    DEBRIEFS_GENERATED: 'STAT_DEBRIEFS_GENERATED',
  },
}))

const SESSION_ID = 'sess-debrief01'

const sampleSetup = {
  scenario_id: 'behavioral_interview',
  difficulty: 'standard' as const,
  player_role_name: 'Candidate',
  language: 'en',
  input_mode: 'text-only' as const,
  tts_enabled: false,
  show_state_meters: false,
  save_transcript: true,
  seed: null,
}

const fullDebriefResponse: SessionDebriefResponse = {
  session_id: SESSION_ID,
  state: 'Ended',
  summary: 'You completed 2 turns of "Behavioral Interview". Session outcome: player exit.',
  outcome: 'player_exit',
  turn_count: 2,
  scenario_id: 'behavioral_interview',
  strengths: ['Engaged with the scenario', 'Completed the session flow'],
  improvements: ['Install a local LLM for real NPC responses'],
  missed_opportunities: ['Consider asking more probing questions to deepen the dialogue.'],
  replay_suggestions: ['Try a different difficulty level'],
  scores: { rapport: 60, clarity: 45 },
  overall_score: 52,
  turning_points: [
    { turn_number: 1, description: 'Strong opening statement', impact: 'positive' },
    { turn_number: 2, description: 'Missed an opportunity to ask a follow-up', impact: 'negative' },
  ],
  used_fallback: false,
  transcript_saving_disabled: false,
}

const fallbackDebriefResponse: SessionDebriefResponse = {
  ...fullDebriefResponse,
  scores: {},
  overall_score: 50,
  turning_points: [],
  used_fallback: true,
}

const transcriptDisabledDebriefResponse: SessionDebriefResponse = {
  ...fullDebriefResponse,
  transcript_saving_disabled: true,
}

const exportData = {
  session: {
    session_id: SESSION_ID,
    scenario_id: 'behavioral_interview',
    state: 'Ended',
    ending_type: 'player_exit',
    created_at: '2024-01-01T00:00:00Z',
    turn_count: 2,
    setup: sampleSetup,
    state_vars: {},
  },
  events: [
    { event_id: 1, session_id: SESSION_ID, event_type: 'player_turn', payload: { content: 'Hello, I am interested in this role.' }, created_at: '2024-01-01T00:00:01Z' },
    { event_id: 2, session_id: SESSION_ID, event_type: 'npc_turn', payload: { content: 'Tell me about yourself.', emotion: 'neutral' }, created_at: '2024-01-01T00:00:02Z' },
  ],
}

function ConversationRouteStub() {
  const { state } = useLocation()
  return (
    <div>
      Conversation page
      <span data-testid="route-state">{JSON.stringify(state)}</span>
    </div>
  )
}

function renderDebrief(routeState?: unknown) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: `/debrief/${SESSION_ID}`, state: routeState }]}>
      <Routes>
        <Route path="/debrief/:sessionId" element={<Debrief />} />
        <Route path="/library" element={<div>Library page</div>} />
        <Route path="/setup/:scenarioId" element={<div>Setup page</div>} />
        <Route path="/settings" element={<div>Settings page</div>} />
        <Route path="/conversation/:sessionId" element={<ConversationRouteStub />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.exportSession.mockResolvedValue({ ok: true, data: exportData })
  mockApi.exportTranscriptText.mockResolvedValue({
    ok: true,
    data: {
      text: '# Session Transcript\n\nSession content here.',
      filename: `session-${SESSION_ID}-transcript.md`,
    },
  })
  mockIsDevModeEnabled.mockReturnValue(false)
  mockReadVoiceInviteState.mockReturnValue('pending')
  mockWriteVoiceInviteState.mockReset()
})

describe('Debrief screen', () => {
  it('shows loading state while generating debrief', () => {
    mockApi.generateDebrief.mockReturnValue(new Promise(() => {}))
    renderDebrief()
    expect(screen.getByText(/generating debrief/i)).toBeInTheDocument()
  })

  it('displays summary after debrief loads', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('summary-section').querySelector('p')).toHaveTextContent(
      'You completed 2 turns',
    )
  })

  it('displays strengths section', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Engaged with the scenario')).toBeInTheDocument(),
    )
  })

  it('displays improvements section', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Install a local LLM for real NPC responses')).toBeInTheDocument(),
    )
  })

  it('displays replay suggestions', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Try a different difficulty level')).toBeInTheDocument(),
    )
  })

  it('shows the session id in the header', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() => expect(screen.getByText(SESSION_ID)).toBeInTheDocument())
  })

  it('shows outcome badge', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('outcome-badge')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('outcome-badge')).toHaveTextContent('player exit')
  })

  it('shows turn count', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
  })

  it('shows error alert when generateDebrief fails', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Session not found' } })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
    )
  })

  it('includes raw JSON debug section', async () => {
    mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('debrief-json')).toBeInTheDocument(),
    )
  })

  describe('steam achievements', () => {
    it('credits scenario completion even when the session ends via player_exit', async () => {
      // fullDebriefResponse.outcome is 'player_exit' — the "manually ended"
      // case the shipped framework (#230) explicitly counts. FIRST_SCENARIO and
      // the SCENARIOS_COMPLETED stat must fire regardless of a 'success' outcome.
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(mockUnlock).toHaveBeenCalledWith('ACH_FIRST_DEBRIEF')
      expect(mockUnlock).toHaveBeenCalledWith('ACH_FIRST_SCENARIO')
      expect(mockIncrementStat).toHaveBeenCalledWith('STAT_DEBRIEFS_GENERATED')
      expect(mockIncrementStat).toHaveBeenCalledWith('STAT_SCENARIOS_COMPLETED')
    })
  })

  describe('scorecard', () => {
    it('shows overall score', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('overall-score')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('overall-score')).toHaveTextContent('52')
    })

    it('shows a dimension row for each score', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('scorecard-section')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('dimension-row-rapport')).toBeInTheDocument()
      expect(screen.getByTestId('dimension-row-clarity')).toBeInTheDocument()
    })

    it('omits scorecard when scores object is empty', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fallbackDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('scorecard-section')).not.toBeInTheDocument()
    })
  })

  describe('turning points', () => {
    it('shows turning points section with key moments', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('turning-points-section')).toBeInTheDocument(),
      )
      expect(screen.getByText('Strong opening statement')).toBeInTheDocument()
      expect(screen.getByText('Missed an opportunity to ask a follow-up')).toBeInTheDocument()
    })

    it('omits turning points section when list is empty', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fallbackDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('turning-points-section')).not.toBeInTheDocument()
    })
  })

  describe('fallback debrief', () => {
    it('shows fallback notice when used_fallback is true', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fallbackDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('fallback-notice')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('fallback-notice')).toHaveTextContent('template')
    })

    it('does not show fallback notice when used_fallback is false', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('fallback-notice')).not.toBeInTheDocument()
    })
  })

  describe('transcript saving disabled', () => {
    it('shows transcript-disabled notice when transcript_saving_disabled is true', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: transcriptDisabledDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-disabled-notice')).toBeInTheDocument(),
      )
    })

    it('does not call exportSession when transcript saving is disabled', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: transcriptDisabledDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(mockApi.exportSession).not.toHaveBeenCalled()
    })
  })

  describe('transcript display', () => {
    it('shows transcript turns from export when available', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-section')).toBeInTheDocument(),
      )
      const turns = screen.getAllByTestId('transcript-turn')
      expect(turns).toHaveLength(2)
    })

    it('omits transcript section when export returns no relevant events', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      mockApi.exportSession.mockResolvedValue({ ok: true, data: { session: exportData.session, events: [] } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      await waitFor(() =>
        expect(mockApi.exportSession).toHaveBeenCalled(),
      )
      expect(screen.queryByTestId('transcript-section')).not.toBeInTheDocument()
    })
  })

  describe('export button', () => {
    it('renders an export button after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('export-btn')).toBeInTheDocument(),
      )
    })

    it('calls exportSession on click', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })

      const createObjectURL = vi.fn().mockReturnValue('blob:mock')
      const revokeObjectURL = vi.fn()
      const originalCreateElement = document.createElement.bind(document)
      const click = vi.fn()
      const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag) => {
        if (tag === 'a') return { href: '', download: '', click } as unknown as HTMLElement
        return originalCreateElement(tag)
      })
      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })

      try {
        renderDebrief()
        await waitFor(() => expect(screen.getByTestId('export-btn')).toBeInTheDocument())

        fireEvent.click(screen.getByTestId('export-btn'))

        await waitFor(() => expect(mockApi.exportSession).toHaveBeenCalledWith(SESSION_ID))
        await waitFor(() => expect(click).toHaveBeenCalled())
        expect(createObjectURL).toHaveBeenCalled()
        expect(revokeObjectURL).toHaveBeenCalled()
      } finally {
        createElementSpy.mockRestore()
        vi.unstubAllGlobals()
      }
    })
  })

  describe('debrief-generation latency (dev mode)', () => {
    it('captures and shows debrief generation latency when dev mode is on', async () => {
      mockIsDevModeEnabled.mockReturnValue(true)
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('debrief-latency')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('debrief-latency')).toHaveTextContent(/debrief generation:.*ms/i)
    })

    it('does not show debrief latency when dev mode is off', async () => {
      mockIsDevModeEnabled.mockReturnValue(false)
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('debrief-latency')).not.toBeInTheDocument()
    })
  })

  describe('replay variation button', () => {
    it('renders a replay button after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-btn')).toBeInTheDocument(),
      )
    })

    it('navigates to setup screen with the scenario id on replay click', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('replay-btn'))
      await waitFor(() =>
        expect(screen.getByText('Setup page')).toBeInTheDocument(),
      )
    })
  })

  describe('model-ready upgrade CTA (issue #383)', () => {
    it('does not render "Try it with the real AI" without the modelReadyAfterTutorial route state', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-btn')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('try-real-ai-btn')).not.toBeInTheDocument()
    })

    it('renders "Try it with the real AI" when the model became ready during the tutorial', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ modelReadyAfterTutorial: true })
      await waitFor(() =>
        expect(screen.getByTestId('try-real-ai-btn')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('try-real-ai-btn')).toHaveTextContent(/try it with the real ai/i)
    })

    it('navigates to the library when "Try it with the real AI" is clicked', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ modelReadyAfterTutorial: true })
      await waitFor(() =>
        expect(screen.getByTestId('try-real-ai-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('try-real-ai-btn'))
      await waitFor(() =>
        expect(screen.getByText('Library page')).toBeInTheDocument(),
      )
    })
  })

  describe('voice invite card (issue #385)', () => {
    it('shows the voice invite card after a real AI conversation when invite is pending', async () => {
      mockReadVoiceInviteState.mockReturnValue('pending')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: false })
      await waitFor(() =>
        expect(screen.getByTestId('voice-invite-card')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('voice-invite-card')).toHaveTextContent(/say it out loud/i)
    })

    it('persists "dismissed" as soon as the card is shown so it never re-nags', async () => {
      // Issue #385: the card must appear exactly once. Merely rendering it (even
      // if the user ignores it and navigates away) marks it seen so a later real
      // conversation does not re-show it.
      mockReadVoiceInviteState.mockReturnValue('pending')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: false })
      await waitFor(() =>
        expect(screen.getByTestId('voice-invite-card')).toBeInTheDocument(),
      )
      // Written without any button click — the card is still visible this time.
      expect(mockWriteVoiceInviteState).toHaveBeenCalledWith('dismissed')
      expect(screen.getByTestId('voice-invite-card')).toBeInTheDocument()
    })

    it('does not show voice invite card when the session was scripted', async () => {
      mockReadVoiceInviteState.mockReturnValue('pending')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: true })
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('voice-invite-card')).not.toBeInTheDocument()
    })

    it('does not show voice invite card when already dismissed', async () => {
      mockReadVoiceInviteState.mockReturnValue('dismissed')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: false })
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('voice-invite-card')).not.toBeInTheDocument()
    })

    it('does not show voice invite card when already in setup state', async () => {
      mockReadVoiceInviteState.mockReturnValue('setup')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: false })
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('voice-invite-card')).not.toBeInTheDocument()
    })

    it('"Maybe later" hides the card and persists dismissed state', async () => {
      mockReadVoiceInviteState.mockReturnValue('pending')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: false })
      await waitFor(() =>
        expect(screen.getByTestId('voice-invite-card')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('voice-invite-later-btn'))
      expect(screen.queryByTestId('voice-invite-card')).not.toBeInTheDocument()
      expect(mockWriteVoiceInviteState).toHaveBeenCalledWith('dismissed')
    })

    it('"Set up voice" hides the card, persists setup state, and navigates to settings', async () => {
      mockReadVoiceInviteState.mockReturnValue('pending')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief({ isScripted: false })
      await waitFor(() =>
        expect(screen.getByTestId('voice-invite-card')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('voice-invite-setup-btn'))
      expect(mockWriteVoiceInviteState).toHaveBeenCalledWith('setup')
      await waitFor(() =>
        expect(screen.getByText('Settings page')).toBeInTheDocument(),
      )
    })

    it('does not show voice invite card when isScripted is absent from route state', async () => {
      // No route state at all (e.g. navigated directly) — default is to treat as non-scripted
      mockReadVoiceInviteState.mockReturnValue('pending')
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      // No route state = isScripted defaults false, so invite appears when pending
      expect(screen.getByTestId('voice-invite-card')).toBeInTheDocument()
    })
  })

  describe('replay same setup button', () => {
    it('renders replay-same-btn after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-same-btn')).toBeInTheDocument(),
      )
    })

    it('creates a new session with same setup and navigates to conversation', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      mockApi.createSession.mockResolvedValue({ ok: true, data: {
        session_id: 'new-sess-01',
        scenario_id: 'behavioral_interview',
        state: 'NotStarted',
        created_at: '2024-01-02T00:00:00Z',
        setup: sampleSetup,
      } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-same-btn')).toBeInTheDocument(),
      )
      // Wait for export to populate sessionSetup
      await waitFor(() =>
        expect(mockApi.exportSession).toHaveBeenCalled(),
      )
      fireEvent.click(screen.getByTestId('replay-same-btn'))
      await waitFor(() =>
        expect(mockApi.createSession).toHaveBeenCalledWith(sampleSetup),
      )
      await waitFor(() =>
        expect(screen.getByText('Conversation page')).toBeInTheDocument(),
      )
    })

    it('forwards input_mode and tts_enabled to the conversation so replayed voice sessions keep their modes', async () => {
      const voiceSetup = { ...sampleSetup, input_mode: 'push-to-talk' as const, tts_enabled: true }
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      mockApi.createSession.mockResolvedValue({ ok: true, data: {
        session_id: 'new-sess-02',
        scenario_id: 'behavioral_interview',
        state: 'NotStarted',
        created_at: '2024-01-02T00:00:00Z',
        setup: voiceSetup,
      } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-same-btn')).toBeInTheDocument(),
      )
      await waitFor(() => expect(mockApi.exportSession).toHaveBeenCalled())
      fireEvent.click(screen.getByTestId('replay-same-btn'))
      await waitFor(() =>
        expect(screen.getByText('Conversation page')).toBeInTheDocument(),
      )
      const routeState = JSON.parse(screen.getByTestId('route-state').textContent || '{}')
      expect(routeState.input_mode).toBe('push-to-talk')
      expect(routeState.tts_enabled).toBe(true)
    })

    it('falls back to setup page when sessionSetup is unavailable', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      // Export returns data without setup (e.g., transcript saving was off)
      mockApi.exportSession.mockResolvedValue({ ok: true, data: { session: {}, events: [] } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-same-btn')).toBeInTheDocument(),
      )
      await waitFor(() =>
        expect(mockApi.exportSession).toHaveBeenCalled(),
      )
      fireEvent.click(screen.getByTestId('replay-same-btn'))
      await waitFor(() =>
        expect(screen.getByText('Setup page')).toBeInTheDocument(),
      )
    })
  })

  describe('missed opportunities section', () => {
    it('displays missed opportunities when present', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('missed-opportunities-section')).toBeInTheDocument(),
      )
      expect(screen.getByText('Consider asking more probing questions to deepen the dialogue.')).toBeInTheDocument()
    })

    it('does not render missed opportunities section when list is empty', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: {
        ...fullDebriefResponse,
        missed_opportunities: [],
      } })
      renderDebrief()
      await waitFor(() => expect(screen.getByTestId('summary-section')).toBeInTheDocument())
      expect(screen.queryByTestId('missed-opportunities-section')).not.toBeInTheDocument()
    })

    it('does not render missed opportunities section when field is absent', async () => {
      const rest = { ...fullDebriefResponse }
      delete (rest as Partial<typeof rest>).missed_opportunities
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: rest })
      renderDebrief()
      await waitFor(() => expect(screen.getByTestId('summary-section')).toBeInTheDocument())
      expect(screen.queryByTestId('missed-opportunities-section')).not.toBeInTheDocument()
    })
  })

  describe('export transcript as Markdown', () => {
    it('renders an export-text-btn after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('export-text-btn')).toBeInTheDocument(),
      )
    })

    it('calls exportTranscriptText on click and triggers download', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })

      const createObjectURL = vi.fn().mockReturnValue('blob:mock-text')
      const revokeObjectURL = vi.fn()
      const originalCreateElement = document.createElement.bind(document)
      const click = vi.fn()
      const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag) => {
        if (tag === 'a') return { href: '', download: '', click } as unknown as HTMLElement
        return originalCreateElement(tag)
      })
      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })

      try {
        renderDebrief()
        await waitFor(() => expect(screen.getByTestId('export-text-btn')).toBeInTheDocument())

        fireEvent.click(screen.getByTestId('export-text-btn'))

        await waitFor(() =>
          expect(mockApi.exportTranscriptText).toHaveBeenCalledWith(SESSION_ID),
        )
        await waitFor(() => expect(click).toHaveBeenCalled())
        expect(createObjectURL).toHaveBeenCalled()
        expect(revokeObjectURL).toHaveBeenCalled()
      } finally {
        createElementSpy.mockRestore()
        vi.unstubAllGlobals()
      }
    })
  })

  describe('export privacy notice', () => {
    it('shows a privacy notice near export buttons after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('export-privacy-notice')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('export-privacy-notice')).toHaveTextContent(/local download folder/i)
    })
  })

  describe('debrief failure retry', () => {
    it('shows a retry button in the error state', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'LLM unavailable' } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('retry-btn')).toBeInTheDocument(),
      )
    })

    it('retry button resets to loading and calls generateDebrief again', async () => {
      mockApi.generateDebrief
        .mockResolvedValueOnce({ ok: false, error: { kind: 'network', message: 'Timeout' } })
        .mockResolvedValue({ ok: true, data: fullDebriefResponse })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('retry-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('retry-btn'))
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(mockApi.generateDebrief).toHaveBeenCalledTimes(2)
    })
  })

  describe('transcript-only fallback', () => {
    it('shows a "Show transcript only" button in the error state', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Model error' } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-btn')).toBeInTheDocument(),
      )
    })

    it('clicking transcript-only loads transcript and shows transcript-only notice', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Model error' } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('transcript-only-btn'))
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-notice')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('transcript-only-notice')).toHaveTextContent(
        /debrief generation failed/i,
      )
    })

    it('transcript-only fallback shows transcript turns fetched via exportSession', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Model error' } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('transcript-only-btn'))
      await waitFor(() =>
        expect(screen.getByTestId('transcript-section')).toBeInTheDocument(),
      )
      expect(screen.getAllByTestId('transcript-turn')).toHaveLength(2)
    })

    it('transcript-only fallback shows no-transcript message when export has no turns', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Model error' } })
      mockApi.exportSession.mockResolvedValue({ ok: true, data: { session: {}, events: [] } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('transcript-only-btn'))
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-notice')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('transcript-section')).not.toBeInTheDocument()
      expect(screen.getByText(/no transcript was saved/i)).toBeInTheDocument()
    })

    it('transcript-only mode shows a retry debrief button', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Model error' } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('transcript-only-btn'))
      await waitFor(() =>
        expect(screen.getByTestId('retry-btn')).toBeInTheDocument(),
      )
    })

    it('transcript-only mode shows export-privacy-notice', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Model error' } })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-only-btn')).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByTestId('transcript-only-btn'))
      await waitFor(() =>
        expect(screen.getByTestId('export-privacy-notice')).toBeInTheDocument(),
      )
    })
  })

  describe('Next up footer', () => {
    function scenario(overrides: Record<string, unknown>) {
      return {
        pack_id: 'p1',
        pack_name: 'Pack',
        title: 'Untitled',
        summary: '',
        content_rating: 'G',
        player_role: { label: 'Role', brief: 'brief' },
        difficulty: { default: 'standard', options: {} },
        supported_languages: ['en'],
        duration: { max_turns: 10, soft_time_limit_minutes: 15 },
        state_meters_permitted: false,
        voice_supported: false,
        safety_summary: '',
        estimated_length_label: '~10 min',
        ...overrides,
      }
    }

    it('does not recommend the scenario that was just completed', async () => {
      mockApi.generateDebrief.mockResolvedValue({ ok: true, data: fullDebriefResponse })
      mockApi.listScenarios.mockResolvedValue({
        ok: true,
        // The completed scenario tests the weakest dimension (clarity=45), so
        // without the exclusion it would rank first in "Next up".
        data: [
          scenario({ scenario_id: 'behavioral_interview', title: 'Behavioral Interview', tested_dimensions: ['clarity'] }),
          scenario({ scenario_id: 'other_scenario', pack_id: 'p2', title: 'Other Scenario', tested_dimensions: ['clarity'] }),
        ] as never,
      })
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('next-up-section')).toBeInTheDocument(),
      )
      const links = screen.getAllByTestId('next-up-link')
      const titles = links.map((l) => l.textContent)
      expect(titles.some((tt) => tt?.includes('Other Scenario'))).toBe(true)
      expect(titles.some((tt) => tt?.includes('Behavioral Interview'))).toBe(false)
    })
  })
})
