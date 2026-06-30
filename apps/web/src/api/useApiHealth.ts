// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { apiClient } from './client'

export type HealthState = 'loading' | 'healthy' | 'unavailable'

export function useApiHealth(): { state: HealthState; healthy: boolean } {
  const [state, setState] = useState<HealthState>('loading')

  useEffect(() => {
    let cancelled = false

    apiClient
      .health()
      .then(({ status }) => {
        if (!cancelled) setState(status === 'ok' ? 'healthy' : 'unavailable')
      })
      .catch(() => {
        if (!cancelled) setState('unavailable')
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { state, healthy: state === 'healthy' }
}
