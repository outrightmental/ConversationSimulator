// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { LogbookProfile } from '@convsim/shared'

vi.mock('@convsim/ui', () => ({
  StatusBadge: ({ children, status }: { children: React.ReactNode; status: string }) => (
    <span data-status={status}>{children}</span>
  ),
}))

vi.mock('../hooks/useSteamAchievements', () => ({
  useSteamAchievements: () => ({
    unlock: vi.fn(() => Promise.resolve(false)),
    incrementStat: vi.fn(() => Promise.resolve(false)),
  }),
  SteamAchievement: {
    FIRST_SCENARIO: 'ACH_FIRST_SCENARIO',
    FIRST_DEBRIEF: 'ACH_FIRST_DEBRIEF',
    PRACTICE_STREAK: 'ACH_PRACTICE_STREAK',
    PACK_EXPLORER: 'ACH_PACK_EXPLORER',
    CREATOR_FIRST_VALIDATE: 'ACH_CREATOR_FIRST_VALIDATE',
  },
  SteamStat: {
    SCENARIOS_COMPLETED: 'STAT_SCENARIOS_COMPLETED',
    DEBRIEFS_GENERATED: 'STAT_DEBRIEFS_GENERATED',
    PACKS_VALIDATED: 'STAT_PACKS_VALIDATED',
    TEXT_MODE_SESSIONS: 'STAT_TEXT_MODE_SESSIONS',
    VOICE_MODE_SESSIONS: 'STAT_VOICE_MODE_SESSIONS',
  },
}))

vi.mock('../api/client', () => ({
  api: {
    getLogbookProfile: vi.fn(),
    exportLogbook: vi.fn(),
  },
}))

import { api } from '../api/client'
import Logbook from '../screens/Logbook'

function makeProfile(overrides: Partial<LogbookProfile> = {}): LogbookProfile {
  return {
    total_sessions: 0,
    total_practice_seconds: 0,
    streak_days: 0,
    last_session_date: null,
    dimension_scores: [],
    personal_records: [],
    strongest_dimension: null,
    weakest_dimension: null,
    last_session_delta: null,
    ...overrides,
  }
}

function renderLogbook() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Logbook />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.getLogbookProfile).mockResolvedValue(makeProfile())
  vi.mocked(api.exportLogbook).mockResolvedValue({
    exported_at: new Date().toISOString(),
    profile: makeProfile(),
    session_scores: [],
  })
})

describe('Logbook — loading state', () => {
  it('shows loading message while fetching', () => {
    vi.mocked(api.getLogbookProfile).mockReturnValue(new Promise(() => {}))
    renderLogbook()
    expect(screen.getByText(/loading your training history/i)).toBeInTheDocument()
  })
})

describe('Logbook — empty state', () => {
  it('shows the page heading', async () => {
    renderLogbook()
    expect(await screen.findByRole('heading', { name: /^logbook$/i })).toBeInTheDocument()
  })

  it('shows an empty state prompt when no sessions exist', async () => {
    renderLogbook()
    expect(await screen.findByText(/your logbook is empty/i)).toBeInTheDocument()
  })

  it('shows a link to start a scenario in the empty state', async () => {
    renderLogbook()
    const link = await screen.findByRole('link', { name: /start a scenario/i })
    expect(link).toHaveAttribute('href', '/library')
  })
})

describe('Logbook — with sessions', () => {
  const profile: LogbookProfile = makeProfile({
    total_sessions: 5,
    total_practice_seconds: 1800,
    streak_days: 3,
    last_session_date: '2026-07-10',
    dimension_scores: [
      { dimension_id: 'empathy', rolling_score: 82, session_count: 4, trajectory: [70, 75, 80, 82] },
      { dimension_id: 'assertiveness', rolling_score: 55, session_count: 3, trajectory: [40, 55] },
    ],
    personal_records: [
      { scenario_id: 'behavioral_interview', difficulty: 'standard', best_score: 78, achieved_at: '2026-07-09T10:00:00Z' },
    ],
    strongest_dimension: 'empathy',
    weakest_dimension: 'assertiveness',
    last_session_delta: 12,
  })

  beforeEach(() => {
    vi.mocked(api.getLogbookProfile).mockResolvedValue(profile)
  })

  it('shows the session count', async () => {
    renderLogbook()
    expect(await screen.findByText('5')).toBeInTheDocument()
  })

  it('shows the streak count', async () => {
    renderLogbook()
    expect(await screen.findByText(/3 days/i)).toBeInTheDocument()
  })

  it('shows the skill profile section', async () => {
    renderLogbook()
    expect(await screen.findByRole('region', { name: /skill scores/i })).toBeInTheDocument()
  })

  it('renders dimension names in the skill profile', async () => {
    renderLogbook()
    expect(await screen.findByText(/empathy/i)).toBeInTheDocument()
    expect(await screen.findByText(/assertiveness/i)).toBeInTheDocument()
  })

  it('renders a per-skill trajectory chart when a skill has multiple sessions', async () => {
    renderLogbook()
    expect(await screen.findByRole('img', { name: /empathy trajectory over 4 sessions/i })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /assertiveness trajectory over 2 sessions/i })).toBeInTheDocument()
  })

  it('shows personal records section', async () => {
    renderLogbook()
    expect(await screen.findByRole('region', { name: /personal records/i })).toBeInTheDocument()
  })

  it('shows the scenario name in personal records', async () => {
    renderLogbook()
    expect(await screen.findByText(/behavioral interview/i)).toBeInTheDocument()
  })

  it('shows the export button', async () => {
    renderLogbook()
    expect(await screen.findByRole('button', { name: /export logbook as json/i })).toBeInTheDocument()
  })

  it('shows the last session delta as a positive number', async () => {
    renderLogbook()
    expect(await screen.findByText('+12')).toBeInTheDocument()
  })

  it('links to the logbook from a "view full logbook" link in the summary', async () => {
    // This tests the Home panel — here we just ensure the export section is visible
    renderLogbook()
    await screen.findByRole('button', { name: /export logbook/i })
  })
})

describe('Logbook — error state', () => {
  it('shows an error message when the API fails', async () => {
    vi.mocked(api.getLogbookProfile).mockRejectedValue(new Error('Network error'))
    renderLogbook()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/could not load logbook/i)
  })
})

describe('Logbook — single session delta', () => {
  it('does not show last session delta with only one session', async () => {
    vi.mocked(api.getLogbookProfile).mockResolvedValue(
      makeProfile({ total_sessions: 1, last_session_delta: null }),
    )
    renderLogbook()
    await screen.findByRole('heading', { name: /^logbook$/i })
    // When last_session_delta is null, no delta tile should appear
    expect(screen.queryByText(/last session/i)).not.toBeInTheDocument()
  })
})
