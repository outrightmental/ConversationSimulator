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
  // Whether the board is narrowed to the runs played under today's seed. That
  // is the comparison the seed exists to make, and it is the only way to make
  // it: the seed labels and groups runs, so without the filter a player can see
  // which rows were seeded but not read them as one day's board.
  const [todayOnly, setTodayOnly] = useState(false)

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
        todayOnly,
      )
      .then((r) => {
        if (r.ok) setBoard(r.data.entries)
      })
  }, [scenarioId, playFormat, battingFormat, todayOnly])

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
      state: { scenarioId, umpireFlavor: scenario?.judge_flavor },
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

  // The board below is narrowed to the selected drill, so the number beside it
  // has to be too: `personal_bests` is keyed by play format only, and a
  // ninety-second run and an endless run are not comparable totals. The board is
  // ordered by total_score DESC, so its first row *is* this board's best; the
  // payload is the fallback for a format with no rows yet.
  //
  // Not while the board is filtered to today, though: the best of today's seeded
  // runs is not a personal best, and labelling it one would make a good day look
  // like a record and a quiet day look like a lost one.
  const personalBest =
    board.length > 0 && !todayOnly
      ? board[0].total_score
      : (scenario.personal_bests[playFormat] ?? null)

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
          {/* `requires_surface_politeness` caps fidelity; whether dropping the
              gloves is also a *foul* is a separate pack setting the payload does
              not carry, so the tag says what this flag actually means. */}
          {scenario.requires_surface_politeness && (
            <Tag
              label="Courtesy required — the sting must be wrapped"
              color="#ef4444"
              title="Overt rudeness costs fidelity here; a scenario may also make it a foul."
            />
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
          {/* The scenario's own opening line. It is what the first volley
              answers, so it belongs in the brief rather than only in the
              transcript. */}
          {scenario.opening && (
            <blockquote
              data-testid="scenario-opening"
              style={{
                margin: 0,
                paddingLeft: '0.7rem',
                borderLeft: '3px solid #3f3f46',
                color: '#d4d4d8',
                fontSize: '0.85rem',
                fontStyle: 'italic',
                lineHeight: 1.6,
              }}
            >
              {scenario.opening}
              <footer
                style={{
                  marginTop: '0.25rem',
                  fontStyle: 'normal',
                  fontSize: '0.72rem',
                  color: '#71717a',
                }}
              >
                — {scenario.target.display_name}, as you arrive
              </footer>
            </blockquote>
          )}
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
          {/* The shot clock bounds a drill's volleys, not a bout's: a bout is
              bounded by its rounds. Advertising one against a bout would
              promise a rule the engine does not apply. */}
          {playFormat === 'batting_practice' && (
            <Stat label="Shot clock" value={`${scenario.shot_clock_s}s`} testId="setup-shot-clock" />
          )}
          <Stat label="Volley cap" value={`${scenario.limits.max_volley_chars} chars`} />
        </div>
        <label
          style={{
            display: 'flex',
            gap: '0.5rem',
            fontSize: '0.8rem',
            color: '#d4d4d8',
            marginBottom: '0.6rem',
          }}
        >
          <input
            type="checkbox"
            data-testid="board-today-only"
            checked={todayOnly}
            onChange={(e) => setTodayOnly(e.target.checked)}
          />
          Today's seed only — the same conditions, for anyone who played it today
        </label>
        <HighScoreTable entries={board} />
      </Section>

      {scenario.judge_flavor && (
        <Section
          title="Your umpire"
          hint="Who is scoring you, and in whose voice the per-volley commentary arrives. Flavour only — it never changes the numbers."
        >
          <p
            data-testid="judge-flavor"
            style={{ margin: 0, fontSize: '0.85rem', color: '#e4e4e7', lineHeight: 1.55 }}
          >
            {scenario.judge_flavor}
          </p>
        </Section>
      )}

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
