// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { apiClient, type HealthResponse, type SttHealthInfo } from './client'

export type HealthState = 'loading' | 'healthy' | 'unavailable'

export interface ApiHealth {
  state: HealthState
  healthy: boolean
  stt: SttHealthInfo | null
}

export function useApiHealth(): ApiHealth {
  const [result, setResult] = useState<ApiHealth>({
    state: 'loading',
    healthy: false,
    stt: null,
  })

  useEffect(() => {
    let cancelled = false

    apiClient
      .health()
      .then((data: HealthResponse) => {
        if (!cancelled) {
          const state: HealthState = data.status === 'ok' ? 'healthy' : 'unavailable'
          setResult({
            state,
            healthy: state === 'healthy',
            stt: data.stt ?? null,
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResult({ state: 'unavailable', healthy: false, stt: null })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return result
}
