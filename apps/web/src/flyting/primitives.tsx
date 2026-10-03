// SPDX-License-Identifier: Apache-2.0
//
// The small, shared pieces every flyting surface draws with: band colours, a
// labelled bar, the heat and momentum meters, and the shot clock. Kept apart
// from the screens so the scorecard, the play screen and the debrief cannot
// drift into disagreeing about what a "strong" volley looks like.
import type { VolleyBand, VolleyFlag, VolleyFoul } from '@convsim/shared'

/** Band colours, darkest to brightest. A dud is grey, not red: it cost nothing. */
export const BAND_COLORS: Record<VolleyBand, string> = {
  dud: '#71717a',
  weak: '#f97316',
  solid: '#eab308',
  strong: '#22c55e',
  highlight: '#a855f7',
}

export const BAND_LABELS: Record<VolleyBand, string> = {
  dud: 'Dud',
  weak: 'Weak',
  solid: 'Solid hit',
  strong: 'Strong',
  highlight: 'Highlight reel',
}

/** Plain-English names for the fouls, so no screen shows a raw enum. */
export const FOUL_LABELS: Record<VolleyFoul, string> = {
  below_the_belt: 'Below the Belt',
  out_of_fiction: 'Out of Fiction',
  bribing_the_ref: 'Bribing the Ref',
  overt_rudeness: 'Overt Rudeness',
  anachronism: 'Anachronism',
}

/**
 * What each mechanical flag means in one phrase. The flags are the player's
 * only window into the deterministic stages, so each one says what it cost.
 */
export const FLAG_LABELS: Record<VolleyFlag, string> = {
  plagiarized_zinger: 'Plagiarized zinger — capped at 10 points',
  run_on: 'Run-on — past 60 words, length is taxed and hooks stop counting',
  gibberish: 'No recognisable words',
  no_aim: 'Not aimed at the target — no second person anywhere',
  too_short: 'Under three words',
  judge_unavailable: 'Scored from mechanics only — the judge did not answer',
  shot_clock_expired: 'Shot clock expired',
  whiff: 'Whiff',
}

/**
 * Why a gate fired, in words. The engine's `reason` is a slug built for the
 * volley log and the calibration suites — `slur_or_protected_class`,
 * `injection:PI001`, `plagiarized:cliche:your mother was a hamster` — and none
 * of that is a sentence to show a player mid-run. The qualified reasons carry
 * their detail after a colon; only the anachronism's detail is the player's
 * business (the word that broke the scene), so it is the only one quoted back.
 */
export const GATE_REASON_LABELS: Record<string, string> = {
  slur_or_protected_class: 'That was an attack on who someone is, not on what they do.',
  addressed_the_judge: 'That was addressed to the scorer, not to the target.',
  meta_or_out_of_fiction: 'That was aimed past the character at the machine.',
  profanity_forbidden_by_pack: 'This pack forbids profanity outright.',
  under_three_words: 'Three words is the floor.',
  gibberish: 'Those were not recognisable words.',
  shot_clock_expired: 'The shot clock ran out.',
}

export function gateReasonLabel(reason: string): string {
  const known = GATE_REASON_LABELS[reason]
  if (known) return known
  const colon = reason.indexOf(':')
  const head = colon === -1 ? reason : reason.slice(0, colon)
  const detail = colon === -1 ? '' : reason.slice(colon + 1)
  if (head === 'anachronism') {
    return `“${detail}”, in this room, in this year?`
  }
  if (head === 'injection') {
    return 'That tried to give the engine instructions rather than insult anyone.'
  }
  if (head === 'plagiarized') {
    return 'That line is famous enough that the room has already heard it.'
  }
  return reason.replace(/[_:]/g, ' ')
}

export function foulLabel(foul: string): string {
  return FOUL_LABELS[foul as VolleyFoul] ?? foul.replace(/_/g, ' ')
}

export function flagLabel(flag: string): string {
  return FLAG_LABELS[flag as VolleyFlag] ?? flag.replace(/_/g, ' ')
}

export function bandLabel(band: string): string {
  return BAND_LABELS[band as VolleyBand] ?? band
}

export function bandColor(band: string): string {
  return BAND_COLORS[band as VolleyBand] ?? '#71717a'
}

export const PLAY_FORMAT_LABELS: Record<string, string> = {
  bout: 'The Bout',
  batting_practice: 'Batting Practice',
}

export const BATTING_FORMAT_LABELS: Record<string, string> = {
  timed_90: 'Timed — 90 seconds',
  set_10: 'Set — 10 volleys',
  endless: 'Endless — three whiffs and out',
}

export function formatLabel(playFormat: string, battingFormat?: string | null): string {
  const base = PLAY_FORMAT_LABELS[playFormat] ?? playFormat
  const drill = battingFormat ? BATTING_FORMAT_LABELS[battingFormat] : null
  return drill ? `${base} · ${drill}` : base
}

/** Run outcomes as the engine names them, in words a player recognises. */
export const OUTCOME_LABELS: Record<string, string> = {
  momentum_win: 'Carried out on their shoulders',
  momentum_loss: 'Shouted down',
  points_win: 'Won on points',
  points_loss: 'Lost on points',
  draw: 'A draw',
  set_complete: 'Set complete',
  time_up: 'Time up',
  three_whiffs: 'Three whiffs — you are out',
  fouled_out: 'Fouled out',
  retired: 'Retired',
  in_progress: 'In progress',
}

export function outcomeLabel(outcome: string | null): string {
  if (!outcome) return 'In progress'
  return OUTCOME_LABELS[outcome] ?? outcome.replace(/_/g, ' ')
}

