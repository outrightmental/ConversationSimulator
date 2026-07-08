// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Conversation from '../screens/Conversation'
import type {
  SessionStartResponse,
  TurnResponse,
  SessionEndResponse,
} from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    startSession: vi.fn(),
    submitTurn: vi.fn(),
    endSession: vi.fn(),
    generateDebrief: vi.fn(),
    connectSession: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const SESSION_ID = 'sess-demo0001'

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

function renderConversation() {
  return render(
    <MemoryRouter initialEntries={[`/conversation/${SESSION_ID}`]}>
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
  })

  describe('state variables panel', () => {
    it('shows NPC state variables section', async () => {
      mockApi.startSession.mockResolvedValue(startResponse)
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('state-vars')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('state-vars')).toHaveTextContent('trust')
      expect(screen.getByTestId('state-vars')).toHaveTextContent('patience')
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

  describe('developer debug drawer', () => {
    beforeEach(() => {
      mockApi.startSession.mockResolvedValue(startResponse)
      localStorage.removeItem('convsim.devMode')
    })

    afterEach(() => {
      localStorage.removeItem('convsim.devMode')
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

    it('shows a debug entry for the npc_opening event in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      renderConversation()
      await waitFor(() => expect(screen.getByTestId('debug-drawer')).toBeInTheDocument())
      expect(screen.getByText('1 entry')).toBeInTheDocument()
    })

    it('accumulates debug entries as turns are submitted in dev mode', async () => {
      localStorage.setItem('convsim.devMode', 'true')
      mockApi.submitTurn.mockResolvedValue(turnResponse)
      renderConversation()
      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument(),
      )

      const textarea = screen.getByRole('textbox', { name: /your response/i })
      fireEvent.change(textarea, { target: { value: 'My answer.' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() => expect(screen.getByText('2 entries')).toBeInTheDocument())
    })

    it('debug drawer is not rendered (not just hidden) in normal mode', async () => {
      renderConversation()
      await waitFor(() =>
        expect(screen.getByTestId('state-vars')).toBeInTheDocument(),
      )
      // The debug drawer must be absent from DOM, not merely invisible
      expect(screen.queryByText('Developer debug')).not.toBeInTheDocument()
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
