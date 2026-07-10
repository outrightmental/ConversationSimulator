// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { recommendNext } from '@convsim/shared'
import type { LogbookProfile, ScenarioInfo } from '@convsim/shared'

function makeScenario(overrides: Partial<ScenarioInfo> = {}): ScenarioInfo {
  return {
    scenario_id: 'scenario_a',
    pack_id: 'pack_x',
    pack_name: 'Test Pack',
    title: 'Scenario A',
    summary: 'A test scenario.',
    content_rating: 'G',
    player_role: { label: 'Employee', brief: 'You are an employee.' },
    difficulty: { default: 'standard', options: {} },
    supported_languages: ['en'],
    duration: { max_turns: 10, soft_time_limit_minutes: 15 },
    state_meters_permitted: false,
    voice_supported: false,
    safety_summary: '',
    estimated_length_label: '~10 min',
    ...overrides,
  }
}

function makeProfile(overrides: Partial<LogbookProfile> = {}): LogbookProfile {
  return {
    total_sessions: 1,
    total_practice_seconds: 600,
    streak_days: 1,
    last_session_date: '2026-07-10',
    dimension_scores: [],
    personal_records: [],
    strongest_dimension: null,
    weakest_dimension: null,
    last_session_delta: null,
    ...overrides,
  }
}

