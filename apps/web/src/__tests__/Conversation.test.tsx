// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { StrictMode } from 'react'
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Conversation from '../screens/Conversation'
import type {
  HealthResponse,
  SessionStartResponse,
  TurnResponse,
  SessionEndResponse,
  ScenarioInfo,
  TurnStage,
  WsEvent,
} from '@convsim/shared'
import type { ApiError } from '../api/errors'

vi.mock('../api/client', () => ({
  api: {
    startSession: vi.fn(),
    submitTurn: vi.fn(),
    endSession: vi.fn(),
    generateDebrief: vi.fn(),
    connectSession: vi.fn(),
    getScenario: vi.fn(),
    getSetupInstallStatus: vi.fn(),
    getSessionTranscript: vi.fn(),
    // Resume reads the recorded setup back when there is no route state
    // (issue #501 §1), which is how most of these tests render the screen.
    getSession: vi.fn(),
    // This machine's recent speeds, for the reply-start estimate (issue #539).
    getRollingSpeeds: vi.fn(),
  },
  apiClient: {
    health: vi.fn(),
    uploadAudio: vi.fn(),
    vadHealth: vi.fn().mockResolvedValue({}),
    vadCalibrate: vi.fn(),
  },
}))

import { api, apiClient } from '../api/client'
import { clearTurnSamples, readTurnSamples, recordTurnSample } from '../lib/turnEstimate'
const mockApi = vi.mocked(api)
const mockApiClient = vi.mocked(apiClient)

const SESSION_ID = 'sess-demo0001'
const SCENARIO_ID = 'scenario-job-interview'

const startResponse: SessionStartResponse = {
  session_id: SESSION_ID,
  state: 'PlayerTurnListening',
  events: [
    {
      event_id: 1,
      session_id: SESSION_ID,
      event_type: 'npc_opening',
      payload: {
        content: "Thanks for coming in. Tell me about yourself.",
        visible_state: { trust: 50, patience: 75, rapport: 50, openness: 50, objective_progress: 0 },
      },
      created_at: '2026-07-01T00:00:00Z',
    },
  ],
}

const turnResponse: TurnResponse = {
  session_id: SESSION_ID,
  state: 'PlayerTurnListening',
  events: [
    {
      event_id: 2,
      session_id: SESSION_ID,
      event_type: 'player_turn',
      payload: { content: 'I have five years of experience.' },
      created_at: '2026-07-01T00:00:01Z',
    },
    {
      event_id: 3,
      session_id: SESSION_ID,
      event_type: 'npc_turn',
      payload: {
        content: 'Hello there. I am a simulated NPC.',
        emotion: 'neutral',
        state_delta: {},
        event_flags: [],
        safety: { status: 'ok' },
        ending_type: null,
      },
      created_at: '2026-07-01T00:00:02Z',
    },
  ],
}

const endResponse: SessionEndResponse = {
  session_id: SESSION_ID,
  state: 'Ended',
  ending_type: 'player_exit',
}

const mockScenario: ScenarioInfo = {
  scenario_id: SCENARIO_ID,
  title: 'Software Engineer Interview',
  summary: 'Practice a technical job interview with a realistic hiring manager.',
  content_rating: 'G',
  pack_id: 'job-interview-basic',
  pack_name: 'Job Interview Basics',
  player_role: { label: 'Job Candidate', brief: 'You are applying for a software engineering role.' },
  difficulty: { default: 'standard', options: { warm: { patience: 80, volatility: 20, disclosure: 70, time_pressure: 20 }, standard: { patience: 50, volatility: 50, disclosure: 50, time_pressure: 50 } } },
  supported_languages: ['en'],
  duration: { max_turns: 20, soft_time_limit_minutes: 15 },
  state_meters_permitted: true,
  voice_supported: false,
  safety_summary: 'This scenario contains professional workplace language only.',
  estimated_length_label: '10–15 min',
}

const MODEL_NAME = 'test-model-7b'

const healthResponse: HealthResponse = {
  status: 'ok',
  version: '0.1.0',
  runtime: {
    llm_ready: true,
    llm_model_name: MODEL_NAME,
    stt_ready: false,
    tts_ready: false,
    tts_voice_name: null,
    network_required: false,
  },
}

