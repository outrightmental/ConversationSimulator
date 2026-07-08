// SPDX-License-Identifier: Apache-2.0
import { useState, useCallback, useEffect } from 'react'
import { apiClient } from '../api/client'
import { useMicCapture, MAX_RECORDING_SECONDS } from '../hooks/useMicCapture'
import MicButton from './MicButton'

interface VoiceInputProps {
  onSubmit?: (text: string) => void
  disabled?: boolean
  language?: string
}

function isInteractiveElement(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button' || tag === 'a'
}

export default function VoiceInput({ onSubmit, disabled = false, language }: VoiceInputProps) {
  const [textValue, setTextValue] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const handleAudioReady = useCallback(
    async (blob: Blob) => {
      setIsSubmitting(true)
      setUploadError(null)
      try {
        const result = await apiClient.uploadAudio(blob, language)
        if (result.status === 'error') {
          setUploadError('Speech could not be transcribed. Please try again or type your response.')
        } else if (result.transcript && !disabled) {
          onSubmit?.(result.transcript)
        }
      } catch (err) {
        console.error('STT upload failed:', err)
        setUploadError('Failed to process audio. Please try again or type your response.')
      } finally {
        setIsSubmitting(false)
      }
    },
    [onSubmit, disabled, language],
  )

  const { permission, isRecording, recordingSeconds, error, requestPermission, startRecording, stopRecording } =
    useMicCapture(handleAudioReady)

  // Global Space hotkey for PTT — skips when any interactive element is focused, mic is
  // unavailable, a prior recording is still being uploaded, or the component is disabled.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat) return
      if (isInteractiveElement(document.activeElement)) return
      if (permission !== 'granted' || isSubmitting || disabled) return
      e.preventDefault()
      startRecording()
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (isInteractiveElement(document.activeElement)) return
      if (permission !== 'granted' || isSubmitting || (disabled && !isRecording)) return
      stopRecording()
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [startRecording, stopRecording, permission, isRecording, isSubmitting, disabled])

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const value = textValue.trim()
    if (!value || disabled) return
    onSubmit?.(value)
    setTextValue('')
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

      <div style={inputRowStyle}>
        <MicButton
          permission={permission}
          isRecording={isRecording}
          recordingSeconds={recordingSeconds}
          isSubmitting={isSubmitting}
          disabled={disabled}
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
                : 'Type or hold the mic button to record'
            }
            disabled={disabled || isRecording}
            aria-label="Text input for conversation response"
            style={textInputStyle}
          />
          <button
            type="submit"
            disabled={disabled || !textValue.trim() || isRecording}
            aria-label="Send text response"
            style={sendButtonStyle}
          >
            Send
          </button>
        </form>
      </div>

      {permission === 'granted' && !isRecording && !isSubmitting && (
        <p style={hintStyle}>
          Press <kbd style={kbdStyle}>Space</kbd> to record when not typing, or hold the mic
          button. Max {MAX_RECORDING_SECONDS}s.
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
