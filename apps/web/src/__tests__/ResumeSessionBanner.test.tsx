// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nProvider } from '../i18n'
import ResumeSessionBanner from '../components/ResumeSessionBanner'
import type { ScenarioInfo } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    listSessions: vi.fn(),
    listScenarios: vi.fn(),
    endSession: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const SESSION = {
  session_id: 'sess-abc123',
  scenario_id: 'behavioral_interview',
  state: 'PlayerTurnListening' as const,
  created_at: '2026-10-01T10:00:00Z',
  turn_count: 3,
  ending_type: null,
  ended_at: null,
  setup: {
    scenario_id: 'behavioral_interview',
    difficulty: 'standard' as const,
    player_role_name: 'Candidate',
    language: 'en',
    input_mode: 'text-only' as const,
    tts_enabled: false,
    show_state_meters: true,
    save_transcript: true,
    seed: null,
  },
}

const SCENARIO = {
  scenario_id: 'behavioral_interview',
  title: 'The Behavioral Interview',
} as unknown as ScenarioInfo

function renderAt(path: string) {
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<><ResumeSessionBanner /><div data-testid="page" /></>} />
        </Routes>
      </MemoryRouter>
    </I18nProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.listScenarios.mockResolvedValue({ ok: true, data: [SCENARIO] })
  mockApi.endSession.mockResolvedValue({
    ok: true,
    data: { session_id: SESSION.session_id, state: 'Ended', ending_type: 'player_exit' },
  })
})

/**
 * Issue #501 §1: "I couldn't easily figure out how to resume my ongoing
 * scenario and resorted to starting a new one." The banner lives in the app
 * chrome so it is on every screen the detour can reach — Settings included,
 * which is where the playtester actually was.
 */
describe('ResumeSessionBanner', () => {
  it('offers the in-progress conversation by scenario title and turn count', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    renderAt('/settings')
    await waitFor(() =>
      expect(screen.getByTestId('resume-session-banner')).toBeInTheDocument(),
    )
    const banner = screen.getByTestId('resume-session-banner')
    expect(banner).toHaveTextContent('The Behavioral Interview')
    expect(banner).toHaveTextContent('3 turns')
  })

  it('says "1 turn" after a single exchange', async () => {
    mockApi.listSessions.mockResolvedValue({
      ok: true,
      data: { sessions: [{ ...SESSION, turn_count: 1 }] },
    })
    renderAt('/settings')
    await waitFor(() =>
      expect(screen.getByTestId('resume-session-banner')).toBeInTheDocument(),
    )
    const banner = screen.getByTestId('resume-session-banner')
    expect(banner).toHaveTextContent('1 turn so far')
    expect(banner).not.toHaveTextContent('1 turns')
  })

  it('resumes into the conversation it names', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/settings']}>
          <Routes>
            <Route path="/settings" element={<ResumeSessionBanner />} />
            <Route path="/conversation/:id" element={<div data-testid="conversation" />} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('resume-session-button')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('resume-session-button'))
    await waitFor(() => expect(screen.getByTestId('conversation')).toBeInTheDocument())
  })

  it('asks only for the resumable set, and only for the newest one', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    renderAt('/settings')
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalled())
    expect(mockApi.listSessions).toHaveBeenCalledWith('in_progress', 1)
  })

  it('renders nothing when there is no conversation to resume', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [] } })
    renderAt('/settings')
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalled())
    expect(screen.queryByTestId('resume-session-banner')).not.toBeInTheDocument()
  })

  it('stays quiet rather than stacking an error when the core is unreachable', async () => {
    mockApi.listSessions.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'unreachable' },
    })
    renderAt('/settings')
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalled())
    expect(screen.queryByTestId('resume-session-banner')).not.toBeInTheDocument()
  })

  it('tolerates a response shape this build does not expect', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: {} as never })
    renderAt('/settings')
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalled())
    expect(screen.queryByTestId('resume-session-banner')).not.toBeInTheDocument()
  })

  it('does not ask while the player is already in the conversation', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    renderAt('/conversation/sess-abc123')
    await waitFor(() => expect(screen.getByTestId('page')).toBeInTheDocument())
    expect(mockApi.listSessions).not.toHaveBeenCalled()
    expect(screen.queryByTestId('resume-session-banner')).not.toBeInTheDocument()
  })

  it('does not ask while the player is reading a debrief', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    renderAt('/debrief/sess-abc123')
    await waitFor(() => expect(screen.getByTestId('page')).toBeInTheDocument())
    expect(mockApi.listSessions).not.toHaveBeenCalled()
  })

  it('ending the session clears the offer', async () => {
    mockApi.listSessions
      .mockResolvedValueOnce({ ok: true, data: { sessions: [SESSION] } })
      .mockResolvedValue({ ok: true, data: { sessions: [] } })
    renderAt('/settings')
    await waitFor(() =>
      expect(screen.getByTestId('resume-session-banner')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('resume-session-end-button'))
    await waitFor(() =>
      expect(screen.queryByTestId('resume-session-banner')).not.toBeInTheDocument(),
    )
    expect(mockApi.endSession).toHaveBeenCalledWith('sess-abc123')
  })

  it('ending the session shows the debrief it just produced', async () => {
    // Ending a conversation always produces a debrief. Left on Settings, the
    // player would have no way to the one they just earned.
    mockApi.listSessions
      .mockResolvedValueOnce({ ok: true, data: { sessions: [SESSION] } })
      .mockResolvedValue({ ok: true, data: { sessions: [] } })
    render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/settings']}>
          <Routes>
            <Route path="/settings" element={<ResumeSessionBanner />} />
            <Route path="/debrief/:id" element={<div data-testid="debrief" />} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('resume-session-end-button')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('resume-session-end-button'))
    await waitFor(() => expect(screen.getByTestId('debrief')).toBeInTheDocument())
  })

  it('stays put when ending fails, so nothing claims a debrief exists', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    mockApi.endSession.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'unreachable' },
    })
    render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/settings']}>
          <Routes>
            <Route path="/settings" element={<ResumeSessionBanner />} />
            <Route path="/debrief/:id" element={<div data-testid="debrief" />} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('resume-session-end-button')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('resume-session-end-button'))
    await waitFor(() => expect(mockApi.endSession).toHaveBeenCalled())
    expect(screen.queryByTestId('debrief')).not.toBeInTheDocument()
  })

  it('re-asks when the window regains focus, so it cannot go stale', async () => {
    // The session can be ended on another screen, or by another window.
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    renderAt('/settings')
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalledTimes(1))
    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalledTimes(2))
  })

  it('falls back to the scenario id when the title has not loaded', async () => {
    mockApi.listSessions.mockResolvedValue({ ok: true, data: { sessions: [SESSION] } })
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    renderAt('/settings')
    await waitFor(() =>
      expect(screen.getByTestId('resume-session-banner')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('resume-session-banner')).toHaveTextContent(
      'behavioral_interview',
    )
  })
})
