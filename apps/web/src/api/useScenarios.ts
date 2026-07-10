// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import type { ScenarioInfo } from '@convsim/shared'
import { api } from './client'

export type ScenariosState = 'loading' | 'ready' | 'error'

export interface ScenariosResult {
  state: ScenariosState
  scenarios: ScenarioInfo[]
}

export function useScenarios(): ScenariosResult {
  const [result, setResult] = useState<ScenariosResult>({ state: 'loading', scenarios: [] })

  useEffect(() => {
    let cancelled = false

    api.listScenarios().then((r) => {
      if (cancelled) return
      if (r.ok) {
        setResult({ state: 'ready', scenarios: r.data })
      } else {
        setResult({ state: 'error', scenarios: [] })
      }
    }).catch(() => {
      if (!cancelled) setResult({ state: 'error', scenarios: [] })
    })

    return () => {
      cancelled = true
    }
  }, [])

  return result
}
