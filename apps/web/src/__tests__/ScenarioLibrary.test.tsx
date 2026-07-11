// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ScenarioInfo, PackValidationResult } from '@convsim/shared'
import ScenarioLibrary from '../screens/ScenarioLibrary'

vi.mock('../api/client', () => ({
  api: {
    listScenarios: vi.fn(),
    validatePack: vi.fn(),
    listPacks: vi.fn(),
    importPack: vi.fn(),
    getModels: vi.fn(),
    workshop: {
      listItems: vi.fn(),
      sync: vi.fn(),
    },
  },
  apiClient: {
    reseedOfficialPacks: vi.fn(),
  },
}))

import { api, apiClient } from '../api/client'
import type { ModelsResponse } from '@convsim/shared'
const mockApi = vi.mocked(api)
const mockApiClient = vi.mocked(apiClient)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SCENARIO_BEHAVIORAL: ScenarioInfo = {
  scenario_id: 'behavioral_interview',
  title: 'Behavioral Interview',
  summary: 'A mid-level job interview focused on communication, clarity, and self-awareness.',
  content_rating: 'PG',
  pack_id: 'official.job_interview_basic',
  pack_name: 'Job Interview Basics',
  player_role: { label: 'Candidate', brief: 'You are interviewing for a product manager role.' },
  difficulty: {
    default: 'standard',
    options: {
      warm:     { patience: 80, volatility: 20, disclosure: 70, time_pressure: 20 },
      standard: { patience: 50, volatility: 50, disclosure: 50, time_pressure: 50 },
      hard:     { patience: 25, volatility: 70, disclosure: 25, time_pressure: 60 },
    },
  },
  supported_languages: ['en'],
  duration: { max_turns: 18, soft_time_limit_minutes: 20 },
  state_meters_permitted: false,
  voice_supported: true,
  safety_summary: 'PG content only.',
  estimated_length_label: '15–20 minutes',
  tags: ['interview', 'professional'],
  recommended_model: ['claude-opus-4-8', 'claude-sonnet-4-6'],
}

const SCENARIO_HOSTILE: ScenarioInfo = {
  scenario_id: 'hostile_executive_interview',
  title: 'Hostile Executive Interview',
  summary: 'A high-pressure interview with a skeptical senior executive.',
  content_rating: 'PG',
  pack_id: 'official.job_interview_basic',
  pack_name: 'Job Interview Basics',
  player_role: { label: 'Candidate', brief: 'VP-level interview.' },
  difficulty: {
    default: 'standard',
    options: {
      standard:    { patience: 30, volatility: 60, disclosure: 30, time_pressure: 60 },
      hard:        { patience: 15, volatility: 80, disclosure: 15, time_pressure: 75 },
      adversarial: { patience: 5,  volatility: 95, disclosure: 5,  time_pressure: 90 },
    },
  },
  supported_languages: ['en'],
  duration: { max_turns: 14, soft_time_limit_minutes: 15 },
  state_meters_permitted: false,
  voice_supported: false,
  safety_summary: 'PG content only.',
  estimated_length_label: '12–18 minutes',
  tags: ['interview', 'professional', 'pressure'],
  recommended_model: ['claude-opus-4-8', 'claude-sonnet-4-6'],
}

const SCENARIO_SPANISH: ScenarioInfo = {
  scenario_id: 'spanish_coffee',
  title: 'Spanish Coffee Conversation',
  summary: 'Practice casual Spanish conversation at a café. Corrections are gentle and optional.',
  content_rating: 'G',
  pack_id: 'official.language_cafe',
  pack_name: 'Language Café',
  player_role: { label: 'Language Learner', brief: 'Practicing Spanish in Madrid.' },
  difficulty: {
    default: 'warm',
    options: {
      warm:     { patience: 80, volatility: 20, disclosure: 80, time_pressure: 10 },
      standard: { patience: 55, volatility: 45, disclosure: 55, time_pressure: 30 },
    },
  },
  supported_languages: ['es', 'en'],
  duration: { max_turns: 20, soft_time_limit_minutes: 25 },
  state_meters_permitted: false,
  voice_supported: true,
  safety_summary: 'G-rated.',
  estimated_length_label: '15–25 minutes',
  tags: ['language', 'social'],
}

