// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Conversation from '../screens/Conversation'
import type {
  SessionStartResponse,
  TurnResponse,
  SessionEndResponse,
  ScenarioInfo,
  WsEvent,
} from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    startSession: vi.fn(),
    submitTurn: vi.fn(),
    endSession: vi.fn(),
    generateDebrief: vi.fn(),
    connectSession: vi.fn(),
    getScenario: vi.fn(),
  },
  apiClient: {
    health: vi.fn(),
    uploadAudio: vi.fn(),
    vadHealth: vi.fn().mockResolvedValue({}),
    vadCalibrate: vi.fn(),
  },
}))

import { api, apiClient } from '../api/client'
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
      payload: { content: "Thanks for coming in. Tell me about yourself." },
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
  // Default: connectSession returns a no-op connection; getScenario returns null
  mockApi.connectSession.mockReturnValue({ close: vi.fn() })
  mockApi.getScenario.mockResolvedValue({ ok: true, data: null } as unknown as ScenarioInfo)
  mockApiClient.uploadAudio.mockResolvedValue({ ok: true, data: { transcript: null, status: 'unavailable' } })
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

    it('shows the session id in the header', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() => expect(screen.getByText(SESSION_ID)).toBeInTheDocument())
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

    it('recovers gracefully when session was already started (409)', async () => {
      mockApi.startSession.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'INVALID_TRANSITION' } })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection failed'),
      )
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

      // A successful retry should be labelled Turn 2 (opening was Turn 1),
      // with no gap or duplicate from the rolled-back attempt.
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      fireEvent.change(screen.getByRole('textbox', { name: /your response/i }), {
        target: { value: 'Retry message.' },
      })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByText('Retry message.')).toBeInTheDocument(),
      )
      // Opening=Turn 1, retry player=Turn 2, NPC=Turn 3. The absence of a
      // Turn 4 confirms the failed attempt did not consume a turn number.
      expect(screen.getByText('Turn 2')).toBeInTheDocument()
      expect(screen.queryByText('Turn 4')).not.toBeInTheDocument()
    })

    it('shows turn number markers in the transcript', async () => {
      mockApi.submitTurn.mockResolvedValue({ ok: true, data: turnResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByText('Thanks for coming in. Tell me about yourself.')).toBeInTheDocument(),
      )
      expect(screen.getByText(/Turn 1/)).toBeInTheDocument()
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

  describe('state variables panel', () => {
    it('shows NPC state variables section when show_state_meters is true (default)', async () => {
      mockApi.startSession.mockResolvedValue({ ok: true, data: startResponse })
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('state-vars')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('state-vars')).toHaveTextContent('trust')
      expect(screen.getByTestId('state-vars')).toHaveTextContent('patience')
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
      expect(screen.getByTestId('banner-event')).toHaveTextContent('rapport_milestone')
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
})
