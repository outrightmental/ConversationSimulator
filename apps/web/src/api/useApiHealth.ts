// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import type { RuntimeReadiness } from '@convsim/shared'
import { apiClient } from './client'

export type HealthState = 'loading' | 'healthy' | 'unavailable'

export interface ApiHealth {
  state: HealthState
  healthy: boolean
  runtime: RuntimeReadiness | null
}

export function useApiHealth(): ApiHealth {
  const [result, setResult] = useState<ApiHealth>({
    state: 'loading',
    healthy: false,
    runtime: null,
  })

  useEffect(() => {
    let cancelled = false

    apiClient
      .health()
      .then((data) => {
        if (!cancelled) {
          const state: HealthState = data.status === 'ok' ? 'healthy' : 'unavailable'
          setResult({
            state,
            healthy: state === 'healthy',
            runtime: data.runtime ?? null,
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResult({ state: 'unavailable', healthy: false, runtime: null })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return result
}