const ALL_SCENARIOS = [SCENARIO_BEHAVIORAL, SCENARIO_HOSTILE, SCENARIO_SPANISH]

const VALID_RESULT: PackValidationResult = {
  pack_id: 'official.job_interview_basic',
  valid: true,
  errors: [],
}

const INVALID_RESULT: PackValidationResult = {
  pack_id: 'official.job_interview_basic',
  valid: false,
  errors: [
    { rule_id: 'MISSING_FILE', file_path: 'scenarios/interview.yaml', message: 'File not found' },
    { rule_id: 'SCHEMA_VALIDATION', message: 'Invalid schema version' },
  ],
}

function renderLibrary() {
  return render(
    <MemoryRouter
      initialEntries={['/library']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ScenarioLibrary />
    </MemoryRouter>,
  )
}

const MODELS_READY: ModelsResponse = {
  runtime_health: { status: 'ready', runtime_id: 'llama', runtime_name: 'llama.cpp', model_id: 'test', latency_ms: null, message: null, checked_at: '' },
  active: { runtime_id: 'llama', model_id: 'test' },
  registry: [],
  installed: [],
  ollama_models: [],
  total: 0,
  last_benchmark: null,
}

const MODELS_UNAVAILABLE: ModelsResponse = {
  ...MODELS_READY,
  runtime_health: { ...MODELS_READY.runtime_health, status: 'unavailable' },
}

const INDEXED_PACKS_EMPTY = { packs: [], total: 0 }

const INDEXED_PACKS_WITH_JOB = {
  packs: [
    {
      pack_id: 'official.job_interview_basic',
      name: 'Job Interview Basics',
      scenario_count: 2,
      pack_root: '/home/user/.convsim/packs/official.job_interview_basic',
    },
  ],
  total: 1,
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  mockApi.listScenarios.mockResolvedValue({ ok: true, data: ALL_SCENARIOS })
  mockApi.validatePack.mockResolvedValue({ ok: true, data: VALID_RESULT })
  mockApi.listPacks.mockResolvedValue({ ok: true, data: INDEXED_PACKS_EMPTY })
  mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_READY })
  mockApi.workshop.listItems.mockResolvedValue({ ok: true, data: { items: [] } })
  mockApi.importPack.mockResolvedValue({ ok: true, data: {
    pack_id: 'community.test_pack',
    name: 'Test Pack',
    version: '1.0.0',
    dest: '/home/user/.convsim/packs/community.test_pack',
  }})
})

// ---------------------------------------------------------------------------
// Heading and basic render
// ---------------------------------------------------------------------------

describe('page heading', () => {
  it('renders the Scenario Library heading', async () => {
    renderLibrary()
    expect(await screen.findByRole('heading', { name: /scenario library/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Loading and error states
// ---------------------------------------------------------------------------

describe('loading states', () => {
  it('shows loading text while fetching', () => {
    mockApi.listScenarios.mockReturnValue(new Promise(() => {}))
    renderLibrary()
    expect(screen.getByText(/loading scenarios/i)).toBeInTheDocument()
  })

  it('shows error message when fetch fails', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'network' } })
    renderLibrary()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/connection failed/i),
    )
  })
})

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe('empty state', () => {
  it('shows empty state when no scenarios are installed', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    renderLibrary()
    await waitFor(() =>
      expect(screen.getByTestId('empty-state')).toBeInTheDocument(),
    )
  })

  it('empty state mentions how to import packs', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    renderLibrary()
    await waitFor(() =>
      expect(screen.getByTestId('empty-state')).toHaveTextContent(/import a pack/i),
    )
  })

  it('empty state has an import pack button', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    renderLibrary()
    await waitFor(() => screen.getByTestId('empty-state'))
    expect(screen.getByTestId('empty-import-pack-button')).toBeInTheDocument()
  })

  it('empty state has a restore official packs button', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    renderLibrary()
    await waitFor(() => screen.getByTestId('empty-state'))
    expect(screen.getByTestId('restore-official-packs-button')).toBeInTheDocument()
  })

  it('restoring official packs reseeds and refreshes the scenario list', async () => {
    // Start empty; after a successful reseed the scenarios reload with content.
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    mockApiClient.reseedOfficialPacks.mockResolvedValue({ ok: true, data: { seeded: 4 } })
    renderLibrary()
    await waitFor(() => screen.getByTestId('empty-state'))

    // Once restore succeeds, the list is reloaded so newly seeded scenarios appear.
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: ALL_SCENARIOS })
    fireEvent.click(screen.getByTestId('restore-official-packs-button'))

    await waitFor(() => expect(mockApiClient.reseedOfficialPacks).toHaveBeenCalled())
    await waitFor(() =>
      expect(screen.queryByTestId('empty-state')).toBeNull(),
    )
  })

  it('shows a retry affordance when restoring official packs fails', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    mockApiClient.reseedOfficialPacks.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'network' },
    })
    renderLibrary()
    await waitFor(() => screen.getByTestId('empty-state'))

    fireEvent.click(screen.getByTestId('restore-official-packs-button'))

    await waitFor(() =>
      expect(screen.getByTestId('restore-official-packs-button')).toHaveTextContent(/retry/i),
    )
  })
})

