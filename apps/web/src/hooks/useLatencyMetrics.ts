// SPDX-License-Identifier: Apache-2.0
import { useCallback, useRef, useState } from 'react'
import type { LatencySnapshot, PerformanceWarning } from '@convsim/shared'

const FIRST_TOKEN_WARN_MS = 3_000
const FULL_RESPONSE_WARN_MS = 10_000
const SESSION_START_WARN_MS = 5_000

export function useLatencyMetrics() {
  const [snapshot, setSnapshot] = useState<LatencySnapshot>({})
  const markersRef = useRef<Record<string, number>>({})

  const mark = useCallback((event: string): void => {
    markersRef.current[event] = performance.now()
  }, [])

  const recordInterval = useCallback(
    (field: keyof LatencySnapshot, startEvent: string, endEvent?: string): void => {
      const start = markersRef.current[startEvent]
      if (start === undefined) return
      const end = endEvent !== undefined ? markersRef.current[endEvent] : performance.now()
      if (end === undefined) return
      setSnapshot((prev) => ({ ...prev, [field]: Math.round(end - start) }))
    },
    [],
  )

  const reset = useCallback((): void => {
    markersRef.current = {}
    setSnapshot({})
  }, [])

  const warnings: PerformanceWarning[] = []

  if (snapshot.session_start_ms !== undefined && snapshot.session_start_ms > SESSION_START_WARN_MS) {
    warnings.push({
      code: 'use_smaller_model',
      title: 'Session startup is slow',
      detail: `Session took ${(snapshot.session_start_ms / 1000).toFixed(1)}s to start. The model may still be loading. Try a smaller model or increase GPU layers in Runtime Settings.`,
    })
  }

  if (snapshot.first_token_ms !== undefined && snapshot.first_token_ms > FIRST_TOKEN_WARN_MS) {
    warnings.push({
      code: 'use_smaller_model',
      title: 'NPC response is slow',
      detail: `First token took ${(snapshot.first_token_ms / 1000).toFixed(1)}s. Try a smaller model, reduce context length, or increase GPU layers in Runtime Settings.`,
    })
  }

  if (snapshot.full_response_ms !== undefined && snapshot.full_response_ms > FULL_RESPONSE_WARN_MS) {
    warnings.push({
      code: 'reduce_context_length',
      title: 'Full NPC response is very slow',
      detail: `Response took ${(snapshot.full_response_ms / 1000).toFixed(1)}s. Reduce context length in Runtime Settings, or switch to push-to-talk instead of VAD.`,
    })
  }

  return { snapshot, mark, recordInterval, reset, warnings }
}
