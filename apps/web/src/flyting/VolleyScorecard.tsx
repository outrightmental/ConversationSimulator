// SPDX-License-Identifier: Apache-2.0
//
// The per-volley scorecard: dimension bars, verified hooks with their quoted
// evidence, the freshness meter, the composition arithmetic, and the umpire's
// line. The arithmetic is the point — a score that cannot show its own working
// is a slot machine, so every multiplier that went into S is on screen and the
// raw judge verdict is one disclosure away.
import { useState } from 'react'
import type { VolleyScorecard as Scorecard, JudgeDimension } from '@convsim/shared'
import { JUDGE_DIMENSIONS } from '@convsim/shared'
import {
  bandColor,
  bandLabel,
  flagLabel,
  foulLabel,
  gateReasonLabel,
  ScoreBar,
  Tag,
} from './primitives'

const DIMENSION_HINTS: Record<JudgeDimension, string> = {
  sting: 'Does it land on THIS target?',
  wit: 'Surprise, cleverness, economy',
  craft: 'Imagery, construction, sound',
  fidelity: 'In-character voice, register, period diction',
}

const DIMENSION_COLORS: Record<JudgeDimension, string> = {
  sting: '#ef4444',
  wit: '#eab308',
  craft: '#6366f1',
  fidelity: '#22c55e',
}

/**
 * Why a hook claim was refused, in the player's terms. Shown rather than
 * hidden: the judge being auditable is the whole reason a verified hook is
 * worth anything.
 */
const DROPPED_HOOK_REASONS: Record<string, string> = {
  evidence_not_in_volley: 'the quoted words are not in your volley',
  unknown_trait: 'not on this target',
  duplicate_trait: 'this trait was already counted for this volley',
  overlapping_evidence: 'those words already counted for another trait',
  over_hook_cap: 'past the four-hook cap',
}

/**
 * Who is speaking the umpire's line. A constant, not the scenario's
 * `judge_flavor`: that field is one to four sentences of character note and
 * reads as gibberish inline ("A retired music-hall chairman who has heard every
 * joke in London twice. Cockney. Unimpressable.: Nought points."). The flavour
 * is the tooltip instead, and the setup screen prints it in full.
 */
const UMPIRE_PREFIX = 'The umpire'

const BONUS_LABELS: Record<string, string> = {
  riposte: 'Riposte',
  callback: 'Callback',
  device_rotation: 'Device rotation',
  compound: 'Compound construction',
}

function num(value: number, places = 2): string {
  return value.toFixed(places)
}

/**
 * The arithmetic line: 100 · Q · T · F · P (· decay) = base, then the bonuses.
 * Written out in the same order as the composition in docs/flyting.md so a
 * player reading both sees the same equation.
 */
function Arithmetic({ card }: { card: Scorecard }) {
  const c = card.composition
  const decay = c.run_on_decay ?? 1
  // A plagiarized zinger is capped before bonuses, so the product of the
  // multipliers is not what the base came out at. Writing `=` there would print
  // a false equation on the one card whose whole point is showing its working.
  const capped = card.flags.includes('plagiarized_zinger')
  const parts = [
    `100`,
    `× ${num(c.quality)} Q`,
    `× ${num(c.topicality)} T`,
    `× ${num(c.freshness)} F`,
    `× ${num(c.difficulty)} P`,
  ]
  if (decay < 1) parts.push(`× ${num(decay)} run-on`)
  return (
    <div
      data-testid="volley-arithmetic"
      style={{
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: '0.75rem',
        color: '#a1a1aa',
        lineHeight: 1.7,
        padding: '0.4rem 0.6rem',
        borderRadius: 6,
        background: '#09090b',
        border: '1px solid #27272a',
      }}
    >
      <div>
        {parts.join(' ')}
        {capped ? (
          <>
            {' '}
            → capped at <strong style={{ color: '#e4e4e7' }}>{c.base}</strong>
            <span style={{ color: '#71717a' }}> — borrowed material</span>
          </>
        ) : (
          <>
            {' '}= <strong style={{ color: '#e4e4e7' }}>{c.base}</strong>
          </>
        )}
      </div>
      {(c.bonuses ?? []).map((bonus) => (
        <div key={bonus.id}>
          + {bonus.points} {BONUS_LABELS[bonus.id] ?? bonus.id}
          {bonus.evidence ? (
            <span style={{ color: '#71717a' }}> — “{bonus.evidence}”</span>
          ) : null}
        </div>
      ))}
      <div style={{ color: '#e4e4e7' }}>
        = <strong>{card.score}</strong> points
        {card.heat != null && card.heat > 1 && card.banked_score != null ? (
          <>
            {' '}× ×{card.heat.toFixed(1)} heat ={' '}
            <strong data-testid="volley-banked">{card.banked_score}</strong> banked
          </>
        ) : null}
      </div>
    </div>
  )
}

/**
 * Verified hooks. Each one names a trait from the target's attack surface and
 * quotes the player's own words, because an unverified hook is just the model
 * agreeing with itself. Refused claims are shown too — the judge being
 * auditable is the whole reason hooks are worth anything.
 */