// ---------------------------------------------------------------------------
// Scenario cards rendering
// ---------------------------------------------------------------------------

describe('scenario card rendering', () => {
  it('renders all scenario titles', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByText('Hostile Executive Interview')).toBeInTheDocument()
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('renders scenario summaries', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText(/mid-level job interview/i))
    expect(screen.getByText(/skeptical senior executive/i)).toBeInTheDocument()
  })

  it('shows estimated length label on each card', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('15–20 minutes'))
    expect(screen.getByText('15–25 minutes')).toBeInTheDocument()
  })

  it('shows the player role label', async () => {
    renderLibrary()
    await waitFor(() => screen.getAllByText(/role: candidate/i))
    expect(screen.getByText(/role: language learner/i)).toBeInTheDocument()
  })

  it('shows content rating chip for each scenario', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const pgChips = screen.getAllByText('PG')
    expect(pgChips.length).toBeGreaterThan(0)
    // G appears in the filter option and the chip — both count as "rendered"
    expect(screen.getAllByText('G').length).toBeGreaterThan(0)
  })

  it('shows voice supported badge only for voice-enabled scenarios', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const voiceBadges = screen.getAllByText('Voice supported')
    // SCENARIO_BEHAVIORAL and SCENARIO_SPANISH have voice; SCENARIO_HOSTILE does not
    expect(voiceBadges).toHaveLength(2)
  })

  it('shows difficulty chips', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    // Warm, Standard, Hard present from SCENARIO_BEHAVIORAL
    const warmChips = screen.getAllByText('Warm')
    expect(warmChips.length).toBeGreaterThan(0)
  })

  it('shows supported languages', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    // EN appears in multiple chips across scenarios
    expect(screen.getAllByText('EN').length).toBeGreaterThan(0)
    // ES appears in both the filter option and the chip for SCENARIO_SPANISH
    expect(screen.getAllByText('ES').length).toBeGreaterThan(0)
  })

  it('shows tag chips when scenario has tags', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    // 'interview' tag appears on two scenario cards
    expect(screen.getAllByText('interview').length).toBeGreaterThan(0)
    // 'language' tag appears on the Spanish scenario card (also in the filter option)
    expect(screen.getAllByText('language').length).toBeGreaterThan(0)
  })

  it('shows recommended model chips when scenario has recommended_model', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    // Both job-interview scenarios have recommended_model set
    expect(screen.getAllByText('claude-opus-4-8').length).toBeGreaterThan(0)
    expect(screen.getAllByText('claude-sonnet-4-6').length).toBeGreaterThan(0)
  })

  it('does not show model chips for scenarios without recommended_model', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Spanish Coffee Conversation'))
    // SCENARIO_SPANISH has no recommended_model — its card section should have no model chips
    // We can't assert model text is absent globally since other cards show them, but
    // the Spanish pack section has exactly 1 scenario
    const spanishSection = screen.getByRole('heading', { name: /language café/i }).closest('section')!
    expect(spanishSection.textContent).not.toMatch(/claude-opus/)
  })
})