describe('recommendNext — cold start', () => {
  it('returns empty list when no scenarios available', () => {
    expect(recommendNext(null, [])).toEqual([])
  })

  it('returns up to 3 intro scenarios from different packs when profile is null', () => {
    const scenarios = [
      makeScenario({ scenario_id: 's1', pack_id: 'p1', title: 'Intro 1', ladder_position: 'intro' }),
      makeScenario({ scenario_id: 's2', pack_id: 'p2', title: 'Intro 2', ladder_position: 'intro' }),
      makeScenario({ scenario_id: 's3', pack_id: 'p3', title: 'Intro 3', ladder_position: 'intro' }),
      makeScenario({ scenario_id: 's4', pack_id: 'p4', title: 'Intro 4', ladder_position: 'intro' }),
    ]
    const recs = recommendNext(null, scenarios)
    expect(recs).toHaveLength(3)
    expect(recs.map((r) => r.ladder_position)).toEqual(['intro', 'intro', 'intro'])
  })

  it('returns only one intro scenario per pack on cold start', () => {
    const scenarios = [
      makeScenario({ scenario_id: 's1', pack_id: 'p1', title: 'Pack1 Intro', ladder_position: 'intro' }),
      makeScenario({ scenario_id: 's2', pack_id: 'p1', title: 'Pack1 Practice', ladder_position: 'practice' }),
      makeScenario({ scenario_id: 's3', pack_id: 'p2', title: 'Pack2 Intro', ladder_position: 'intro' }),
    ]
    const recs = recommendNext(null, scenarios)
    expect(recs).toHaveLength(2)
    const packIds = recs.map((r) => r.pack_id)
    expect(new Set(packIds).size).toBe(2)
  })

  it('falls back to first scenario per pack when no intro scenarios exist', () => {
    const scenarios = [
      makeScenario({ scenario_id: 's1', pack_id: 'p1', title: 'Practice 1', ladder_position: 'practice' }),
      makeScenario({ scenario_id: 's2', pack_id: 'p2', title: 'Stretch 2', ladder_position: 'stretch' }),
    ]
    const recs = recommendNext(null, scenarios)
    expect(recs).toHaveLength(2)
    expect(recs[0].pack_id).toBe('p1')
    expect(recs[1].pack_id).toBe('p2')
  })

  it('cold-starts when total_sessions is 0 even with a profile object', () => {
    const profile = makeProfile({ total_sessions: 0 })
    const scenarios = [
      makeScenario({ scenario_id: 's1', pack_id: 'p1', title: 'Intro', ladder_position: 'intro' }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs).toHaveLength(1)
    expect(recs[0].reason).toMatch(/starting point|baseline/i)
  })

  it('uses the pack default difficulty on cold start', () => {
    const scenarios = [
      makeScenario({
        scenario_id: 's1',
        pack_id: 'p1',
        title: 'Warmup',
        ladder_position: 'intro',
        difficulty: { default: 'warm', options: {} },
      }),
    ]
    const recs = recommendNext(null, scenarios)
    expect(recs[0].recommended_difficulty).toBe('warm')
  })
})

describe('recommendNext — active profile', () => {
  it('recommends scenarios that test the weakest dimension', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'active_listening', rolling_score: 20, session_count: 3, trajectory: [20] },
        { dimension_id: 'composure', rolling_score: 80, session_count: 3, trajectory: [80] },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's_listen',
        pack_id: 'p1',
        title: 'Listening drill',
        tested_dimensions: ['active_listening'],
      }),
      makeScenario({
        scenario_id: 's_composure',
        pack_id: 'p2',
        title: 'Composure drill',
        tested_dimensions: ['composure'],
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs.length).toBeGreaterThan(0)
    expect(recs[0].scenario_id).toBe('s_listen')
  })

  it('includes the weak dimension name and score in the reason string', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'open_question_rate', rolling_score: 15, session_count: 2, trajectory: [15] },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's1',
        pack_id: 'p1',
        title: 'Question drills',
        tested_dimensions: ['open_question_rate'],
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].reason).toMatch(/open question rate/i)
    expect(recs[0].reason).toMatch(/15/)
  })

  it('recommends warm difficulty when weakest score is below 30', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'clarity', rolling_score: 10, session_count: 2, trajectory: [10] },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's1',
        pack_id: 'p1',
        title: 'Clarity basics',
        tested_dimensions: ['clarity'],
        ladder_position: 'intro',
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].recommended_difficulty).toBe('warm')
  })

  it('recommends standard difficulty for a score between 30 and 55', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'specificity', rolling_score: 45, session_count: 2, trajectory: [45] },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's1',
        pack_id: 'p1',
        title: 'Specificity practice',
        tested_dimensions: ['specificity'],
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].recommended_difficulty).toBe('standard')
  })

  it('recommends hard difficulty for a score between 55 and 75', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'composure', rolling_score: 65, session_count: 4, trajectory: [65] },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's1',
        pack_id: 'p1',
        title: 'Composure challenge',
        tested_dimensions: ['composure'],
        ladder_position: 'practice',
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].recommended_difficulty).toBe('hard')
  })

  it('recommends adversarial difficulty when all weak scores are above 75', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'negotiation', rolling_score: 85, session_count: 5, trajectory: [85] },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's1',
        pack_id: 'p1',
        title: 'Expert negotiation',
        tested_dimensions: ['negotiation'],
        ladder_position: 'stretch',
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].recommended_difficulty).toBe('adversarial')
  })

  it('de-prioritises cleared scenarios in favour of uncleared ones', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'clarity', rolling_score: 25, session_count: 3, trajectory: [25] },
      ],
      personal_records: [
        { scenario_id: 's_cleared', difficulty: 'warm', best_score: 85, achieved_at: '2026-07-01' },
      ],
    })
    const scenarios = [
      makeScenario({
        scenario_id: 's_cleared',
        pack_id: 'p1',
        title: 'Already cleared',
        tested_dimensions: ['clarity'],
      }),
      makeScenario({
        scenario_id: 's_fresh',
        pack_id: 'p2',
        title: 'Fresh scenario',
        tested_dimensions: ['clarity'],
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    // The fresh scenario should rank higher despite same dimensions.
    expect(recs[0].scenario_id).toBe('s_fresh')
  })

  it('returns at most 3 recommendations', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'clarity', rolling_score: 40, session_count: 2, trajectory: [40] },
      ],
    })
    const scenarios = Array.from({ length: 10 }, (_, i) =>
      makeScenario({
        scenario_id: `s${i}`,
        pack_id: `p${i}`,
        title: `Scenario ${i}`,
        tested_dimensions: ['clarity'],
      }),
    )
    const recs = recommendNext(profile, scenarios)
    expect(recs.length).toBeLessThanOrEqual(3)
  })

  it('still surfaces suggestions when installed scenarios lack ladder/dimension metadata', () => {
    // Real packs may not declare the optional metadata yet; an active user with
    // installed packs must not be told to "install a pack".
    const profile = makeProfile({
      total_sessions: 5,
      dimension_scores: [
        { dimension_id: 'clarity', rolling_score: 40, session_count: 5, trajectory: [40] },
      ],
    })
    const scenarios = [
      makeScenario({ scenario_id: 's1', pack_id: 'p1', title: 'Plain One' }),
      makeScenario({ scenario_id: 's2', pack_id: 'p2', title: 'Plain Two' }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs.length).toBeGreaterThan(0)
    expect(recs.length).toBeLessThanOrEqual(3)
    expect(recs.every((r) => r.reason.length > 0)).toBe(true)
  })

  it('ranks a weak-dimension match above metadata-less scenarios', () => {
    const profile = makeProfile({
      total_sessions: 5,
      dimension_scores: [
        { dimension_id: 'clarity', rolling_score: 20, session_count: 5, trajectory: [20] },
      ],
    })
    const scenarios = [
      makeScenario({ scenario_id: 's_plain', pack_id: 'p1', title: 'Plain' }),
      makeScenario({
        scenario_id: 's_match',
        pack_id: 'p2',
        title: 'Targeted',
        tested_dimensions: ['clarity'],
      }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].scenario_id).toBe('s_match')
  })

  it('never recommends a scenario from an uninstalled pack', () => {
    // Only the installed scenario should appear.
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'clarity', rolling_score: 40, session_count: 2, trajectory: [40] },
      ],
    })
    const installedScenarios = [
      makeScenario({ scenario_id: 's_installed', pack_id: 'installed_pack', title: 'Installed', tested_dimensions: ['clarity'] }),
    ]
    const recs = recommendNext(profile, installedScenarios)
    expect(recs.every((r) => r.pack_id === 'installed_pack')).toBe(true)
  })

  it('does not over-claim "weakest" when the drilled dimension is not the global lowest', () => {
    const profile = makeProfile({
      dimension_scores: [
        { dimension_id: 'open_question_rate', rolling_score: 10, session_count: 3, trajectory: [10] },
        { dimension_id: 'clarity', rolling_score: 25, session_count: 3, trajectory: [25] },
      ],
    })
    const scenarios = [
      // Only tests clarity (the 2nd-weakest), not the global weakest.
      makeScenario({ scenario_id: 's1', pack_id: 'p1', title: 'Clarity drill', tested_dimensions: ['clarity'] }),
    ]
    const recs = recommendNext(profile, scenarios)
    expect(recs[0].reason).toMatch(/clarity/i)
    expect(recs[0].reason).toMatch(/one of your weakest metrics/i)
    expect(recs[0].reason).not.toMatch(/is your weakest metric/i)
  })
})
