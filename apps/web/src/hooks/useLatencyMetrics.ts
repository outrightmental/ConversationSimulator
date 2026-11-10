// SPDX-License-Identifier: Apache-2.0
import { useCallback, useRef, useState } from 'react'
import type { LatencySnapshot } from '@convsim/shared'

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

  // Record a latency value that was measured outside the mark/interval flow
  // (e.g. STT round-trip timed inside VoiceInput).
  const recordValue = useCallback((field: keyof LatencySnapshot, ms: number): void => {
    setSnapshot((prev) => ({ ...prev, [field]: Math.round(ms) }))
  }, [])

  const reset = useCallback((): void => {
    markersRef.current = {}
    setSnapshot({})
  }, [])

  // No warnings are derived here any more (issue #539): the rows that said
  // "first token took…" and pointed at settings that did nothing were removed.
  // The snapshot is still kept for the developer debug drawer.
  return { snapshot, mark, recordInterval, recordValue, reset }
}
