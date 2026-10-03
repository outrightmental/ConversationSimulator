// SPDX-License-Identifier: Apache-2.0
import { StatusBadge } from '@convsim/ui'
import { useApiHealth } from '../api/useApiHealth'

// "AI engine", not "runtime": this badge is in the app header on every screen,
// so it is the single most-seen label in the app, and 'runtime' is one of the
// four words the issue #501 playtest named as unexplained jargon.
const LABELS = {
  loading: 'AI engine: Checking…',
  healthy: 'AI engine: Ready',
  unavailable: 'AI engine: Unavailable',
} as const

export default function OfflineIndicator() {
  const { state } = useApiHealth()
  return (
    <StatusBadge status={state === 'loading' ? 'loading' : state === 'healthy' ? 'online' : 'offline'}>
      {LABELS[state]}
    </StatusBadge>
  )
}
