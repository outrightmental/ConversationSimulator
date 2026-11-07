// SPDX-License-Identifier: Apache-2.0
import { useNavigate } from 'react-router-dom'
import type { PerformanceWarning } from '@convsim/shared'
import { useIsDemo } from '../edition'

interface PerformanceWarningBannerProps {
  warnings: PerformanceWarning[]
}

export default function PerformanceWarningBanner({ warnings }: PerformanceWarningBannerProps) {
  const navigate = useNavigate()
  // The demo edition (issue #495) hides the runtime section of Settings, so
  // the button would land the player on a page with nothing to adjust. The
  // warning text itself still shows.
  const isDemo = useIsDemo()

  if (warnings.length === 0) return null

  return (
    <div
      data-testid="performance-warnings"
      role="status"
      aria-label="Performance warnings"
      style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}
    >
      {warnings.map((w, i) => (
        <div
          // Multiple warnings can share a `code` (e.g. slow session start and slow
          // first token both suggest `use_smaller_model`), so the index keeps keys unique.
          key={`${w.code}-${i}`}
          data-testid={`perf-warning-${w.code}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '0.5rem',
            padding: '0.6rem 1rem',
            borderRadius: 6,
            border: '1px solid #713f12',
            background: '#1c1000',
            color: '#fde68a',
            fontSize: '0.85rem',
          }}
        >
          <span>
            <strong>{w.title}:</strong> {w.detail}
          </span>
          {!isDemo && (
          // "Runtime" is one of the four words the issue #501 playtest named as
          // unexplained jargon, and this button renders on the conversation
          // screen — right above the slow-reply notice that now offers "Make
          // replies faster →". Plain wording, and the same destination.
          <button
            onClick={() => navigate('/settings')}
            aria-label="Open settings"
            style={{
              padding: '0.25rem 0.75rem',
              borderRadius: 4,
              border: '1px solid #713f12',
              background: '#292100',
              color: '#fde68a',
              fontSize: '0.8rem',
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            Open settings
          </button>
          )}
        </div>
      ))}
    </div>
  )
}
