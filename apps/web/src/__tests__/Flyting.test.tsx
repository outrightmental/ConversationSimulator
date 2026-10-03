// SPDX-License-Identifier: Apache-2.0
//
// The three flyting screens, driven the way a player drives them: pick a
// format, volley for score, read the scorecard. The engine is mocked, but the
// payload shapes are the ones /api/flyting/* returns, so a contract change in
// @convsim/shared fails here rather than at runtime.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import type {
  FlytingRunDetail,
  FlytingRunState,
  FlytingRunSummaryResponse,
  FlytingScenarioSetup,
  FlytingVolleyResponse,
  VolleyScorecard as Scorecard,
} from '@convsim/shared'
import FlytingSetup from '../screens/FlytingSetup'
import Flyting from '../screens/Flyting'
import FlytingDebrief from '../screens/FlytingDebrief'

vi.mock('../api/client', () => ({
  api: {
    flyting: {
      getScenario: vi.fn(),
      highScores: vi.fn(),
      startRun: vi.fn(),
      getRun: vi.fn(),
      submitVolley: vi.fn(),
      endRun: vi.fn(),
    },
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api, true)

const SCENARIO_ID = 'whitechapel_rose'
const SESSION_ID = 'sess-flyt01'

const SETUP: FlytingScenarioSetup = {
  scenario_id: SCENARIO_ID,
  pack_id: 'official.flyting_school',
  title: 'The Scorned Rose of Whitechapel',
  summary: 'Outside his club, in front of his friends.',
  mode: 'flyting',
  content_rating: 'PG-13',
  player_role: { label: 'the Scorned Rose', brief: 'Ruined and discarded.' },
  opening: 'I do not know this woman. Doorman — I do not know this woman.',
  target: {
    npc_id: 'lord_bellingham',
    display_name: 'Lord Bellingham',
    attack_surface: [
      { id: 'vanity', brief: 'Powdered, corseted, and fifty.' },
      { id: 'hypocrisy', brief: 'Preaches temperance; owns two gin palaces.' },
    ],
    discoverable_count: 2,
  },
  formats: ['batting_practice', 'bout'],
  batting_formats: ['set_10', 'timed_90', 'endless'],
  shot_clock_s: 20,
  bout: {
    rounds: 8,
    momentum_win: 85,
    riposte_bonus: 15,
    npc_tier: 'wildean',
    npc_tier_label: 'Wildean',
  },
  difficulty_multiplier: 1.2,
  verse_required: false,
  requires_surface_politeness: false,
  lexicon_hints: ['blackguard'],
  judge_flavor: 'A retired music-hall chairman.',
  audience: { label: 'The club steps' },
  personal_bests: { batting_practice: 420, bout: null },
  goals: ['Land on what he cannot deny.'],
  limits: { max_volley_chars: 500, set_volleys: 10, timed_seconds: 90, endless_whiffs: 3 },
}

const RUN: FlytingRunState = {
  play_format: 'batting_practice',
  batting_format: 'set_10',
  shot_clock_s: 20,
  momentum: 50,
  heat: 1.2,
  whiffs: 0,
  player_total: 129,
  npc_total: 0,
  banked_total: 129,
  round_number: 1,
  player_volleys: 1,
  npc_volleys: 0,
  best_volley_score: 129,
  sudden_death: false,
  theme_uses: { hypocrisy: 1 },
  npc_theme_uses: {},
  recent_devices: [['metaphor']],
  npc_recent_devices: [],
  discovered_traits: [],
  foul_counts: {},
  gate_foul_counts: {},
  elapsed_s: 12,
  daily_seed: null,
  outcome: null,
}

function scorecard(overrides: Partial<Scorecard> = {}): Scorecard {
  return {
    volley_number: 1,
    speaker: 'player',
    score: 129,
    band: 'strong',
    gate: { outcome: 'ok' },
    composition: {
      quality: 0.84,
      topicality: 1.27,
      freshness: 0.97,
      difficulty: 1.2,
      base: 124,
      bonuses: [{ id: 'device_rotation', points: 5 }],
      bonus_total: 5,
    },
    judge: {
      sting: 8,
      wit: 8,
      craft: 9,
      fidelity: 9,
      hooks: [{ trait: 'hypocrisy', evidence: 'polish your virtue' }],
      themes: ['hypocrisy'],
      devices: ['metaphor'],
      umpire_line: 'That one left a mark, madam.',
    },
    craft_metrics: {
      word_count: 24,
      type_token_ratio: 0.9,
      mean_zipf: 3.8,
      second_person: true,
      rarest_words: ['sterling'],
    },
    freshness: { value: 0.97, s_max: 0.17, method: 'lexical', nearest_source: 'none' },
    heat: 1.2,
    banked_score: 155,
    flags: [],
    ...overrides,
  }
}

const VOLLEY_TEXT = 'You polish your virtue like your carriage brass, and both are plate.'

const VOLLEY_RESPONSE: FlytingVolleyResponse = {
  session_id: SESSION_ID,
  state: 'PlayerTurnListening',
  player_volley: scorecard(),
  npc_line: 'The Lord sniffs and studies his gloves.',
  npc_volley: null,
  exchange: null,
  run: RUN,
  run_outcome: null,
  volleys_remaining: 9,
  seconds_remaining: null,
  whiffs_remaining: null,
  target_surface: [
    { id: 'vanity', brief: 'Powdered, corseted, and fifty.', discovered: false },
    { id: 'hypocrisy', brief: 'Preaches temperance; owns two gin palaces.', discovered: false },
  ],
}

const RUN_DETAIL: FlytingRunDetail = {
  session_id: SESSION_ID,
  scenario_id: SCENARIO_ID,
  state: 'PlayerTurnListening',
  run: { ...RUN, player_total: 0, banked_total: 0, best_volley_score: 0, heat: 1, player_volleys: 0 },
  volleys: [],
  volleys_remaining: 10,
  seconds_remaining: null,
  whiffs_remaining: null,
  opening: 'I do not know this woman. Doorman — I do not know this woman.',
  target_surface: [
    { id: 'vanity', brief: 'Powdered, corseted, and fifty.', discovered: false },
    { id: 'hypocrisy', brief: 'Preaches temperance; owns two gin palaces.', discovered: false },
  ],
}

const SUMMARY: FlytingRunSummaryResponse = {
  session_id: SESSION_ID,
  scenario_id: SCENARIO_ID,
  summary: {
    play_format: 'batting_practice',
    batting_format: 'set_10',
    outcome: 'set_complete',
    total_score: 806,
    player_total: 700,
    npc_total: 0,
    volley_count: 10,
    best_volley_score: 129,
    best_volley_text: VOLLEY_TEXT,
    peak_heat: 1.6,
    final_momentum: null,
    whiffs: 1,
    fouls: { bribing_the_ref: 1 },
    theme_report: [
      { theme: 'hygiene', uses: 4, remaining_value: 0.316 },
      { theme: 'hypocrisy', uses: 1, remaining_value: 0.75 },
    ],
    device_histogram: { metaphor: 5, triple: 2 },
    rarest_words: ['sterling', 'blackguard'],
    coaching_notes: [
      'You went to hygiene 4 times; its value had decayed to 31%. Variety is the meta.',
    ],
  },
  volleys: [
    {
      speaker: 'player',
      text: VOLLEY_TEXT,
      score: 129,
      band: 'strong',
      heat: 1.2,
      banked_score: 155,
      momentum: null,
      scorecard: scorecard(),
      created_at: '2026-10-02 18:00:00',
    },
  ],
  high_score_rank: 2,
  personal_best: 900,
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.flyting.getScenario.mockResolvedValue({ ok: true, data: SETUP })
  mockApi.flyting.highScores.mockResolvedValue({
    ok: true,
    data: { scenario_id: SCENARIO_ID, play_format: 'batting_practice', batting_format: 'set_10', entries: [] },
  })
  mockApi.flyting.startRun.mockResolvedValue({
    ok: true,
    data: {
      session_id: SESSION_ID,
      scenario_id: SCENARIO_ID,
      state: 'PlayerTurnListening',
      run: RUN_DETAIL.run,
      created_at: '2026-10-02T18:00:00Z',
    },
  })
  mockApi.flyting.getRun.mockResolvedValue({ ok: true, data: RUN_DETAIL })
  mockApi.flyting.submitVolley.mockResolvedValue({ ok: true, data: VOLLEY_RESPONSE })
  mockApi.flyting.endRun.mockResolvedValue({ ok: true, data: SUMMARY })
})

// ---------------------------------------------------------------------------
// Setup screen
// ---------------------------------------------------------------------------

describe('FlytingSetup', () => {
  function renderSetup() {
    return render(
      <MemoryRouter
        initialEntries={[`/flyting/setup/${SCENARIO_ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <LocationProbe />
        <Routes>
          <Route path="/flyting/setup/:scenarioId" element={<FlytingSetup />} />
          <Route path="/flyting/run/:sessionId" element={<div>playing</div>} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('names the visible attack surface and counts the hidden traits', async () => {
    renderSetup()
    await waitFor(() => screen.getByTestId('attack-surface'))
    expect(screen.getByText(/powdered, corseted, and fifty/i)).toBeInTheDocument()
    // Discoverables are counted, never named: a brief that gives one away
    // cannot make finding it worth double.
    expect(screen.getByTestId('discoverable-count')).toHaveTextContent('2 more')
    expect(screen.queryByText(/gin palaces.*cousin/i)).not.toBeInTheDocument()
  })

  it("quotes the scenario's own opening line in the brief", async () => {
    // The line the first volley answers. It is a required field of every
    // scenario, so a brief that omitted it would be reading past the content
    // the pack actually ships.
    renderSetup()
    await waitFor(() => screen.getByTestId('scenario-opening'))
    expect(screen.getByTestId('scenario-opening')).toHaveTextContent(
      /I do not know this woman/i,
    )
  })

  it('shows the personal best for the chosen format', async () => {
    renderSetup()
    await waitFor(() => screen.getByTestId('personal-best'))
    expect(screen.getByTestId('personal-best')).toHaveTextContent('420')
  })

  it('reads the personal best off the drill board, not the whole play format', async () => {
    // `personal_bests` is keyed by play format alone, so a 3000-point Endless
    // run would otherwise be shown as the mark to beat on a ten-volley Set.
    // The board beside it is narrowed to the drill, and so is this number.
    mockApi.flyting.highScores.mockResolvedValue({
      ok: true,
      data: {
        scenario_id: SCENARIO_ID,
        play_format: 'batting_practice',
        batting_format: 'set_10',
        entries: [
          {
            scenario_id: SCENARIO_ID,
            pack_id: 'official.flyting_school',
            play_format: 'batting_practice',
            batting_format: 'set_10',
            session_id: 'sess-older',
            outcome: 'set_complete',
            total_score: 612,
            volley_count: 10,
            best_volley_score: 141,
            peak_heat: 1.6,
            daily_seed: null,
            achieved_at: '2026-09-30 19:02:00',
          },
        ],
      },
    })
    renderSetup()
    await waitFor(() => expect(screen.getByTestId('personal-best')).toHaveTextContent('612'))
    expect(screen.getByTestId('personal-best')).not.toHaveTextContent('420')
  })

  it('narrows the board to today\'s seed on request', async () => {
    renderSetup()
    await waitFor(() =>
      expect(mockApi.flyting.highScores).toHaveBeenLastCalledWith(
        SCENARIO_ID, 'batting_practice', 'set_10', false,
      ),
    )

    fireEvent.click(screen.getByTestId('board-today-only'))
    await waitFor(() =>
      expect(mockApi.flyting.highScores).toHaveBeenLastCalledWith(
        SCENARIO_ID, 'batting_practice', 'set_10', true,
      ),
    )
  })

  it('does not report the best of today\'s seeded runs as a personal best', async () => {
    // One all-time row of 310; today's seed has nothing on it yet.
    const row = {
      scenario_id: SCENARIO_ID,
      pack_id: 'official.flyting_school',
      play_format: 'batting_practice' as const,
      batting_format: 'set_10' as const,
      session_id: 'sess-older',
      outcome: 'set_complete',
      total_score: 310,
      volley_count: 10,
      best_volley_score: 98,
      peak_heat: 1.4,
      daily_seed: null,
      achieved_at: '2026-09-30 19:00:00',
    }
    mockApi.flyting.highScores.mockImplementation((_id, playFormat, battingFormat, today) =>
      Promise.resolve({
        ok: true,
        data: {
          scenario_id: SCENARIO_ID,
          play_format: playFormat ?? null,
          batting_format: battingFormat ?? null,
          entries: today ? [] : [row],
        },
      }),
    )

    renderSetup()
    await waitFor(() => expect(screen.getByTestId('personal-best')).toHaveTextContent('310'))

    // Filtered, the number falls back to the payload's per-format best rather
    // than calling the best of one day's runs a record.
    fireEvent.click(screen.getByTestId('board-today-only'))
    await waitFor(() => expect(screen.getByTestId('personal-best')).toHaveTextContent('420'))
    expect(screen.getByTestId('high-scores-empty')).toBeInTheDocument()
  })

  it('prints the umpire flavour where there is room for it', async () => {
    renderSetup()
    await waitFor(() => screen.getByTestId('judge-flavor'))
    expect(screen.getByTestId('judge-flavor')).toHaveTextContent('A retired music-hall chairman.')
  })

  it('starts a run and goes to the play screen', async () => {
    renderSetup()
    await waitFor(() => screen.getByTestId('start-flyting-run'))
    fireEvent.click(screen.getByTestId('start-flyting-run'))
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(`/flyting/run/${SESSION_ID}`)
    })
    expect(mockApi.flyting.startRun).toHaveBeenCalledWith(
      expect.objectContaining({ scenario_id: SCENARIO_ID, play_format: 'batting_practice' }),
    )
  })
})

// ---------------------------------------------------------------------------
// Play screen
// ---------------------------------------------------------------------------

describe('Flyting play screen', () => {
  function renderPlay() {
    return render(
      <MemoryRouter
        initialEntries={[`/flyting/run/${SESSION_ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <LocationProbe />
        <Routes>
          <Route path="/flyting/run/:sessionId" element={<Flyting />} />
          <Route path="/flyting/debrief/:sessionId" element={<div>debrief</div>} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('scores a volley and shows its arithmetic', async () => {
    renderPlay()
    await waitFor(() => screen.getByTestId('volley-input'))
    fireEvent.change(screen.getByTestId('volley-input'), { target: { value: VOLLEY_TEXT } })
    fireEvent.click(screen.getByTestId('submit-volley'))

    await waitFor(() => screen.getByTestId('scorecard-player-1'))
    expect(screen.getByTestId('volley-score')).toHaveTextContent('129')
    // The composition is the point: a score that cannot show its working is a
    // slot machine.
    expect(screen.getByTestId('volley-arithmetic')).toHaveTextContent('1.27 T')
    expect(screen.getByTestId('run-total')).toHaveTextContent('129')
    expect(screen.getByTestId('volleys-left')).toHaveTextContent('9')
  })

  it('shows the line the run opened on', async () => {
    renderPlay()
    await waitFor(() => screen.getByTestId('run-opening'))
    expect(screen.getByTestId('run-opening')).toHaveTextContent(/I do not know this woman/i)
  })

  it('lists what is fair game, as the run currently knows it', async () => {
    renderPlay()
    await waitFor(() => screen.getByTestId('target-surface'))
    expect(screen.getByTestId('surface-hypocrisy')).toHaveTextContent(/gin palaces/i)
  })

  it('reveals a discoverable trait the volley that struck it', async () => {
    // npc.schema.json promises a discoverable trait is "revealed when first
    // struck". The engine sends the surface back with every volley, so the
    // reveal has to land on the screen the player is already looking at —
    // without a reload, and without the brief having given it away first.
    mockApi.flyting.submitVolley.mockResolvedValue({
      ok: true,
      data: {
        ...VOLLEY_RESPONSE,
        target_surface: [
          ...VOLLEY_RESPONSE.target_surface,
          { id: 'cowardice', brief: 'Bought his way out of the Crimea.', discovered: true },
        ],
      },
    })
    renderPlay()
    await waitFor(() => screen.getByTestId('volley-input'))
    expect(screen.queryByTestId('surface-cowardice')).not.toBeInTheDocument()

    fireEvent.change(screen.getByTestId('volley-input'), { target: { value: VOLLEY_TEXT } })
    fireEvent.click(screen.getByTestId('submit-volley'))

    await waitFor(() => screen.getByTestId('surface-cowardice'))
    expect(screen.getByTestId('surface-cowardice')).toHaveTextContent(/out of the Crimea/i)
    expect(screen.getByTestId('target-surface')).toHaveTextContent(/one discovered/i)
  })

  it('restores a bout log in the same order it was played in', async () => {
    // The engine writes an exchange player-then-opponent, and the live path puts
    // the player's card at the top of each exchange — only index 0 renders
    // uncompacted, and the player's own arithmetic is what they came to read. A
    // flat reverse of the stored log handed that slot to the opponent, so the
    // log silently reordered itself on reload.
    const stored = (
      speaker: 'player' | 'npc',
      volleyNumber: number,
      score: number,
      text: string,
    ) => ({
      speaker,
      text,
      score,
      band: 'strong' as const,
      heat: 1,
      banked_score: score,
      momentum: 54,
      scorecard: scorecard({ speaker, volley_number: volleyNumber, score }),
      created_at: '2026-10-02 18:00:00',
    })
    mockApi.flyting.getRun.mockResolvedValue({
      ok: true,
      data: {
        ...RUN_DETAIL,
        run: { ...RUN_DETAIL.run, play_format: 'bout', batting_format: null },
        volleys_remaining: null,
        volleys: [
          stored('player', 1, 110, 'first of mine'),
          stored('npc', 1, 90, 'first of theirs'),
          stored('player', 2, 140, 'second of mine'),
          stored('npc', 2, 70, 'second of theirs'),
        ],
      },
    })
    renderPlay()
    await waitFor(() => screen.getByTestId('volley-input'))

    const log = screen.getByLabelText('Volley log')
    const cards = Array.from(
      log.querySelectorAll('[data-testid^="scorecard-"]'),
    ).map((el) => el.getAttribute('data-testid'))
    // Newest exchange first, player above opponent inside each one.
    expect(cards).toEqual([
      'scorecard-player-2',
      'scorecard-npc-2',
      'scorecard-player-1',
      'scorecard-npc-1',
    ])
  })

  it('labels the umpire line without printing the whole flavour note inline', async () => {
    // judge_flavor is a character note of up to 300 characters ("A retired
    // music-hall chairman who has heard every joke in London twice. Cockney.
    // Unimpressable."), not a name. Printed inline before the colon it reads as
    // nonsense, so the visible prefix is a constant and the note is the tooltip.
    const FLAVOUR =
      'A retired music-hall chairman who has heard every joke in London twice. ' +
      'Cockney. Unimpressable. Keeps the gavel in his coat pocket.'
    mockApi.flyting.getScenario.mockResolvedValue({
      ok: true,
      data: { ...SETUP, judge_flavor: FLAVOUR },
    })
    render(
      <MemoryRouter
        initialEntries={[{ pathname: `/flyting/run/${SESSION_ID}`, state: { umpireFlavor: FLAVOUR } }]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/flyting/run/:sessionId" element={<Flyting />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => screen.getByTestId('volley-input'))
    fireEvent.change(screen.getByTestId('volley-input'), { target: { value: VOLLEY_TEXT } })
    fireEvent.click(screen.getByTestId('submit-volley'))

    const line = await waitFor(() => screen.getByTestId('umpire-line'))
    expect(line).toHaveTextContent('The umpire: That one left a mark, madam.')
    expect(line).not.toHaveTextContent('Keeps the gavel in his coat pocket')
    // The voice is still reachable, just not shouted over the verdict.
    expect(line.querySelector(`[title="${FLAVOUR}"]`)).not.toBeNull()
  })

  it('reports the verified hook with the words that earned it', async () => {
    renderPlay()
    await waitFor(() => screen.getByTestId('volley-input'))
    fireEvent.change(screen.getByTestId('volley-input'), { target: { value: VOLLEY_TEXT } })
    fireEvent.click(screen.getByTestId('submit-volley'))
    await waitFor(() => screen.getByTestId('volley-hooks'))
    expect(screen.getByTestId('volley-hooks')).toHaveTextContent('hypocrisy')
    expect(screen.getByTestId('volley-hooks')).toHaveTextContent('polish your virtue')
  })

  it('does not resubmit on a loop when the clock expires and the volley is refused', async () => {
    // A refused volley deliberately leaves the shot clock expired, so the
    // auto-submit has to be armed once per prompt window. Without the latch
    // it fires again on the very next render and keeps firing: a retry loop
    // against the same rejection. `shot_clock_s: 0` expires on the first tick.
    mockApi.flyting.getRun.mockResolvedValue({
      ok: true,
      data: { ...RUN_DETAIL, run: { ...RUN_DETAIL.run, shot_clock_s: 0 }, volleys: [] },
    })
    mockApi.flyting.submitVolley.mockResolvedValue({
      ok: false,
      error: { kind: 'http-error', message: 'This run already ended.', status: 409 },
    })
    renderPlay()
    await waitFor(() => expect(mockApi.flyting.submitVolley).toHaveBeenCalledTimes(1))
    // Several clock ticks (200ms each) pass with the clock still at zero.
    await new Promise((resolve) => setTimeout(resolve, 700))
    expect(mockApi.flyting.submitVolley).toHaveBeenCalledTimes(1)
  })

  it('runs no shot clock in a bout', async () => {
    // The shot clock is a batting-practice mechanic: a bout is bounded by its
    // rounds and decided on momentum. Force-submitting a dud there would hand
    // the opponent the exchange for the crime of thinking about the reply.
    mockApi.flyting.getRun.mockResolvedValue({
      ok: true,
      data: {
        ...RUN_DETAIL,
        run: { ...RUN_DETAIL.run, play_format: 'bout', batting_format: null, shot_clock_s: 0 },
        volleys_remaining: null,
      },
    })
    renderPlay()
    await waitFor(() => screen.getByTestId('volley-input'))
    expect(screen.queryByTestId('shot-clock')).not.toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 500))
    expect(mockApi.flyting.submitVolley).not.toHaveBeenCalled()
  })

  it('reports no shot-clock reading for a bout volley', async () => {
    mockApi.flyting.getRun.mockResolvedValue({
      ok: true,
      data: {
        ...RUN_DETAIL,
        run: { ...RUN_DETAIL.run, play_format: 'bout', batting_format: null },
        volleys_remaining: null,
      },
    })
    renderPlay()
    await waitFor(() => screen.getByTestId('volley-input'))
    fireEvent.change(screen.getByTestId('volley-input'), { target: { value: VOLLEY_TEXT } })
    fireEvent.click(screen.getByTestId('submit-volley'))
    await waitFor(() => expect(mockApi.flyting.submitVolley).toHaveBeenCalled())
    expect(mockApi.flyting.submitVolley).toHaveBeenCalledWith(
      SESSION_ID,
      VOLLEY_TEXT,
      undefined,
      expect.any(Number),
    )
  })

  it('retiring ends the run and goes to the debrief', async () => {
    renderPlay()
    await waitFor(() => screen.getByText('Retire'))
    fireEvent.click(screen.getByText('Retire'))
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(`/flyting/debrief/${SESSION_ID}`)
    })
    // The closing clock reading rides along: a timed drill finishes when its
    // ninety seconds pass, and this screen is the only thing that saw them.
    expect(mockApi.flyting.endRun).toHaveBeenCalledWith(SESSION_ID, expect.any(Number))
  })
})

// ---------------------------------------------------------------------------
// Debrief
// ---------------------------------------------------------------------------

describe('FlytingDebrief', () => {
  function renderDebrief() {
    return render(
      <MemoryRouter
        initialEntries={[`/flyting/debrief/${SESSION_ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/flyting/debrief/:sessionId" element={<FlytingDebrief />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('reports the run, its rank and the personal best', async () => {
    renderDebrief()
    await waitFor(() => screen.getByTestId('summary-total'))
    expect(screen.getByTestId('summary-total')).toHaveTextContent('806')
    expect(screen.getByTestId('summary-best')).toHaveTextContent('129')
    expect(screen.getByTestId('summary-personal-best')).toHaveTextContent('900')
    expect(screen.getByText(/#2 on this board/i)).toBeInTheDocument()
    expect(screen.getByText(/set complete/i)).toBeInTheDocument()
  })

  it('shows the best volley and the coaching notes', async () => {
    renderDebrief()
    await waitFor(() => screen.getByTestId('best-volley'))
    expect(screen.getByTestId('best-volley')).toHaveTextContent('carriage brass')
    expect(screen.getByTestId('coaching-notes')).toHaveTextContent('Variety is the meta')
  })

  it('reports what the next use of an over-used theme would be worth', async () => {
    renderDebrief()
    await waitFor(() => screen.getByTestId('theme-report'))
    // 4 uses of hygiene → the fifth carries 32 % of its value. Showing the
    // remaining value rather than the count is what changes behaviour.
    expect(screen.getByTestId('theme-hygiene')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('32%'),
    )
    expect(screen.getByTestId('device-histogram')).toHaveTextContent('metaphor')
    expect(screen.getByTestId('rarest-words')).toHaveTextContent('sterling')
  })

  it('lists every volley, each opening onto its own scorecard', async () => {
    renderDebrief()
    await waitFor(() => screen.getByTestId('volley-log'))
    expect(screen.getByTestId('volley-row-0')).toHaveTextContent('129')
    expect(screen.getByTestId('scorecard-player-1')).toBeInTheDocument()
  })

  it('offers another run on the same scenario', async () => {
    renderDebrief()
    await waitFor(() => screen.getByTestId('run-again'))
    expect(screen.getByTestId('run-again')).toHaveAttribute(
      'href',
      `/flyting/setup/${SCENARIO_ID}`,
    )
  })

  it('surfaces a failure to end the run, with a retry', async () => {
    mockApi.flyting.endRun.mockResolvedValue({
      ok: false,
      error: { kind: 'runtime-unreachable', message: 'core down' },
    })
    renderDebrief()
    await waitFor(() => screen.getByRole('alert'))
    expect(screen.getByText(/local runtime is unavailable/i)).toBeInTheDocument()
  })
})
