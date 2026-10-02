// SPDX-License-Identifier: Apache-2.0
//
// The flyting pre-run screen: pick a format, read the target's attack surface,
// and see what you have already scored here. The attack surface is the point of
// the brief — it is the list of things that are fair game, and the only thing a
// verified hook can name — so it gets more room than the prose.
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import type {
  BattingFormat,
  FlytingHighScore,
  FlytingScenarioSetup,
  PlayFormat,
} from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'
import HighScoreTable from '../flyting/HighScoreTable'
import { BATTING_FORMAT_LABELS, PLAY_FORMAT_LABELS, Stat, Tag } from '../flyting/primitives'

const BATTING_FORMAT_HINTS: Record<BattingFormat, string> = {
  timed_90: 'Ninety seconds. As many volleys as you can land.',
  set_10: 'Ten volleys, then the scorecard. The fairest comparison run.',
  endless: 'Keep going until three whiffs — a dud, a foul, or the shot clock.',
}

const PLAY_FORMAT_HINTS: Record<PlayFormat, string> = {
  bout: 'You and the target trade volleys. Both sides are scored by the same pipeline, and the numbers are shown.',
  batting_practice: 'The target reacts but never counters. Pure practice, for score.',
}

function Section({
  title,
  children,
  hint,
}: {
  title: string
  children: React.ReactNode
  hint?: string
}) {
  return (
    <section
      style={{
        border: '1px solid #27272a',
        borderRadius: 8,
        padding: '0.85rem 1rem',
        background: '#111113',
      }}
    >
      <h2 style={{ fontSize: '0.95rem', margin: '0 0 0.15rem', color: '#f4f4f5' }}>{title}</h2>
      {hint && (
        <p style={{ fontSize: '0.78rem', color: '#71717a', margin: '0 0 0.6rem' }}>{hint}</p>
      )}
      {children}
    </section>
  )
}

function RadioCard({
  name,
  value,
  checked,
  label,
  hint,
  onSelect,
}: {
  name: string
  value: string
  checked: boolean
  label: string
  hint: string
  onSelect: (value: string) => void
}) {
  return (
    <label
      style={{
        display: 'flex',
        gap: '0.6rem',
        alignItems: 'flex-start',
        padding: '0.55rem 0.7rem',
        borderRadius: 6,
        cursor: 'pointer',
        border: `1px solid ${checked ? 'rgba(99,102,241,0.6)' : '#27272a'}`,
        background: checked ? 'rgba(99,102,241,0.12)' : 'transparent',
      }}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onSelect(value)}
        style={{ marginTop: 3 }}
      />
      <span>
        <span style={{ display: 'block', fontSize: '0.85rem', color: '#f4f4f5', fontWeight: 500 }}>
          {label}
        </span>
        <span style={{ display: 'block', fontSize: '0.75rem', color: '#a1a1aa' }}>{hint}</span>
      </span>
    </label>
  )
}

