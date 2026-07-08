// SPDX-License-Identifier: Apache-2.0
import type { VadState } from '../hooks/useVad'

interface VadStatusIndicatorProps {
  state: VadState
}

const _CONFIG: Record<
  VadState,
  { label: string; color: string; background: string; animate: boolean }
> = {
  idle:      { label: 'Idle',             color: '#71717a', background: '#27272a', animate: false },
  listening: { label: 'Listening…',       color: '#60a5fa', background: '#1e3a5f', animate: true  },
  speech:    { label: 'Speech detected',  color: '#4ade80', background: '#14532d', animate: false },
  silence:   { label: 'Silence…',         color: '#facc15', background: '#3b2f00', animate: false },
  stopping:  { label: 'Auto-stopping…',   color: '#fb923c', background: '#431407', animate: false },
}

export default function VadStatusIndicator({ state }: VadStatusIndicatorProps) {
  const cfg = _CONFIG[state]

  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={`VAD status: ${cfg.label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.35rem',
        padding: '0.2rem 0.6rem',
        borderRadius: '999px',
        background: cfg.background,
        color: cfg.color,
        fontSize: '0.78rem',
        fontWeight: 500,
        userSelect: 'none',
        transition: 'background 0.2s, color 0.2s',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: cfg.color,
          flexShrink: 0,
          animation: cfg.animate ? 'vad-pulse 1.2s ease-in-out infinite' : 'none',
        }}
      />
      {cfg.label}
      <style>{`
        @keyframes vad-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>
    </span>
  )
}
