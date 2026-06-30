// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react'

export type BadgeStatus = 'online' | 'offline' | 'loading'

interface Props {
  status: BadgeStatus
  children: ReactNode
}

const COLORS: Record<BadgeStatus, string> = {
  online: '#2a9d2a',
  offline: '#cc4444',
  loading: '#888888',
}

export function StatusBadge({ status, children }: Props) {
  return (
    <span
      data-status={status}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.375rem',
        fontSize: '0.8rem',
        color: COLORS[status],
      }}
    >
      <span
        aria-hidden="true"
        style={{
          display: 'inline-block',
          width: '0.5rem',
          height: '0.5rem',
          borderRadius: '50%',
          backgroundColor: COLORS[status],
        }}
      />
      {children}
    </span>
  )
}
