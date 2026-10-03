// SPDX-License-Identifier: Apache-2.0
import { humanizeIdentifier } from '../lib/plainLanguage'

/**
 * The conversation meters (issue #501 §3).
 *
 * What was wrong, from the playtest:
 *
 *   - The panel was collapsed behind a summary reading "NPC state variables",
 *     below the transcript, while the tutorial's opening line says "Notice the
 *     two meters at the top". The label, the name and the placement all
 *     disagreed, so "generally confused about meters and where they appear".
 *   - Each bar showed a number and nothing else. The tutorial says "Engagement
 *     just ticked up" and "See how Engagement just ticked up?", but nothing on
 *     screen ever ticked: the number was simply different than the last time
 *     you looked at it. The change is the whole mechanic, so it is now drawn.
 *   - The NPC's emotion was rendered right next to the bars, so it read as one
 *     of them — "unclear which meter (if any) the emotions in parentheses are".
 *     Emotion now lives in the NPC panel under an explicit "Mood" label and
 *     never inside this component.
 *
 * Caller places this ABOVE the transcript so "the meters at the top" is true.
 */
export default function StateMeters({
  stateVars,
  deltas,
  isPlain,
}: {
  stateVars: Record<string, number>
  /** Change applied by the most recent turn, per variable. */
  deltas: Record<string, number>
  /** Plain wording hides the raw snake_case variable keys. */
  isPlain: boolean
}) {
  const entries = Object.entries(stateVars)
  if (entries.length === 0) return null

  return (
    <section
      aria-label="Conversation meters"
      style={{
        padding: '0.6rem 0.75rem',
        borderRadius: 8,
        border: '1px solid #27272a',
        background: '#18181b',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: '0.8rem', fontWeight: 600, color: '#e4e4e7' }}>
          Conversation meters
        </h2>
        <p style={{ margin: 0, fontSize: '0.72rem', color: '#71717a' }}>
          These move with every turn. They are not moods.
        </p>
      </div>
      <div
        data-testid="state-vars"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.5rem',
          marginTop: '0.5rem',
        }}
      >
        {entries.map(([key, value]) => {
          const delta = deltas[key] ?? 0
          const label = isPlain ? humanizeIdentifier(key) : key
          return (
            <div
              key={key}
              data-testid={`state-meter-${key}`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                minWidth: 112,
                flex: '1 1 112px',
                padding: '0.4rem 0.5rem',
                borderRadius: 4,
                background: '#111113',
                fontSize: '0.8rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.4rem' }}>
                <span style={{ color: '#a1a1aa' }}>{label}</span>
                <span style={{ color: '#f4f4f5', fontWeight: 600 }}>{value}</span>
              </div>
              <div
                role="meter"
                // The accessible name carries the plain label in both wording
                // levels: a screen-reader user reading "objective_progress" out
                // loud as a word is the same problem this issue is about.
                aria-label={`${humanizeIdentifier(key)}: ${value} out of 100`}
                aria-valuenow={value}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuetext={
                  delta === 0
                    ? `${value} out of 100`
                    : `${value} out of 100, ${delta > 0 ? 'up' : 'down'} ${Math.abs(delta)} this turn`
                }
                style={{
                  width: '100%',
                  height: 5,
                  borderRadius: 2,
                  background: '#27272a',
                  marginTop: 5,
                }}
              >
                <div
                  aria-hidden="true"
                  style={{
                    width: `${value}%`,
                    height: '100%',
                    borderRadius: 2,
                    background: value >= 50 ? '#22c55e' : '#f97316',
                  }}
                />
              </div>
              {/* The tick the tutorial talks about. aria-hidden because the
                  meter's aria-valuetext above already says it, and announcing
                  both would read every change twice. */}
              <span
                aria-hidden="true"
                data-testid={`state-meter-delta-${key}`}
                style={{
                  marginTop: 3,
                  fontSize: '0.7rem',
                  minHeight: '0.95rem',
                  color: delta > 0 ? '#4ade80' : delta < 0 ? '#f87171' : 'transparent',
                }}
              >
                {delta > 0 ? `▲ +${delta} this turn` : delta < 0 ? `▼ ${delta} this turn` : '·'}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
