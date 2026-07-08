// SPDX-License-Identifier: Apache-2.0
import { useState, useRef, useCallback, useEffect } from 'react'

export type MicPermission = 'unsupported' | 'idle' | 'requesting' | 'granted' | 'denied'

export interface UseMicCaptureReturn {
  permission: MicPermission
  isRecording: boolean
  recordingSeconds: number
  error: string | null
  /** The active MediaStream after permission is granted, null otherwise. */
  stream: MediaStream | null
  requestPermission: () => Promise<void>
  startRecording: () => void
  stopRecording: () => void
}

export const MAX_RECORDING_SECONDS = 60

function isBrowserSupported(): boolean {
  try {
    return (
      typeof MediaRecorder !== 'undefined' &&
      typeof (navigator.mediaDevices as { getUserMedia?: unknown } | undefined)?.getUserMedia ===
        'function'
    )
  } catch {
    return false
  }
}

export function useMicCapture(onAudioReady?: (blob: Blob) => void): UseMicCaptureReturn {
  const [permission, setPermission] = useState<MicPermission>(
    isBrowserSupported() ? 'idle' : 'unsupported',
  )
  const [isRecording, setIsRecording] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)

  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onAudioReadyRef = useRef(onAudioReady)
  onAudioReadyRef.current = onAudioReady

  const clearTimers = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (maxTimerRef.current !== null) {
      clearTimeout(maxTimerRef.current)
      maxTimerRef.current = null
    }
  }, [])

  const stopRecording = useCallback(() => {
    clearTimers()
    setRecordingSeconds(0)
    const rec = recorderRef.current
    if (rec && rec.state === 'recording') {
      rec.stop()
    }
  }, [clearTimers])

  const startRecording = useCallback(() => {
    if (permission !== 'granted' || !streamRef.current || isRecording) return

    chunksRef.current = []

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
        ? 'audio/ogg;codecs=opus'
        : ''

    const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined)
    recorderRef.current = recorder

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      setIsRecording(false)
      onAudioReadyRef.current?.(blob)
    }

    recorder.start(250)
    setIsRecording(true)
    setRecordingSeconds(0)

    timerRef.current = setInterval(() => {
      setRecordingSeconds((s) => s + 1)
    }, 1000)

    // Stop automatically at the max duration so the user is always aware.
    maxTimerRef.current = setTimeout(() => {
      clearTimers()
      setRecordingSeconds(0)
      const rec = recorderRef.current
      if (rec && rec.state === 'recording') rec.stop()
    }, MAX_RECORDING_SECONDS * 1000)
  }, [permission, isRecording, clearTimers])

  const requestPermission = useCallback(async () => {
    if (!isBrowserSupported()) return
    setPermission('requesting')
    setError(null)
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      streamRef.current = s
      setStream(s)
      setPermission('granted')
    } catch (err) {
      const isDenied =
        err instanceof Error &&
        (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError')
      setPermission(isDenied ? 'denied' : 'idle')
      setError(isDenied ? 'Microphone access was denied.' : 'Could not access microphone.')
    }
  }, [])

  useEffect(() => {
    return () => {
      clearTimers()
      const rec = recorderRef.current
      if (rec && rec.state === 'recording') rec.stop()
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [clearTimers])

  return {
    permission,
    isRecording,
    recordingSeconds,
    error,
    stream,
    requestPermission,
    startRecording,
    stopRecording,
  }
}