// ---------------------------------------------------------------------------
// Pack group headings
// ---------------------------------------------------------------------------

describe('pack group sections', () => {
  it('renders a section heading for each pack', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByRole('heading', { name: /job interview basics/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /language café/i })).toBeInTheDocument()
  })

  it('shows scenario count per pack', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByText(/2 scenarios/i)).toBeInTheDocument()
    expect(screen.getByText(/1 scenario\b/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Launch action
// ---------------------------------------------------------------------------

describe('launch action', () => {
  it('renders a launch link for each scenario', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('launch-behavioral_interview'))
    expect(screen.getByTestId('launch-hostile_executive_interview')).toBeInTheDocument()
    expect(screen.getByTestId('launch-spanish_coffee')).toBeInTheDocument()
  })

  it('behavioral interview launch link points to /setup/behavioral_interview', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('launch-behavioral_interview'))
    expect(screen.getByTestId('launch-behavioral_interview')).toHaveAttribute(
      'href',
      '/setup/behavioral_interview',
    )
  })

  it('launch link has accessible aria-label', async () => {
    renderLibrary()
    await waitFor(() => screen.getByRole('link', { name: /launch behavioral interview/i }))
    expect(screen.getByRole('link', { name: /launch behavioral interview/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

describe('search', () => {
  it('search input is present', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByRole('searchbox', { name: /search scenarios/i })).toBeInTheDocument()
  })

  it('typing in search filters scenarios by title', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('searchbox', { name: /search scenarios/i }), {
      target: { value: 'Spanish' },
    })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('search filters by summary text', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('searchbox', { name: /search scenarios/i }), {
      target: { value: 'casual Spanish' },
    })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('search filters by pack name', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('searchbox', { name: /search scenarios/i }), {
      target: { value: 'Language Café' },
    })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('search is case-insensitive', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('searchbox', { name: /search scenarios/i }), {
      target: { value: 'behavioral INTERVIEW' },
    })
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.queryByText('Spanish Coffee Conversation')).not.toBeInTheDocument()
  })

  it('clearing search restores all scenarios', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const input = screen.getByRole('searchbox', { name: /search scenarios/i })
    fireEvent.change(input, { target: { value: 'Spanish' } })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    fireEvent.change(input, { target: { value: '' } })
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

describe('filters', () => {
  it('filter by content rating shows only matching scenarios', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('combobox', { name: /filter by content rating/i }), {
      target: { value: 'G' },
    })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('filter by language shows only matching scenarios', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('combobox', { name: /filter by language/i }), {
      target: { value: 'es' },
    })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('filter by difficulty removes scenarios lacking that difficulty option', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    // SCENARIO_HOSTILE only has standard, hard, adversarial; filtering for 'warm' should hide it
    fireEvent.change(screen.getByRole('combobox', { name: /filter by difficulty/i }), {
      target: { value: 'warm' },
    })
    await waitFor(() =>
      expect(screen.queryByText('Hostile Executive Interview')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Behavioral Interview')).toBeInTheDocument()
  })

  it('voice-only checkbox hides scenarios without voice support', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Hostile Executive Interview'))
    fireEvent.click(
      screen.getByRole('checkbox', { name: /show voice-supported scenarios only/i }),
    )
    await waitFor(() =>
      expect(screen.queryByText('Hostile Executive Interview')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Behavioral Interview')).toBeInTheDocument()
  })

  it('filter by tag shows only matching scenarios', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('combobox', { name: /filter by tag/i }), {
      target: { value: 'language' },
    })
    await waitFor(() => expect(screen.queryByText('Behavioral Interview')).not.toBeInTheDocument())
    expect(screen.getByText('Spanish Coffee Conversation')).toBeInTheDocument()
  })

  it('filter by recommended model shows only matching scenarios', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('combobox', { name: /filter by recommended model/i }), {
      target: { value: 'claude-opus-4-8' },
    })
    await waitFor(() => expect(screen.queryByText('Spanish Coffee Conversation')).not.toBeInTheDocument())
    expect(screen.getByText('Behavioral Interview')).toBeInTheDocument()
    expect(screen.getByText('Hostile Executive Interview')).toBeInTheDocument()
  })

  it('model filter dropdown is hidden when no scenarios have recommended_model', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [SCENARIO_SPANISH] })
    renderLibrary()
    await waitFor(() => screen.getByText('Spanish Coffee Conversation'))
    expect(screen.queryByRole('combobox', { name: /filter by recommended model/i })).not.toBeInTheDocument()
  })

  it('shows no-results message when filters produce zero matches', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    fireEvent.change(screen.getByRole('searchbox', { name: /search scenarios/i }), {
      target: { value: 'xyzzy_nonexistent_q1w2e3' },
    })
    await waitFor(() => screen.getByTestId('no-results'))
    expect(screen.getByTestId('no-results')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Results count
// ---------------------------------------------------------------------------

describe('results count', () => {
  it('shows scenario and pack count when scenarios are loaded', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('results-count'))
    const count = screen.getByTestId('results-count')
    expect(count).toHaveTextContent(/3 scenarios/i)
    expect(count).toHaveTextContent(/2 packs/i)
  })

  it('results count updates when filters are applied', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('results-count'))
    fireEvent.change(screen.getByRole('combobox', { name: /filter by content rating/i }), {
      target: { value: 'G' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('results-count')).toHaveTextContent(/1 scenario/i),
    )
  })
})

