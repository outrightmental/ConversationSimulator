// SPDX-License-Identifier: Apache-2.0
import { useNavigate } from 'react-router-dom'
import type { PerformanceWarning } from '@convsim/shared'

interface PerformanceWarningBannerProps {
  warnings: PerformanceWarning[]
}

export default function PerformanceWarningBanner({ warnings }: PerformanceWarningBannerProps) {
  const navigate = useNavigate()

  if (warnings.length === 0) return null

  return (
    <div
      data-testid="performance-warnings"
      role="status"
      aria-label="Performance warnings"
      style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}
    >
      {warnings.map((w) => (
        <div
          key={w.code}
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
          <button
            onClick={() => navigate('/settings')}
            aria-label="Open Runtime Settings"
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
            Runtime Settings
          </button>
        </div>
      ))}
    </div>
  )
}
