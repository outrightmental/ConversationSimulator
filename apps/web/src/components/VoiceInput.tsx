// SPDX-License-Identifier: Apache-2.0
import { useState, useCallback, useEffect, useRef } from 'react'
import type { InputMode } from '@convsim/shared'
import { apiClient, api } from '../api/client'
import { useMicCapture, MAX_RECORDING_SECONDS } from '../hooks/useMicCapture'
import { useVad } from '../hooks/useVad'
import MicButton from './MicButton'
import VadStatusIndicator from './VadStatusIndicator'
import VadCalibration from './VadCalibration'
import TranscriptReviewPanel from './TranscriptReviewPanel'

const BACKCHANNEL_TRIGGER_MS = 3_500

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
  /**
   * Called when the player starts recording while NPC TTS may be playing.
   * The parent uses this to fade TTS and register a barge-in for the next turn.
   */
  onRecordingStart?: () => void
  disabled?: boolean
  language?: string
  /**
   * Input mode selected at session setup. Initialises the VAD mode and hides
   * mic controls when set to 'text-only'. Can be overridden mid-session via the
   * in-conversation "Switch to text-only" fallback.
   */
  inputMode?: InputMode
  /** Play short NPC acknowledgments ("mm-hm") while the player speaks. Default false. */
  backchannelEnabled?: boolean
}

function isInteractiveElement(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button' || tag === 'a'
}

