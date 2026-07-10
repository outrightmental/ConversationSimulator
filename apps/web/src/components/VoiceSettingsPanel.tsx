// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback } from 'react'
import type { VoiceInfo } from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from './ApiErrorView'

export const VOICE_PREF_THINKING_PAUSE = 'convsim.voice.thinkingPauseEnabled'
export const VOICE_PREF_BACKCHANNEL = 'convsim.voice.backchannelEnabled'
export const VOICE_PREF_BARGE_IN = 'convsim.voice.bargeInEnabled'

export function getVoiceTimingPrefs(): {
  thinkingPauseEnabled: boolean
  backchannelEnabled: boolean
  bargeInEnabled: boolean
} {
  return {
    thinkingPauseEnabled: localStorage.getItem(VOICE_PREF_THINKING_PAUSE) !== 'false',
    backchannelEnabled: localStorage.getItem(VOICE_PREF_BACKCHANNEL) === 'true',
    bargeInEnabled: localStorage.getItem(VOICE_PREF_BARGE_IN) !== 'false',
  }
}

type MicPermission = 'granted' | 'denied' | 'prompt' | 'unavailable' | 'checking'
type ReadinessStatus = 'ready' | 'unavailable' | 'checking' | 'error'

interface ReadinessCardProps {
  label: string
  testId: string
  status: ReadinessStatus
  detail: string
  guidance?: string
}

function ReadinessCard({ label, testId, status, detail, guidance }: ReadinessCardProps) {
  const color =
    status === 'ready' ? '#86efac' :
    status === 'checking' ? '#a1a1aa' :
    '#f87171'

  const dot =
    status === 'ready' ? '#22c55e' :
    status === 'checking' ? '#71717a' :
    '#ef4444'

  return (
    <div
      data-testid={testId}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.6rem',
        padding: '0.5rem 0',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          flexShrink: 0,
          width: '0.5rem',
          height: '0.5rem',
          borderRadius: '50%',
          background: dot,
          marginTop: '0.35rem',
        }}
      />
      <div>
        <span style={{ fontWeight: 500, color, fontSize: '0.875rem' }}>{label}</span>
        <span style={{ color: '#a1a1aa', fontSize: '0.875rem' }}>: {detail}</span>
        {guidance && status !== 'ready' && (
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.8rem', color: '#71717a' }}>
            {guidance}
          </p>
        )}
      </div>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

type CacheClearState = 'idle' | 'clearing' | 'done' | 'error'

