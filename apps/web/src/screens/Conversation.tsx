// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import VoiceInput from '../components/VoiceInput'
import DebugDrawer, { type DebugTurnEntry } from '../components/DebugDrawer'
import { isDevModeEnabled } from '../privacyPrefs'

const BASELINE_STATE_VARS: Record<string, number> = {
  trust: 50,
  patience: 75,
  pressure: 25,
  rapport: 50,
  openness: 50,
  objective_progress: 0,
}

type TurnEntry = {
  id: number  // client-side sequential id used as React key; NOT the server event_id
  role: 'npc_opening' | 'npc' | 'player'
  content: string
  emotion?: string
  eventFlags?: string[]
}

type Phase = 'starting' | 'active' | 'submitting' | 'ending' | 'ended' | 'error'

export default function Conversation() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const { state } = useLocation()
  const language = (state as { language?: string } | null)?.language

  const [phase, setPhase] = useState<Phase>('starting')
  const [sessionState, setSessionState] = useState('NotStarted')
  const [endingType, setEndingType] = useState<string | null>(null)
  const [turns, setTurns] = useState<TurnEntry[]>([])
  const [stateVars, setStateVars] = useState<Record<string, number>>(BASELINE_STATE_VARS)
  const [allEventFlags, setAllEventFlags] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [devMode] = useState(() => isDevModeEnabled())
  const [debugEntries, setDebugEntries] = useState<DebugTurnEntry[]>([])

  const transcriptRef = useRef<HTMLDivElement>(null)
  const turnUidRef = useRef(0)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    api.startSession(sessionId).then(
      (res) => {
        if (cancelled) return
        const opening = res.events.find((e) => e.event_type === 'npc_opening')
        if (opening) {
          const uid = ++turnUidRef.current
          setTurns([
            {
              id: uid,
              role: 'npc_opening',
              content: opening.payload['content'] as string,
            },
          ])
          if (devMode) {
            setDebugEntries([
              {
                turnId: uid,
                role: 'npc_opening',
                rawPayload: opening.payload,
                appliedDelta: {},
              },
            ])
          }
        }
        setSessionState(res.state)
        setStateVars({ ...BASELINE_STATE_VARS })
        setPhase('active')
      },
      (err: unknown) => {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : String(err)
        if (msg.includes('INVALID_TRANSITION') || msg.includes('409')) {
          setError('This session was already started. Previous turns are not shown here.')
          setSessionState('PlayerTurnListening')
          setPhase('active')
        } else {
          setError(msg)
          setPhase('error')
        }
      },
    )

    return () => {
      cancelled = true
    }
  }, [sessionId, devMode])

  useEffect(() => {
    const el = transcriptRef.current
    if (el && typeof el.scrollTo === 'function') {
      el.scrollTo(0, el.scrollHeight)
    }
  }, [turns])

  async function handleSubmit(text: string) {
    if (!text || phase !== 'active') return

    setPhase('submitting')
    setError(null)

    try {
      const res = await api.submitTurn(sessionId!, text)

      const playerEvent = res.events.find((e) => e.event_type === 'player_turn')
      const npcEvent = res.events.find((e) => e.event_type === 'npc_turn')

      const newTurns: TurnEntry[] = []
      if (playerEvent) {
        newTurns.push({
          id: ++turnUidRef.current,
          role: 'player',
          content: playerEvent.payload['content'] as string,
        })
      }
      if (npcEvent) {
        const payload = npcEvent.payload
        const delta = (payload['state_delta'] ?? {}) as Record<string, number>
        const flags = (payload['event_flags'] ?? []) as string[]

        const uid = ++turnUidRef.current
        newTurns.push({
          id: uid,
          role: 'npc',
          content: payload['content'] as string,
          emotion: payload['emotion'] as string | undefined,
          eventFlags: flags.length > 0 ? flags : undefined,
        })

        if (devMode) {
          // Split the model's requested delta into entries that target tracked
          // state variables (applied) and entries for unknown variables that the
          // reducer below silently drops (rejected) — surfacing model drift.
          const appliedDelta: Record<string, number> = {}
          const rejectedDelta: Record<string, number> = {}
          for (const [k, d] of Object.entries(delta)) {
            if (k in BASELINE_STATE_VARS) appliedDelta[k] = d
            else rejectedDelta[k] = d
          }
          setDebugEntries((prev) => [
            ...prev,
            { turnId: uid, role: 'npc', rawPayload: payload, appliedDelta, rejectedDelta },
          ])
        }

        if (Object.keys(delta).length > 0) {
          setStateVars((prev) => {
            const next = { ...prev }
            for (const [k, d] of Object.entries(delta)) {
              if (k in next) next[k] = Math.max(0, Math.min(100, next[k] + d))
            }
            return next
          })
        }
        if (flags.length > 0) {
          setAllEventFlags((prev) => [...prev, ...flags])
        }
      }

      setTurns((prev) => [...prev, ...newTurns])
      setSessionState(res.state)

      if (res.state === 'Ended') {
        const npcPayload = npcEvent?.payload
        setEndingType((npcPayload?.['ending_type'] as string | null | undefined) ?? null)
        setPhase('ended')
      } else {
        setPhase('active')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setPhase('active')
    }
  }

  async function handleEndSession() {
    if (phase !== 'active') return
    setPhase('ending')
    setError(null)
    try {
      const res = await api.endSession(sessionId!)
      setSessionState(res.state)
      setEndingType(res.ending_type)
      setPhase('ended')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setPhase('active')
    }
  }

  const isIdle = phase === 'active'
  const isBusy = phase === 'submitting' || phase === 'ending'
  const isEnded = phase === 'ended'

  return (
    <div
      data-testid="conversation-page"
      style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: 760 }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <div>
          <h1 style={{ margin: 0 }}>Conversation</h1>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#71717a' }}>
            Session: <code>{sessionId}</code> &nbsp;|&nbsp; State:{' '}
            <code>{sessionState}</code>
            {endingType && (
              <span style={{ marginLeft: '0.5rem', color: '#a1a1aa' }}>
                ({endingType.replace(/_/g, ' ')})
              </span>
            )}
          </p>
        </div>
        {!isEnded && phase !== 'error' && (
          <button
            onClick={() => void handleEndSession()}
            disabled={isBusy || phase === 'starting'}
            style={{
              padding: '0.4rem 1rem',
              borderRadius: 6,
              border: '1px solid #52525b',
              background: '#18181b',
              color: '#f4f4f5',
              cursor: 'pointer',
            }}
            aria-label="End session"
          >
            End session
          </button>
        )}
      </div>

      {error && (
        <div
          role="alert"
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 6,
            border: '1px solid #7f1d1d',
            background: '#450a0a',
            color: '#fca5a5',
            fontSize: '0.875rem',
          }}
        >
          {error}
        </div>
      )}

      {phase === 'starting' && (
        <p aria-live="polite" aria-busy="true" style={{ color: '#71717a' }}>
          Starting session…
        </p>
      )}

      {/* Transcript */}
      <div
        ref={transcriptRef}
        role="log"
        aria-label="Conversation transcript"
        aria-live="polite"
        style={{
          minHeight: 240,
          maxHeight: 480,
          overflowY: 'auto',
          padding: '1rem',
          borderRadius: 8,
          border: '1px solid #27272a',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}
      >
        {turns.length === 0 && phase !== 'starting' && (
          <em style={{ color: '#52525b', fontSize: '0.875rem' }}>No turns yet.</em>
        )}
        {turns.map((turn) => (
          <div key={turn.id} data-role={turn.role}>
            <div
              style={{
                fontSize: '0.7rem',
                color: turn.role === 'player' ? '#a78bfa' : '#6ee7b7',
                marginBottom: 2,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              {turn.role === 'player' ? 'You' : 'NPC'}
              {turn.emotion && turn.emotion !== 'neutral' && (
                <span style={{ marginLeft: 6, opacity: 0.7 }}>({turn.emotion})</span>
              )}
            </div>
            <div
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: 6,
                background: turn.role === 'player' ? '#1e1b4b' : '#052e16',
                color: '#f4f4f5',
                fontSize: '0.9rem',
                lineHeight: 1.5,
              }}
            >
              {turn.content}
            </div>
            {turn.eventFlags && turn.eventFlags.length > 0 && (
              <div style={{ fontSize: '0.7rem', color: '#fbbf24', marginTop: 2 }}>
                Flags: {turn.eventFlags.join(', ')}
              </div>
            )}
          </div>
        ))}
        {isBusy && (
          <div
            aria-live="polite"
            aria-busy="true"
            style={{ color: '#71717a', fontSize: '0.875rem', fontStyle: 'italic' }}
          >
            {phase === 'submitting' ? 'NPC is responding…' : 'Ending session…'}
          </div>
        )}
      </div>

      {/* State variables panel */}
      <details open>
        <summary
          style={{ cursor: 'pointer', fontSize: '0.8rem', color: '#71717a', userSelect: 'none' }}
        >
          NPC state variables
        </summary>
        <div
          data-testid="state-vars"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem',
            marginTop: '0.5rem',
            padding: '0.5rem',
            borderRadius: 6,
            border: '1px solid #27272a',
          }}
        >
          {Object.entries(stateVars).map(([key, value]) => (
            <div
              key={key}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                minWidth: 80,
                padding: '0.4rem 0.5rem',
                borderRadius: 4,
                background: '#18181b',
                fontSize: '0.8rem',
              }}
            >
              <span style={{ color: '#a1a1aa', marginBottom: 2 }}>{key}</span>
              <span style={{ color: '#f4f4f5', fontWeight: 600 }}>{value}</span>
              <div
                style={{
                  width: '100%',
                  height: 4,
                  borderRadius: 2,
                  background: '#27272a',
                  marginTop: 4,
                }}
              >
                <div
                  style={{
                    width: `${value}%`,
                    height: '100%',
                    borderRadius: 2,
                    background: value >= 50 ? '#22c55e' : '#f97316',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </details>

      {allEventFlags.length > 0 && (
        <div
          style={{
            padding: '0.5rem 0.75rem',
            borderRadius: 6,
            border: '1px solid #451a03',
            background: '#1c0a00',
            fontSize: '0.8rem',
            color: '#fbbf24',
          }}
        >
          Event flags: {allEventFlags.join(', ')}
        </div>
      )}

      {devMode && <DebugDrawer entries={debugEntries} />}

      {/* Input / end section */}
      {isEnded ? (
        <div
          style={{
            padding: '1rem',
            borderRadius: 8,
            border: '1px solid #27272a',
            textAlign: 'center',
          }}
        >
          <p style={{ margin: '0 0 0.75rem', color: '#a1a1aa' }}>
            Session ended.{endingType ? ` Outcome: ${endingType.replace(/_/g, ' ')}.` : ''}
          </p>
          <button
            onClick={() => navigate(`/debrief/${sessionId}`)}
            style={{
              padding: '0.5rem 1.5rem',
              borderRadius: 6,
              border: 'none',
              background: '#4f46e5',
              color: '#fff',
              fontWeight: 600,
              cursor: 'pointer',
              marginRight: '0.5rem',
            }}
          >
            Generate debrief
          </button>
          <button
            onClick={() => navigate('/library')}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 6,
              border: '1px solid #52525b',
              background: 'transparent',
              color: '#a1a1aa',
              cursor: 'pointer',
            }}
          >
            Back to library
          </button>
        </div>
      ) : phase === 'error' ? (
        <div style={{ textAlign: 'center' }}>
          <button
            onClick={() => navigate('/library')}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 6,
              border: '1px solid #52525b',
              background: 'transparent',
              color: '#a1a1aa',
              cursor: 'pointer',
            }}
          >
            Back to library
          </button>
        </div>
      ) : (
        <VoiceInput
          onSubmit={(text) => void handleSubmit(text)}
          disabled={!isIdle}
          language={language}
        />
      )}
    </div>
  )
}
