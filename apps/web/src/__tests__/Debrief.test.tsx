// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Debrief from '../screens/Debrief'
import type { SessionDebriefResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    generateDebrief: vi.fn(),
    exportSession: vi.fn(),
    exportTranscriptText: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

vi.mock('../privacyPrefs', () => ({
  isDevModeEnabled: vi.fn(() => false),
}))
import { isDevModeEnabled } from '../privacyPrefs'
const mockIsDevModeEnabled = vi.mocked(isDevModeEnabled)

const SESSION_ID = 'sess-debrief01'

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
  session: { session_id: SESSION_ID, scenario_id: 'behavioral_interview', state: 'Ended', ending_type: 'player_exit', created_at: '2024-01-01T00:00:00Z', turn_count: 2, setup: {}, state_vars: {} },
  events: [
    { event_id: 1, session_id: SESSION_ID, event_type: 'player_turn', payload: { content: 'Hello, I am interested in this role.' }, created_at: '2024-01-01T00:00:01Z' },
    { event_id: 2, session_id: SESSION_ID, event_type: 'npc_turn', payload: { content: 'Tell me about yourself.', emotion: 'neutral' }, created_at: '2024-01-01T00:00:02Z' },
  ],
}

function renderDebrief() {
  return render(
    <MemoryRouter initialEntries={[`/debrief/${SESSION_ID}`]}>
      <Routes>
        <Route path="/debrief/:sessionId" element={<Debrief />} />
        <Route path="/library" element={<div>Library page</div>} />
        <Route path="/setup/:scenarioId" element={<div>Setup page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.exportSession.mockResolvedValue(exportData)
  mockApi.exportTranscriptText.mockResolvedValue({
    text: '# Session Transcript\n\nSession content here.',
    filename: `session-${SESSION_ID}-transcript.md`,
  })
  mockIsDevModeEnabled.mockReturnValue(false)
})

describe('Debrief screen', () => {
  it('shows loading state while generating debrief', () => {
    mockApi.generateDebrief.mockReturnValue(new Promise(() => {}))
    renderDebrief()
    expect(screen.getByText(/generating debrief/i)).toBeInTheDocument()
  })

  it('displays summary after debrief loads', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('summary-section').querySelector('p')).toHaveTextContent(
      'You completed 2 turns',
    )
  })

  it('displays strengths section', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Engaged with the scenario')).toBeInTheDocument(),
    )
  })

  it('displays improvements section', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Install a local LLM for real NPC responses')).toBeInTheDocument(),
    )
  })

  it('displays replay suggestions', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByText('Try a different difficulty level')).toBeInTheDocument(),
    )
  })

  it('shows the session id in the header', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() => expect(screen.getByText(SESSION_ID)).toBeInTheDocument())
  })

  it('shows outcome badge', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('outcome-badge')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('outcome-badge')).toHaveTextContent('player exit')
  })

  it('shows turn count', async () => {
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
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
    mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
    renderDebrief()
    await waitFor(() =>
      expect(screen.getByTestId('debrief-json')).toBeInTheDocument(),
    )
  })

  describe('scorecard', () => {
    it('shows overall score', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('overall-score')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('overall-score')).toHaveTextContent('52')
    })

    it('shows a dimension row for each score', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('scorecard-section')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('dimension-row-rapport')).toBeInTheDocument()
      expect(screen.getByTestId('dimension-row-clarity')).toBeInTheDocument()
    })

    it('omits scorecard when scores object is empty', async () => {
      mockApi.generateDebrief.mockResolvedValue(fallbackDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('scorecard-section')).not.toBeInTheDocument()
    })
  })

  describe('turning points', () => {
    it('shows turning points section with key moments', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('turning-points-section')).toBeInTheDocument(),
      )
      expect(screen.getByText('Strong opening statement')).toBeInTheDocument()
      expect(screen.getByText('Missed an opportunity to ask a follow-up')).toBeInTheDocument()
    })

    it('omits turning points section when list is empty', async () => {
      mockApi.generateDebrief.mockResolvedValue(fallbackDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('turning-points-section')).not.toBeInTheDocument()
    })
  })

  describe('fallback debrief', () => {
    it('shows fallback notice when used_fallback is true', async () => {
      mockApi.generateDebrief.mockResolvedValue(fallbackDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('fallback-notice')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('fallback-notice')).toHaveTextContent('template')
    })

    it('does not show fallback notice when used_fallback is false', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('fallback-notice')).not.toBeInTheDocument()
    })
  })

  describe('transcript saving disabled', () => {
    it('shows transcript-disabled notice when transcript_saving_disabled is true', async () => {
      mockApi.generateDebrief.mockResolvedValue(transcriptDisabledDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-disabled-notice')).toBeInTheDocument(),
      )
    })

    it('does not call exportSession when transcript saving is disabled', async () => {
      mockApi.generateDebrief.mockResolvedValue(transcriptDisabledDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(mockApi.exportSession).not.toHaveBeenCalled()
    })
  })

  describe('transcript display', () => {
    it('shows transcript turns from export when available', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('transcript-section')).toBeInTheDocument(),
      )
      const turns = screen.getAllByTestId('transcript-turn')
      expect(turns).toHaveLength(2)
    })

    it('omits transcript section when export returns no relevant events', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      mockApi.exportSession.mockResolvedValue({ events: [] })
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
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('export-btn')).toBeInTheDocument(),
      )
    })

    it('calls exportSession on click', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)

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
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('debrief-latency')).toBeInTheDocument(),
      )
      expect(screen.getByTestId('debrief-latency')).toHaveTextContent(/debrief generation:.*ms/i)
    })

    it('does not show debrief latency when dev mode is off', async () => {
      mockIsDevModeEnabled.mockReturnValue(false)
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('summary-section')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('debrief-latency')).not.toBeInTheDocument()
    })
  })

  describe('replay button', () => {
    it('renders a replay button after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('replay-btn')).toBeInTheDocument(),
      )
    })

    it('navigates to setup screen with the scenario id on replay click', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
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

  describe('missed opportunities section', () => {
    it('displays missed opportunities when present', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('missed-opportunities-section')).toBeInTheDocument(),
      )
      expect(screen.getByText('Consider asking more probing questions to deepen the dialogue.')).toBeInTheDocument()
    })

    it('does not render missed opportunities section when list is empty', async () => {
      mockApi.generateDebrief.mockResolvedValue({
        ...fullDebriefResponse,
        missed_opportunities: [],
      })
      renderDebrief()
      await waitFor(() => expect(screen.getByTestId('summary-section')).toBeInTheDocument())
      expect(screen.queryByTestId('missed-opportunities-section')).not.toBeInTheDocument()
    })

    it('does not render missed opportunities section when field is absent', async () => {
      const { missed_opportunities: _omit, ...rest } = fullDebriefResponse
      mockApi.generateDebrief.mockResolvedValue(rest)
      renderDebrief()
      await waitFor(() => expect(screen.getByTestId('summary-section')).toBeInTheDocument())
      expect(screen.queryByTestId('missed-opportunities-section')).not.toBeInTheDocument()
    })
  })

  describe('export transcript as Markdown', () => {
    it('renders an export-text-btn after debrief loads', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)
      renderDebrief()
      await waitFor(() =>
        expect(screen.getByTestId('export-text-btn')).toBeInTheDocument(),
      )
    })

    it('calls exportTranscriptText on click and triggers download', async () => {
      mockApi.generateDebrief.mockResolvedValue(fullDebriefResponse)

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
})
