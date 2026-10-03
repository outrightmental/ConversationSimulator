// SPDX-License-Identifier: Apache-2.0
//
// The scorecard on its own, across the states a run actually produces: a clean
// hit, a volley the gates zeroed, a borrowed line capped before its bonuses, a
// register foul the umpire called rather than a pattern, and a volley no judge
// answered.
//
// It is tested apart from the play screen because the arithmetic is the claim
// the mode makes — "the scorecard shows its own working" — and because every
// one of these states reaches the player through a different branch. The play
// screen only ever exercises the happy one.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { VolleyScorecard as Scorecard } from '@convsim/shared'
import VolleyScorecard from '../flyting/VolleyScorecard'

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
      run_on_decay: 1,
      base: 124,
      bonuses: [{ id: 'device_rotation', points: 5, evidence: 'metaphor' }],
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
      riposte: { is_riposte: false, evidence: null },
      callback: { is_callback: false, evidence: null },
      fouls: [],
      umpire_line: 'That one went in sideways.',
      dropped_hooks: [],
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

describe('VolleyScorecard arithmetic', () => {
  it('writes the equation out and banks it at the heat in force', () => {
    render(<VolleyScorecard card={scorecard()} text="You polish your virtue…" />)
    const sum = screen.getByTestId('volley-arithmetic')
    expect(sum).toHaveTextContent('× 0.84 Q')
    expect(sum).toHaveTextContent('× 1.27 T')
    expect(sum).toHaveTextContent('= 124')
    expect(sum).toHaveTextContent('+ 5 Device rotation')
    expect(screen.getByTestId('volley-banked')).toHaveTextContent('155')
  })

  it('shows the run-on decay only when length actually cost something', () => {
    const { rerender } = render(<VolleyScorecard card={scorecard()} />)
    expect(screen.getByTestId('volley-arithmetic')).not.toHaveTextContent('run-on')

    rerender(
      <VolleyScorecard
        card={scorecard({
          composition: { ...scorecard().composition, run_on_decay: 0.9, base: 112 },
          flags: ['run_on'],
        })}
      />,
    )
    expect(screen.getByTestId('volley-arithmetic')).toHaveTextContent('× 0.90 run-on')
  })

  it('does not print an equation a capped volley never satisfied', () => {
    // A borrowed line is capped at 10 before bonuses, so the product of the
    // multipliers is not what the base came out at. Writing `=` there would be
    // a false equation on the one card whose point is showing its working.
    const card = scorecard({
      score: 10,
      band: 'weak',
      composition: { ...scorecard().composition, base: 10, bonuses: [], bonus_total: 0 },
      flags: ['plagiarized_zinger'],
      gate: {
        outcome: 'ok',
        reason: 'plagiarized:cliche:your mother was a hamster',
        umpire_mock: 'Borrowed, and the lender wants it back.',
      },
    })
    render(<VolleyScorecard card={card} />)
    const sum = screen.getByTestId('volley-arithmetic')
    expect(sum).toHaveTextContent('capped at 10')
    expect(sum).toHaveTextContent('borrowed material')
    expect(sum).not.toHaveTextContent('× 1.20 P = 10')
    // And the flag says what it cost, rather than naming the matched line.
    expect(screen.getByLabelText('Volley flags')).toHaveTextContent('capped at 10 points')
    expect(screen.getByRole('status')).toHaveTextContent('famous enough')
  })
})