function renderConversation(routeState?: Record<string, unknown>) {
  return render(
    <MemoryRouter
      initialEntries={[
        routeState
          ? { pathname: `/conversation/${SESSION_ID}`, state: routeState }
          : `/conversation/${SESSION_ID}`,
      ]}
    >
      <Routes>
        <Route path="/conversation/:sessionId" element={<Conversation />} />
        <Route path="/debrief/:sessionId" element={<div>Debrief page</div>} />
        <Route path="/library" element={<div>Library page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Tests that opt into technical wording (or dev mode) write to localStorage,
  // and jsdom keeps it between tests in the same file — so a later test would
  // inherit the previous one's wording level.
  localStorage.clear()
  // Default: connectSession returns a no-op connection; getScenario returns null
  mockApi.connectSession.mockReturnValue({ close: vi.fn() })
  mockApi.getScenario.mockResolvedValue({ ok: true, data: null } as never)
  // Rendering without route state is the resume path, so the screen asks the
  // core for the setup it recorded. Default to "unavailable": these tests are
  // about the conversation, not about what the setup fetch adds.
  mockApi.getSession.mockResolvedValue({
    ok: false,
    error: { kind: 'network', message: 'not mocked' },
  } as never)
  mockApiClient.uploadAudio.mockResolvedValue({ ok: true, data: { transcript: null, status: 'unavailable' } })
  // No recorded turns on this machine unless a test says otherwise (issue #539).
  mockApi.getRollingSpeeds.mockResolvedValue({
    ok: true,
    data: { runtime_id: 'fake', model_id: null, samples: 0, reading_tps: null, writing_tps: null, first_token_ms: null, first_words_ms: null, total_ms: null },
  })
  // The screen reads health to learn which model the turn estimate belongs to.
  mockApiClient.health.mockResolvedValue({ ok: true, data: healthResponse })
  // Turn timings persist in localStorage by design, and the test store is shared
  // across the file — clear it so one test's turns cannot seed another's estimate.
  clearTurnSamples()
})

describe('Conversation screen', () => {
  describe('session start', () => {
    it('shows loading state while session is starting', () => {
      mockApi.startSession.mockReturnValue(new Promise(() => {}))
      renderConversation()
      expect(screen.getByText(/starting session/i)).toBeInTheDocument()
    })

    it('displays the NPC opening after session starts', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() =>
        expect(
          screen.getByText('Thanks for coming in. Tell me about yourself.'),
        ).toBeInTheDocument(),
      )
    })

    it('shows the transcript log region', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())
    })

    it('keeps the session id and raw flow state out of the header by default', async () => {
      // Issue #501 §2: "Session: sess-… | State: PlayerTurnListening" was the
      // first thing a new player read on this screen.
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('conversation-subhead')).toBeInTheDocument(),
      )
      expect(screen.queryByText(SESSION_ID)).not.toBeInTheDocument()
      expect(screen.queryByText('PlayerTurnListening')).not.toBeInTheDocument()
      expect(screen.getByTestId('conversation-subhead')).toHaveTextContent('Your turn')
    })

    it('shows the session id and raw flow state at the technical wording level', async () => {
      localStorage.setItem('convsim.ui.languageLevel', 'technical')
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByText(SESSION_ID)).toBeInTheDocument())
      expect(screen.getByText('PlayerTurnListening')).toBeInTheDocument()
    })

    it('shows an error alert when startSession fails', async () => {
      mockApi.startSession.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Connection refused' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
    })

    it('shows a back-to-library button when startSession fails fatally', async () => {
      mockApi.startSession.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Connection refused' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /back to library/i })).toBeInTheDocument(),
      )
    })

    it('recovers silently when session was already started (409): hydrates transcript, no error banner', async () => {
      mockApi.startSession.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'INVALID_TRANSITION' } })
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          transcript_saved: true,
          turns: [
            { turn_number: 0, role: 'npc_opening', content: 'Thanks for coming in. Tell me about yourself.', flow_state_after: 'PlayerTurnListening' },
            { turn_number: 1, role: 'player', content: 'Happy to be here.', flow_state_after: 'NpcThinking' },
            { turn_number: 2, role: 'npc', content: 'Great — walk me through your background.', flow_state_after: 'PlayerTurnListening' },
          ],
        },
      })
      renderConversation()
      // The prior turns are rehydrated (opening included) …
      await waitFor(() =>
        expect(screen.getByText('Thanks for coming in. Tell me about yourself.')).toBeInTheDocument(),
      )
      expect(screen.getByText('Great — walk me through your background.')).toBeInTheDocument()
      // … the conversation is interactive …
      expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument()
      // … and no scary error banner covers a working conversation.
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('restores the meters when resuming, not just the transcript', async () => {
      // Issue #501 §1 and §3: meter values only ever arrived with a turn, so a
      // player who stepped out to Settings came back to a conversation with no
      // meters at all — on the screen whose opening line tells them to watch
      // the two meters above it — until they sent another message.
      mockApi.startSession.mockResolvedValue({
        ok: false,
        error: { kind: 'network', message: 'INVALID_TRANSITION' },
      })
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          transcript_saved: true,
          turns: [
            { turn_number: 0, role: 'npc_opening', content: 'Thanks for coming in.', flow_state_after: 'PlayerTurnListening' },
            { turn_number: 1, role: 'player', content: 'Happy to be here.', flow_state_after: 'NpcThinking' },
            { turn_number: 2, role: 'npc', content: 'Walk me through your background.', flow_state_after: 'PlayerTurnListening' },
          ],
        },
      })
      mockApi.getSession.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          state: 'PlayerTurnListening',
          created_at: '2026-07-01T00:00:00Z',
          setup: {},
          turn_count: 1,
          visible_state: { trust: 62, patience: 70 },
        },
      } as never)
      renderConversation()

      await waitFor(() => expect(screen.getByTestId('state-vars')).toBeInTheDocument())
      expect(screen.getByTestId('state-meter-trust')).toHaveTextContent('62')
      expect(screen.getByTestId('state-meter-patience')).toHaveTextContent('70')
      // Nothing moved on arrival: the values the session was left at are the
      // baseline, not a change from anything.
      expect(screen.getByTestId('state-meter-delta-trust')).not.toHaveTextContent('+')
    })

    it('keeps counting whole turns when resuming a session that saves no transcript', async () => {
      // Issue #501 §4: the transcript endpoint answers a session started with
      // transcript saving off with no rows, always, so there is nothing to count
      // the resumed turns from and the labels restarted at "Turn 1" over a
      // session the server was three turns into — the debrief-says-4 /
      // transcript-says-1 mismatch again, on the screen resume was added for.
      mockApi.startSession.mockResolvedValue({
        ok: false,
        error: { kind: 'network', message: 'INVALID_TRANSITION' },
      })
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          transcript_saved: false,
          message: 'Transcript saving is disabled for this session.',
          turns: [],
        },
      })
      mockApi.getSession.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          state: 'PlayerTurnListening',
          created_at: '2026-07-01T00:00:00Z',
          setup: { save_transcript: false },
          turn_count: 3,
          visible_state: { trust: 55 },
        },
      } as never)
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()

      // Wait for the session read to land before sending, so the counter is
      // seeded rather than racing the player's message.
      await waitFor(() => expect(screen.getByTestId('state-meter-trust')).toHaveTextContent('55'))
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Picking up where we left off.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
      )
      // Three whole turns already played, so this exchange is the fourth — both
      // halves of it, and nothing numbered 1.
      expect(screen.getAllByText('Turn 4')).toHaveLength(2)
      expect(screen.queryByText('Turn 1')).not.toBeInTheDocument()
    })

    it('restores the voice input mode when resuming, not just the transcript', async () => {
      // Issue #501 §1: the resume path has no route state, so the composer
      // mounted text-only, and VoiceInput decides text-only versus mic once, at
      // mount. The input mode read back from the server arrived too late to be
      // honoured and a push-to-talk session came back without its mic.
      mockApi.startSession.mockResolvedValue({
        ok: false,
        error: { kind: 'network', message: 'INVALID_TRANSITION' },
      })
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          transcript_saved: true,
          turns: [
            { turn_number: 0, role: 'npc_opening', content: 'Thanks for coming in.', flow_state_after: 'PlayerTurnListening' },
          ],
        },
      })
      mockApi.getSession.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: 'behavioral_interview',
          state: 'PlayerTurnListening',
          created_at: '2026-07-01T00:00:00Z',
          setup: { input_mode: 'push-to-talk' },
          turn_count: 0,
          visible_state: {},
        },
      } as never)
      renderConversation()

      // jsdom has no MediaRecorder, so the voice-mode composer reports capture
      // as unsupported — a notice only that composer renders, which makes it
      // the marker that the mode was restored. The text-only composer's own
      // notice must be gone with it.
      await waitFor(() =>
        expect(screen.getByText(/microphone capture is not supported/i)).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('text-only-notice')).not.toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument()
    })
  })

  describe('NPC panel', () => {
    it('renders the NPC panel with placeholder', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('npc-panel')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('npc-panel')).toHaveTextContent('NPC')
    })

    it('shows npc status as Thinking while submitting', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'Hello' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByTestId('npc-status')).toHaveTextContent('Thinking…'),
      )
    })

    it('disables text input and submit button while NPC is thinking', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'Hello' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByTestId('npc-status')).toHaveTextContent('Thinking…'),
      )
      expect(screen.getByRole('textbox', { name: /your response/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
    })

    it('updates npc emotion when turn has non-neutral emotion', async () => {
      const emotionalTurnResponse: TurnResponse = {
        ...turnResponse,
        events: [
          turnResponse.events[0],
          {
            ...turnResponse.events[1],
            payload: { ...turnResponse.events[1].payload, emotion: 'curious' },
          },
        ],
      }
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: emotionalTurnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Test message' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByTestId('npc-emotion')).toHaveTextContent('curious'),
      )
    })
  })

  describe('scene card', () => {
    it('renders scene card when scenario data is available', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.getScenario.mockResolvedValue({ ok: true, data: mockScenario })
      renderConversation({ scenario_id: SCENARIO_ID })
      await waitFor(() =>
        expect(screen.getByTestId('scene-card')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('scene-card')).toHaveTextContent('Software Engineer Interview')
    })

    it('does not render scene card without scenario data', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('npc-panel')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('scene-card')).not.toBeInTheDocument()
    })
  })

  describe('player turn submission', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
    })

    it('renders the text input and submit button', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
    })

    it('submit button is disabled when input is empty', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled(),
      )
    })

    it('submits a turn and shows player and NPC messages in the transcript', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'I have five years of experience.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(
          screen.getByText('I have five years of experience.'),
        ).toBeInTheDocument(),
      )
      await waitFor(() =>
        expect(
          screen.getByText('Hello there. I am a simulated NPC.'),
        ).toBeInTheDocument(),
      )
    })

    it('clears the input after a successful turn', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'Hello there!' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect((screen.getByRole('textbox', { name: /your response/i }) as HTMLTextAreaElement).value).toBe(''),
      )
    })

    it('shows an error alert when submitTurn fails', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Turn failed' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'Test turn' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
    })

    it('rolls back the optimistic player turn when submitTurn fails', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Turn failed' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'This will fail.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
      // The failed message must not linger in the transcript.
      expect(screen.queryByText('This will fail.')).not.toBeInTheDocument()

      // A successful retry is the first whole turn, with no gap or duplicate
      // from the rolled-back attempt.
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Retry message.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByText('Retry message.')).toBeInTheDocument(),
      )
      // Opening is labelled, the retry's message and the reply to it are both
      // "Turn 1" (issue #501 §4). The absence of a Turn 2 confirms the failed
      // attempt did not consume a turn number.
      expect(screen.getByText('Opening')).toBeInTheDocument()
      expect(screen.getAllByText('Turn 1')).toHaveLength(2)
      expect(screen.queryByText('Turn 2')).not.toBeInTheDocument()
    })

    it('labels the opening rather than numbering it as a turn', async () => {
      // Issue #501 §4: the opening answers nothing, so it is not half a turn.
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByText('Thanks for coming in. Tell me about yourself.')).toBeInTheDocument(),
      )
      expect(screen.getByText('Opening')).toBeInTheDocument()
      expect(screen.queryByText(/Turn 1/)).not.toBeInTheDocument()
    })

    it('numbers one player message and the reply to it as a single turn', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'I have five years of experience.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
      )
      // Both halves of the exchange carry Turn 1 — which is also what
      // convsim-core counts in turn_count and what max_turns is measured in.
      const labels = screen.getAllByText('Turn 1')
      expect(labels).toHaveLength(2)
      expect(screen.queryByText('Turn 2')).not.toBeInTheDocument()
      expect(screen.queryByText('Turn 3')).not.toBeInTheDocument()
    })

    it('shows the player message immediately after submit without waiting for REST', async () => {
      // submitTurn never resolves — simulates slow network
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Fast message.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      // Player turn must appear before REST resolves
      await waitFor(() =>
        expect(screen.getByText('Fast message.')).toBeInTheDocument(),
      )
    })
  })

  describe('transcript persistence', () => {
    it('accumulates all turns in the transcript across multiple consecutive submissions', async () => {
      const secondTurnResponse: TurnResponse = {
        session_id: SESSION_ID,
        state: 'PlayerTurnListening',
        events: [
          {
            event_id: 4,
            session_id: SESSION_ID,
            event_type: 'player_turn',
            payload: { content: 'Tell me more about the role.' },
            created_at: '2026-07-01T00:00:03Z',
          },
          {
            event_id: 5,
            session_id: SESSION_ID,
            event_type: 'npc_turn',
            payload: {
              content: 'The role involves leading a small engineering team.',
              emotion: 'neutral',
              state_delta: {},
              event_flags: [],
              safety: { status: 'ok' },
              ending_type: null,
            },
            created_at: '2026-07-01T00:00:04Z',
          },
        ],
      }

      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn
        .mockResolvedValueOnce({ ok: true, data: turnResponse })
        .mockResolvedValueOnce({ ok: true, data: secondTurnResponse })

      renderConversation()
      await waitFor(() =>
        expect(
          screen.getByText('Thanks for coming in. Tell me about yourself.'),
        ).toBeInTheDocument(),
      )

      // First turn
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'I have five years of experience.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      await waitFor(() =>
        expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
      )

      // Second turn
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Tell me more about the role.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      await waitFor(() =>
        expect(
          screen.getByText('The role involves leading a small engineering team.'),
        ).toBeInTheDocument(),
      )

      // All previous turns must still be visible — the transcript accumulates.
      expect(
        screen.getByText('Thanks for coming in. Tell me about yourself.'),
      ).toBeInTheDocument()
      expect(screen.getByText('I have five years of experience.')).toBeInTheDocument()
      expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument()
      expect(screen.getByText('Tell me more about the role.')).toBeInTheDocument()
    })
  })

  describe('recoverable errors', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
    })

    it('shows a recoverable error when model output fails validation and re-enables input', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'NPC output failed validation after 3 retries' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'My answer.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
      // Input must be re-enabled so the player can retry (recoverable).
      expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
    })

    it('shows a recoverable error when the local runtime becomes unavailable', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Runtime unavailable: llama-server exited unexpectedly' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'My answer.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
      // Rolled-back turn must not remain in the transcript.
      expect(screen.queryByText('My answer.')).not.toBeInTheDocument()
      // Session must remain interactive so the player can retry.
      expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
    })
  })

  describe('conversation meters', () => {
    it('shows the meters when show_state_meters is true (default)', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('state-vars')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('state-vars')).toHaveTextContent('Trust')
      expect(screen.getByTestId('state-vars')).toHaveTextContent('Patience')
    })

    it('humanizes snake_case variable names in plain wording', async () => {
      // Issue #501 §3: "objective_progress" is a YAML key, not a label.
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('state-vars')).toBeInTheDocument())
      expect(screen.getByTestId('state-meter-objective_progress')).toHaveTextContent(
        'Objective progress',
      )
    })

    it('keeps the raw variable keys at the technical wording level', async () => {
      localStorage.setItem('convsim.ui.languageLevel', 'technical')
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('state-vars')).toBeInTheDocument())
      expect(screen.getByTestId('state-meter-objective_progress')).toHaveTextContent(
        'objective_progress',
      )
    })

    it('sits above the transcript, where the tutorial says the meters are', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('state-vars')).toBeInTheDocument())
      const meters = screen.getByTestId('state-vars')
      const transcript = screen.getByRole('log')
      // Node.DOCUMENT_POSITION_FOLLOWING === 4: the transcript comes after.
      expect(meters.compareDocumentPosition(transcript) & 4).toBeTruthy()
    })

    it('shows how far each meter moved on the latest turn', async () => {
      // The tutorial says "Engagement just ticked up"; nothing on screen used
      // to tick (issue #501 §3).
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({
        ok: true,
        data: {
          ...turnResponse,
          events: [
            turnResponse.events[0],
            {
              ...turnResponse.events[1],
              payload: {
                ...turnResponse.events[1].payload,
                visible_state: { trust: 60, patience: 75, rapport: 50, openness: 50, objective_progress: 0 },
              },
            },
          ],
        },
      })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Something encouraging.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByTestId('state-meter-delta-trust')).toHaveTextContent('+10'),
      )
      // A meter that did not move says nothing.
      expect(screen.getByTestId('state-meter-delta-patience')).not.toHaveTextContent('+')
    })

    it('keeps the movement when the authoritative snapshot repeats it', async () => {
      // One turn produces two snapshots: npc.final applies the delta
      // optimistically, then session.state delivers the same numbers as fact.
      // Measured against the previous snapshot the second one is a move of
      // zero, which wiped the arrow the first one had just earned — so the
      // tick the tutorial talks about flashed and vanished (issue #501 §3).
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Something encouraging.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      const moved = { trust: 60, patience: 75, rapport: 50, openness: 50, objective_progress: 0 }
      act(() => {
        wsCallback?.({
          type: 'npc.final',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: {
            content: 'Good to hear.',
            emotion: 'warm',
            state_delta: { trust: 10 },
            event_flags: [],
          },
        })
      })
      await waitFor(() =>
        expect(screen.getByTestId('state-meter-delta-trust')).toHaveTextContent('+10'),
      )

      act(() => {
        wsCallback?.({
          type: 'session.state',
          seq: 2,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:01Z',
          payload: { state: 'PlayerTurnListening', state_vars: moved, ending_type: null },
        })
      })
      expect(screen.getByTestId('state-meter-delta-trust')).toHaveTextContent('+10')
    })

    it('hides state variables when show_state_meters is false', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation({ show_state_meters: false })
      await waitFor(() =>
        expect(screen.getByTestId('npc-panel')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('state-vars')).not.toBeInTheDocument()
    })
  })

  describe('event and safety banners', () => {
    it('shows a scenario event banner when websocket delivers scenario.event', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('npc-panel')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'scenario.event',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { flags: ['rapport_milestone'] },
        })
      })

      await waitFor(() =>
        expect(screen.getByTestId('banner-event')).toBeInTheDocument(),
      )
      // Issue #501 §2: "Scenario event: rapport_milestone" is two pieces of
      // jargon and an identifier. Plain wording says what happened.
      expect(screen.getByTestId('banner-event')).toHaveTextContent(
        'Something changed: Rapport milestone',
      )
    })

    it('announces a scenario event the engine fired on the turn', async () => {
      // Engine-fired events (a meter crossing a threshold) arrive only on the
      // npc_turn payload as triggered_scenario_events, and nothing read them:
      // the banner was fed solely by the WebSocket scenario.event frame, which
      // carries the NPC's self-declared flags and which convsim-core does not
      // send. So the tutorial fired warm_moment and then told the player they
      // "would have seen a short note above the transcript" (issue #501 §3).
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({
        ok: true,
        data: {
          ...turnResponse,
          events: [
            turnResponse.events[0],
            {
              ...turnResponse.events[1],
              payload: {
                ...turnResponse.events[1].payload,
                triggered_scenario_events: ['warm_moment'],
              },
            },
          ],
        },
      })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Something encouraging.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByTestId('banner-event')).toHaveTextContent(
          'Something changed: Warm moment',
        ),
      )
    })

    it('keeps the raw event flags in the banner at the technical level', async () => {
      localStorage.setItem('convsim.ui.languageLevel', 'technical')
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('npc-panel')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'scenario.event',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { flags: ['rapport_milestone'] },
        })
      })

      await waitFor(() =>
        expect(screen.getByTestId('banner-event')).toHaveTextContent(
          'Scenario event: rapport_milestone',
        ),
      )
    })

    it('shows a safety redirect banner when websocket delivers safety.redirect', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('npc-panel')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'safety.redirect',
          seq: 2,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:01Z',
          payload: { reason: 'Off-topic content detected.' },
        })
      })

      await waitFor(() =>
        expect(screen.getByTestId('banner-safety')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('banner-safety')).toHaveTextContent('Off-topic content detected.')
    })

    it('dismisses a banner when the dismiss button is clicked', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('npc-panel')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'scenario.event',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { flags: ['rapport_milestone'] },
        })
      })

      await waitFor(() => expect(screen.getByTestId('banner-event')).toBeInTheDocument())
      fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
      await waitFor(() =>
        expect(screen.queryByTestId('banner-event')).not.toBeInTheDocument(),
      )
    })
  })

  describe('websocket token streaming', () => {
    it('shows streaming text as NPC types via npc.token events', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Tell me more.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      act(() => {
        wsCallback?.({
          type: 'npc.token',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { text: 'Great ' },
        })
        wsCallback?.({
          type: 'npc.token',
          seq: 2,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { text: 'question!' },
        })
      })

      await waitFor(() =>
        expect(screen.getByTestId('streaming-turn')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('streaming-turn')).toHaveTextContent('Great question!')
    })

    it('commits npc turn to transcript when npc.final arrives before REST completes', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      // submitTurn never resolves — simulates LLM streaming finishing before REST returns
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Tell me more.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      // Deliver streaming tokens then the final event via WebSocket
      act(() => {
        wsCallback?.({
          type: 'npc.token',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { text: 'Great ' },
        })
        wsCallback?.({
          type: 'npc.token',
          seq: 2,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { text: 'question!' },
        })
        wsCallback?.({
          type: 'npc.final',
          seq: 3,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:01Z',
          payload: {
            content: 'Great question!',
            emotion: 'curious',
            state_delta: {},
            event_flags: [],
          },
        })
      })

      // NPC turn committed from WS — streaming bubble gone, committed turn present
      await waitFor(() =>
        expect(screen.queryByTestId('streaming-turn')).not.toBeInTheDocument(),
      )
      expect(screen.getByText('Great question!')).toBeInTheDocument()
      // Emotion update from npc.final should show in the NPC panel
      expect(screen.getByTestId('npc-emotion')).toHaveTextContent('curious')
    })

    it('clears streaming text when REST turn completes', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      // Emit some streaming tokens
      act(() => {
        wsCallback?.({
          type: 'npc.token',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { text: 'Partial text…' },
        })
      })

      // Submit turn (REST)
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Hello' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      // After REST completes, streaming bubble should be gone
      await waitFor(() =>
        expect(screen.queryByTestId('streaming-turn')).not.toBeInTheDocument(),
      )
      // Final NPC content from REST should be present
      expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument()
    })

    it('clears streaming text when the turn fails', async () => {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Turn failed' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Tell me more.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      // Partial tokens stream in before the REST call rejects.
      act(() => {
        wsCallback?.({
          type: 'npc.token',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:01:00Z',
          payload: { text: 'Partial…' },
        })
      })

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
      // No phantom streaming bubble should linger next to the error.
      expect(screen.queryByTestId('streaming-turn')).not.toBeInTheDocument()
    })
  })

  describe('streaming sentence by sentence (issue #538)', () => {
    function connectWith(): { fire: (event: WsEvent) => void } {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      return { fire: (event) => act(() => wsCallback?.(event)) }
    }

    function ev<T extends WsEvent['type']>(type: T, payload: Extract<WsEvent, { type: T }>['payload'], seq = 1): WsEvent {
      return { type, seq, session_id: SESSION_ID, ts: '2026-07-01T00:01:00Z', payload } as WsEvent
    }

    async function submitFirst(text = 'Tell me more.') {
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), { target: { value: text } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
    }

    it('commits the line from npc.final with content only and re-enables the reply box before the turn commits', async () => {
      const { fire } = connectWith()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await submitFirst()

      fire(ev('npc.token', { text: 'First sentence.' }, 1))
      fire(ev('npc.token', { text: ' Second one.' }, 2))
      await waitFor(() => expect(screen.getByTestId('streaming-turn')).toHaveTextContent('First sentence. Second one.'))
      // Still writing: the box is disabled.
      expect(screen.getByRole('textbox', { name: /your response/i })).toBeDisabled()

      fire(ev('npc.final', { content: 'First sentence. Second one.' }, 3))
      await waitFor(() => expect(screen.queryByTestId('streaming-turn')).not.toBeInTheDocument())
      expect(screen.getByText('First sentence. Second one.')).toBeInTheDocument()
      // The line is complete: the player can type again while the core finishes.
      expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      // No emotion was claimed before the commit reported one.
      expect(screen.queryByTestId('npc-emotion')).not.toBeInTheDocument()
      expect(screen.getByTestId('turn-finishing-indicator')).toHaveTextContent(/updating the scene/i)
    })

    it('applies the emotion, flags and meters from scenario.state_delta onto the committed row', async () => {
      const { fire } = connectWith()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ show_state_meters: true })
      await submitFirst()

      fire(ev('npc.token', { text: 'Interesting.' }, 1))
      fire(ev('npc.final', { content: 'Interesting.' }, 2))
      fire(ev('scenario.state_delta', {
        delta: { trust: 5 },
        state_vars: { trust: 55, patience: 75, rapport: 50, openness: 50, objective_progress: 0 },
        turn_number: 1,
        emotion: 'impressed',
        event_flags: ['honesty_demonstrated'],
        triggered_scenario_events: [],
        ending_type: null,
      }, 3))

      await waitFor(() => expect(screen.getByTestId('npc-emotion')).toHaveTextContent(/impressed/i))
      expect(screen.getByTestId('turn-mood')).toHaveTextContent(/impressed/i)
      const trust = screen.getByRole('meter', { name: /trust/i })
      expect(trust).toHaveAttribute('aria-valuenow', '55')
    })

    it('queues a message sent before the commit and delivers it exactly once when the turn lands', async () => {
      const { fire } = connectWith()
      let resolveFirst: ((r: { ok: true; data: TurnResponse }) => void) | null = null
      mockApi.submitTurn
        .mockReturnValueOnce(new Promise((r) => { resolveFirst = r }))
        .mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await submitFirst('Opening question.')

      fire(ev('npc.token', { text: 'Here is the reply.' }, 1))
      fire(ev('npc.final', { content: 'Here is the reply.' }, 2))
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled(),
      )

      // The player answers before the core has saved the turn.
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), { target: { value: 'My follow-up.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      await waitFor(() => expect(screen.getByTestId('queued-message')).toHaveTextContent('My follow-up.'))
      expect(mockApi.submitTurn).toHaveBeenCalledTimes(1)

      // The first turn commits; the queued message goes out once.
      await act(async () => {
        resolveFirst!({ ok: true, data: turnResponse })
      })
      await waitFor(() => expect(mockApi.submitTurn).toHaveBeenCalledTimes(2))
      expect(mockApi.submitTurn).toHaveBeenLastCalledWith(SESSION_ID, 'My follow-up.', false)
      await waitFor(() => expect(screen.queryByTestId('queued-message')).not.toBeInTheDocument())
      // Both messages are in the transcript, numbered as two whole turns.
      await waitFor(() => expect(screen.getByText('My follow-up.')).toBeInTheDocument())
      // The label is two spans ("Turn 2" · "You"); the follow-up opened whole turn 2.
      expect(screen.getAllByText('Turn 2').length).toBeGreaterThanOrEqual(1)
    })

    it('lets the player remove a queued message instead of sending it', async () => {
      const { fire } = connectWith()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await submitFirst()
      fire(ev('npc.final', { content: 'Reply.' }, 1))
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), { target: { value: 'Never mind.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      await waitFor(() => expect(screen.getByTestId('queued-message')).toBeInTheDocument())
      fireEvent.click(screen.getByRole('button', { name: /remove queued message/i }))
      expect(screen.queryByTestId('queued-message')).not.toBeInTheDocument()
      expect(mockApi.submitTurn).toHaveBeenCalledTimes(1)
    })

    it('applies the REST snapshot when the row was committed over the socket', async () => {
      const { fire } = connectWith()
      let resolveTurn: ((r: { ok: true; data: TurnResponse }) => void) | null = null
      mockApi.submitTurn.mockReturnValueOnce(new Promise((r) => { resolveTurn = r }))
      renderConversation({ show_state_meters: true })
      await submitFirst()
      fire(ev('npc.final', { content: 'Hello there. I am a simulated NPC.' }, 1))
      await act(async () => {
        resolveTurn!({
          ok: true,
          data: {
            ...turnResponse,
            events: [
              turnResponse.events[0],
              {
                ...turnResponse.events[1],
                payload: {
                  ...turnResponse.events[1].payload,
                  emotion: 'curious',
                  event_flags: ['asked_a_question'],
                  visible_state: { trust: 61, patience: 75, rapport: 50, openness: 50, objective_progress: 0 },
                },
              },
            ],
          },
        })
      })
      // One row, not two; and the REST state landed on it.
      await waitFor(() => expect(screen.getByTestId('npc-emotion')).toHaveTextContent(/curious/i))
      expect(screen.getAllByText('Hello there. I am a simulated NPC.')).toHaveLength(1)
      expect(screen.getByRole('meter', { name: /trust/i })).toHaveAttribute('aria-valuenow', '61')
    })

    it('records the stage the core reports while the turn runs', async () => {
      const { fire } = connectWith()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await submitFirst()
      fire(ev('turn.progress', { stage: 'reading', prompt: { processed: 256, total: 2034, cached: 0 }, output_tokens: 0, elapsed_ms: 3000 }, 1))
      await waitFor(() => expect(screen.getByTestId('conversation-page')).toHaveAttribute('data-turn-stage', 'reading'))
      fire(ev('turn.progress', { stage: 'writing', prompt: null, output_tokens: 3, elapsed_ms: 9000 }, 2))
      await waitFor(() => expect(screen.getByTestId('conversation-page')).toHaveAttribute('data-turn-stage', 'writing'))
      // Writing counts as streaming for the panel even before a sentence lands.
      expect(screen.getByTestId('npc-turn-progress-heading')).toHaveTextContent(/replying/i)
    })
  })

  describe('live turn progress (issue #539)', () => {
    const namedScenario: ScenarioInfo = { ...mockScenario, npc_name: 'Dana Whitfield' }

    function connect(): { fire: (event: WsEvent) => void } {
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.getScenario.mockResolvedValue({ ok: true, data: namedScenario })
      return { fire: (event) => act(() => wsCallback?.(event)) }
    }
    const progress = (stage: TurnStage, prompt: { processed: number; total: number; cached: number } | null, seq: number): WsEvent =>
      ({ type: 'turn.progress', seq, session_id: SESSION_ID, ts: 't', payload: { stage, prompt, output_tokens: 0, elapsed_ms: seq * 1000 } }) as WsEvent

    async function submitFirst() {
      await waitFor(() => expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument())
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), { target: { value: 'Hello.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
    }

    it('shows the stages in order, in the fiction, with the character\'s name, and the thinking bar as read ÷ total', async () => {
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      const heading = () => screen.getByTestId('npc-turn-progress-heading')

      fire(progress('waiting', null, 1))
      await waitFor(() => expect(heading()).toHaveTextContent('Dana Whitfield is getting ready…'))
      fire(progress('reading', { processed: 509, total: 2036, cached: 0 }, 2))
      await waitFor(() => expect(heading()).toHaveTextContent('Dana Whitfield is thinking…'))
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25')
      fire(progress('reading', { processed: 2036, total: 2036, cached: 0 }, 3))
      await waitFor(() => expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100'))
      fire(progress('writing', null, 4))
      await waitFor(() => expect(heading()).toHaveTextContent('Dana Whitfield is replying…'))
      // Focus rests on the panel during the wait, never on the page body.
      expect(document.activeElement).toBe(screen.getByTestId('npc-turn-progress'))
    })

    it('estimates when the reply will start from this machine\'s speeds, and drops it once words arrive', async () => {
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'llama_cpp', model_id: 'm', samples: 5, reading_tps: 87, writing_tps: 6.5, first_token_ms: 24000, first_words_ms: 27000, total_ms: 62000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      // Before any progress report: the measured time to first words, as a range.
      fire(progress('waiting', null, 1))
      await waitFor(() => expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(/Reply starts in about 20–35 s\./))
      // 1,527 unread tokens at 87 tokens/s plus one short sentence at 6.5 tokens/s ≈ 21 s.
      fire(progress('reading', { processed: 509, total: 2036, cached: 0 }, 2))
      await waitFor(() => expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(/Reply starts in about 15–25 s\./))
      // Words arriving: no estimate.
      fire({ type: 'npc.token', seq: 3, session_id: SESSION_ID, ts: 't', payload: { text: 'Well.' } })
      await waitFor(() => expect(screen.queryByTestId('npc-turn-progress-detail')).not.toBeInTheDocument())
    })

    it('announces each stage once, however many progress reports the read takes', async () => {
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'llama_cpp', model_id: 'm', samples: 5, reading_tps: 87, writing_tps: 6.5, first_token_ms: 24000, first_words_ms: 27000, total_ms: 62000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      const status = () => screen.getByTestId('npc-turn-progress-status').textContent
      const detail = () => screen.queryByTestId('npc-turn-progress-detail')?.textContent ?? ''
      fire(progress('waiting', null, 1))
      await waitFor(() => expect(status()).toMatch(/getting ready… Reply starts/))
      const heard = new Set([status()])
      const captions = new Set<string>()
      // A 2,036-token prompt reported in 509-token batches, the way
      // llama-server reports it.
      for (const [i, processed] of [509, 1018, 1527].entries()) {
        fire(progress('reading', { processed, total: 2036, cached: 0 }, i + 2))
        heard.add(status())
        captions.add(detail())
      }
      // The caption followed the read …
      expect(captions.size).toBe(3)
      // … and the status region spoke once for getting ready and once for
      // thinking, not once per batch.
      expect([...heard]).toEqual([
        'Dana Whitfield is getting ready… Reply starts in about 20–35 s.',
        'Dana Whitfield is thinking… Reply starts in about 15–25 s.',
      ])
    })

    it('quotes a CPU-speed read in minutes, not in three-digit seconds', async () => {
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'llama_cpp', model_id: 'm', samples: 5, reading_tps: 20, writing_tps: 3, first_token_ms: 90000, first_words_ms: 100000, total_ms: 180000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      // 2,000 unread tokens at 20 tokens/s plus one short sentence at 3: 108 s.
      fire(progress('reading', { processed: 200, total: 2200, cached: 0 }, 1))
      await waitFor(() => expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent('Reply starts in about 1–2 min.'))
    })

    it('counts the measured time to first words down with the clock, and withdraws it once it has passed', async () => {
      // An engine that reports no reading progress (Ollama, or a llama-server
      // that refuses the progress field) leaves only this machine's median
      // time to first words. That median runs from the moment the turn went
      // out, so it is a whole-wait figure: quoted unchanged, it promised the
      // full 27 s again at 20 s and at 40 s.
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'ollama', model_id: 'm', samples: 5, reading_tps: null, writing_tps: null, first_token_ms: 24000, first_words_ms: 27000, total_ms: 62000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation({ scenario_id: SCENARIO_ID })
        await submitFirst()
        const detail = () => screen.queryByTestId('npc-turn-progress-detail')
        fire(progress('waiting', null, 1))
        await waitFor(() => expect(detail()).toHaveTextContent('Reply starts in about 20–35 s.'))
        await vi.advanceTimersByTimeAsync(10_000)
        expect(detail()).toHaveTextContent('Reply starts in about 15–20 s.')
        await vi.advanceTimersByTimeAsync(10_000)
        expect(detail()).toHaveTextContent('Reply starts in about 6–9 s.')
        // Past the median there is nothing honest left to quote: the stage and
        // the clock carry on alone.
        await vi.advanceTimersByTimeAsync(20_000)
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('40s')
        expect(detail()).not.toBeInTheDocument()
      } finally {
        vi.useRealTimers()
      }
    })

    it('counts a reading estimate down from the report it was built from', async () => {
      // The last report of a read can be the last word for a while: once the
      // prompt is read, nothing more arrives until the first sentence does.
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'llama_cpp', model_id: 'm', samples: 5, reading_tps: 87, writing_tps: 2, first_token_ms: 24000, first_words_ms: 27000, total_ms: 62000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation({ scenario_id: SCENARIO_ID })
        await submitFirst()
        const detail = () => screen.queryByTestId('npc-turn-progress-detail')
        // Fully read: one short sentence at 2 tokens/s, 12 s from this report.
        fire(progress('reading', { processed: 2036, total: 2036, cached: 0 }, 1))
        await waitFor(() => expect(detail()).toHaveTextContent('Reply starts in about 10–15 s.'))
        await vi.advanceTimersByTimeAsync(6_000)
        expect(detail()).toHaveTextContent('Reply starts in about 5–8 s.')
      } finally {
        vi.useRealTimers()
      }
    })

    it('shows no estimate when the expected wait is under the threshold', async () => {
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'llama_cpp', model_id: 'm', samples: 5, reading_tps: 2000, writing_tps: 60, first_token_ms: 900, first_words_ms: 1200, total_ms: 6000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      fire(progress('reading', { processed: 100, total: 300, cached: 0 }, 1))
      await waitFor(() => expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '33'))
      expect(screen.queryByTestId('npc-turn-progress-detail')).not.toBeInTheDocument()
    })

    it('quotes no estimate while a failed reply is tried again', async () => {
      // The repair is a second, unstreamed generation. Neither the first one's
      // progress report nor this machine's time to first words says when it
      // will be done, so the panel names the stage and quotes nothing.
      mockApi.getRollingSpeeds.mockResolvedValue({
        ok: true,
        data: { runtime_id: 'llama_cpp', model_id: 'm', samples: 5, reading_tps: 87, writing_tps: 6.5, first_token_ms: 24000, first_words_ms: 27000, total_ms: 62000 },
      })
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      fire(progress('reading', { processed: 509, total: 2036, cached: 0 }, 1))
      await waitFor(() => expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(/Reply starts in about/))
      fire(progress('checking', null, 2))
      await waitFor(() => expect(screen.getByTestId('npc-turn-progress-heading')).toHaveTextContent('Dana Whitfield is trying that again…'))
      expect(screen.queryByTestId('npc-turn-progress-detail')).not.toBeInTheDocument()
      expect(screen.getByTestId('npc-turn-progress-status')).not.toHaveTextContent(/Reply starts/)
    })

    it('keeps the finishing stage visible with the meters hidden', async () => {
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID, show_state_meters: false })
      await submitFirst()
      fire({ type: 'npc.final', seq: 1, session_id: SESSION_ID, ts: 't', payload: { content: 'Done talking.' } })
      fire(progress('finishing', null, 2))
      await waitFor(() => expect(screen.getByTestId('turn-finishing-indicator')).toHaveTextContent('Updating the scene…'))
      expect(screen.queryByTestId('state-meters')).not.toBeInTheDocument()
    })

    it('never puts engine jargon on the screen, in any state', async () => {
      const { fire } = connect()
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation({ scenario_id: SCENARIO_ID })
      await submitFirst()
      for (const stage of ['waiting', 'reading', 'writing', 'checking', 'voice'] as const) {
        fire(progress(stage, stage === 'reading' ? { processed: 1, total: 2, cached: 0 } : null, 1))
        const text = document.body.textContent ?? ''
        expect(text).not.toMatch(/first token|GPU layers|context length/i)
      }
    })
  })

  describe('debug drawer', () => {
    afterEach(() => {
      localStorage.removeItem('convsim.devMode')
    })

    it('renders the debug drawer in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('debug-drawer')).toBeInTheDocument())
    })
  })

  describe('end session', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
    })

    it('shows the end session button while active', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /end session/i })).toBeInTheDocument(),
      )
    })

    it('transitions to ended state and shows debrief button', async () => {
      mockApi.endSession.mockResolvedValue({ ok: true, data: endResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /end session/i })).toBeInTheDocument(),
      )

      fireEvent.click(screen.getByRole('button', { name: /end session/i }))

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /generate debrief/i })).toBeInTheDocument(),
      )
    })

    it('shows an error when endSession fails', async () => {
      mockApi.endSession.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'End failed' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /end session/i })).toBeInTheDocument(),
      )

      fireEvent.click(screen.getByRole('button', { name: /end session/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
    })
  })

  describe('developer debug drawer', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      localStorage.removeItem('convsim.devMode')
    })

    afterEach(() => {
      localStorage.removeItem('convsim.devMode')
      vi.unstubAllEnvs()
    })

    it('does not render the debug drawer in normal mode', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByText('Thanks for coming in. Tell me about yourself.')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('debug-drawer')).not.toBeInTheDocument()
    })

    it('renders the debug drawer when dev mode is enabled via localStorage', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('debug-drawer')).toBeInTheDocument(),
      )
    })

    it('renders the debug drawer when VITE_DEV_TOOLS=true build flag is set', async () => {
      vi.stubEnv('VITE_DEV_TOOLS', 'true')
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('debug-drawer')).toBeInTheDocument(),
      )
    })

    it('shows a debug entry for the npc_opening event in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('debug-drawer')).toBeInTheDocument())
      expect(screen.getByText('1 entry')).toBeInTheDocument()
    })

    it('accumulates debug entries as turns are submitted in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'My answer.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      // Opening entry + player entry + NPC entry = 3 entries
      await waitFor(() => expect(screen.getByText('3 entries')).toBeInTheDocument())
    })

    it('creates a player debug entry when a turn is submitted in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'My answer.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      // 3 entries: opening + player turn + NPC turn
      await waitFor(() => expect(screen.getByText('3 entries')).toBeInTheDocument())
    })

    it('debug drawer is not rendered (not just hidden) in normal mode', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('state-vars')).toBeInTheDocument(),
      )
      // The debug drawer must be absent from DOM, not merely invisible
      expect(screen.queryByText('Developer debug')).not.toBeInTheDocument()
    })

    it('hidden NPC agenda field values do not appear in the DOM in normal mode', async () => {
      const HIDDEN_AGENDA = 'HIDDEN_AGENDA_VALUE_abc123'
      mockApi.startSession.mockResolvedValue({ ok: true, data: {
        ...startResponse,
        events: [
          {
            ...startResponse.events[0],
            payload: {
              content: "Thanks for coming in. Tell me about yourself.",
              agenda: HIDDEN_AGENDA,
              hidden_state: 'suspicious',
            },
          },
        ],
      }})
      renderConversation()
      await waitFor(() =>
        expect(screen.getByText('Thanks for coming in. Tell me about yourself.')).toBeInTheDocument(),
      )
      expect(document.body.innerHTML).not.toContain(HIDDEN_AGENDA)
      expect(document.body.innerHTML).not.toContain('suspicious')
    })

    it('surfaces model deltas for unknown variables as rejected in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: {
        ...turnResponse,
        events: [
          turnResponse.events[0],
          {
            ...turnResponse.events[1],
            payload: {
              ...turnResponse.events[1].payload,
              // trust is a tracked variable; made_up_var is not and must be rejected
              state_delta: { trust: 5, made_up_var: 9 },
            },
          },
        ],
      }})
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'My answer.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByLabelText('Contains rejected state delta')).toBeInTheDocument(),
      )
    })
  })

  describe('TTS audio playback', () => {
    let wsCallback: ((event: WsEvent) => void) | null = null

    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
    })

    it('plays audio when tts.audio_chunk event has a cache_path and tts_enabled is true', async () => {
      const mockPlay = vi.fn().mockResolvedValue(undefined)
      const mockAudio = { play: mockPlay, pause: vi.fn(), onended: null as unknown, onerror: null as unknown }
      const AudioSpy = vi.spyOn(window, 'Audio').mockReturnValue(
        mockAudio as unknown as HTMLAudioElement,
      )

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hello there.',
            voice_id: 'af_heart',
            cache_path: '/home/user/.convsim/tts_cache/abc123.wav',
            error: null,
          },
        })
      })

      expect(AudioSpy).toHaveBeenCalledWith('/api/tts/audio/abc123.wav')
      expect(mockPlay).toHaveBeenCalled()

      AudioSpy.mockRestore()
    })

    it('defers playback (thinking pause) when thinking_pause_ms is present and the toggle is enabled', async () => {
      // Toggle defaults to enabled (localStorage key unset).
      localStorage.removeItem('convsim.voice.thinkingPauseEnabled')
      const mockPlay = vi.fn().mockResolvedValue(undefined)
      const AudioSpy = vi.spyOn(window, 'Audio').mockReturnValue(
        { play: mockPlay, pause: vi.fn(), onended: null, onerror: null } as unknown as HTMLAudioElement,
      )

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hello there.',
            voice_id: 'af_heart',
            cache_path: '/home/user/.convsim/tts_cache/abc123.wav',
            error: null,
            thinking_pause_ms: 400,
          },
        })
      })

      // Playback must be held back by the thinking-pause timer, not started synchronously.
      expect(mockPlay).not.toHaveBeenCalled()

      AudioSpy.mockRestore()
    })

    it('skips the thinking pause (immediate playback) when the toggle is disabled', async () => {
      // Voice settings toggle off — the pause must not apply even though the
      // backend still sends thinking_pause_ms.
      localStorage.setItem('convsim.voice.thinkingPauseEnabled', 'false')
      const mockPlay = vi.fn().mockResolvedValue(undefined)
      const AudioSpy = vi.spyOn(window, 'Audio').mockReturnValue(
        { play: mockPlay, pause: vi.fn(), onended: null, onerror: null } as unknown as HTMLAudioElement,
      )

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hello there.',
            voice_id: 'af_heart',
            cache_path: '/home/user/.convsim/tts_cache/abc123.wav',
            error: null,
            thinking_pause_ms: 400,
          },
        })
      })

      expect(mockPlay).toHaveBeenCalled()

      localStorage.removeItem('convsim.voice.thinkingPauseEnabled')
      AudioSpy.mockRestore()
    })

    it('does not play audio when tts_enabled is false (text-only session)', async () => {
      const mockPlay = vi.fn().mockResolvedValue(undefined)
      const AudioSpy = vi.spyOn(window, 'Audio').mockReturnValue(
        { play: mockPlay, pause: vi.fn(), onended: null, onerror: null } as unknown as HTMLAudioElement,
      )

      renderConversation({ tts_enabled: false })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hello there.',
            voice_id: 'af_heart',
            cache_path: '/home/user/.convsim/tts_cache/abc123.wav',
            error: null,
          },
        })
      })

      expect(AudioSpy).not.toHaveBeenCalled()
      expect(mockPlay).not.toHaveBeenCalled()

      AudioSpy.mockRestore()
    })

    it('does not play audio when tts.audio_chunk cache_path is null', async () => {
      const mockPlay = vi.fn().mockResolvedValue(undefined)
      const AudioSpy = vi.spyOn(window, 'Audio').mockReturnValue(
        { play: mockPlay, pause: vi.fn(), onended: null, onerror: null } as unknown as HTMLAudioElement,
      )

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hello there.',
            voice_id: 'af_heart',
            cache_path: null,
            error: 'synthesis failed',
          },
        })
      })

      expect(AudioSpy).not.toHaveBeenCalled()
      expect(mockPlay).not.toHaveBeenCalled()

      AudioSpy.mockRestore()
    })

    it('constructs audio URL from the filename of the cache path', async () => {
      const urls: string[] = []
      const AudioSpy = vi.spyOn(window, 'Audio').mockImplementation(
        (url?: string) => {
          if (url) urls.push(url)
          return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn(), onended: null, onerror: null } as unknown as HTMLAudioElement
        },
      )

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hi.',
            voice_id: 'af_heart',
            cache_path: '/Users/someone/.convsim/tts_cache/deadbeef1234.wav',
            error: null,
          },
        })
      })

      expect(urls).toContain('/api/tts/audio/deadbeef1234.wav')

      AudioSpy.mockRestore()
    })

    it('TTS queue is cleared when a new player turn is submitted', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })

      const pauseMock = vi.fn()
      const mockAudio = {
        play: vi.fn().mockResolvedValue(undefined),
        pause: pauseMock,
        onended: null as unknown,
        onerror: null as unknown,
      }
      const AudioSpy = vi.spyOn(window, 'Audio').mockReturnValue(
        mockAudio as unknown as HTMLAudioElement,
      )

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument())

      // Enqueue a chunk
      act(() => {
        wsCallback?.({
          type: 'tts.audio_chunk',
          seq: 1,
          session_id: SESSION_ID,
          ts: '2026-07-01T00:00:00Z',
          payload: {
            chunk_index: 0,
            total_chunks: 1,
            text: 'Hello.',
            voice_id: 'af_heart',
            cache_path: '/home/user/.convsim/tts_cache/abc.wav',
            error: null,
          },
        })
      })

      // Submit a turn — should stop playback
      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'My response.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      expect(pauseMock).toHaveBeenCalled()

      AudioSpy.mockRestore()
    })

    it('does not double-advance the queue when a chunk both errors and rejects play()', async () => {
      // A failed load can fire the error event and reject the play() promise for
      // the same element. The queue must advance only once — otherwise two chunks
      // play at the same time and one is skipped.
      const created: Array<{ url?: string; onerror: (() => void) | null }> = []
      let rejectFirst: ((err: unknown) => void) | null = null
      const AudioSpy = vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
        const isFirst = created.length === 0
        const el = {
          url,
          pause: vi.fn(),
          onended: null as unknown,
          onerror: null as unknown,
          play: vi.fn().mockImplementation(() =>
            isFirst
              ? new Promise((_resolve, reject) => {
                  rejectFirst = reject
                })
              : Promise.resolve(undefined),
          ),
        }
        created.push(el as unknown as { url?: string; onerror: (() => void) | null })
        return el as unknown as HTMLAudioElement
      })

      renderConversation({ tts_enabled: true })
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())

      const chunk = (name: string, seq: number): WsEvent => ({
        type: 'tts.audio_chunk',
        seq,
        session_id: SESSION_ID,
        ts: '2026-07-01T00:00:00Z',
        payload: {
          chunk_index: seq - 1,
          total_chunks: 3,
          text: name,
          voice_id: 'af_heart',
          cache_path: `/home/user/.convsim/tts_cache/${name}`,
          error: null,
        },
      })

      // Enqueue three chunks; the first is stuck on a pending play() promise.
      act(() => wsCallback?.(chunk('a.wav', 1)))
      act(() => wsCallback?.(chunk('b.wav', 2)))
      act(() => wsCallback?.(chunk('c.wav', 3)))

      // The first chunk fails: fire its error event AND reject its play() promise.
      await act(async () => {
        created[0].onerror?.()
        rejectFirst?.(new Error('load failed'))
        await Promise.resolve()
      })

      // Should have advanced to 'b.wav' exactly once; 'c.wav' must stay queued.
      expect(created.map((el) => el.url)).toEqual([
        '/api/tts/audio/a.wav',
        '/api/tts/audio/b.wav',
      ])

      AudioSpy.mockRestore()
    })
  })

  describe('voice mode integration', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
    })

    it('renders VoiceInput in text-only mode when input_mode is text-only', async () => {
      renderConversation({ input_mode: 'text-only' })
      await waitFor(() =>
        expect(screen.getByTestId('text-only-notice')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('text-only-notice')).toHaveTextContent(
        /voice input disabled/i,
      )
    })

    it('renders VoiceInput with mic button when input_mode is push-to-talk', async () => {
      mockApiClient.uploadAudio.mockResolvedValue({ ok: true, data: { transcript: null, status: 'unavailable' } })
      renderConversation({ input_mode: 'push-to-talk' })
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      // In push-to-talk mode the text-only notice must not appear
      expect(screen.queryByTestId('text-only-notice')).not.toBeInTheDocument()
    })
  })

  describe('session ends via max turns', () => {
    it('shows debrief button when turn response has state=Ended', async () => {
      const endedTurnResponse: TurnResponse = {
        ...turnResponse,
        state: 'Ended',
        events: [
          turnResponse.events[0],
          {
            ...turnResponse.events[1],
            payload: { ...turnResponse.events[1].payload, ending_type: 'timeout' },
          },
        ],
      }
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: endedTurnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'Final message.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /generate debrief/i })).toBeInTheDocument(),
      )
    })
  })

  // A local model on CPU-only hardware legitimately spends a minute or more on
  // one reply. The screen must wait that out, say so while it waits, and never
  // throw away a reply convsim-core already committed (issue #489).
  describe('slow NPC replies (issue #489)', () => {
    const SLOW_TURN_SECONDS = 90
    // When the screen stops trusting the request and starts asking the server.
    const DEADLINE_MS = 300_000
    // When it finally gives up, having polled the server in between.
    const ABANDON_MS = 600_000

    /** Transcript rows convsim-core holds once a turn has been committed. */
    const committedTranscript = {
      session_id: SESSION_ID,
      scenario_id: SCENARIO_ID,
      transcript_saved: true,
      turns: [
        { turn_number: 0, role: 'npc_opening' as const, content: 'Thanks for coming in. Tell me about yourself.', flow_state_after: 'PlayerTurnListening' },
        { turn_number: 1, role: 'player' as const, content: 'My answer.', flow_state_after: 'NpcThinking' },
        { turn_number: 2, role: 'npc' as const, content: 'Committed by the server while the UI waited.', emotion: 'neutral', flow_state_after: 'PlayerTurnListening' },
      ],
    }

    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      mockApi.getSessionTranscript.mockResolvedValue({ ok: true, data: committedTranscript })
    })

    async function submitAndWait(advanceMs: number) {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'My answer.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      await waitFor(() => expect(screen.getByText('My answer.')).toBeInTheDocument())
      await vi.advanceTimersByTimeAsync(advanceMs)
    }

    it('commits a reply that arrives well past the old 60s deadline', async () => {
      let resolveTurn: (r: { ok: true; data: TurnResponse }) => void = () => {}
      mockApi.submitTurn.mockReturnValue(
        new Promise((resolve) => { resolveTurn = resolve }) as never,
      )
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(SLOW_TURN_SECONDS * 1000)
        // Still waiting, not failed: the old deadline would have fired 30s ago.
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()

        resolveTurn({ ok: true, data: turnResponse })
        await waitFor(() =>
          expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
        )
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    it('reports how long it has been waiting, and says so again past 30s', async () => {
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(6_000)
        // The clock runs from the first second of the turn (issue #488) …
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('6s')
        // … and no second notice repeats it in other words: issue #539 folded
        // the fixed 5 s "taking longer than usual" row into the panel, whose
        // heading already says who the player is waiting on. What the panel
        // adds at five seconds is the reply-speed footnote from issue #501, and
        // only that.
        expect(screen.queryByText(/taking longer than usual/i)).not.toBeInTheDocument()
        expect(screen.getByTestId('slow-response-indicator')).toBeInTheDocument()

        await vi.advanceTimersByTimeAsync(60_000)
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('1m 06s')
        // The "not lost" reassurance is the panel's half-minute announcement
        // now; the old second-stage row under the notice went with the notice.
        expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(/not lost/i)
        expect(screen.queryByTestId('slow-response-reassurance')).not.toBeInTheDocument()
      } finally {
        vi.useRealTimers()
      }
    })

    // Issue #501 §1: the playtester hit a slow turn, went to Settings to speed
    // the model up, "was a little unclear on how to do that", and lost the
    // session. The slow-state footnote is where that detour starts, so it names
    // the setting instead of saying "you can adjust settings" — but as text,
    // not a link: the footnote only exists while a turn is in flight, and
    // leaving then loses the pending message on resume and puts the turn
    // numbering one behind the server (issue #501 §4). Since issue #539 it is
    // part of the turn panel rather than a notice of its own.
    it('names the reply-speed setting without a link away from the in-flight turn', async () => {
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(6_000)
        const notice = screen.getByTestId('slow-response-indicator')
        const hint = screen.getByTestId('slow-response-speed-hint')
        expect(hint).toHaveTextContent(/reply speed/i)
        expect(hint).toHaveTextContent(/settings/i)
        // Honest about the timing: changing it now does not shorten this reply.
        expect(hint).toHaveTextContent(/once this reply arrives/i)
        expect(within(notice).queryByRole('link', { hidden: true })).not.toBeInTheDocument()
        expect(screen.queryByText(/you can adjust settings/i)).not.toBeInTheDocument()
        // It reads with the panel, not beside it.
        expect(within(screen.getByTestId('npc-turn-progress')).getByTestId('slow-response-indicator')).toBe(notice)
      } finally {
        vi.useRealTimers()
      }
    })

    it('names the setting in the demo edition too, where reply speed is the only speed lever', async () => {
      // The demo's curated model is fixed and its Settings has no engine panel,
      // so a demo player on modest hardware had "closing other apps usually
      // helps" and nothing else — the exact #501 dead end, in the edition
      // being shipped.
      vi.stubEnv('VITE_CONVSIM_EDITION', 'demo')
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(6_000)
        const notice = screen.getByTestId('slow-response-indicator')
        expect(notice).toHaveTextContent(/closing other apps usually helps/i)
        expect(screen.getByTestId('slow-response-speed-hint')).toHaveTextContent(/reply speed/i)
        expect(within(notice).queryByRole('link', { hidden: true })).not.toBeInTheDocument()
      } finally {
        vi.useRealTimers()
        vi.unstubAllEnvs()
      }
    })

    it('announces the elapsed wait on a coarse grid so the live region is not spammed', async () => {
      // The visible clock ticks every second; left audible that is ~270
      // announcements over a five-minute turn. It is aria-hidden, and a separate
      // status re-announces every 30s only.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(35_000)
        expect(screen.getByTestId('npc-turn-progress-detail')).toHaveAttribute('aria-hidden', 'true')
        const announcement = screen.getByTestId('npc-turn-progress-announcement')
        expect(announcement).toHaveTextContent('30s')

        // Ten more seconds of ticking must not change the announced text.
        await vi.advanceTimersByTimeAsync(10_000)
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('45s')
        expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('30s')

        // Crossing the next interval does.
        await vi.advanceTimersByTimeAsync(20_000)
        expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('1m 00s')
      } finally {
        vi.useRealTimers()
      }
    })

    it('adopts the committed reply when the deadline expires after the turn landed', async () => {
      // The request never resolves (a wedged connection), but the core had
      // already written the turn — the reply must survive, not be rolled back.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(DEADLINE_MS)
        await waitFor(() =>
          expect(
            screen.getByText('Committed by the server while the UI waited.'),
          ).toBeInTheDocument(),
        )
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        // Server copy is authoritative, so the player turn stays and keeps its
        // number — and the server's turn_number is what the whole-turn labels
        // are derived from, so a reconciled transcript numbers identically to
        // one built turn by turn (issue #501 §4).
        expect(screen.getByText('My answer.')).toBeInTheDocument()
        expect(screen.getByText('Opening')).toBeInTheDocument()
        expect(screen.getAllByText('Turn 1')).toHaveLength(2)
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    it('counts an adopted reply as a landed turn: "Your turn." and fresh speeds', async () => {
      // The adopted turn is not timed on the client (its wait measures the
      // polling), but it did land and the core did record it. Skipping the
      // count left a screen-reader player with no "Your turn." on the first
      // turn of a screen, and the reply-start estimate on stale speeds.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(DEADLINE_MS)
        await waitFor(() =>
          expect(screen.getByText('Committed by the server while the UI waited.')).toBeInTheDocument(),
        )
        await waitFor(() => expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent('Your turn.'))
        // Once on opening the screen, and again for the turn that landed.
        await waitFor(() => expect(mockApi.getRollingSpeeds).toHaveBeenCalledTimes(2))
      } finally {
        vi.useRealTimers()
      }
    })

    it('keeps waiting past the deadline and adopts a reply that lands later', async () => {
      // The core's own budget outlasts the deadline — it allows 180s of engine
      // silence and *then* a full reply, so hardware slower than the machine in
      // issue #489 is still working when the deadline fires. Failing there would
      // reintroduce issue #489 at a longer timescale, so the screen polls until
      // the turn actually lands.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: { ...committedTranscript, turns: committedTranscript.turns.slice(0, 1) },
      })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(DEADLINE_MS)
        // Nothing on the server yet, but no verdict either: still waiting.
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(screen.getByTestId('npc-turn-progress')).toBeInTheDocument()

        // The turn lands while the screen is polling.
        mockApi.getSessionTranscript.mockResolvedValue({ ok: true, data: committedTranscript })
        await vi.advanceTimersByTimeAsync(20_000)
        await waitFor(() =>
          expect(
            screen.getByText('Committed by the server while the UI waited.'),
          ).toBeInTheDocument(),
        )
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    it('still reconciles after React re-runs the mount effects', async () => {
      // The reconcile loop is gated on a mounted flag that the cleanup clears.
      // StrictMode runs setup → cleanup → setup, so a flag only ever set at
      // construction stays false for the lifetime of the screen and the loop
      // bails on its first check — issue #489 all over again, in every dev
      // build: a reply the core had committed, discarded at the deadline.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        render(
          <StrictMode>
            <MemoryRouter initialEntries={[`/conversation/${SESSION_ID}`]}>
              <Routes>
                <Route path="/conversation/:sessionId" element={<Conversation />} />
              </Routes>
            </MemoryRouter>
          </StrictMode>,
        )
        await waitFor(() =>
          expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
        )
        fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
          target: { value: 'My answer.' },
        })
        fireEvent.click(screen.getByRole('button', { name: /submit/i }))
        await vi.advanceTimersByTimeAsync(DEADLINE_MS)

        await waitFor(() =>
          expect(
            screen.getByText('Committed by the server while the UI waited.'),
          ).toBeInTheDocument(),
        )
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      } finally {
        vi.useRealTimers()
      }
    })

    it('does not report a timeout over a reply the stream already delivered', async () => {
      // A WebSocket npc.final puts the reply on screen and counts it, so the
      // transcript can never pull ahead of the view — polling for it would run
      // to the ceiling and then blame a timeout on a turn the player can read.
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(1_000)
        act(() => {
          wsCallback?.({
            type: 'npc.final',
            seq: 1,
            session_id: SESSION_ID,
            ts: '2026-07-01T00:01:01Z',
            payload: {
              content: 'Delivered over the stream.',
              emotion: 'neutral',
              state_delta: {},
              event_flags: [],
            },
          })
        })
        await waitFor(() =>
          expect(screen.getByText('Delivered over the stream.')).toBeInTheDocument(),
        )

        await vi.advanceTimersByTimeAsync(DEADLINE_MS)
        // The turn is over at the deadline, not ten minutes later: no verdict,
        // and the player can speak again.
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(screen.getByText('Delivered over the stream.')).toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    /** What the transcript endpoint answers when the session saves no transcript. */
    const unsavedTranscript = {
      session_id: SESSION_ID,
      scenario_id: SCENARIO_ID,
      transcript_saved: false,
      message: 'Transcript saving is disabled for this session.',
      turns: [],
    }

    it('still waits out a slow turn when the session keeps no transcript', async () => {
      // With transcript saving off the endpoint answers with no turns, always —
      // but convsim-core still commits the turn, only withholding the endpoint.
      // Giving the verdict at the deadline would roll back a turn the session
      // holds and leave the view a turn behind: issue #489 at five minutes.
      let resolveTurn: (r: { ok: true; data: TurnResponse }) => void = () => {}
      mockApi.submitTurn.mockReturnValue(
        new Promise((resolve) => { resolveTurn = resolve }) as never,
      )
      mockApi.getSessionTranscript.mockResolvedValue({ ok: true, data: unsavedTranscript })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(DEADLINE_MS)
        // No verdict, and no pointless re-polling of an endpoint that cannot answer.
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        const callsAtDeadline = mockApi.getSessionTranscript.mock.calls.length
        await vi.advanceTimersByTimeAsync(60_000)
        expect(mockApi.getSessionTranscript.mock.calls.length).toBe(callsAtDeadline)
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()

        // The request answers late; its reply is committed as normal.
        resolveTurn({ ok: true, data: turnResponse })
        await vi.advanceTimersByTimeAsync(100)
        await waitFor(() =>
          expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
        )
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      } finally {
        vi.useRealTimers()
      }
    })

    it('reports a timeout at the ceiling when the session keeps no transcript', async () => {
      // The request never answers and the transcript cannot speak for it, so the
      // verdict comes at the ceiling — not five minutes early.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      mockApi.getSessionTranscript.mockResolvedValue({ ok: true, data: unsavedTranscript })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(ABANDON_MS)
        await waitFor(() =>
          expect(screen.getByRole('alert')).toHaveTextContent('Request timed out'),
        )
        expect(screen.queryByText('My answer.')).not.toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    it('reports a timeout once the ceiling passes with nothing on the server', async () => {
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: { ...committedTranscript, turns: committedTranscript.turns.slice(0, 1) },
      })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(ABANDON_MS)
        await waitFor(() =>
          expect(screen.getByRole('alert')).toHaveTextContent('Request timed out'),
        )
        // Nothing landed, so the optimistic player turn is rolled back for a retry.
        expect(screen.queryByText('My answer.')).not.toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    it('reports the core’s own failure as soon as it arrives after the deadline', async () => {
      // The deadline only suspends judgement; it does not discard the request.
      // When the core itself answers 504 TURN_TIMEOUT at, say, seven minutes —
      // it allows 180 s of engine silence *after* generation has started — that
      // is the verdict, with the cause named. Polling on to the ten-minute
      // ceiling would make the player wait three more minutes for a vaguer one.
      let rejectTurn: (r: { ok: false; error: ApiError }) => void = () => {}
      mockApi.submitTurn.mockReturnValue(
        new Promise((resolve) => { rejectTurn = resolve }) as never,
      )
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: { ...committedTranscript, turns: committedTranscript.turns.slice(0, 1) },
      })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(DEADLINE_MS)
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()

        rejectTurn({
          ok: false,
          error: {
            kind: 'http-error',
            status: 504,
            message: 'TURN_TIMEOUT: The AI engine stopped responding partway through its reply.',
          },
        })
        // Resolved mid-interval: the loop must wake on it, not on the next tick.
        await vi.advanceTimersByTimeAsync(100)
        await waitFor(() =>
          expect(screen.getByRole('alert')).toHaveTextContent(/stopped responding partway/i),
        )
        expect(screen.queryByText('My answer.')).not.toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })

    it('commits a reply that answers after the deadline with its state delta intact', async () => {
      // The transcript carries no variable snapshot, so adopting from it leaves
      // the meters stale. When the request does answer, its payload is the
      // authoritative one and must still drive the normal commit path.
      let resolveTurn: (r: { ok: true; data: TurnResponse }) => void = () => {}
      mockApi.submitTurn.mockReturnValue(
        new Promise((resolve) => { resolveTurn = resolve }) as never,
      )
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: { ...committedTranscript, turns: committedTranscript.turns.slice(0, 1) },
      })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        await submitAndWait(DEADLINE_MS)
        resolveTurn({ ok: true, data: turnResponse })
        await vi.advanceTimersByTimeAsync(100)
        await waitFor(() =>
          expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
        )
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: /your response/i })).not.toBeDisabled()
      } finally {
        vi.useRealTimers()
      }
    })
  })

  // A local model gives no progress signal to report, so the only honest estimate
  // is how long turns on this machine have cost before (issue #488).
  describe('NPC turn-time estimate (issue #488)', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
    })

    /** Type a turn and submit it, without waiting for the reply. */
    async function submit(text = 'My answer.') {
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: text },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      await waitFor(() => expect(screen.getByText(text)).toBeInTheDocument())
    }

    it('shows the clock and no estimate on the first turn this machine has run', async () => {
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(12_000)

        // Nothing to compare against yet, so the clock stands alone …
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('12s')
        expect(screen.getByTestId('npc-turn-progress-clock')).not.toHaveTextContent('~')
        expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(/timing this turn/i)
        // … and the bar reports no value rather than guessing one.
        expect(screen.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow')
      } finally {
        vi.useRealTimers()
      }
    })

    it('estimates the next turn from the one that just finished', async () => {
      let resolveTurn: (r: { ok: true; data: TurnResponse }) => void = () => {}
      mockApi.submitTurn.mockReturnValue(
        new Promise((resolve) => { resolveTurn = resolve }) as never,
      )
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit('First answer.')
        await vi.advanceTimersByTimeAsync(40_000)
        resolveTurn({ ok: true, data: turnResponse })
        await waitFor(() =>
          expect(screen.getByText('Hello there. I am a simulated NPC.')).toBeInTheDocument(),
        )

        // Second turn: the 40s it just measured is what the player is told to expect.
        mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
        await submit('Second answer.')
        await vi.advanceTimersByTimeAsync(10_000)
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('10s / ~40s')
        expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(
          /about 30s to go/i,
        )
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25')
      } finally {
        vi.useRealTimers()
      }
    })

    it('estimates the very first turn from a previous session on the same model', async () => {
      // The whole complaint in issue #488 is not knowing before the wait starts,
      // so samples outlive the session that measured them.
      recordTurnSample(MODEL_NAME, 90_000)
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(45_000)

        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('45s / ~1m 30s')
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores timings measured on a different model', async () => {
      // Switching to a smaller model is the app's own advice when turns are slow;
      // the old model's minutes must not keep being quoted afterwards.
      recordTurnSample('some-other-model-70b', 240_000)
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(5_000)

        expect(screen.getByTestId('npc-turn-progress-clock')).not.toHaveTextContent('~')
        expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(/timing this turn/i)
      } finally {
        vi.useRealTimers()
      }
    })

    it('says the turn is running long rather than letting the bar fill', async () => {
      recordTurnSample(MODEL_NAME, 30_000)
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(75_000)

        expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(
          /longer than the usual 30s/i,
        )
        // 250% of the estimate, but a full bar would read as a finished turn.
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '95')
      } finally {
        vi.useRealTimers()
      }
    })

    it('says the NPC is replying, not thinking, once tokens arrive', async () => {
      recordTurnSample(MODEL_NAME, 30_000)
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(20_000)
        expect(screen.getByTestId('npc-turn-progress')).toHaveTextContent('Thinking…')

        act(() => {
          wsCallback?.({
            type: 'npc.token',
            seq: 1,
            session_id: SESSION_ID,
            ts: '2026-07-01T00:01:00Z',
            payload: { text: 'Well, ' },
          })
        })

        // The words are visibly arriving; the clock still covers the round trip.
        const panel = screen.getByTestId('npc-turn-progress')
        expect(panel).toHaveTextContent('Replying…')
        expect(panel).not.toHaveTextContent('Thinking…')
        expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('20s / ~30s')
      } finally {
        vi.useRealTimers()
      }
    })

    it('stops asking the player to wait once the stream has delivered the reply', async () => {
      // npc.final commits the reply while the REST request is still out — and
      // past the turn deadline that gap runs a whole reconcile interval. A panel
      // counting up under a reply the player is reading is simply wrong.
      let wsCallback: ((event: WsEvent) => void) | null = null
      mockApi.connectSession.mockImplementation((_id, cb) => {
        wsCallback = cb
        return { close: vi.fn() }
      })
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(40_000)
        expect(screen.getByTestId('npc-turn-progress')).toBeInTheDocument()

        act(() => {
          wsCallback?.({
            type: 'npc.final',
            seq: 1,
            session_id: SESSION_ID,
            ts: '2026-07-01T00:01:01Z',
            payload: {
              content: 'Here is my answer.',
              emotion: 'neutral',
              state_delta: {},
              event_flags: [],
            },
          })
        })

        expect(screen.getByText('Here is my answer.')).toBeInTheDocument()
        expect(screen.queryByTestId('npc-turn-progress')).not.toBeInTheDocument()
        // Until the request carrying the state delta answers, the screen says
        // what it is still doing — without claiming the NPC is working on a
        // reply that is already there.
        expect(screen.getByTestId('turn-finishing-indicator')).toHaveTextContent(
          'Updating the scene…',
        )
      } finally {
        vi.useRealTimers()
      }
    })

    it('does not say the NPC is responding twice over', async () => {
      // The panel below the transcript is the status while the NPC is out; the
      // transcript's own busy line would only repeat it in different words.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(4_000)

        expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent(
          'Thinking…',
        )
        expect(screen.queryByTestId('turn-finishing-indicator')).not.toBeInTheDocument()
      } finally {
        vi.useRealTimers()
      }
    })

    it('has its live region on screen before the first turn goes out', async () => {
      // A region created in the same breath as its text is not reliably
      // announced, and this one carries the estimate — the whole of issue #488
      // for a screen-reader user. The line it replaced was announced by the
      // transcript's own always-present region, so it has to be mounted and
      // silent between turns rather than conjured with the panel.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )
      const status = screen.getByTestId('npc-turn-progress-status')
      expect(status).toHaveTextContent('')
      expect(screen.queryByTestId('npc-turn-progress')).not.toBeInTheDocument()

      await submit()
      expect(screen.getByTestId('npc-turn-progress-status')).toBe(status)
      expect(status).toHaveTextContent('Thinking…')
    })

    it('keeps the ticking panel out of the transcript live region', async () => {
      // The transcript is role="log" with aria-live="polite", so a live region
      // re-announces everything inside it on every text change. The panel's
      // clock changes every second: nested in there it would be ~300
      // announcements over a five-minute turn, which is exactly what the
      // aria-hidden clock and the 30 s announcement grid exist to avoid. The
      // panel's placement below the transcript is what makes that work, so pin
      // it — a future tidy-up that moves it inside would silently undo all of it.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      renderConversation()
      await submit()

      const transcript = screen.getByRole('log', { name: /conversation transcript/i })
      expect(transcript).toHaveAttribute('aria-live', 'polite')
      for (const testId of [
        'npc-turn-progress',
        'npc-turn-progress-clock',
        'npc-turn-progress-status',
        'npc-turn-progress-announcement',
        'npc-turn-progress-hint',
      ]) {
        expect(transcript).not.toContainElement(screen.getByTestId(testId))
      }
    })

    it('does not learn a duration from a turn that failed', async () => {
      // A turn that errored out at 30s says nothing about how long a reply takes.
      let failTurn: (r: { ok: false; error: ApiError }) => void = () => {}
      mockApi.submitTurn.mockReturnValue(
        new Promise((resolve) => { failTurn = resolve }) as never,
      )
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        await vi.advanceTimersByTimeAsync(30_000)
        failTurn({ ok: false, error: { kind: 'network', message: 'Connection refused' } })
        await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())

        mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
        await submit('Retrying.')
        await vi.advanceTimersByTimeAsync(3_000)
        expect(screen.getByTestId('npc-turn-progress-clock')).not.toHaveTextContent('~')
      } finally {
        vi.useRealTimers()
      }
    })

    it('does not learn a duration from a turn recovered by polling', async () => {
      // Past the deadline the screen finds the reply by asking the session what
      // it recorded (issue #489), and the reconcile loop only looks every 15s —
      // so the wait measures when the screen *noticed* the turn, not what the
      // model spent on it. If the request was wedged it measures nothing about
      // the model at all. Either way, quoting it back would promise minutes for
      // turns that take seconds.
      mockApi.submitTurn.mockReturnValue(new Promise(() => {}))
      mockApi.getSessionTranscript.mockResolvedValue({
        ok: true,
        data: {
          session_id: SESSION_ID,
          scenario_id: SCENARIO_ID,
          transcript_saved: true,
          turns: [
            { turn_number: 0, role: 'npc_opening' as const, content: 'Thanks for coming in. Tell me about yourself.', flow_state_after: 'PlayerTurnListening' },
            { turn_number: 1, role: 'player' as const, content: 'My answer.', flow_state_after: 'NpcThinking' },
            { turn_number: 2, role: 'npc' as const, content: 'Committed by the server while the UI waited.', emotion: 'neutral', flow_state_after: 'PlayerTurnListening' },
          ],
        },
      })
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        renderConversation()
        await submit()
        // Past the 300s deadline, then far enough for one reconcile poll.
        await vi.advanceTimersByTimeAsync(320_000)
        await waitFor(() =>
          expect(
            screen.getByText('Committed by the server while the UI waited.'),
          ).toBeInTheDocument(),
        )

        expect(readTurnSamples(MODEL_NAME)).toEqual([])
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe('no runtime badges or model-ready toast (issue #473)', () => {
    afterEach(() => {
      localStorage.clear()
    })

    it('renders no runtime badge and no toast even with stale legacy keys present', async () => {
      // Old app versions wrote these; they must be inert now.
      localStorage.setItem('convsim.active_runtime_hint', 'scripted')
      localStorage.setItem('convsim.tutorial.install_id', '42')
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })

      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('heading', { name: /^conversation$/i })).toBeInTheDocument(),
      )

      expect(screen.queryByTestId('runtime-label')).not.toBeInTheDocument()
      expect(screen.queryByTestId('model-ready-toast')).not.toBeInTheDocument()
      // No background-install polling is wired to the legacy key any more.
      expect(mockApi.getSetupInstallStatus).not.toHaveBeenCalled()
    })
  })
})