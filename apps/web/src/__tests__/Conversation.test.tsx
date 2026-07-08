// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
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
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

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
  difficulty: { default: 'normal', options: { easy: { npc_patience_modifier: 0.5, challenge_frequency: 'low' }, normal: { npc_patience_modifier: 0, challenge_frequency: 'medium' } } },
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
  mockApi.getScenario.mockResolvedValue(null as unknown as ScenarioInfo)
})

describe('Conversation screen', () => {
  describe('session start', () => {
    it('shows loading state while session is starting', () => {
      mockApi.startSession.mockReturnValue(new Promise(() => {}))
      renderConversation()
      expect(screen.getByText(/starting session/i)).toBeInTheDocument()
    })

    it('displays the NPC opening after session starts', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() =>
        expect(
          screen.getByText('Thanks for coming in. Tell me about yourself.'),
        ).toBeInTheDocument(),
      )
    })

    it('shows the transcript log region', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() => expect(screen.getByRole('log')).toBeInTheDocument())
    })

    it('shows the session id in the header', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() => expect(screen.getByText(SESSION_ID)).toBeInTheDocument())
    })

    it('shows an error alert when startSession fails', async () => {
      mockApi.startSession.mockRejectedValue(new Error('Connection refused'))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Connection refused'),
      )
    })

    it('shows a back-to-library button when startSession fails fatally', async () => {
      mockApi.startSession.mockRejectedValue(new Error('Connection refused'))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /back to library/i })).toBeInTheDocument(),
      )
    })

    it('recovers gracefully when session was already started (409)', async () => {
      mockApi.startSession.mockRejectedValue(new Error('INVALID_TRANSITION'))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('already started'),
      )
      expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument()
    })
  })

  describe('NPC panel', () => {
    it('renders the NPC panel with placeholder', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('npc-panel')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('npc-panel')).toHaveTextContent('NPC')
    })

    it('shows npc status as Thinking while submitting', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
      mockApi.submitTurn.mockResolvedValue(emotionalTurnResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
      mockApi.getScenario.mockResolvedValue(mockScenario)
      renderConversation({ scenario_id: SCENARIO_ID })
      await waitFor(() =>
        expect(screen.getByTestId('scene-card')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('scene-card')).toHaveTextContent('Software Engineer Interview')
    })

    it('does not render scene card without scenario data', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('npc-panel')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('scene-card')).not.toBeInTheDocument()
    })
  })

  describe('player turn submission', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.submitTurn.mockResolvedValue(turnResponse)
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
      mockApi.submitTurn.mockResolvedValue(turnResponse)
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
      mockApi.submitTurn.mockRejectedValue(new Error('Turn failed'))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'Test turn' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Turn failed'),
      )
    })

    it('shows turn number markers in the transcript', async () => {
      mockApi.submitTurn.mockResolvedValue(turnResponse)
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

  describe('state variables panel', () => {
    it('shows NPC state variables section when show_state_meters is true (default)', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('state-vars')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('state-vars')).toHaveTextContent('trust')
      expect(screen.getByTestId('state-vars')).toHaveTextContent('patience')
    })

    it('hides state variables when show_state_meters is false', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
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
      mockApi.startSession.mockResolvedValue(startResponse)
      mockApi.submitTurn.mockResolvedValue(turnResponse)
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
  })

  describe('debug drawer', () => {
    it('renders the debug drawer in dev mode', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('npc-panel')).toBeInTheDocument())
      expect(screen.getByTestId('debug-drawer')).toBeInTheDocument()
    })
  })

  describe('end session', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue(startResponse)
    })

    it('shows the end session button while active', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /end session/i })).toBeInTheDocument(),
      )
    })

    it('transitions to ended state and shows debrief button', async () => {
      mockApi.endSession.mockResolvedValue(endResponse)
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
      mockApi.endSession.mockRejectedValue(new Error('End failed'))
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /end session/i })).toBeInTheDocument(),
      )

      fireEvent.click(screen.getByRole('button', { name: /end session/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('End failed'),
      )
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
      mockApi.startSession.mockResolvedValue(startResponse)
      mockApi.submitTurn.mockResolvedValue(endedTurnResponse)
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