export default function VoiceInput({ onSubmit, onRawStt, onSttLatency, onRecordingStart, disabled = false, language, inputMode, backchannelEnabled = false }: VoiceInputProps) {
  const [textValue, setTextValue] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [showCalibration, setShowCalibration] = useState(false)
  const [reviewState, setReviewState] = useState<ReviewState | null>(null)
  // Tracks whether the player has switched to text-only fallback mid-session.
  const [textOnly, setTextOnly] = useState(() => inputMode === 'text-only')

  // Backchannel audio: pre-fetched paths played during extended player speech.
  const backchannelPathsRef = useRef<string[]>([])
  const backchannelTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const backchannelAudioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    if (!backchannelEnabled) return
    api.getBackchannels()
      .then((r) => {
        backchannelPathsRef.current = r.backchannels
          .map((b) => {
            const filename = b.cache_path.replace(/\\/g, '/').split('/').pop()
            return filename ? `/api/tts/audio/${filename}` : ''
          })
          .filter(Boolean)
      })
      .catch(() => {})
  }, [backchannelEnabled])

  function _playRandomBackchannel() {
    const paths = backchannelPathsRef.current
    if (!paths.length) return
    const url = paths[Math.floor(Math.random() * paths.length)]
    const audio = new Audio(url)
    backchannelAudioRef.current = audio
    audio.play().catch(() => {})
  }

  function _startBackchannelTimer() {
    if (!backchannelEnabled || !backchannelPathsRef.current.length) return
    if (backchannelTimerRef.current) clearTimeout(backchannelTimerRef.current)
    backchannelTimerRef.current = setTimeout(() => {
      backchannelTimerRef.current = null
      _playRandomBackchannel()
    }, BACKCHANNEL_TRIGGER_MS)
  }

  function _cancelBackchannelTimer() {
    if (backchannelTimerRef.current) {
      clearTimeout(backchannelTimerRef.current)
      backchannelTimerRef.current = null
    }
    if (backchannelAudioRef.current) {
      backchannelAudioRef.current.pause()
      backchannelAudioRef.current = null
    }
  }

  const vad = useVad()
  const isHandsFree = vad.settings.mode === 'hands-free'
  const { startSilenceDetection, stopSilenceDetection, setMode: vadSetMode } = vad

  // Initialise VAD mode from the session setup choice on first render only.
  const initModeRef = useRef(false)
  useEffect(() => {
    if (initModeRef.current) return
    initModeRef.current = true
    if (inputMode === 'hands-free') vadSetMode('hands-free')
    else if (inputMode === 'push-to-talk') vadSetMode('ptt')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAudioReady = useCallback(
    async (blob: Blob) => {
      setIsSubmitting(true)
      setUploadError(null)
      const sttStart = performance.now()
      try {
        const result = await apiClient.uploadAudio(blob, language)
        onSttLatency?.(Math.round(performance.now() - sttStart))
        if (!result.ok) {
          setUploadError(result.error.message)
        } else if (result.data.status === 'error') {
          setUploadError('Speech could not be transcribed. Please try again or type your response.')
        } else if (result.data.status === 'unavailable') {
          setUploadError('Speech-to-text is not installed. Please type your response.')
        } else if (result.data.transcript) {
          setReviewState({
            transcript: result.data.transcript,
            language: result.data.language,
            confidence: result.data.confidence,
          })
        } else if (result.data.status === 'ok' && !result.data.transcript) {
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
    releaseStream,
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
    // Notify the parent so it can fade NPC TTS (barge-in) if it is currently playing.
    onRecordingStart?.()
    // Start a timer to play a backchannel acknowledgment during extended speech.
    _startBackchannelTimer()
    startPttRecording()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRecording, isHandsFree, stream, startSilenceDetection, startPttRecording, stopPttRecording, onRecordingStart, backchannelEnabled])

  const stopRecording = useCallback(() => {
    _cancelBackchannelTimer()
    stopSilenceDetection()
    stopPttRecording()
  }, [stopSilenceDetection, stopPttRecording])

  // Close the AudioContext after auto-stop. The onSilence callback only calls stopPttRecording
  // so that the 'stopping' vadState survives its React render before being cleaned up here.
  useEffect(() => {
    if (!isRecording) {
      stopSilenceDetection()
      // Hands-free auto-stop bypasses the stopRecording() wrapper, so cancel any
      // pending backchannel here too — otherwise a short (<3.5 s) utterance would
      // fire a stray acknowledgment after the player already finished speaking.
      _cancelBackchannelTimer()
    }
  }, [isRecording, stopSilenceDetection])

  // Cancel any pending/playing backchannel on unmount (e.g. navigating away
  // mid-utterance) so it cannot fire after the component is gone.
  useEffect(() => () => _cancelBackchannelTimer(), [])

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
      // In text-only mode there is no mic recording — the hotkey must be inert
      // even when microphone permission is still granted from an active stream.
      if (textOnly) return
      if (permission !== 'granted' || isSubmitting || disabled) return
      // Don't start recording while the transcript review panel is open.
      if (reviewState !== null) return
      // In hands-free mode: Space toggles — starts if idle, manually stops if already recording.
      if (isHandsFree && isRecording) {
        e.preventDefault()
        stopRecording()
        return
      }
      e.preventDefault()
      startRecording()
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (isInteractiveElement(document.activeElement)) return
      if (textOnly) return
      if (permission !== 'granted' || isSubmitting || (disabled && !isRecording)) return
      // PTT only: release Space to stop. In hands-free mode, stop is handled on keydown.
      if (!isHandsFree) stopRecording()
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [startRecording, stopRecording, permission, isRecording, isSubmitting, disabled, isHandsFree, reviewState, textOnly])

  // Gamepad R1 / right-shoulder push-to-talk — mirrors the Space hotkey above
  // but driven by the custom events emitted by useGamepadNavigation.
  useEffect(() => {
    const handlePttStart = () => {
      if (textOnly) return
      if (permission !== 'granted' || isSubmitting || disabled) return
      if (reviewState !== null) return
      if (isHandsFree && isRecording) {
        stopRecording()
        return
      }
      startRecording()
    }

    const handlePttStop = () => {
      if (textOnly) return
      if (permission !== 'granted' || isSubmitting || (disabled && !isRecording)) return
      if (!isHandsFree) stopRecording()
    }

    document.addEventListener('gamepad-ptt-start', handlePttStart)
    document.addEventListener('gamepad-ptt-stop', handlePttStop)
    return () => {
      document.removeEventListener('gamepad-ptt-start', handlePttStart)
      document.removeEventListener('gamepad-ptt-stop', handlePttStop)
    }
  }, [startRecording, stopRecording, permission, isRecording, isSubmitting, disabled, isHandsFree, reviewState, textOnly])

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

  // Text-only mode: render a minimal input without any mic controls.
  if (textOnly) {
    return (
      <div style={containerStyle}>
        <p role="status" data-testid="text-only-notice" style={noticeStyle}>
          Voice input disabled — using text only for this session.
        </p>
        {uploadError && (
          <p role="alert" style={{ ...noticeStyle, color: '#f87171' }}>
            {uploadError}
          </p>
        )}
        <form onSubmit={handleTextSubmit} style={{ display: 'flex', flex: 1, gap: '0.5rem' }}>
          <input
            type="text"
            value={textValue}
            onChange={(e) => setTextValue(e.target.value)}
            placeholder="Type your response…"
            disabled={disabled}
            aria-label="Your response"
            style={textInputStyle}
          />
          <button
            type="submit"
            disabled={disabled || !textValue.trim()}
            style={sendButtonStyle}
          >
            Submit
          </button>
        </form>
      </div>
    )
  }

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
              onRecordStop={stopRecording}
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

          {/* Voice controls row: mode toggle, VAD indicator, calibrate, text-only fallback */}
          {permission === 'granted' && (
            <div style={hfRowStyle}>
              <button
                type="button"
                onClick={handleModeToggle}
                aria-pressed={isHandsFree}
                aria-label={isHandsFree ? 'Hands-free mode active — activate to switch to push-to-talk' : 'Push-to-talk mode active — activate to switch to hands-free (auto-stop on silence)'}
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

              <button
                type="button"
                data-testid="switch-to-text-only"
                onClick={() => {
                  if (isRecording) stopRecording()
                  // Release the microphone so the recording indicator turns off —
                  // the player has opted out of voice for the rest of the session.
                  releaseStream()
                  setTextOnly(true)
                }}
                aria-label="Switch to text-only input"
                style={switchToTextOnlyStyle}
              >
                Text only
              </button>
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
          Press <kbd style={kbdStyle}>Space</kbd> or tap the mic — auto-stops on silence; press
          again to stop manually.{' '}
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

const switchToTextOnlyStyle: React.CSSProperties = {
  marginLeft: 'auto',
  padding: '0.25rem 0.6rem',
  borderRadius: '6px',
  border: '1px solid #3f3f46',
  background: 'transparent',
  color: '#71717a',
  cursor: 'pointer',
  fontSize: '0.78rem',
}
