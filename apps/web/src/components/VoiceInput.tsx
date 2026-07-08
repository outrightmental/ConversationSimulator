// SPDX-License-Identifier: Apache-2.0
import { useState, useCallback, useEffect } from 'react'
import { apiClient } from '../api/client'
import { useMicCapture, MAX_RECORDING_SECONDS } from '../hooks/useMicCapture'
import { useVad } from '../hooks/useVad'
import MicButton from './MicButton'
import VadStatusIndicator from './VadStatusIndicator'
import VadCalibration from './VadCalibration'
import TranscriptReviewPanel from './TranscriptReviewPanel'

export interface SttReviewMeta {
  rawTranscript: string
  finalTranscript: string
  language?: string | null
  confidence?: number | null
}

type ReviewState = {
  transcript: string
  language?: string | null
  confidence?: number | null
}

interface VoiceInputProps {
  onSubmit?: (text: string) => void
  onRawStt?: (meta: SttReviewMeta) => void
  /** Called with the STT round-trip latency (ms) once a transcript is returned. */
  onSttLatency?: (ms: number) => void
  disabled?: boolean
  language?: string
}

function isInteractiveElement(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button' || tag === 'a'
}

export default function VoiceInput({ onSubmit, onRawStt, onSttLatency, disabled = false, language }: VoiceInputProps) {
  const [textValue, setTextValue] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [showCalibration, setShowCalibration] = useState(false)
  const [reviewState, setReviewState] = useState<ReviewState | null>(null)

  const vad = useVad()
  const isHandsFree = vad.settings.mode === 'hands-free'
  const { startSilenceDetection, stopSilenceDetection } = vad

  const handleAudioReady = useCallback(
    async (blob: Blob) => {
      setIsSubmitting(true)
      setUploadError(null)
      const sttStart = performance.now()
      try {
        const result = await apiClient.uploadAudio(blob, language)
        onSttLatency?.(Math.round(performance.now() - sttStart))
        if (result.status === 'error') {
          setUploadError('Speech could not be transcribed. Please try again or type your response.')
        } else if (result.status === 'unavailable') {
          setUploadError('Speech-to-text is not installed. Please type your response.')
        } else if (result.transcript) {
          setReviewState({
            transcript: result.transcript,
            language: result.language,
            confidence: result.confidence,
          })
        } else if (result.status === 'ok' && !result.transcript) {
          setUploadError('No speech detected. Please try again or type your response.')
        }
      } catch (err) {
        console.error('STT upload failed:', err)
        setUploadError('Failed to process audio. Please try again or type your response.')
      } finally {
        setIsSubmitting(false)
      }
    },
    [language, onSttLatency],
  )

  const {
    permission,
    isRecording,
    recordingSeconds,
    error,
    stream,
    requestPermission,
    startRecording: startPttRecording,
    stopRecording: stopPttRecording,
  } = useMicCapture(handleAudioReady)

  // Wrap start/stop to hook in VAD silence detection for hands-free mode.
  const startRecording = useCallback(() => {
    // Guard against re-triggering while already recording: startSilenceDetection calls
    // stopSilenceDetection() internally, which cancels any pending silence timer and resets
    // the auto-stop countdown — defeating the hands-free behaviour.
    if (!isRecording && isHandsFree && stream) {
      startSilenceDetection(stream, () => {
        // Don't call stopSilenceDetection here — it would reset vadState to 'idle' in the
        // same React batch as 'stopping', preventing the auto-stopping state from rendering.
        // The effect below cleans up the AudioContext once isRecording becomes false.
        stopPttRecording()
      })
    }
    startPttRecording()
  }, [isRecording, isHandsFree, stream, startSilenceDetection, startPttRecording, stopPttRecording])

  const stopRecording = useCallback(() => {
    stopSilenceDetection()
    stopPttRecording()
  }, [stopSilenceDetection, stopPttRecording])

  // Close the AudioContext after auto-stop. The onSilence callback only calls stopPttRecording
  // so that the 'stopping' vadState survives its React render before being cleaned up here.
  useEffect(() => {
    if (!isRecording) stopSilenceDetection()
  }, [isRecording, stopSilenceDetection])

  function handleReviewConfirm(finalText: string) {
    const raw = reviewState
    setReviewState(null)
    if (raw) {
      onRawStt?.({
        rawTranscript: raw.transcript,
        finalTranscript: finalText,
        language: raw.language,
        confidence: raw.confidence,
      })
    }
    if (!disabled) {
      onSubmit?.(finalText)
    } else {
      setTextValue(finalText)
    }
  }

  function handleReviewCancel() {
    setReviewState(null)
  }

  function handleReviewRetry() {
    setReviewState(null)
  }

  // Global Space hotkey for PTT — skips when any interactive element is focused, mic is
  // unavailable, a prior recording is still being uploaded, or the component is disabled.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat) return
      if (isInteractiveElement(document.activeElement)) return
      if (permission !== 'granted' || isSubmitting || disabled) return
      // Don't start recording while the transcript review panel is open.
      if (reviewState !== null) return
      // In hands-free mode Space starts recording; once recording, VAD drives the stop so
      // we ignore further presses to avoid resetting the auto-stop countdown.
      if (isHandsFree && isRecording) return
      e.preventDefault()
      startRecording()
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (isInteractiveElement(document.activeElement)) return
      if (permission !== 'granted' || isSubmitting || (disabled && !isRecording)) return
      // In hands-free mode, Space also starts/stops but VAD drives the stop.
      // Releasing Space should always stop when PTT is active.
      if (!isHandsFree) stopRecording()
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [startRecording, stopRecording, permission, isRecording, isSubmitting, disabled, isHandsFree, reviewState])

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const value = textValue.trim()
    if (!value || disabled) return
    onSubmit?.(value)
    setTextValue('')
  }

  const handleModeToggle = () => {
    const next = isHandsFree ? 'ptt' : 'hands-free'
    vad.setMode(next)
    if (next === 'hands-free' && !vad.settings.calibratedAt) {
      setShowCalibration(true)
    }
    if (isRecording) stopRecording()
  }

  const showDeniedNotice = permission === 'denied'
  const showUnsupportedNotice = permission === 'unsupported'

  return (
    <div style={containerStyle}>
      {showDeniedNotice && (
        <p role="status" style={noticeStyle}>
          Microphone access denied. Please type your response below, or allow microphone access in
          your browser settings and reload.
        </p>
      )}
      {showUnsupportedNotice && (
        <p role="status" style={noticeStyle}>
          Microphone capture is not supported in this browser. Please type your response below.
        </p>
      )}
      {error && !showDeniedNotice && (
        <p role="alert" style={{ ...noticeStyle, color: '#f87171' }}>
          {error}
        </p>
      )}
      {uploadError && (
        <p role="alert" style={{ ...noticeStyle, color: '#f87171' }}>
          {uploadError}
        </p>
      )}

      {reviewState ? (
        <TranscriptReviewPanel
          transcript={reviewState.transcript}
          language={reviewState.language}
          confidence={reviewState.confidence}
          onConfirm={handleReviewConfirm}
          onCancel={handleReviewCancel}
          onRetry={handleReviewRetry}
        />
      ) : (
        <>
          <div style={inputRowStyle}>
            <MicButton
              permission={permission}
              isRecording={isRecording}
              recordingSeconds={recordingSeconds}
              isSubmitting={isSubmitting}
              disabled={disabled}
              isHandsFree={isHandsFree}
              onRequestPermission={requestPermission}
              onRecordStart={startRecording}
              onRecordStop={isHandsFree ? () => {} : stopRecording}
            />

            <form onSubmit={handleTextSubmit} style={{ display: 'flex', flex: 1, gap: '0.5rem' }}>
              <input
                type="text"
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                placeholder={
                  permission === 'denied' || permission === 'unsupported'
                    ? 'Type your response…'
                    : isHandsFree
                      ? 'Type or press the mic to record (auto-stops on silence)'
                      : 'Type or hold the mic button to record'
                }
                disabled={disabled || isRecording}
                aria-label="Your response"
                style={textInputStyle}
              />
              <button
                type="submit"
                disabled={disabled || !textValue.trim() || isRecording}
                style={sendButtonStyle}
              >
                Submit
              </button>
            </form>
          </div>

          {/* Hands-free controls row */}
          {permission === 'granted' && (
            <div style={hfRowStyle}>
              <button
                type="button"
                onClick={handleModeToggle}
                aria-pressed={isHandsFree}
                aria-label={isHandsFree ? 'Switch to push-to-talk mode' : 'Switch to hands-free mode (auto-stop on silence)'}
                style={isHandsFree ? modeActiveStyle : modeInactiveStyle}
              >
                <span aria-hidden="true">{isHandsFree ? '🤲 ' : '👆 '}</span>
                {isHandsFree ? 'Hands-free' : 'Push-to-talk'}
              </button>

              {isHandsFree && (
                <>
                  <VadStatusIndicator state={vad.vadState} />
                  <button
                    type="button"
                    onClick={() => setShowCalibration((v) => !v)}
                    aria-label={vad.settings.calibratedAt ? 'Recalibrate noise threshold' : 'Calibrate noise threshold'}
                    aria-expanded={showCalibration}
                    style={calibrateBtnStyle}
                  >
                    {vad.settings.calibratedAt ? 'Recalibrate' : 'Calibrate noise'}
                  </button>
                </>
              )}
            </div>
          )}

          {/* Calibration panel */}
          {showCalibration && isHandsFree && (
            <VadCalibration
              vad={vad}
              stream={stream}
              onDone={() => setShowCalibration(false)}
            />
          )}
        </>
      )}

      {/* PTT hint */}
      {permission === 'granted' && !isRecording && !isSubmitting && !isHandsFree && !reviewState && (
        <p style={hintStyle}>
          Press <kbd style={kbdStyle}>Space</kbd> to record when not typing, or hold the mic
          button. Max {MAX_RECORDING_SECONDS}s.
        </p>
      )}

      {/* Hands-free hint */}
      {permission === 'granted' && !isRecording && !isSubmitting && isHandsFree && !reviewState && (
        <p style={hintStyle}>
          Press <kbd style={kbdStyle}>Space</kbd> or tap the mic — recording stops automatically
          after silence.{' '}
          {!vad.settings.calibratedAt && (
            <span style={{ color: '#fbbf24' }}>Calibrate noise for best results.</span>
          )}
        </p>
      )}
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.5rem',
}

const inputRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: '0.5rem',
  alignItems: 'center',
}

const hfRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: '0.5rem',
  alignItems: 'center',
  flexWrap: 'wrap',
}

const textInputStyle: React.CSSProperties = {
  flex: 1,
  padding: '0.5rem 0.75rem',
  borderRadius: '6px',
  border: '1px solid #3f3f46',
  background: '#18181b',
  color: '#e4e4e7',
  fontSize: '0.95rem',
  outline: 'none',
}

const sendButtonStyle: React.CSSProperties = {
  padding: '0.5rem 1rem',
  borderRadius: '6px',
  border: 'none',
  background: '#2563eb',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '0.9rem',
}

const noticeStyle: React.CSSProperties = {
  margin: 0,
  padding: '0.5rem 0.75rem',
  borderRadius: '6px',
  background: '#27272a',
  color: '#a1a1aa',
  fontSize: '0.875rem',
}

const hintStyle: React.CSSProperties = {
  margin: 0,
  color: '#71717a',
  fontSize: '0.8rem',
}

const kbdStyle: React.CSSProperties = {
  padding: '0.1rem 0.35rem',
  borderRadius: '3px',
  border: '1px solid #52525b',
  fontFamily: 'monospace',
  fontSize: '0.75rem',
  background: '#27272a',
}

const modeBase: React.CSSProperties = {
  padding: '0.25rem 0.6rem',
  borderRadius: '6px',
  border: '1px solid #3f3f46',
  cursor: 'pointer',
  fontSize: '0.8rem',
  fontWeight: 500,
}

const modeActiveStyle: React.CSSProperties = {
  ...modeBase,
  background: '#1e3a5f',
  color: '#60a5fa',
  borderColor: '#2563eb',
}

const modeInactiveStyle: React.CSSProperties = {
  ...modeBase,
  background: '#27272a',
  color: '#a1a1aa',
}

const calibrateBtnStyle: React.CSSProperties = {
  padding: '0.25rem 0.6rem',
  borderRadius: '6px',
  border: '1px solid #3f3f46',
  background: 'transparent',
  color: '#71717a',
  cursor: 'pointer',
  fontSize: '0.78rem',
}