/**
 * A labelled horizontal bar. `value` and `max` are in the caller's own units
 * and are announced as such, because a dimension scored 8/10 and a multiplier
 * of 1.27 are not the same kind of number and should not pretend to be.
 */
export function ScoreBar({
  label,
  value,
  max,
  color = '#6366f1',
  valueText,
  testId,
}: {
  label: string
  value: number
  max: number
  color?: string
  valueText?: string
  testId?: string
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  const shown = valueText ?? `${value} / ${max}`
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
      <span style={{ width: 88, color: '#a1a1aa', textTransform: 'capitalize' }}>{label}</span>
      <div
        role="meter"
        data-testid={testId}
        aria-label={`${label}: ${shown}`}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        style={{ flex: 1, height: 8, borderRadius: 4, background: '#27272a', overflow: 'hidden' }}
      >
        <div aria-hidden="true" style={{ width: `${pct}%`, height: '100%', background: color }} />
      </div>
      <span style={{ width: 64, textAlign: 'right', color: '#f4f4f5', fontVariantNumeric: 'tabular-nums' }}>
        {shown}
      </span>
    </div>
  )
}

/**
 * The heat multiplier, ×1.0 to ×2.0. Rendered as its own meter rather than a
 * number because it is the thing a batting-practice player is protecting — the
 * reason not to throw away a volley on a guess.
 */
export function HeatMeter({ heat }: { heat: number }) {
  const pct = Math.max(0, Math.min(100, ((heat - 1) / 1) * 100))
  return (
    <div data-testid="heat-meter" style={{ minWidth: 120 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#a1a1aa' }}>
        <span>Heat</span>
        <span style={{ color: heat > 1 ? '#f97316' : '#71717a', fontWeight: 600 }}>
          ×{heat.toFixed(1)}
        </span>
      </div>
      <div
        role="meter"
        aria-label={`Heat multiplier: ${heat.toFixed(1)} times`}
        aria-valuenow={heat}
        aria-valuemin={1}
        aria-valuemax={2}
        style={{ height: 6, borderRadius: 3, background: '#27272a', marginTop: 3, overflow: 'hidden' }}
      >
        <div
          aria-hidden="true"
          style={{
            width: `${pct}%`,
            height: '100%',
            background: 'linear-gradient(90deg,#f59e0b,#ef4444)',
          }}
        />
      </div>
    </div>
  )
}

/**
 * Bout momentum, 0-100, with the win threshold marked. The marker matters:
 * momentum with no visible finish line is just a number that moves.
 */
export function MomentumMeter({ momentum, winAt }: { momentum: number; winAt: number }) {
  return (
    <div data-testid="momentum-meter" style={{ minWidth: 180 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#a1a1aa' }}>
        <span>Momentum</span>
        <span style={{ color: '#f4f4f5', fontWeight: 600 }}>{momentum}</span>
      </div>
      <div
        role="meter"
        aria-label={`Momentum: ${momentum} out of 100, win at ${winAt}`}
        aria-valuenow={momentum}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{
          position: 'relative',
          height: 6,
          borderRadius: 3,
          background: '#27272a',
          marginTop: 3,
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: `${Math.max(0, Math.min(100, momentum))}%`,
            height: '100%',
            borderRadius: 3,
            background: momentum >= 50 ? '#22c55e' : '#f97316',
          }}
        />
        <div
          aria-hidden="true"
          title={`Win at ${winAt}`}
          style={{
            position: 'absolute',
            left: `${Math.max(0, Math.min(100, winAt))}%`,
            top: -2,
            width: 2,
            height: 10,
            background: '#a855f7',
          }}
        />
      </div>
    </div>
  )
}

/**
 * The per-volley shot clock. Turns amber in the last third and red in the last
 * fifth, so the pressure is legible without reading the number.
 */
export function ShotClock({ remaining, total }: { remaining: number; total: number }) {
  const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0
  const color = pct <= 20 ? '#ef4444' : pct <= 33 ? '#f59e0b' : '#22c55e'
  return (
    <div data-testid="shot-clock" style={{ minWidth: 110 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#a1a1aa' }}>
        <span>Shot clock</span>
        <span style={{ color, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
          {Math.max(0, Math.ceil(remaining))}s
        </span>
      </div>
      <div
        role="timer"
        aria-label={`Shot clock: ${Math.max(0, Math.ceil(remaining))} seconds remaining`}
        style={{ height: 6, borderRadius: 3, background: '#27272a', marginTop: 3, overflow: 'hidden' }}
      >
        <div aria-hidden="true" style={{ width: `${pct}%`, height: '100%', background: color }} />
      </div>
    </div>
  )
}

/** A compact statistic: a label over a value. Used in every run header. */
export function Stat({
  label,
  value,
  accent,
  testId,
}: {
  label: string
  value: string | number
  accent?: string
  testId?: string
}) {
  return (
    <div data-testid={testId} style={{ minWidth: 72 }}>
      <div style={{ fontSize: '0.7rem', color: '#a1a1aa' }}>{label}</div>
      <div
        style={{
          fontSize: '1.05rem',
          fontWeight: 600,
          color: accent ?? '#f4f4f5',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </div>
    </div>
  )
}

/** A small rounded tag. */
export function Tag({ label, color = '#a1a1aa', title }: { label: string; color?: string; title?: string }) {
  return (
    <span
      title={title}
      style={{
        padding: '0.1rem 0.45rem',
        borderRadius: 999,
        border: `1px solid ${color}55`,
        background: `${color}1a`,
        color,
        fontSize: '0.7rem',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}