export default function FlytingSetup() {
  const { scenarioId } = useParams<{ scenarioId: string }>()
  const navigate = useNavigate()

  const [scenario, setScenario] = useState<FlytingScenarioSetup | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [playFormat, setPlayFormat] = useState<PlayFormat>('batting_practice')
  const [battingFormat, setBattingFormat] = useState<BattingFormat>('set_10')
  const [useDailySeed, setUseDailySeed] = useState(false)
  const [saveTranscript, setSaveTranscript] = useState(true)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<ApiError | null>(null)
  const [board, setBoard] = useState<FlytingHighScore[]>([])

  useEffect(() => {
    if (!scenarioId) return
    let cancelled = false
    setLoading(true)
    void api.flyting.getScenario(scenarioId).then((r) => {
      if (cancelled) return
      setLoading(false)
      if (!r.ok) {
        setError(r.error)
        return
      }
      setScenario(r.data)
      // Default to whatever the scenario actually offers rather than to our own
      // preference: a bout-only scenario must not open on a drill it has no
      // formats for.
      const firstFormat = r.data.formats[0]
      if (firstFormat) setPlayFormat(firstFormat)
      const firstDrill = r.data.batting_formats[0]
      if (firstDrill) setBattingFormat(firstDrill)
    })
    return () => {
      cancelled = true
    }
  }, [scenarioId])

  const loadBoard = useCallback(() => {
    if (!scenarioId) return
    void api.flyting
      .highScores(
        scenarioId,
        playFormat,
        playFormat === 'batting_practice' ? battingFormat : null,
      )
      .then((r) => {
        if (r.ok) setBoard(r.data.entries)
      })
  }, [scenarioId, playFormat, battingFormat])

  useEffect(() => loadBoard(), [loadBoard])

  async function handleStart() {
    if (!scenarioId || starting) return
    setStarting(true)
    setStartError(null)
    const r = await api.flyting.startRun({
      scenario_id: scenarioId,
      play_format: playFormat,
      batting_format: playFormat === 'batting_practice' ? battingFormat : null,
      use_daily_seed: useDailySeed,
      save_transcript: saveTranscript,
    })
    if (!r.ok) {
      setStartError(r.error)
      setStarting(false)
      return
    }
    navigate(`/flyting/run/${r.data.session_id}`, {
      state: { scenarioId, umpireLabel: scenario?.judge_flavor },
    })
  }

  if (loading) {
    return (
      <div style={{ padding: '1.5rem', color: '#71717a', fontSize: '0.875rem' }}>
        Loading the scenario…
      </div>
    )
  }

  if (error || !scenario) {
    return (
      <div style={{ padding: '1.5rem' }}>
        <ApiErrorView error={error ?? { kind: 'schema-mismatch', message: 'The scenario could not be read.' }} context="FlytingSetup" />
        <Link to="/library" style={{ color: '#93c5fd', fontSize: '0.85rem' }}>
          ← Back to the library
        </Link>
      </div>
    )
  }

  const personalBest = scenario.personal_bests[playFormat] ?? null

  return (
    <div style={{ padding: '1.25rem', display: 'grid', gap: '0.85rem', maxWidth: 860 }}>
      <header>
        <Link to="/library" style={{ color: '#93c5fd', fontSize: '0.8rem', textDecoration: 'none' }}>
          ← Scenario library
        </Link>
        <h1 style={{ fontSize: '1.4rem', margin: '0.4rem 0 0.2rem', color: '#fafafa' }}>
          {scenario.title}
        </h1>
        <p style={{ margin: 0, color: '#a1a1aa', fontSize: '0.875rem', lineHeight: 1.55 }}>
          {scenario.summary}
        </p>
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.55rem' }}>
          <Tag label="Flyting" color="#a855f7" />
          <Tag label={scenario.content_rating} />
          <Tag label={`Difficulty ×${scenario.difficulty_multiplier.toFixed(2)}`} color="#f59e0b" />
          {scenario.verse_required && (
            <Tag label="Verse — alliteration and scansion scored" color="#38bdf8" />
          )}
          {scenario.requires_surface_politeness && (
            <Tag label="Overt rudeness is a foul" color="#ef4444" />
          )}
          {scenario.audience && <Tag label={scenario.audience.label} color="#a3e635" />}
        </div>
      </header>

      <Section
        title={`You are ${scenario.player_role.label}`}
        hint={scenario.player_role.brief || undefined}
      >
        <div style={{ display: 'grid', gap: '0.5rem' }}>
          <p style={{ margin: 0, fontSize: '0.85rem', color: '#e4e4e7' }}>
            Your target: <strong>{scenario.target.display_name}</strong>
          </p>
          {scenario.goals.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: '1.1rem', color: '#a1a1aa', fontSize: '0.8rem' }}>
              {scenario.goals.map((goal) => (
                <li key={goal}>{goal}</li>
              ))}
            </ul>
          )}
        </div>
      </Section>

      <Section
        title="Attack surface"
        hint="What about this character is fair game. A jab that lands on one of these — in your own words, quoted back to you — is worth more than generic abuse."
      >
        <ul
          data-testid="attack-surface"
          style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '0.45rem' }}
        >
          {scenario.target.attack_surface.map((trait) => (
            <li key={trait.id} style={{ display: 'flex', gap: '0.55rem', alignItems: 'baseline' }}>
              <Tag label={trait.id.replace(/_/g, ' ')} color="#22c55e" />
              <span style={{ fontSize: '0.82rem', color: '#d4d4d8', lineHeight: 1.5 }}>
                {trait.brief}
              </span>
            </li>
          ))}
        </ul>
        {scenario.target.discoverable_count > 0 && (
          <p
            data-testid="discoverable-count"
            style={{ fontSize: '0.78rem', color: '#a855f7', margin: '0.6rem 0 0' }}
          >
            {scenario.target.discoverable_count} more{' '}
            {scenario.target.discoverable_count === 1 ? 'trait is' : 'traits are'} hidden. Strike
            one and it is revealed — and worth double on discovery.
          </p>
        )}
      </Section>

      <Section title="Format">
        <div style={{ display: 'grid', gap: '0.4rem' }}>
          {scenario.formats.map((format) => (
            <RadioCard
              key={format}
              name="play-format"
              value={format}
              checked={playFormat === format}
              label={PLAY_FORMAT_LABELS[format] ?? format}
              hint={PLAY_FORMAT_HINTS[format]}
              onSelect={(v) => setPlayFormat(v as PlayFormat)}
            />
          ))}
        </div>

        {playFormat === 'batting_practice' && (
          <fieldset style={{ border: 'none', margin: '0.7rem 0 0', padding: 0 }}>
            <legend style={{ fontSize: '0.8rem', color: '#a1a1aa', padding: 0 }}>Drill</legend>
            <div style={{ display: 'grid', gap: '0.4rem', marginTop: '0.4rem' }}>
              {scenario.batting_formats.map((drill) => (
                <RadioCard
                  key={drill}
                  name="batting-format"
                  value={drill}
                  checked={battingFormat === drill}
                  label={BATTING_FORMAT_LABELS[drill] ?? drill}
                  hint={BATTING_FORMAT_HINTS[drill]}
                  onSelect={(v) => setBattingFormat(v as BattingFormat)}
                />
              ))}
            </div>
          </fieldset>
        )}

        {playFormat === 'bout' && (
          <p style={{ fontSize: '0.78rem', color: '#a1a1aa', margin: '0.6rem 0 0' }}>
            {scenario.bout.rounds} rounds · carry momentum past {scenario.bout.momentum_win} to win
            outright · countering their last line earns +{scenario.bout.riposte_bonus} ·{' '}
            opponent: {scenario.bout.npc_tier_label}
          </p>
        )}

        <div style={{ display: 'grid', gap: '0.4rem', marginTop: '0.8rem' }}>
          <label style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8rem', color: '#d4d4d8' }}>
            <input
              type="checkbox"
              checked={useDailySeed}
              onChange={(e) => setUseDailySeed(e.target.checked)}
            />
            Use today's seed — makes runs comparable, with no server involved
          </label>
          <label style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8rem', color: '#d4d4d8' }}>
            <input
              type="checkbox"
              checked={saveTranscript}
              onChange={(e) => setSaveTranscript(e.target.checked)}
            />
            Save the transcript on this computer
          </label>
        </div>
      </Section>

      <Section title="Your board" hint="Stored on this computer only.">
        <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '0.7rem' }}>
          <Stat
            label="Personal best"
            value={personalBest ?? '—'}
            accent="#a855f7"
            testId="personal-best"
          />
          <Stat label="Shot clock" value={`${scenario.shot_clock_s}s`} />
          <Stat label="Volley cap" value={`${scenario.limits.max_volley_chars} chars`} />
        </div>
        <HighScoreTable entries={board} />
      </Section>

      {scenario.lexicon_hints.length > 0 && (
        <Section
          title="Period diction"
          hint="Encouraged vocabulary for this scenario. Hints, never requirements — the engine does not make you use them."
        >
          <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
            {scenario.lexicon_hints.map((word) => (
              <Tag key={word} label={word} color="#38bdf8" />
            ))}
          </div>
        </Section>
      )}

      {startError && (
        <ApiErrorView error={startError} context="FlytingSetup-start" />
      )}

      <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => void handleStart()}
          disabled={starting}
          data-testid="start-flyting-run"
          style={{
            padding: '0.5rem 1.2rem',
            borderRadius: 6,
            border: '1px solid rgba(168,85,247,0.5)',
            background: 'rgba(168,85,247,0.18)',
            color: '#e9d5ff',
            fontSize: '0.9rem',
            fontWeight: 600,
            cursor: starting ? 'default' : 'pointer',
            opacity: starting ? 0.6 : 1,
          }}
        >
          {starting ? 'Starting…' : 'Step up'}
        </button>
        <span style={{ fontSize: '0.75rem', color: '#71717a' }}>
          The judge is your own local model. Nothing leaves this computer.
        </span>
      </div>
    </div>
  )
}
