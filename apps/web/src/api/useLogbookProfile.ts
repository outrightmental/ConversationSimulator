// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import type { LogbookProfile } from '@convsim/shared'
import { api } from './client'

export type LogbookState = 'loading' | 'ready' | 'error'

export interface LogbookResult {
  state: LogbookState
  profile: LogbookProfile | null
}

export function useLogbookProfile(): LogbookResult {
  const [result, setResult] = useState<LogbookResult>({ state: 'loading', profile: null })

  useEffect(() => {
    let cancelled = false

    api.getLogbookProfile().then((r) => {
      if (cancelled) return
      if (r.ok) {
        setResult({ state: 'ready', profile: r.data })
      } else {
        setResult({ state: 'error', profile: null })
      }
    }).catch(() => {
      if (!cancelled) setResult({ state: 'error', profile: null })
    })

    return () => {
      cancelled = true
    }
  }, [])

  return result
}
