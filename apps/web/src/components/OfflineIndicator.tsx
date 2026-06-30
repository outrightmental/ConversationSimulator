// SPDX-License-Identifier: Apache-2.0
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'

const LABELS = {
  loading: 'Local runtime: Checking…',
  healthy: 'Local runtime: Ready',
  unavailable: 'Local runtime: Unavailable',
} as const

export default function OfflineIndicator() {
  const { state } = useApiHealth()
  return (
    <StatusBadge status={state === 'loading' ? 'loading' : state === 'healthy' ? 'online' : 'offline'}>
      {LABELS[state]}
    </StatusBadge>
  )
}
