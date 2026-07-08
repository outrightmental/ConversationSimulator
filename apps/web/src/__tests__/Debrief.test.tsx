// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Debrief from '../screens/Debrief'
import type { SessionDebriefResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    generateDebrief: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const SESSION_ID = 'sess-debrief01'

const debriefResponse: SessionDebriefResponse = {
  session_id: SESSION_ID,
  state: 'Ended',
  summary: 'You completed 2 turns of "Behavioral Interview". Session outcome: player exit.',
  outcome: 'player_exit',
  turn_count: 2,
  scenario_id: 'behavioral_interview',
  strengths: ['Engaged with the scenario', 'Completed the session flow'],
  improvements: ['Install a local LLM for real NPC responses'],
  replay_suggestions: ['Try a different difficulty level'],
}

function renderDebrief() {
  return render(
    <MemoryRouter initialEntries={[`/debrief/${SESSION_ID}`]}>
      <Routes>
        <Route path="/debrief/:sessionId" element={<Debrief />} />
        <Route path="/library" element={<div>Library page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Debrief screen', () => {
  it('shows loading state while generating debrief', () => {
    mockApi.generateDebrief.mockReturnValue(new Promise(() => {}))
    renderDebrief()
    expect(screen.getByText(/generating debrief/i)).toBeInTheDocument()
  })

  it('displays summary after debrief loads', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('summary-section').querySelector('p')).toHaveTextContent(
      'You completed 2 turns',
    )
  })

  it('displays strengths section', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Engaged with the scenario')).toBeInTheDocument(),
    )
  })

  it('displays improvements section', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Install a local LLM for real NPC responses')).toBeInTheDocument(),
    )
  })

  it('displays replay suggestions', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Try a different difficulty level')).toBeInTheDocument(),
    )
  })

  it('shows the session id in the header', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() => expect(screen.getByText(SESSION_ID)).toBeInTheDocument())
  })

  it('shows outcome badge', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('outcome-badge')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('outcome-badge')).toHaveTextContent('player exit')
  })

  it('shows turn count', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
  })

  it('shows error alert when generateDebrief fails', async () => {
    mockApi.generateDebrief.mockRejectedValue(new Error('Session not found'))
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Session not found'),
    )
  })

  it('includes raw JSON debug section', async () => {
    mockApi.generateDebrief.mockResolvedValue(debriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('debrief-json')).toBeInTheDocument(),
    )
  })
})
