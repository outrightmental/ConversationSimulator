// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef, useCallback } from 'react'
import type { UseVadReturn, VadSettings } from '../hooks/useVad'

interface VadCalibrationProps {
  vad: UseVadReturn
  stream: MediaStream | null
  onDone: () => void
}

type Phase = 'ready' | 'countdown' | 'recording' | 'done' | 'error'

const CALIBRATION_SECONDS = 3

export default function VadCalibration({ vad, stream, onDone }: VadCalibrationProps) {
  const [phase, setPhase] = useState<Phase>('ready')
  const [countdown, setCountdown] = useState(CALIBRATION_SECONDS)
  const [settings, setLocalSettings] = useState<VadSettings>(vad.settings)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  // Keep local settings preview in sync with saved settings.
  useEffect(() => {
    setLocalSettings(vad.settings)
  }, [vad.settings])

  const startCalibration = useCallback(() => {
    if (!stream) return
    setPhase('countdown')
    setCountdown(CALIBRATION_SECONDS)

    let remaining = CALIBRATION_SECONDS
    const tick = setInterval(() => {
      remaining -= 1
      setCountdown(remaining)
      if (remaining <= 0) {
        clearInterval(tick)
        beginRecording()
      }
    }, 1000)
  }, [stream]) // eslint-disable-line react-hooks/exhaustive-deps

  const beginRecording = useCallback(() => {
    if (!stream) return
    chunksRef.current = []
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
        ? 'audio/ogg;codecs=opus'
        : ''
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recorderRef.current = rec

    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    rec.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
      setPhase('recording') // brief "processing" label before calibrate resolves
      try {
        await vad.calibrate(blob)
        setLocalSettings(vad.settings)
        setPhase('done')
      } catch {
        setPhase('error')
      }
    }

    setPhase('recording')
    rec.start(250)
    setTimeout(() => {
      if (rec.state === 'recording') rec.stop()
    }, CALIBRATION_SECONDS * 1000)
  }, [stream, vad])

  const handleThresholdChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = Number(e.target.value)
    setLocalSettings((s) => ({ ...s, threshold: t }))
    vad.setThreshold(t)
  }

  const handleSilenceDurationChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const ms = Number(e.target.value)
    setLocalSettings((s) => ({ ...s, silenceDurationMs: ms }))
    vad.setSilenceDurationMs(ms)
  }

  return (
    <div style={panelStyle}>
      <p style={titleStyle}>Noise calibration</p>

      {phase === 'ready' && (
        <>
          <p style={descStyle}>
            Stay quiet for {CALIBRATION_SECONDS} seconds so the app can measure your ambient noise
            level. No audio is saved.
          </p>
          {!stream && (
            <p style={warnStyle}>Microphone not yet enabled — enable it first.</p>
          )}
          <button
            onClick={startCalibration}
            disabled={!stream}
            style={primaryBtnStyle}
          >
            Start {CALIBRATION_SECONDS}-second calibration
          </button>
        </>
      )}

      {phase === 'countdown' && (
        <p style={bigCountdownStyle} aria-live="assertive">
          Recording in {countdown}…
        </p>
      )}

      {phase === 'recording' && (
        <p style={descStyle} aria-live="polite">
          {vad.isCalibrating ? 'Analysing…' : 'Recording ambient noise…'}
        </p>
      )}

      {phase === 'done' && (
        <>
          <p style={{ ...descStyle, color: '#4ade80' }}>
            Calibration complete. Threshold set to{' '}
            <strong>{settings.threshold.toFixed(3)}</strong>.
          </p>
          <button onClick={startCalibration} style={secondaryBtnStyle}>
            Re-calibrate
          </button>
        </>
      )}

      {phase === 'error' && (
        <>
          <p style={{ ...descStyle, color: '#f87171' }}>
            Calibration failed. A default threshold is still in use.
          </p>
          <button onClick={startCalibration} style={secondaryBtnStyle}>
            Try again
          </button>
        </>
      )}

      <hr style={dividerStyle} />

      <label style={labelStyle}>
        Silence threshold:{' '}
        <strong>{settings.threshold.toFixed(3)}</strong>
        <input
          type="range"
          min={0.005}
          max={0.3}
          step={0.005}
          value={settings.threshold}
          onChange={handleThresholdChange}
          style={sliderStyle}
          aria-label="Silence threshold"
        />
        <span style={sliderHintStyle}>← quieter / louder →</span>
      </label>

      <label style={labelStyle}>
        Auto-stop delay:{' '}
        <strong>{(settings.silenceDurationMs / 1000).toFixed(1)} s</strong>
        <input
          type="range"
          min={500}
          max={3000}
          step={100}
          value={settings.silenceDurationMs}
          onChange={handleSilenceDurationChange}
          style={sliderStyle}
          aria-label="Auto-stop silence duration"
        />
        <span style={sliderHintStyle}>← faster / slower →</span>
      </label>

      <button onClick={onDone} style={doneBtnStyle}>
        Done
      </button>
    </div>
  )
}

const panelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.6rem',
  padding: '0.75rem',
  borderRadius: '8px',
  background: '#18181b',
  border: '1px solid #3f3f46',
}

const titleStyle: React.CSSProperties = {
  margin: 0,
  fontWeight: 600,
  color: '#e4e4e7',
  fontSize: '0.9rem',
}

const descStyle: React.CSSProperties = {
  margin: 0,
  color: '#a1a1aa',
  fontSize: '0.85rem',
}

const warnStyle: React.CSSProperties = {
  ...descStyle,
  color: '#fbbf24',
}

const bigCountdownStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '1.5rem',
  fontWeight: 700,
  color: '#60a5fa',
  textAlign: 'center',
}

const labelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.2rem',
  color: '#a1a1aa',
  fontSize: '0.82rem',
}

const sliderStyle: React.CSSProperties = {
  width: '100%',
  accentColor: '#2563eb',
}

const sliderHintStyle: React.CSSProperties = {
  fontSize: '0.75rem',
  color: '#52525b',
}

const dividerStyle: React.CSSProperties = {
  border: 'none',
  borderTop: '1px solid #3f3f46',
  margin: '0.25rem 0',
}

const base: React.CSSProperties = {
  padding: '0.4rem 0.9rem',
  borderRadius: '6px',
  border: 'none',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: '0.85rem',
  alignSelf: 'flex-start',
}

const primaryBtnStyle: React.CSSProperties = {
  ...base,
  background: '#2563eb',
  color: '#fff',
}

const secondaryBtnStyle: React.CSSProperties = {
  ...base,
  background: '#3f3f46',
  color: '#e4e4e7',
}

const doneBtnStyle: React.CSSProperties = {
  ...base,
  background: '#3f3f46',
  color: '#e4e4e7',
  alignSelf: 'flex-end',
}
