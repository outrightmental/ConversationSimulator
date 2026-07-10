// SPDX-License-Identifier: Apache-2.0
import { useCallback, useRef, useState } from 'react'
import { LATENCY_BUDGETS } from '@convsim/shared'
import type { LatencySnapshot, PerformanceWarning } from '@convsim/shared'

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

  const warnings: PerformanceWarning[] = []

  if (snapshot.session_start_ms !== undefined && snapshot.session_start_ms > LATENCY_BUDGETS.COLD_START_MS) {
    warnings.push({
      code: 'use_smaller_model',
      title: 'Session startup is slow',
      detail: `Session took ${(snapshot.session_start_ms / 1000).toFixed(1)}s to start. The model may still be loading. Try a smaller model or increase GPU layers in Runtime Settings.`,
    })
  }

  if (snapshot.first_token_ms !== undefined && snapshot.first_token_ms > LATENCY_BUDGETS.TTFT_MS) {
    warnings.push({
      code: 'use_smaller_model',
      title: 'NPC response is slow',
      detail: `First token took ${(snapshot.first_token_ms / 1000).toFixed(1)}s. Try a smaller model, reduce context length, or increase GPU layers in Runtime Settings.`,
    })
  }

  if (snapshot.full_response_ms !== undefined && snapshot.full_response_ms > LATENCY_BUDGETS.FULL_RESPONSE_MS) {
    warnings.push({
      code: 'reduce_context_length',
      title: 'Full NPC response is very slow',
      detail: `Response took ${(snapshot.full_response_ms / 1000).toFixed(1)}s. Reduce context length in Runtime Settings, or switch to push-to-talk instead of VAD.`,
    })
  }

  if (snapshot.tts_first_sentence_ms !== undefined && snapshot.tts_first_sentence_ms > LATENCY_BUDGETS.TTS_FIRST_AUDIO_MS) {
    warnings.push({
      code: 'disable_tts',
      title: 'TTS audio is slow to start',
      detail: `TTS took ${(snapshot.tts_first_sentence_ms / 1000).toFixed(1)}s to produce the first audio chunk. Disable TTS in scenario setup for a faster, text-only experience.`,
    })
  }

  if (snapshot.stt_final_ms !== undefined && snapshot.stt_final_ms > LATENCY_BUDGETS.STT_ROUND_TRIP_MS) {
    warnings.push({
      code: 'switch_to_push_to_talk',
      title: 'Speech recognition is slow',
      detail: `STT took ${(snapshot.stt_final_ms / 1000).toFixed(1)}s to return a transcript. Switch to push-to-talk to reduce VAD overhead, or use text input instead.`,
    })
  }

  return { snapshot, mark, recordInterval, recordValue, reset, warnings }
}
