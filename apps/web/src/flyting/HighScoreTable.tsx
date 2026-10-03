// SPDX-License-Identifier: Apache-2.0
//
// The local high-score board. Local in the strong sense: these rows come from
// a SQLite table on this machine and go nowhere, which is why there is no
// "submit score" anything here and no notion of a global rank.
import type { FlytingHighScore } from '@convsim/shared'
import { formatLabel, outcomeLabel } from './primitives'

function shortDate(iso: string): string {
  // The achieved_at column is a SQLite 'YYYY-MM-DD HH:MM:SS' UTC stamp, which
  // Date cannot parse portably without the separator, so normalise it first.
  const parsed = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T') + 'Z')
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function HighScoreTable({
  entries,
  highlightSessionId,
  showFormat = false,
}: {
  entries: FlytingHighScore[]
  /** The run just finished, marked so a player can find themselves. */
  highlightSessionId?: string | null
  showFormat?: boolean
}) {
  if (entries.length === 0) {
    return (
      <p data-testid="high-scores-empty" style={{ fontSize: '0.8rem', color: '#71717a', margin: 0 }}>
        No runs on this board yet. The first one sets the mark.
      </p>
    )
  }

  return (
    <table
      data-testid="high-score-table"
      style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}
    >
      <caption style={{ captionSide: 'top', textAlign: 'left', color: '#71717a', fontSize: '0.72rem', paddingBottom: '0.3rem' }}>
        Stored on this computer only.
      </caption>
      <thead>
        <tr style={{ color: '#a1a1aa', textAlign: 'left' }}>
          <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>#</th>
          <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>Score</th>
          {showFormat && (
            <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>Format</th>
          )}
          <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>Best volley</th>
          <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>Heat</th>
          <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>Result</th>
          <th scope="col" style={{ padding: '0.25rem 0.4rem', fontWeight: 500 }}>When</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry, index) => {
          const mine = highlightSessionId != null && entry.session_id === highlightSessionId
          return (
            <tr
              key={entry.session_id ?? `${entry.total_score}-${entry.achieved_at}-${index}`}
              data-testid={mine ? 'high-score-row-current' : undefined}
              style={{
                borderTop: '1px solid #27272a',
                background: mine ? 'rgba(168,85,247,0.12)' : undefined,
                color: mine ? '#e9d5ff' : '#d4d4d8',
              }}
            >
              <td style={{ padding: '0.3rem 0.4rem', color: '#71717a' }}>{index + 1}</td>
              <td style={{ padding: '0.3rem 0.4rem', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                {entry.total_score}
                {entry.daily_seed != null && (
                  <span title="Played on the daily seed" style={{ color: '#38bdf8' }}> ◆</span>
                )}
              </td>
              {showFormat && (
                <td style={{ padding: '0.3rem 0.4rem', color: '#a1a1aa' }}>
                  {formatLabel(entry.play_format, entry.batting_format)}
                </td>
              )}
              <td style={{ padding: '0.3rem 0.4rem', fontVariantNumeric: 'tabular-nums' }}>
                {entry.best_volley_score}
              </td>
              <td style={{ padding: '0.3rem 0.4rem', fontVariantNumeric: 'tabular-nums' }}>
                ×{entry.peak_heat.toFixed(1)}
              </td>
              <td style={{ padding: '0.3rem 0.4rem', color: '#a1a1aa' }}>
                {outcomeLabel(entry.outcome)}
              </td>
              <td style={{ padding: '0.3rem 0.4rem', color: '#71717a' }}>
                {shortDate(entry.achieved_at)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default HighScoreTable