export default function VoiceSettingsPanel() {
  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const [voicesError, setVoicesError] = useState<ApiError | null>(null)

  const [cacheFiles, setCacheFiles] = useState<number | null>(null)
  const [cacheSizeBytes, setCacheSizeBytes] = useState<number | null>(null)
  const [cacheError, setCacheError] = useState<ApiError | null>(null)
  const [clearState, setClearState] = useState<CacheClearState>('idle')
  const [clearError, setClearError] = useState<ApiError | null>(null)

  const [micPerm, setMicPerm] = useState<MicPermission>('checking')
  const [sttReady, setSttReady] = useState<boolean | null>(null)
  const [ttsReady, setTtsReady] = useState<boolean | null>(null)
  const [vadReady, setVadReady] = useState<boolean | null>(null)

  const [preferredVoiceId, setPreferredVoiceId] = useState<string>(
    () => localStorage.getItem('convsim.voice.preferredVoiceId') ?? ''
  )

  const [thinkingPauseEnabled, setThinkingPauseEnabled] = useState(
    () => localStorage.getItem(VOICE_PREF_THINKING_PAUSE) !== 'false'
  )
  const [backchannelEnabled, setBackchannelEnabled] = useState(
    () => localStorage.getItem(VOICE_PREF_BACKCHANNEL) === 'true'
  )
  const [bargeInEnabled, setBargeInEnabled] = useState(
    () => localStorage.getItem(VOICE_PREF_BARGE_IN) !== 'false'
  )

  const loadCacheSize = useCallback(() => {
    api.getTtsCacheSize()
      .then((r) => { if (r.ok) { setCacheFiles(r.data.file_count); setCacheSizeBytes(r.data.bytes) } else setCacheError(r.error) })
  }, [])

  useEffect(() => {
    // Load voices from the approved list
    api.listVoices()
      .then((r) => {
        if (r.ok) {
          setVoices(r.data.voices)
          setVoicesError(null)
          // Initialise preferred voice from localStorage if set, else default to first
          const stored = localStorage.getItem('convsim.voice.preferredVoiceId')
          if (stored && r.data.voices.some((v) => v.voice_id === stored)) {
            setPreferredVoiceId(stored)
          } else if (r.data.voices.length > 0) {
            setPreferredVoiceId(r.data.voices[0].voice_id)
          }
        } else {
          setVoicesError(r.error)
        }
      })

    // Load cache size
    loadCacheSize()

    // Health check for STT and TTS readiness
    api.health()
      .then((r) => { if (r.ok) { setSttReady(r.data.runtime?.stt_ready ?? false); setTtsReady(r.data.runtime?.tts_ready ?? false) } })

    // VAD health check
    api.vadHealth()
      .then((r) => { if (r.ok) setVadReady(r.data.status === 'ready') })

    // Microphone permission
    if (!navigator.permissions) {
      setMicPerm('unavailable')
      return
    }
    navigator.permissions.query({ name: 'microphone' as PermissionName })
      .then((result) => {
        setMicPerm(result.state as MicPermission)
        result.addEventListener('change', () => {
          setMicPerm(result.state as MicPermission)
        })
      })
      .catch(() => setMicPerm('unavailable'))
  }, [loadCacheSize])

  function handleVoiceChange(voiceId: string) {
    setPreferredVoiceId(voiceId)
    localStorage.setItem('convsim.voice.preferredVoiceId', voiceId)
  }

  async function handleClearCache() {
    setClearState('clearing')
    setClearError(null)
    const r = await api.clearTtsCache()
    if (!r.ok) {
      setClearState('error')
      setClearError(r.error)
    } else {
      setCacheFiles(0)
      setCacheSizeBytes(0)
      setClearState('done')
    }
  }

  function handleThinkingPauseToggle() {
    const next = !thinkingPauseEnabled
    setThinkingPauseEnabled(next)
    localStorage.setItem(VOICE_PREF_THINKING_PAUSE, String(next))
  }

  function handleBackchannelToggle() {
    const next = !backchannelEnabled
    setBackchannelEnabled(next)
    localStorage.setItem(VOICE_PREF_BACKCHANNEL, String(next))
  }

  function handleBargeInToggle() {
    const next = !bargeInEnabled
    setBargeInEnabled(next)
    localStorage.setItem(VOICE_PREF_BARGE_IN, String(next))
  }

  function cacheSizeLabel(): string {
    if (cacheError) return 'unavailable'
    if (cacheFiles === null || cacheSizeBytes === null) return 'Loading…'
    if (cacheFiles === 0) return 'Empty'
    return `${cacheFiles} file${cacheFiles === 1 ? '' : 's'} · ${formatBytes(cacheSizeBytes)}`
  }

  const micStatus: ReadinessStatus =
    micPerm === 'granted' ? 'ready' :
    micPerm === 'checking' ? 'checking' :
    'unavailable'

  const sttStatus: ReadinessStatus =
    sttReady === null ? 'checking' :
    sttReady ? 'ready' : 'unavailable'

  const vadStatus: ReadinessStatus =
    vadReady === null ? 'checking' :
    vadReady ? 'ready' : 'unavailable'

  const ttsStatus: ReadinessStatus =
    ttsReady === null ? 'checking' :
    ttsReady ? 'ready' : 'unavailable'

  return (
    <div>
      {/* Voice readiness */}
      <div style={{ marginBottom: '1.25rem' }}>
        <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#a1a1aa', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Voice readiness
        </h3>
        <div
          data-testid="voice-readiness"
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '6px',
            padding: '0.5rem 0.75rem',
          }}
        >
          <ReadinessCard
            label="Microphone"
            testId="readiness-mic"
            status={micStatus}
            detail={
              micPerm === 'granted' ? 'permission granted' :
              micPerm === 'denied' ? 'permission denied' :
              micPerm === 'prompt' ? 'permission not yet granted' :
              micPerm === 'checking' ? 'checking…' :
              'permissions API unavailable'
            }
            guidance={
              micPerm === 'denied'
                ? 'Allow microphone access in your browser or OS settings to use voice input.'
                : micPerm === 'prompt'
                ? 'Microphone permission will be requested when you start a voice session.'
                : undefined
            }
          />
          <ReadinessCard
            label="STT"
            testId="readiness-stt"
            status={sttStatus}
            detail={sttReady === null ? 'checking…' : sttReady ? 'model loaded' : 'no model loaded'}
            guidance={!sttReady && sttReady !== null ? 'Install a speech-to-text model to enable voice input modes.' : undefined}
          />
          <ReadinessCard
            label="VAD"
            testId="readiness-vad"
            status={vadStatus}
            detail={vadReady === null ? 'checking…' : vadReady ? 'ready' : 'not available'}
            guidance={!vadReady && vadReady !== null ? 'Hands-free mode uses voice activity detection. VAD is not available in this environment.' : undefined}
          />
          <ReadinessCard
            label="TTS"
            testId="readiness-tts"
            status={ttsStatus}
            detail={ttsReady === null ? 'checking…' : ttsReady ? 'model loaded' : 'no model loaded'}
            guidance={!ttsReady && ttsReady !== null ? 'Install a text-to-speech model to enable NPC voice output. Text-only is always available.' : undefined}
          />
        </div>
      </div>

      {/* Voice selection */}
      <div style={{ marginBottom: '1.25rem' }}>
        <label htmlFor="preferred-voice" style={{ display: 'block', fontWeight: 500, marginBottom: '0.35rem', fontSize: '0.875rem' }}>
          Default NPC voice
        </label>
        {voicesError ? (
          <ApiErrorView error={voicesError} compact context="VoiceSettings-Voices" />
        ) : voices.length === 0 ? (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Loading…</p>
        ) : (
          <>
            <select
              id="preferred-voice"
              value={preferredVoiceId}
              onChange={(e) => handleVoiceChange(e.target.value)}
              aria-label="Default NPC voice"
              style={{
                width: '100%',
                padding: '0.4rem 0.6rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: '4px',
                color: '#d4d4d8',
                fontSize: '0.875rem',
              }}
            >
              {voices.map((v) => (
                <option key={v.voice_id} value={v.voice_id}>
                  {v.display_name}
                </option>
              ))}
            </select>
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', color: '#71717a' }}>
              Voice selection is limited to approved built-in voices. No voice cloning or import is supported.
            </p>
          </>
        )}
      </div>

      {/* Conversational timing features */}
      <div style={{ marginBottom: '1.25rem' }}>
        <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#a1a1aa', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Conversational timing
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              data-testid="toggle-thinking-pause"
              checked={thinkingPauseEnabled}
              onChange={handleThinkingPauseToggle}
              style={{ marginTop: '0.15rem', flexShrink: 0 }}
            />
            <span>
              <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>NPC thinking pause</span>
              <span style={{ display: 'block', fontSize: '0.8rem', color: '#71717a' }}>
                Adds a brief delay before the NPC speaks — longer for patient NPCs, shorter for adversarial ones.
              </span>
            </span>
          </label>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              data-testid="toggle-backchannel"
              checked={backchannelEnabled}
              onChange={handleBackchannelToggle}
              style={{ marginTop: '0.15rem', flexShrink: 0 }}
            />
            <span>
              <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>Backchannels</span>
              <span style={{ display: 'block', fontSize: '0.8rem', color: '#71717a' }}>
                NPC plays short acknowledgments ("mm-hm", "right") while you speak.{' '}
                <em>Off by default — may add latency on slower hardware.</em>
              </span>
            </span>
          </label>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              data-testid="toggle-barge-in"
              checked={bargeInEnabled}
              onChange={handleBargeInToggle}
              style={{ marginTop: '0.15rem', flexShrink: 0 }}
            />
            <span>
              <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>Barge-in</span>
              <span style={{ display: 'block', fontSize: '0.8rem', color: '#71717a' }}>
                Speaking while the NPC is talking stops NPC audio immediately and starts your turn.
              </span>
            </span>
          </label>
        </div>
      </div>

      {/* TTS cache */}
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
          <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>TTS audio cache</span>
          <span
            data-testid="cache-size-label"
            style={{ fontSize: '0.8rem', color: cacheError ? '#f87171' : '#a1a1aa' }}
          >
            {cacheSizeLabel()}
          </span>
        </div>
        <p style={{ fontSize: '0.8rem', color: '#71717a', margin: '0 0 0.5rem' }}>
          Cached audio files speed up repeated phrases. Clear the cache to free disk space or reset synthesised audio.
        </p>

        {cacheError && <ApiErrorView error={cacheError} compact context="VoiceSettings-Cache" />}

        {clearState === 'done' && (
          <p aria-live="polite" style={{ fontSize: '0.875rem', color: '#86efac', marginBottom: '0.4rem' }}>
            Cache cleared.
          </p>
        )}
        {clearError && <ApiErrorView error={clearError} compact context="VoiceSettings-Clear" />}

        <button
          onClick={handleClearCache}
          disabled={clearState === 'clearing' || cacheFiles === 0}
          aria-label="Clear TTS cache"
          style={{
            padding: '0.4rem 0.9rem',
            borderRadius: '4px',
            border: 'none',
            cursor: clearState === 'clearing' || cacheFiles === 0 ? 'not-allowed' : 'pointer',
            background: 'rgba(239,68,68,0.15)',
            color: '#f87171',
            fontWeight: 500,
            fontSize: '0.875rem',
            opacity: cacheFiles === 0 ? 0.5 : 1,
          }}
        >
          {clearState === 'clearing' ? 'Clearing…' : 'Clear TTS cache'}
        </button>
      </div>
    </div>
  )
}
