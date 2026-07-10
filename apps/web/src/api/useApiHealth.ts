// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react'
import type { RuntimeReadiness } from '@convsim/shared'
import { apiClient } from './client'

export type HealthState = 'loading' | 'healthy' | 'unavailable'

export interface ApiHealth {
  state: HealthState
  healthy: boolean
  runtime: RuntimeReadiness | null
  /** Manually trigger an immediate health re-check (e.g. after a restart action). */
  refetch: () => void
}

const POLL_INTERVAL_MS = 3000

export function useApiHealth(): ApiHealth {
  const [result, setResult] = useState<Omit<ApiHealth, 'refetch'>>({
    state: 'loading',
    healthy: false,
    runtime: null,
  })

  // Stable ref so refetch() can trigger a re-check without re-mounting the effect.
  const checkRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    let cancelled = false
    let timeoutId: ReturnType<typeof setTimeout> | undefined

    async function check() {
      clearTimeout(timeoutId)
      const r = await apiClient.health()
      if (cancelled) return

      if (r.ok) {
        const state: HealthState = r.data.status === 'ok' ? 'healthy' : 'unavailable'
        setResult({ state, healthy: state === 'healthy', runtime: r.data.runtime ?? null })
        // Only poll when not healthy so we detect recovery within POLL_INTERVAL_MS.
        if (state !== 'healthy') {
          timeoutId = setTimeout(check, POLL_INTERVAL_MS)
        }
      } else {
        setResult({ state: 'unavailable', healthy: false, runtime: null })
        timeoutId = setTimeout(check, POLL_INTERVAL_MS)
      }
    }

    checkRef.current = () => void check()
    void check()

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
      checkRef.current = null
    }
  }, [])

  const refetch = () => checkRef.current?.()

  return { ...result, refetch }
}