function Hooks({ card }: { card: Scorecard }) {
  const hooks = card.judge?.hooks ?? []
  const dropped = card.judge?.dropped_hooks ?? []
  if (hooks.length === 0 && dropped.length === 0) return null
  return (
    <div data-testid="volley-hooks">
      <h4 style={{ fontSize: '0.75rem', color: '#a1a1aa', margin: '0 0 0.3rem' }}>
        Verified hooks
      </h4>
      {hooks.length === 0 && (
        <p style={{ fontSize: '0.75rem', color: '#71717a', margin: '0 0 0.3rem' }}>
          Nothing landed on the target's attack surface.
        </p>
      )}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '0.25rem' }}>
        {hooks.map((hook, i) => (
          <li
            key={`${hook.trait}-${i}`}
            style={{ fontSize: '0.78rem', display: 'flex', gap: '0.4rem', alignItems: 'baseline' }}
          >
            <Tag
              label={hook.trait.replace(/_/g, ' ')}
              color={hook.discovered ? '#a855f7' : '#22c55e'}
              title={hook.discovered ? 'Discovered this run — worth double' : undefined}
            />
            <span style={{ color: '#d4d4d8' }}>“{hook.evidence}”</span>
            {hook.discovered && (
              <span style={{ color: '#a855f7', fontSize: '0.7rem' }}>discovered ×2</span>
            )}
          </li>
        ))}
        {dropped.map((hook, i) => (
          <li
            key={`dropped-${hook.trait}-${i}`}
            style={{ fontSize: '0.75rem', color: '#71717a', display: 'flex', gap: '0.4rem' }}
          >
            <Tag label={hook.trait.replace(/_/g, ' ')} color="#71717a" />
            <span>
              refused — {DROPPED_HOOK_REASONS[hook.reason] ?? hook.reason.replace(/_/g, ' ')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Freshness({ card }: { card: Scorecard }) {
  const f = card.freshness
  const pct = Math.round(f.value * 100)
  const source =
    f.nearest_source === 'cliche'
      ? 'closest match: a stock insult'
      : f.nearest_source === 'session'
        ? 'closest match: an earlier volley this session'
        : 'nothing like it yet'
  return (
    <div data-testid="volley-freshness">
      <ScoreBar
        label="Freshness"
        value={f.value}
        max={1}
        color={f.value >= 0.8 ? '#22c55e' : f.value >= 0.5 ? '#eab308' : '#ef4444'}
        valueText={`${pct}%`}
        testId="freshness-meter"
      />
      <p style={{ fontSize: '0.7rem', color: '#71717a', margin: '0.2rem 0 0 88px' }}>
        {source}
        {f.nearest_label ? ` — “${f.nearest_label}”` : ''}
        {f.method === 'lexical' ? ' · lexical fallback' : ''}
      </p>
    </div>
  )
}

export interface VolleyScorecardProps {
  card: Scorecard
  /** The volley's own text. Shown above the numbers so the two read together. */
  text?: string
  /**
   * The scenario's `judge_flavor` — one to four sentences establishing the
   * umpire's voice ("A retired music-hall chairman who has heard every joke in
   * London twice. Cockney. Unimpressable."). It is a character note, not a
   * name, so it rides on the line as a tooltip; the visible prefix stays the
   * constant below. The setup screen is where the whole note is shown.
   */
  umpireFlavor?: string
  /** Collapsed by default in a log; expanded for the volley just played. */
  defaultOpen?: boolean
  compact?: boolean
}

export function VolleyScorecard({
  card,
  text,
  umpireFlavor,
  defaultOpen = true,
  compact = false,
}: VolleyScorecardProps) {
  const [showJudgeJson, setShowJudgeJson] = useState(false)
  const judge = card.judge
  const color = bandColor(card.band)
  const foul = card.gate.foul
  const umpireLine = card.gate.umpire_mock || judge?.umpire_line || null

  return (
    <article
      data-testid={`scorecard-${card.speaker}-${card.volley_number}`}
      aria-label={`${card.speaker === 'npc' ? 'Opponent' : 'Your'} volley ${card.volley_number}: ${card.score} points, ${bandLabel(card.band)}`}
      style={{
        border: `1px solid ${color}44`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 8,
        background: '#111113',
        padding: compact ? '0.5rem 0.7rem' : '0.75rem 0.9rem',
        display: 'grid',
        gap: '0.6rem',
      }}
    >
      <header style={{ display: 'flex', alignItems: 'baseline', gap: '0.6rem', flexWrap: 'wrap' }}>
        <span
          data-testid="volley-score"
          style={{ fontSize: '1.6rem', fontWeight: 700, color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}
        >
          {card.score}
        </span>
        <span style={{ color, fontSize: '0.85rem', fontWeight: 600 }}>{bandLabel(card.band)}</span>
        <span style={{ color: '#71717a', fontSize: '0.75rem' }}>
          {card.speaker === 'npc' ? 'Opponent' : 'You'} · volley {card.volley_number}
        </span>
        <span style={{ flex: 1 }} />
        {foul && <Tag label={`Foul: ${foulLabel(foul)}`} color="#ef4444" />}
        {card.gate.outcome === 'dud' && !foul && <Tag label="Dud" color="#71717a" />}
        {card.momentum != null && <Tag label={`Momentum ${card.momentum}`} color="#a855f7" />}
      </header>

      {text && (
        <blockquote
          style={{
            margin: 0,
            paddingLeft: '0.6rem',
            borderLeft: '2px solid #27272a',
            color: '#e4e4e7',
            fontSize: '0.88rem',
            lineHeight: 1.5,
          }}
        >
          {text}
        </blockquote>
      )}

      {card.gate.reason && (
        <p role="status" style={{ margin: 0, fontSize: '0.8rem', color: '#fca5a5' }}>
          {gateReasonLabel(card.gate.reason)}
        </p>
      )}

      {card.flags.length > 0 && (
        <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }} aria-label="Volley flags">
          {card.flags.map((flag) => (
            <Tag key={flag} label={flagLabel(flag)} color="#f59e0b" />
          ))}
        </div>
      )}

      {!compact && (
        <>
          <div style={{ display: 'grid', gap: '0.3rem' }} aria-label="Judge dimensions">
            {JUDGE_DIMENSIONS.map((dim) => (
              // The hint rides on the row's title: a player who has forgotten
              // what "fidelity" is scoring should not have to open the docs.
              <div key={dim} title={`${dim} — ${DIMENSION_HINTS[dim]}`}>
                <ScoreBar
                  label={dim}
                  value={judge ? judge[dim] : 0}
                  max={10}
                  color={DIMENSION_COLORS[dim]}
                  valueText={judge ? `${judge[dim]} / 10` : '—'}
                  testId={`dimension-${dim}`}
                />
              </div>
            ))}
          </div>

          {!judge && (
            <p style={{ margin: 0, fontSize: '0.75rem', color: '#fbbf24' }}>
              The judge did not answer, so this volley was scored from the
              deterministic stages alone. The dimension bars are blank rather
              than guessed.
            </p>
          )}

          <Hooks card={card} />
          <Freshness card={card} />

          {(judge?.themes?.length || judge?.devices?.length) ? (
            <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
              {(judge?.themes ?? []).map((theme) => (
                <Tag key={`t-${theme}`} label={theme.replace(/_/g, ' ')} color="#38bdf8" />
              ))}
              {(judge?.devices ?? []).map((device) => (
                <Tag key={`d-${device}`} label={device.replace(/_/g, ' ')} color="#818cf8" />
              ))}
            </div>
          ) : null}

          <Arithmetic card={card} />

          {card.craft_metrics.rarest_words && card.craft_metrics.rarest_words.length > 0 && (
            <p style={{ margin: 0, fontSize: '0.72rem', color: '#71717a' }}>
              Rarest words: {card.craft_metrics.rarest_words.join(', ')} ·{' '}
              {card.craft_metrics.word_count} words
              {card.craft_metrics.second_person ? '' : ' · not aimed at anyone'}
            </p>
          )}
        </>
      )}

      {umpireLine && (
        <p
          data-testid="umpire-line"
          style={{
            margin: 0,
            fontSize: '0.85rem',
            fontStyle: 'italic',
            color: '#fcd34d',
            borderTop: '1px solid #27272a',
            paddingTop: '0.5rem',
          }}
        >
          <span
            title={umpireFlavor || undefined}
            style={{
              color: '#71717a',
              fontStyle: 'normal',
              cursor: umpireFlavor ? 'help' : undefined,
            }}
          >
            {UMPIRE_PREFIX}:{' '}
          </span>
          {umpireLine}
        </p>
      )}

      {card.audience_reaction && (
        <p style={{ margin: 0, fontSize: '0.8rem', color: '#a3e635' }} role="status">
          {card.audience_reaction}
        </p>
      )}

      {!compact && defaultOpen && (
        <div>
          <button
            type="button"
            onClick={() => setShowJudgeJson((v) => !v)}
            aria-expanded={showJudgeJson}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              color: '#71717a',
              fontSize: '0.7rem',
              cursor: 'pointer',
              textDecoration: 'underline',
            }}
          >
            {showJudgeJson ? 'Hide' : 'Show'} the raw judge verdict
          </button>
          {showJudgeJson && (
            <pre
              data-testid="judge-json"
              style={{
                margin: '0.4rem 0 0',
                padding: '0.5rem',
                borderRadius: 6,
                background: '#09090b',
                border: '1px solid #27272a',
                color: '#a1a1aa',
                fontSize: '0.68rem',
                overflowX: 'auto',
                maxHeight: 260,
              }}
            >
              {JSON.stringify(judge ?? { judge: null }, null, 2)}
            </pre>
          )}
        </div>
      )}
    </article>
  )
}

export default VolleyScorecard