// ---------------------------------------------------------------------------
// Pack validation
// ---------------------------------------------------------------------------

describe('pack validation', () => {
  it('renders a validate-pack button for each pack', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByTestId('validate-official.job_interview_basic')).toBeInTheDocument()
    expect(screen.getByTestId('validate-official.language_cafe')).toBeInTheDocument()
  })

  it('clicking validate calls validatePack with the pack id', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('validate-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('validate-official.job_interview_basic'))
    await waitFor(() => expect(mockApi.validatePack).toHaveBeenCalledWith('official.job_interview_basic'))
  })

  it('shows valid message when pack validation passes', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('validate-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('validate-official.job_interview_basic'))
    await waitFor(() =>
      expect(
        screen.getByTestId('validation-result-official.job_interview_basic'),
      ).toHaveTextContent(/valid — no issues found/i),
    )
  })

  it('shows validation errors with rule_id when pack is invalid', async () => {
    mockApi.validatePack.mockResolvedValue({ ok: true, data: INVALID_RESULT })
    renderLibrary()
    await waitFor(() => screen.getByTestId('validate-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('validate-official.job_interview_basic'))
    await waitFor(() => screen.getAllByTestId('validation-error'))
    const errors = screen.getAllByTestId('validation-error')
    expect(errors).toHaveLength(2)
    expect(errors[0]).toHaveTextContent('MISSING_FILE')
    expect(errors[1]).toHaveTextContent('SCHEMA_VALIDATION')
  })

  it('shows file_path in validation error when present', async () => {
    mockApi.validatePack.mockResolvedValue({ ok: true, data: INVALID_RESULT })
    renderLibrary()
    await waitFor(() => screen.getByTestId('validate-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('validate-official.job_interview_basic'))
    await waitFor(() => screen.getAllByTestId('validation-error'))
    expect(screen.getAllByTestId('validation-error')[0]).toHaveTextContent(
      'scenarios/interview.yaml',
    )
  })

  it('shows error alert when validate API call fails', async () => {
    mockApi.validatePack.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'network' } })
    renderLibrary()
    await waitFor(() => screen.getByTestId('validate-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('validate-official.job_interview_basic'))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/connection failed/i),
    )
  })

  it('validate button shows loading state while request is in flight', async () => {
    let resolve: (v: { ok: true; data: PackValidationResult }) => void
    mockApi.validatePack.mockReturnValue(new Promise((r) => { resolve = r }))
    renderLibrary()
    await waitFor(() => screen.getByTestId('validate-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('validate-official.job_interview_basic'))
    await waitFor(() =>
      expect(screen.getByTestId('validate-official.job_interview_basic')).toHaveTextContent(
        /validating/i,
      ),
    )
    await act(async () => { resolve!({ ok: true, data: VALID_RESULT }) })
  })
})

// ---------------------------------------------------------------------------
// Hidden agenda / private persona must never appear in UI
// ---------------------------------------------------------------------------

describe('privacy: hidden agenda / private persona', () => {
  it('does not render any element with text "hidden_agenda"', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.queryByText(/hidden.?agenda/i)).not.toBeInTheDocument()
  })

  it('does not render any element with text "private_persona"', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.queryByText(/private.?persona/i)).not.toBeInTheDocument()
  })

  it('only public-facing scenario fields are rendered on cards', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    // npc brief / private fields should not appear; they aren't on ScenarioInfo at all
    expect(screen.queryByText(/private/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

describe('accessibility', () => {
  it('scenario cards use article elements with accessible headings', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const cards = screen.getAllByRole('article')
    expect(cards.length).toBeGreaterThan(0)
  })

  it('pack sections use list role for scenario cards', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const lists = screen.getAllByRole('list')
    expect(lists.length).toBeGreaterThan(0)
  })

  it('search region has accessible role', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByRole('search', { name: /search and filter scenarios/i })).toBeInTheDocument()
  })

  it('results count region is aria-live polite', async () => {
    renderLibrary()
    await waitFor(() => screen.getByTestId('results-count'))
    expect(screen.getByTestId('results-count')).toHaveAttribute('aria-live', 'polite')
  })

  it('each pack section has an aria-label on its scenario list', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const lists = screen.getAllByRole('list')
    const labelledLists = lists.filter((l) => l.getAttribute('aria-label'))
    expect(labelledLists.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// Import pack
// ---------------------------------------------------------------------------

describe('import pack', () => {
  it('renders an import pack button', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByTestId('import-pack-button')).toBeInTheDocument()
  })

  it('import pack button has aria-label', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.getByRole('button', { name: /import pack/i })).toBeInTheDocument()
  })

  it('shows success message after successful import', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const fileInput = screen.getByTestId('import-file-input')
    const file = new File(['PK'], 'test.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => screen.getByTestId('import-success'))
    expect(screen.getByTestId('import-success')).toHaveTextContent(/test pack/i)
  })

  it('calls importPack with the selected file', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const fileInput = screen.getByTestId('import-file-input')
    const file = new File(['PK'], 'mypack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => expect(mockApi.importPack).toHaveBeenCalledWith(file))
  })

  it('shows error message when import fails', async () => {
    mockApi.importPack.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'network' } })
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    const fileInput = screen.getByTestId('import-file-input')
    const file = new File(['bad'], 'bad.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => screen.getByTestId('import-error'))
    expect(screen.getByTestId('import-error')).toHaveTextContent(/connection failed/i)
  })

  it('reloads scenarios after successful import', async () => {
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    mockApi.listScenarios.mockClear()
    const fileInput = screen.getByTestId('import-file-input')
    const file = new File(['PK'], 'mypack.zip', { type: 'application/zip' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => screen.getByTestId('import-success'))
    expect(mockApi.listScenarios).toHaveBeenCalled()
  })

  it('empty state shows an import pack button', async () => {
    mockApi.listScenarios.mockResolvedValue({ ok: true, data: [] })
    renderLibrary()
    await waitFor(() => screen.getByTestId('empty-state'))
    expect(screen.getByTestId('empty-import-pack-button')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Open pack folder
// ---------------------------------------------------------------------------

describe('open pack folder', () => {
  it('shows open-folder button for indexed (imported) packs', async () => {
    mockApi.listPacks.mockResolvedValue({ ok: true, data: INDEXED_PACKS_WITH_JOB })
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    await waitFor(() =>
      expect(
        screen.getByTestId('open-folder-official.job_interview_basic'),
      ).toBeInTheDocument(),
    )
  })

  it('does not show open-folder button for packs not in index', async () => {
    mockApi.listPacks.mockResolvedValue({ ok: true, data: INDEXED_PACKS_EMPTY })
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(
      screen.queryByTestId('open-folder-official.job_interview_basic'),
    ).not.toBeInTheDocument()
  })

  it('clicking open-folder reveals the pack root path', async () => {
    mockApi.listPacks.mockResolvedValue({ ok: true, data: INDEXED_PACKS_WITH_JOB })
    renderLibrary()
    await waitFor(() => screen.getByTestId('open-folder-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('open-folder-official.job_interview_basic'))
    await waitFor(() =>
      expect(
        screen.getByTestId('folder-path-official.job_interview_basic'),
      ).toBeInTheDocument(),
    )
    expect(
      screen.getByTestId('folder-path-official.job_interview_basic'),
    ).toHaveTextContent('/home/user/.convsim/packs/official.job_interview_basic')
  })

  it('open-folder button has an accessible aria-label', async () => {
    mockApi.listPacks.mockResolvedValue({ ok: true, data: INDEXED_PACKS_WITH_JOB })
    renderLibrary()
    await waitFor(() => screen.getByTestId('open-folder-official.job_interview_basic'))
    expect(
      screen.getByRole('button', { name: /open folder for pack job interview basics/i }),
    ).toBeInTheDocument()
  })

  it('clicking open-folder again hides the path', async () => {
    mockApi.listPacks.mockResolvedValue({ ok: true, data: INDEXED_PACKS_WITH_JOB })
    renderLibrary()
    await waitFor(() => screen.getByTestId('open-folder-official.job_interview_basic'))
    fireEvent.click(screen.getByTestId('open-folder-official.job_interview_basic'))
    await waitFor(() =>
      screen.getByTestId('folder-path-official.job_interview_basic'),
    )
    fireEvent.click(screen.getByTestId('open-folder-official.job_interview_basic'))
    await waitFor(() =>
      expect(
        screen.queryByTestId('folder-path-official.job_interview_basic'),
      ).not.toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Model-missing state
// ---------------------------------------------------------------------------

describe('model-missing state', () => {
  it('does not show model-missing banner when runtime is ready', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_READY })
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.queryByTestId('model-missing-banner')).not.toBeInTheDocument()
  })

  it('does not show model-missing banner when runtime is degraded', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: {
      ...MODELS_READY,
      runtime_health: { ...MODELS_READY.runtime_health, status: 'degraded' },
    }})
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.queryByTestId('model-missing-banner')).not.toBeInTheDocument()
  })

  it('shows model-missing banner when runtime is unavailable', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_UNAVAILABLE })
    renderLibrary()
    await waitFor(() => screen.getByTestId('model-missing-banner'))
    expect(screen.getByTestId('model-missing-banner')).toBeInTheDocument()
  })

  it('model-missing banner mentions model setup', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_UNAVAILABLE })
    renderLibrary()
    await waitFor(() => screen.getByTestId('model-missing-banner'))
    expect(screen.getByTestId('model-missing-banner')).toHaveTextContent(/no model is ready/i)
  })

  it('model-missing banner links to model manager', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_UNAVAILABLE })
    renderLibrary()
    await waitFor(() => screen.getByTestId('model-manager-link'))
    expect(screen.getByTestId('model-manager-link')).toHaveAttribute('href', '/model-manager')
  })

  it('model-missing banner is an alert region', async () => {
    mockApi.getModels.mockResolvedValue({ ok: true, data: MODELS_UNAVAILABLE })
    renderLibrary()
    await waitFor(() => screen.getByTestId('model-missing-banner'))
    const banner = screen.getByTestId('model-missing-banner')
    expect(banner).toHaveAttribute('role', 'alert')
  })

  it('does not show model-missing banner when getModels fails', async () => {
    mockApi.getModels.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'network' } })
    renderLibrary()
    await waitFor(() => screen.getByText('Behavioral Interview'))
    expect(screen.queryByTestId('model-missing-banner')).not.toBeInTheDocument()
  })
})
