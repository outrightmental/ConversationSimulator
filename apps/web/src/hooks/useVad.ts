// SPDX-License-Identifier: Apache-2.0
import { useState, useCallback, useRef, useEffect } from 'react'
import { apiClient } from '../api/client'

export type VadMode = 'ptt' | 'hands-free'
/** Visual state of the VAD engine during hands-free recording. */
export type VadState = 'idle' | 'listening' | 'speech' | 'silence' | 'stopping'

export interface VadSettings {
  mode: VadMode
  /** RMS energy threshold (0–1). Audio below this level is treated as silence. */
  threshold: number
  /** How long (ms) silence must persist before auto-stop fires. */
  silenceDurationMs: number
  /** ISO timestamp of last calibration, or null if not yet calibrated. */
  calibratedAt: string | null
}

const _KEY = 'convsim_vad_settings'
const _DEFAULTS: VadSettings = {
  mode: 'ptt',
  threshold: 0.05,
  silenceDurationMs: 1500,
  calibratedAt: null,
}

function _loadSettings(): VadSettings {
  try {
    const raw = localStorage.getItem(_KEY)
    if (raw) return { ..._DEFAULTS, ...(JSON.parse(raw) as Partial<VadSettings>) }
  } catch {
    // localStorage unavailable or corrupt — use defaults
  }
  return { ..._DEFAULTS }
}

function _saveSettings(s: VadSettings): void {
  try {
    localStorage.setItem(_KEY, JSON.stringify(s))
  } catch {
    // ignore — best-effort
  }
}

export interface UseVadReturn {
  settings: VadSettings
  vadState: VadState
  isCalibrating: boolean
  /** null = not yet checked; true/false = result of last health check */
  backendAvailable: boolean | null
  setMode: (mode: VadMode) => void
  setThreshold: (t: number) => void
  setSilenceDurationMs: (ms: number) => void
  /**
   * Start real-time silence detection against the given MediaStream.
   * Calls `onSilence` once silence has persisted for `silenceDurationMs`.
   */
  startSilenceDetection: (stream: MediaStream, onSilence: () => void) => void
  stopSilenceDetection: () => void
  /**
   * Send a calibration audio blob to the backend, update threshold from the result,
   * and persist the new threshold to localStorage.
   */
  calibrate: (blob: Blob) => Promise<void>
}

export function useVad(): UseVadReturn {
  const [settings, setSettings] = useState<VadSettings>(_loadSettings)
  const [vadState, setVadState] = useState<VadState>('idle')
  const [isCalibrating, setIsCalibrating] = useState(false)
  const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null)

  const settingsRef = useRef(settings)
  settingsRef.current = settings

  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const frameRef = useRef<number | null>(null)
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onSilenceRef = useRef<(() => void) | null>(null)

  const update = useCallback((patch: Partial<VadSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch }
      _saveSettings(next)
      return next
    })
  }, [])

  const setMode = useCallback((mode: VadMode) => update({ mode }), [update])
  const setThreshold = useCallback((threshold: number) => update({ threshold }), [update])
  const setSilenceDurationMs = useCallback(
    (ms: number) => update({ silenceDurationMs: ms }),
    [update],
  )

  const stopSilenceDetection = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }
    if (silenceTimerRef.current !== null) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    analyserRef.current = null
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    setVadState('idle')
  }, [])

  const startSilenceDetection = useCallback(
    (stream: MediaStream, onSilence: () => void) => {
      stopSilenceDetection()
      onSilenceRef.current = onSilence

      let ctx: AudioContext
      try {
        ctx = new AudioContext()
      } catch {
        return
      }
      audioCtxRef.current = ctx

      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.3
      try {
        ctx.createMediaStreamSource(stream).connect(analyser)
      } catch {
        ctx.close().catch(() => {})
        audioCtxRef.current = null
        return
      }
      analyserRef.current = analyser

      const buf = new Float32Array(analyser.fftSize)
      setVadState('listening')

      const tick = () => {
        const a = analyserRef.current
        if (!a) return

        a.getFloatTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
        const rms = Math.sqrt(sum / buf.length)

        const { threshold, silenceDurationMs } = settingsRef.current

        if (rms >= threshold) {
          if (silenceTimerRef.current !== null) {
            clearTimeout(silenceTimerRef.current)
            silenceTimerRef.current = null
          }
          setVadState('speech')
        } else if (silenceTimerRef.current === null) {
          setVadState('silence')
          silenceTimerRef.current = setTimeout(() => {
            silenceTimerRef.current = null
            setVadState('stopping')
            onSilenceRef.current?.()
          }, silenceDurationMs)
        }

        frameRef.current = requestAnimationFrame(tick)
      }

      frameRef.current = requestAnimationFrame(tick)
    },
    [stopSilenceDetection],
  )

  const calibrate = useCallback(
    async (blob: Blob) => {
      setIsCalibrating(true)
      try {
        const result = await apiClient.vadCalibrate(blob)
        update({ threshold: result.recommended_threshold, calibratedAt: new Date().toISOString() })
        setBackendAvailable(true)
      } catch {
        setBackendAvailable(false)
      } finally {
        setIsCalibrating(false)
      }
    },
    [update],
  )

  // Check backend availability once on mount.
  useEffect(() => {
    apiClient
      .vadHealth()
      .then(() => setBackendAvailable(true))
      .catch(() => setBackendAvailable(false))
  }, [])

  useEffect(() => () => stopSilenceDetection(), [stopSilenceDetection])

  return {
    settings,
    vadState,
    isCalibrating,
    backendAvailable,
    setMode,
    setThreshold,
    setSilenceDurationMs,
    startSilenceDetection,
    stopSilenceDetection,
    calibrate,
  }
}