describe('VolleyScorecard on a volley that scored nothing', () => {
  const fouled = scorecard({
    score: 0,
    band: 'dud',
    judge: null,
    gate: {
      outcome: 'foul',
      foul: 'bribing_the_ref',
      reason: 'addressed_the_judge',
      umpire_mock: 'The judge is not your target.',
      ends_session: false,
    },
    composition: {
      quality: 0,
      topicality: 1,
      freshness: 1,
      difficulty: 1.2,
      base: 0,
      bonuses: [],
      bonus_total: 0,
    },
    heat: 1,
    banked_score: 0,
    flags: [],
  })

  it('names the foul and says why in words, not in slugs', () => {
    render(<VolleyScorecard card={fouled} />)
    expect(screen.getByText('Foul: Bribing the Ref')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('addressed to the scorer')
    expect(screen.getByTestId('umpire-line')).toHaveTextContent('The judge is not your target.')
  })

  it('leaves the dimension bars blank rather than guessing at them', () => {
    render(<VolleyScorecard card={fouled} />)
    expect(screen.getByTestId('dimension-sting')).toHaveAttribute('aria-label', 'sting: —')
    expect(screen.getByText(/judge did not answer/i)).toBeInTheDocument()
  })

  it('translates a register foul the umpire called rather than a pattern', () => {
    render(
      <VolleyScorecard
        card={scorecard({
          score: 0,
          band: 'dud',
          gate: { outcome: 'foul', foul: 'overt_rudeness', reason: 'judge:overt_rudeness' },
          flags: ['judge_foul'],
        })}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('courtesy it had to arrive in')
    expect(screen.getByLabelText('Volley flags')).toHaveTextContent('foul on the register')
  })

  it('says why in words when the shared safety router is what stopped the volley', () => {
    // That router reports its own policy category — `harassment_extreme`,
    // `nsfw_sexual_content` — and those slugs were the one set the label table
    // never covered, so they reached the screen de-slugged and in red. "You
    // deserve to die" is an ordinary thing to type into an insult drill, so
    // this is not an exotic path.
    render(
      <VolleyScorecard
        card={scorecard({
          score: 0,
          band: 'dud',
          judge: null,
          gate: {
            outcome: 'foul',
            reason: 'harassment_extreme',
            umpire_mock: 'That is outside the rules of this contest.',
            ends_session: false,
          },
          flags: [],
        })}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('a real threat rather than a taunt')
    expect(screen.getByRole('status')).not.toHaveTextContent('harassment')
  })

  it('shows no reason line at all for the crisis route, which answers for itself', () => {
    // `self_harm_crisis` reaches the gate through the same branch, and the
    // policy's reply to it is the crisis resource message. A red editorial line
    // above that — least of all one reading "self harm crisis" — is noise at
    // the one moment that calls for none.
    render(
      <VolleyScorecard
        card={scorecard({
          score: 0,
          band: 'dud',
          judge: null,
          gate: {
            outcome: 'foul',
            reason: 'self_harm_crisis',
            umpire_mock: 'Real help is available: call or text 988.',
            ends_session: true,
          },
          flags: [],
        })}
      />,
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByTestId('umpire-line')).toHaveTextContent('Real help is available')
  })
})

describe('VolleyScorecard hook audit', () => {
  it('quotes the words that earned each verified hook', () => {
    render(<VolleyScorecard card={scorecard()} />)
    expect(screen.getByTestId('volley-hooks')).toHaveTextContent('“polish your virtue”')
  })

  it('shows refused claims and why, so the judge stays auditable', () => {
    const card = scorecard()
    render(
      <VolleyScorecard
        card={{
          ...card,
          judge: {
            ...card.judge!,
            dropped_hooks: [
              { trait: 'vanity', evidence: 'his powdered wig', reason: 'evidence_not_in_volley' },
              { trait: 'cowardice', evidence: 'polish your virtue', reason: 'overlapping_evidence' },
            ],
          },
        }}
      />,
    )
    const hooks = screen.getByTestId('volley-hooks')
    expect(hooks).toHaveTextContent('the quoted words are not in your volley')
    expect(hooks).toHaveTextContent('those words already counted for another trait')
  })

  it('says plainly when the comparison was the lexical fallback', () => {
    render(<VolleyScorecard card={scorecard()} />)
    expect(screen.getByTestId('volley-freshness')).toHaveTextContent('lexical fallback')
  })
})
