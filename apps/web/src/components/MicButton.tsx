// SPDX-License-Identifier: Apache-2.0
import type { MicPermission } from '../hooks/useMicCapture'
import { MAX_RECORDING_SECONDS } from '../hooks/useMicCapture'

interface MicButtonProps {
  permission: MicPermission
  isRecording: boolean
  recordingSeconds: number
  isSubmitting: boolean
  disabled?: boolean
  onRequestPermission: () => void
  onRecordStart: () => void
  onRecordStop: () => void
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString()}:${s.toString().padStart(2, '0')}`
}

const srOnly: React.CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0,0,0,0)',
  whiteSpace: 'nowrap',
  border: 0,
}

export default function MicButton({
  permission,
  isRecording,
  recordingSeconds,
  isSubmitting,
  disabled = false,
  onRequestPermission,
  onRecordStart,
  onRecordStop,
}: MicButtonProps) {
  if (permission === 'unsupported' || permission === 'denied') return null

  if (permission === 'idle') {
    return (
      <button
        type="button"
        onClick={onRequestPermission}
        aria-label="Enable microphone access for push-to-talk"
        style={idleStyle}
      >
        Enable mic
      </button>
    )
  }

  if (permission === 'requesting') {
    return (
      <button type="button" disabled aria-label="Requesting microphone access" style={idleStyle}>
        Requesting…
      </button>
    )
  }

  // permission === 'granted'
  if (isSubmitting) {
    return (
      <button type="button" disabled aria-label="Processing audio" style={idleStyle}>
        Processing…
      </button>
    )
  }

  const label = isRecording
    ? `Recording ${formatDuration(recordingSeconds)} of ${MAX_RECORDING_SECONDS}s — release to stop`
    : 'Hold to record (or press Space when not typing)'

  return (
    <>
      <button
        type="button"
        aria-label={label}
        aria-pressed={isRecording}
        disabled={disabled}
        onPointerDown={onRecordStart}
        onPointerUp={onRecordStop}
        onPointerLeave={onRecordStop}
        onKeyDown={(e) => {
          if (e.code === 'Space' && !e.repeat) {
            e.preventDefault()
            onRecordStart()
          }
        }}
        onKeyUp={(e) => {
          if (e.code === 'Space') {
            e.preventDefault()
            onRecordStop()
          }
        }}
        style={isRecording ? recordingStyle : readyStyle}
      >
        {isRecording ? `● ${formatDuration(recordingSeconds)}` : '🎙 Hold'}
      </button>
      <span role="status" aria-live="polite" style={srOnly}>
        {isRecording ? `Recording ${formatDuration(recordingSeconds)}` : ''}
      </span>
    </>
  )
}

const base: React.CSSProperties = {
  padding: '0.5rem 1rem',
  borderRadius: '6px',
  border: 'none',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: '0.9rem',
  userSelect: 'none',
}

const idleStyle: React.CSSProperties = {
  ...base,
  background: '#3f3f46',
  color: '#e4e4e7',
}

const readyStyle: React.CSSProperties = {
  ...base,
  background: '#27272a',
  color: '#a1a1aa',
  border: '1px solid #52525b',
}

const recordingStyle: React.CSSProperties = {
  ...base,
  background: '#b91c1c',
  color: '#fef2f2',
  boxShadow: '0 0 0 3px rgba(185,28,28,0.4)',
}
