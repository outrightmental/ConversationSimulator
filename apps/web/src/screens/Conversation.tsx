// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import type { InputMode, ScenarioInfo, TurnResponse, WsEvent } from '@convsim/shared'
import VoiceInput, { type SttReviewMeta } from '../components/VoiceInput'
import DebugDrawer, { type DebugTurnEntry } from '../components/DebugDrawer'
import PerformanceWarningBanner from '../components/PerformanceWarning'
import { useLatencyMetrics } from '../hooks/useLatencyMetrics'
import { isDevModeEnabled } from '../privacyPrefs'
import { getVoiceTimingPrefs } from '../components/VoiceSettingsPanel'
import type { ApiError } from '../api/errors'
import type { ApiResult } from '../api/client'
import { ApiErrorView } from '../components/ApiErrorView'
import { useIsDemo } from '../edition'

// How long a wait is allowed to look normal before the UI says something.
const SLOW_RESPONSE_MS = 5_000
// Second stage: past this point a static "taking longer than usual" line reads
// as a frozen app, so the notice starts reporting the elapsed time instead.
const VERY_SLOW_RESPONSE_MS = 30_000
// The elapsed time is read out on this coarser grid. The visible clock ticks
// every second, but a polite live region re-announces on every text change, and
// 270 announcements over a five-minute turn drowns out everything else — so the
// screen-reader copy only changes once per interval.
const ELAPSED_ANNOUNCE_INTERVAL_MS = 30_000
// When to stop trusting the in-flight request and start asking convsim-core what
// it actually recorded. It is NOT a latency budget: a local model on CPU-only
// hardware spends real minutes on one turn — the Windows machine in issue #489
// measured ~24 s of prompt eval plus ~6.5 tokens/s of generation, so a single
// 250-token reply took 62 s and tripped the old 60 s deadline, cancelling a turn
// convsim-core had already committed.
const TURN_TIMEOUT_MS = 300_000
// Past that point the turn may still be legitimately in flight, so the deadline
// is a cue to start reconciling rather than a verdict. The core allows the engine
// CONVSIM_LLAMA_CPP_CHAT_TIMEOUT (180 s) of silence *and then* a full 1024-token
// reply, so its own worst case runs well past five minutes — and prompt eval
// grows with the transcript, so the issue #489 machine would reach it late in a
// long conversation (a ~12 k-token prompt is ~140 s of eval at its measured
// 87 tok/s, plus ~158 s of generation). Keep asking the server on this grid so a
// reply that lands late is adopted within a few seconds of existing.
const TURN_RECONCILE_INTERVAL_MS = 15_000
// Absolute ceiling, so a wedged connection can never pin the UI in "submitting"
// forever. Sized above anything the core itself permits (180 s of silence plus a
// 1024-token reply at ~3 tokens/s is ~8.5 min), so giving up here really does
// mean the request, not the model, is stuck.
const TURN_ABANDON_MS = 600_000

const BASELINE_STATE_VARS: Record<string, number> = {
  trust: 50,
  patience: 75,
  pressure: 25,
  rapport: 50,
  openness: 50,
  objective_progress: 0,
}

type TurnEntry = {
  id: number
  role: 'npc_opening' | 'npc' | 'player'
  content: string
  emotion?: string
  eventFlags?: string[]
  turnNum: number
}

type Phase = 'starting' | 'active' | 'submitting' | 'ending' | 'ended' | 'error'

type Banner = { id: number; kind: 'event' | 'safety'; text: string }

function NpcAvatar() {
  return (
    <div
      style={{
        width: 52,
        height: 52,
        borderRadius: '50%',
        background: '#27272a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        border: '2px solid #3f3f46',
      }}
      aria-hidden="true"
    >
      <svg width="30" height="30" viewBox="0 0 30 30" fill="none">
        <circle cx="15" cy="10" r="6" fill="#71717a" />
        <path d="M2 28c0-7.2 5.8-13 13-13s13 5.8 13 13" fill="#71717a" />
      </svg>
    </div>
  )
}

const srOnly: CSSProperties = {
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

/** "45s" / "2m 05s" — a wait long enough to show is long enough to read. */
function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

function npcStatusLabel(sessionState: string, phase: Phase): string {
  if (phase === 'submitting') return 'Thinking…'
  if (sessionState === 'NpcThinking') return 'Thinking…'
  if (sessionState === 'NpcSpeaking') return 'Speaking…'
  if (sessionState === 'ScenarioEvent') return 'Event in progress…'
  if (sessionState === 'PlayerTurnListening') return 'Listening'
  return ''
}

export default function Conversation() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  // Demo edition (issue #495): there is no library to go back to.
  const isDemo = useIsDemo()
  const { state } = useLocation()
  const routeState = state as {
    language?: string
    show_state_meters?: boolean
    scenario_id?: string
    input_mode?: InputMode
    tts_enabled?: boolean
  } | null

  const language = routeState?.language
  const showStateMeters = routeState?.show_state_meters ?? true
  const scenarioIdFromRoute = routeState?.scenario_id
  const inputMode = routeState?.input_mode ?? 'text-only'
  const ttsEnabled = routeState?.tts_enabled ?? false

  // Voice timing preferences (issue #308) — read once at mount from localStorage.
  const voiceTimingPrefs = getVoiceTimingPrefs()

  const [phase, setPhase] = useState<Phase>('starting')
  const [sessionState, setSessionState] = useState('NotStarted')
  const [endingType, setEndingType] = useState<string | null>(null)
  const [turns, setTurns] = useState<TurnEntry[]>([])
  // Populated from the server's visible_state snapshots (scenario-specific).
  const [stateVars, setStateVars] = useState<Record<string, number>>({})
  const [allEventFlags, setAllEventFlags] = useState<string[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [devMode] = useState(() => isDevModeEnabled())
  const [debugEntries, setDebugEntries] = useState<DebugTurnEntry[]>([])
  const [scenario, setScenario] = useState<ScenarioInfo | null>(null)
  const [npcEmotion, setNpcEmotion] = useState<string | null>(null)
  const [streamingText, setStreamingText] = useState('')
  const [banners, setBanners] = useState<Banner[]>([])
  // Milliseconds the current turn has been waiting on the NPC. Drives both
  // stages of the slow-response notice, so one clock answers "how long has the
  // player been staring at 'NPC is responding…'".
  const [waitElapsedMs, setWaitElapsedMs] = useState(0)

  const { snapshot: latencySnapshot, mark, recordInterval, recordValue, warnings: perfWarnings } = useLatencyMetrics()
  const firstTokenMarkedRef = useRef(false)
  const turnTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Ticks once a second while a turn is in flight to advance waitElapsedMs.
  const waitClockRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const waitStartedAtRef = useRef(0)
  // Spaces out the post-deadline transcript re-checks.
  const reconcileTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // False once the screen unmounts, so the reconcile loop stops touching state.
  const mountedRef = useRef(true)

  // TTS audio queue — plays synthesized sentence chunks in order.
  const ttsQueueRef = useRef<string[]>([])
  const ttsPlayingRef = useRef<HTMLAudioElement | null>(null)
  // Holds a setTimeout ID while the NPC thinking-pause delay is active.
  const ttsHoldTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // True when the player started recording while TTS was playing (barge-in).
  const bargedInRef = useRef(false)

  const transcriptRef = useRef<HTMLDivElement>(null)
  const turnUidRef = useRef(0)
  const turnNumRef = useRef(0)
  const bannerUidRef = useRef(0)
  const streamingRef = useRef('')
  const phaseRef = useRef<Phase>('starting')
  const npcTurnCommittedRef = useRef(false)
  const pendingRawSttRef = useRef<SttReviewMeta | null>(null)
  phaseRef.current = phase

  // Clean up any pending timers and TTS audio when the component unmounts.
  useEffect(() => {
    return () => {
      mountedRef.current = false
      if (turnTimeoutRef.current) clearTimeout(turnTimeoutRef.current)
      if (waitClockRef.current) clearInterval(waitClockRef.current)
      if (reconcileTimerRef.current) clearTimeout(reconcileTimerRef.current)
      if (ttsHoldTimerRef.current) clearTimeout(ttsHoldTimerRef.current)
      if (ttsPlayingRef.current) {
        ttsPlayingRef.current.pause()
        ttsPlayingRef.current = null
      }
      ttsQueueRef.current = []
    }
  }, [])

  function _startWaitClock() {
    if (waitClockRef.current) clearInterval(waitClockRef.current)
    waitStartedAtRef.current = Date.now()
    setWaitElapsedMs(0)
    waitClockRef.current = setInterval(
      () => setWaitElapsedMs(Date.now() - waitStartedAtRef.current),
      1_000,
    )
  }

  function _stopWaitClock() {
    if (waitClockRef.current) {
      clearInterval(waitClockRef.current)
      waitClockRef.current = null
    }
    setWaitElapsedMs(0)
  }

  /** Replace the transcript with the server's copy, renumbering from the top. */
  function _hydrateTurnsFromServer(
    serverTurns: Array<{ role: TurnEntry['role']; content: string; emotion?: string | null }>,
  ) {
    turnNumRef.current = 0
    setTurns(
      serverTurns.map((t) => ({
        id: ++turnUidRef.current,
        role: t.role,
        content: t.content,
        emotion: t.emotion ?? undefined,
        turnNum: ++turnNumRef.current,
      })),
    )
  }

  function _playNextTtsChunk() {
    const url = ttsQueueRef.current.shift()
    if (!url) {
      ttsPlayingRef.current = null
      return
    }
    const audio = new Audio(url)
    ttsPlayingRef.current = audio
    // A failed load can fire both the error event and reject the play() promise;
    // guard so this element advances the queue at most once — otherwise two
    // chunks start playing at the same time and one is skipped.
    let advanced = false
    const advance = () => {
      if (advanced) return
      advanced = true
      _playNextTtsChunk()
    }
    audio.onended = advance
    audio.onerror = advance
    audio.play().catch(() => {
      // Autoplay blocked or resource unavailable — skip to next chunk.
      advance()
    })
  }

  function _enqueueTtsChunk(cachePath: string, thinkingPauseMs?: number) {
    // Only play TTS audio when the session was started with TTS enabled.
    // The text transcript remains authoritative regardless of this flag.
    if (!ttsEnabled) return
    const filename = cachePath.replace(/\\/g, '/').split('/').pop()
    if (!filename) return
    const url = `/api/tts/audio/${filename}`
    ttsQueueRef.current.push(url)
    if (ttsPlayingRef.current === null && ttsHoldTimerRef.current === null) {
      // Apply the NPC thinking pause before starting the first chunk, but only
      // when the player has left the "NPC thinking pause" setting enabled. The
      // backend always sends thinking_pause_ms (its own toggle is not wired
      // through session setup), so this client-side gate is what actually
      // honors the Voice settings toggle.
      const pause =
        voiceTimingPrefs.thinkingPauseEnabled && thinkingPauseMs && thinkingPauseMs > 0
          ? thinkingPauseMs
          : 0
      if (pause > 0) {
        ttsHoldTimerRef.current = setTimeout(() => {
          ttsHoldTimerRef.current = null
          _playNextTtsChunk()
        }, pause)
      } else {
        _playNextTtsChunk()
      }
    }
  }

  function _fadeTtsOut(durationMs: number, onDone: () => void) {
    const audio = ttsPlayingRef.current
    if (!audio) { onDone(); return }
    const startVol = audio.volume
    const steps = 10
    const stepMs = durationMs / steps
    let step = 0
    const interval = setInterval(() => {
      step++
      if (!ttsPlayingRef.current || step >= steps) {
        clearInterval(interval)
        if (ttsPlayingRef.current) {
          ttsPlayingRef.current.pause()
          ttsPlayingRef.current = null
        }
        onDone()
        return
      }
      audio.volume = Math.max(0, startVol * (1 - step / steps))
    }, stepMs)
  }

  function _stopTtsPlayback() {
    if (ttsHoldTimerRef.current) {
      clearTimeout(ttsHoldTimerRef.current)
      ttsHoldTimerRef.current = null
    }
    ttsQueueRef.current = []
    if (ttsPlayingRef.current) {
      ttsPlayingRef.current.pause()
      ttsPlayingRef.current = null
    }
  }

  function handleBargeIn() {
    if (!ttsEnabled || !voiceTimingPrefs.bargeInEnabled) return
    const isTtsActive = ttsPlayingRef.current !== null || ttsHoldTimerRef.current !== null
    // Reset the flag on every recording start so it always reflects whether THIS
    // recording began during NPC playback. Otherwise a barge-in the player then
    // discards or re-records in transcript review would leave the flag set and be
    // mis-attributed to a later, non-interrupting turn — over-counting
    // interruption_count in the debrief.
    bargedInRef.current = isTtsActive
    if (!isTtsActive) return
    _fadeTtsOut(180, () => {
      ttsQueueRef.current = []
    })
  }

  // Fetch scenario for NPC panel and scene card — best effort
  useEffect(() => {
    if (!scenarioIdFromRoute) return
    let cancelled = false
    api.getScenario(scenarioIdFromRoute).then(
      (r) => { if (!cancelled && r.ok) setScenario(r.data) },
    )
    return () => { cancelled = true }
  }, [scenarioIdFromRoute])

  // Start session
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    mark('session_start')
    void (async () => {
      const startResult = await api.startSession(sessionId)
      if (cancelled) return
      if (!startResult.ok) {
        // A 409 / INVALID_TRANSITION means the session was already started
        // (dev-mode double mount, or a page reload). That is fully
        // recoverable: rehydrate the transcript (opening + any prior turns)
        // and continue silently. Showing an error card here put a scary red
        // "Request failed" banner over a perfectly working conversation and
        // dropped Alex's opening message on the floor.
        const e = startResult.error
        const alreadyStarted =
          e.status === 409 || e.message.includes('INVALID_TRANSITION')
        if (alreadyStarted) {
          const tr = await api.getSessionTranscript(sessionId)
          if (cancelled) return
          if (tr.ok && tr.data.turns.length > 0) {
            _hydrateTurnsFromServer(tr.data.turns)
          }
          const lastState = tr.ok
            ? tr.data.turns[tr.data.turns.length - 1]?.flow_state_after
            : null
          setSessionState(lastState ?? 'PlayerTurnListening')
          setPhase('active')
        } else {
          setError(e)
          setPhase('error')
        }
        return
      }
      const startData = startResult.data
      recordInterval('session_start_ms', 'session_start')
      const opening = startData.events.find((e) => e.event_type === 'npc_opening')
      if (opening) {
        const uid = ++turnUidRef.current
        setTurns([
          {
            id: uid,
            role: 'npc_opening',
            content: opening.payload['content'] as string,
            emotion: opening.payload['emotion'] as string | undefined,
            turnNum: ++turnNumRef.current,
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
      setSessionState(startData.state)
      const openingVisible = opening?.payload['visible_state']
      if (openingVisible && typeof openingVisible === 'object') {
        setStateVars({ ...(openingVisible as Record<string, number>) })
      }
      setPhase('active')
    })()

    return () => {
      cancelled = true
    }
  }, [sessionId, devMode, mark, recordInterval])

  // WebSocket connection — best effort; REST fallback continues to work
  useEffect(() => {
    if (!sessionId) return

    let conn: ReturnType<typeof api.connectSession> | null = null
    try {
      conn = api.connectSession(sessionId, (event: WsEvent) => {
        switch (event.type) {
          case 'session.state':
            setSessionState(event.payload.state)
            if (event.payload.state_vars) {
              setStateVars((prev) => ({ ...prev, ...event.payload.state_vars! }))
            }
            break
          case 'npc.token':
            if (!firstTokenMarkedRef.current) {
              firstTokenMarkedRef.current = true
              recordInterval('first_token_ms', 'turn_submit')
            }
            streamingRef.current += event.payload.text
            setStreamingText(streamingRef.current)
            break
          case 'npc.final':
            setNpcEmotion(event.payload.emotion)
            streamingRef.current = ''
            setStreamingText('')
            // During an active turn submission, commit the NPC response immediately
            // so the transcript is populated as soon as streaming finishes rather
            // than waiting for the REST round-trip to complete.
            if (phaseRef.current === 'submitting' && !npcTurnCommittedRef.current) {
              npcTurnCommittedRef.current = true
              const { content, emotion: npcEmotion, state_delta, event_flags } = event.payload
              const flags = event_flags ?? []
              setTurns((prev) => [
                ...prev,
                {
                  id: ++turnUidRef.current,
                  role: 'npc',
                  content,
                  emotion: npcEmotion !== 'neutral' ? npcEmotion : undefined,
                  eventFlags: flags.length > 0 ? flags : undefined,
                  turnNum: ++turnNumRef.current,
                },
              ])
              if (Object.keys(state_delta ?? {}).length > 0) {
                setStateVars((prev) => {
                  const next = { ...prev }
                  for (const [k, d] of Object.entries(state_delta)) {
                    if (k in next) next[k] = Math.max(0, Math.min(100, next[k] + d))
                  }
                  return next
                })
              }
              if (flags.length > 0) {
                setAllEventFlags((prev) => [...prev, ...flags])
              }
            }
            break
          case 'scenario.event':
            if (event.payload.flags.length > 0) {
              setBanners((prev) => [
                ...prev,
                {
                  id: ++bannerUidRef.current,
                  kind: 'event',
                  text: event.payload.flags.join(' · '),
                },
              ])
            }
            break
          case 'safety.redirect':
            setBanners((prev) => [
              ...prev,
              { id: ++bannerUidRef.current, kind: 'safety', text: event.payload.reason },
            ])
            break
          case 'tts.audio_chunk':
            if (event.payload.cache_path) {
              _enqueueTtsChunk(
                event.payload.cache_path,
                event.payload.thinking_pause_ms,
              )
            }
            break
          case 'stt.partial':
          case 'stt.final':
            // STT streaming events — handled by VoiceInput via REST; these WS events
            // are emitted by future streaming STT backends and are safe to ignore here.
            break
        }
      })
    } catch {
      // WS unavailable — REST-only mode
    }

    return () => {
      conn?.close()
    }
    // _enqueueTtsChunk is a ref-only helper; the WS connection must not be
    // torn down and re-established on every render, so it is deliberately
    // excluded from the dependency array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, recordInterval])

  // Auto-scroll transcript
  useEffect(() => {
    const el = transcriptRef.current
    if (el && typeof el.scrollTo === 'function') {
      el.scrollTo(0, el.scrollHeight)
    }
  }, [turns, streamingText])

  /**
   * Reconcile the transcript with convsim-core after a turn deadline expires.
   *
   * The core commits the player turn and the NPC reply in one transaction
   * before it answers the request, so a reply that lands just after the
   * deadline is a reply the session already holds. Reporting a timeout there
   * both hid a finished turn and left the view one turn behind the session the
   * core was actually running — the bug in issue #489, where a 62 s turn missed
   * a 60 s deadline by two seconds.
   *
   * State meters are not refreshed here (the transcript carries no variable
   * snapshot); the next turn's `visible_state` is authoritative and restores
   * them.
   *
   * Returns true when the server's copy was adopted, meaning the turn is
   * complete and the caller must not report an error.
   */
  async function _adoptServerTurnAfterDeadline(): Promise<boolean> {
    const tr = await api.getSessionTranscript(sessionId!)
    // Nothing to compare against when the fetch failed, or when the session was
    // started with transcript saving off — that makes this endpoint return no
    // turns, so the deadline has to stand.
    if (!tr.ok) return false
    const serverTurns = tr.data.turns
    const last = serverTurns[serverTurns.length - 1]
    // turnNumRef counts every row this view holds, the optimistic player turn
    // included, so the reply only landed if the server is ahead of that.
    if (!last || last.role !== 'npc' || serverTurns.length <= turnNumRef.current) return false

    _hydrateTurnsFromServer(serverTurns)
    setNpcEmotion(last.emotion ?? null)
    npcTurnCommittedRef.current = true
    streamingRef.current = ''
    setStreamingText('')
    recordInterval('full_response_ms', 'turn_submit')
    const flowState = last.flow_state_after ?? 'PlayerTurnListening'
    setSessionState(flowState)
    setPhase(flowState === 'Ended' ? 'ended' : 'active')
    return true
  }

  /**
   * Keep reconciling past the deadline until the turn lands or we give up.
   *
   * The deadline is not evidence that the turn failed — the core's own budget
   * runs past it (see TURN_RECONCILE_INTERVAL_MS), and prompt eval grows with
   * the transcript, so the very machine in issue #489 would cross five minutes
   * late in a long conversation. Failing there would reintroduce the reported
   * bug at a longer timescale: a turn the session holds, reported as lost and
   * rolled back. So the deadline only starts the polling; a verdict waits for
   * TURN_ABANDON_MS, by which point nothing the core permits can still be
   * running and the request itself must be wedged.
   *
   * Returns true when the server's copy was adopted.
   */
  async function _awaitServerTurnAfterDeadline(): Promise<boolean> {
    while (mountedRef.current) {
      if (await _adoptServerTurnAfterDeadline()) return true
      if (!mountedRef.current) return false
      if (Date.now() - waitStartedAtRef.current >= TURN_ABANDON_MS) return false
      await new Promise<void>((resolve) => {
        reconcileTimerRef.current = setTimeout(resolve, TURN_RECONCILE_INTERVAL_MS)
      })
    }
    return false
  }

  async function handleSubmit(text: string) {
    if (!text || phase !== 'active') return

    // Capture any pending STT metadata before resetting it (set synchronously by onRawStt).
    const rawSttMeta = pendingRawSttRef.current
    pendingRawSttRef.current = null

    // Add the player turn immediately so it appears before the NPC response
    // regardless of whether the NPC turn is committed by WebSocket or REST.
    const playerTurnId = ++turnUidRef.current
    const playerTurnNum = ++turnNumRef.current
    setTurns((prev) => [
      ...prev,
      {
        id: playerTurnId,
        role: 'player',
        content: text,
        turnNum: playerTurnNum,
      },
    ])

    if (devMode) {
      const playerDebugEntry: DebugTurnEntry = {
        turnId: playerTurnId,
        role: 'player',
        rawPayload: { content: text },
        ...(rawSttMeta && rawSttMeta.rawTranscript !== rawSttMeta.finalTranscript
          ? { rawStt: rawSttMeta.rawTranscript }
          : {}),
      }
      setDebugEntries((prev) => [...prev, playerDebugEntry])
    }

    // Capture barge-in state and reset for next turn.
    const didBargeIn = bargedInRef.current
    bargedInRef.current = false

    _stopTtsPlayback()
    setPhase('submitting')
    setError(null)
    streamingRef.current = ''
    setStreamingText('')
    npcTurnCommittedRef.current = false
    firstTokenMarkedRef.current = false

    mark('turn_submit')

    // Drives the staged "this is taking a while" notice while the turn is out.
    _startWaitClock()

    // Wrap the API call with a deadline so the UI is never stuck indefinitely on a
    // request that will never answer. Expiry hands over to the reconcile loop
    // below rather than failing the turn outright.
    let deadlineExpired = false
    const result = await Promise.race([
      api.submitTurn(sessionId!, text, didBargeIn),
      new Promise<ApiResult<TurnResponse>>((resolve) => {
        turnTimeoutRef.current = setTimeout(() => {
          deadlineExpired = true
          resolve({ ok: false, error: { kind: 'timeout', message: 'The AI took too long to respond.' } })
        }, TURN_TIMEOUT_MS)
      }),
    ])
    if (turnTimeoutRef.current) clearTimeout(turnTimeoutRef.current)

    if (!result.ok) {
      // The deadline expiring says nothing about whether the turn failed:
      // convsim-core commits the player turn and the NPC reply in one
      // transaction *before* it answers the request, so ask the server what it
      // actually has before declaring the turn lost (issue #489). The wait clock
      // keeps running through this, so the player still sees a live "still
      // waiting" notice rather than a screen that goes quiet.
      const adopted = deadlineExpired && (await _awaitServerTurnAfterDeadline())
      _stopWaitClock()
      if (adopted) return
      setError(result.error)
      // Discard any partial streamed tokens so a failed turn doesn't leave a
      // phantom "Responding…" bubble alongside the error.
      streamingRef.current = ''
      setStreamingText('')
      // Roll back the optimistic player turn if the NPC never responded, so a
      // retry doesn't leave an orphaned failed message or skip a turn number.
      if (!npcTurnCommittedRef.current) {
        setTurns((prev) => prev.filter((t) => t.id !== playerTurnId))
        turnNumRef.current -= 1
      }
      setPhase('active')
      return
    }
    _stopWaitClock()
    const turnData = result.data

    if (!firstTokenMarkedRef.current) {
      recordInterval('first_token_ms', 'turn_submit')
      firstTokenMarkedRef.current = true
    }
    recordInterval('full_response_ms', 'turn_submit')

    const npcEvent = turnData.events.find((e) => e.event_type === 'npc_turn')

    // Only commit the NPC turn from REST if the WebSocket npc.final handler
    // has not already done so (to avoid duplicate transcript entries).
    if (npcEvent && !npcTurnCommittedRef.current) {
      npcTurnCommittedRef.current = true
      const payload = npcEvent.payload
      const delta = (payload['state_delta'] ?? {}) as Record<string, number>
      const flags = (payload['event_flags'] ?? []) as string[]
      const emotion = payload['emotion'] as string | undefined
      setNpcEmotion(emotion ?? null)

      const uid = ++turnUidRef.current
      setTurns((prev) => [
        ...prev,
        {
          id: uid,
          role: 'npc',
          content: payload['content'] as string,
          emotion: emotion !== 'neutral' ? emotion : undefined,
          eventFlags: flags.length > 0 ? flags : undefined,
          turnNum: ++turnNumRef.current,
        },
      ])

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

      const visibleState = payload?.['visible_state']
      if (visibleState && typeof visibleState === 'object' && Object.keys(visibleState).length > 0) {
        // Authoritative snapshot of the scenario's visible variables.
        setStateVars({ ...(visibleState as Record<string, number>) })
      } else if (Object.keys(delta).length > 0) {
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

    setSessionState(turnData.state)
    streamingRef.current = ''
    setStreamingText('')

    if (turnData.state === 'Ended') {
      const npcPayload = npcEvent?.payload
      setEndingType((npcPayload?.['ending_type'] as string | null | undefined) ?? null)
      setPhase('ended')
    } else {
      setPhase('active')
    }
  }

  async function handleEndSession() {
    if (phase !== 'active') return
    setPhase('ending')
    setError(null)
    const endResult = await api.endSession(sessionId!)
    if (endResult.ok) {
      setSessionState(endResult.data.state)
      setEndingType(endResult.data.ending_type)
      setPhase('ended')
    } else {
      // Surface the failure and return to the active conversation rather than
      // leaving the UI stuck in the 'ending' (busy) phase.
      setError(endResult.error)
      setPhase('active')
    }
  }

  function dismissBanner(id: number) {
    setBanners((prev) => prev.filter((b) => b.id !== id))
  }

  const isIdle = phase === 'active'
  const isBusy = phase === 'submitting' || phase === 'ending'
  const isEnded = phase === 'ended'
  const isSlowResponse = phase === 'submitting' && waitElapsedMs >= SLOW_RESPONSE_MS
  const isVerySlowResponse = phase === 'submitting' && waitElapsedMs >= VERY_SLOW_RESPONSE_MS
  const announcedElapsedMs =
    Math.floor(waitElapsedMs / ELAPSED_ANNOUNCE_INTERVAL_MS) * ELAPSED_ANNOUNCE_INTERVAL_MS
  const npcStatus = npcStatusLabel(sessionState, phase)

  return (
    <div
      data-testid="conversation-page"
      style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: 760 }}
    >
      {/* Header */}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <h1 style={{ margin: 0 }}>Conversation</h1>
          </div>
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

      {/* NPC panel + scene card */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div
          data-testid="npc-panel"
          style={{
            display: 'flex',
            gap: '0.75rem',
            alignItems: 'center',
            padding: '0.75rem',
            borderRadius: 8,
            border: '1px solid #27272a',
            background: '#18181b',
            minWidth: 180,
          }}
        >
          <NpcAvatar />
          <div>
            <div style={{ fontWeight: 600, color: '#e4e4e7', fontSize: '0.95rem' }}>NPC</div>
            {npcEmotion && npcEmotion !== 'neutral' && (
              <div
                data-testid="npc-emotion"
                style={{
                  fontSize: '0.8rem',
                  color: '#6ee7b7',
                  textTransform: 'capitalize',
                  marginTop: 2,
                }}
              >
                {npcEmotion}
              </div>
            )}
            {/* Always mounted so screen readers announce status transitions;
                a conditionally-rendered live region is re-inserted rather than
                updated and often goes unannounced. */}
            <div
              data-testid="npc-status"
              aria-live="polite"
              style={{
                fontSize: '0.75rem',
                color: '#71717a',
                marginTop: npcStatus ? 2 : 0,
              }}
            >
              {npcStatus}
            </div>
          </div>
        </div>

        {scenario && (
          <div
            data-testid="scene-card"
            style={{
              flex: 1,
              padding: '0.75rem',
              borderRadius: 8,
              border: '1px solid #27272a',
              background: '#18181b',
              minWidth: 160,
            }}
          >
            <div style={{ fontWeight: 600, color: '#e4e4e7', fontSize: '0.9rem', marginBottom: 4 }}>
              {scenario.title}
            </div>
            <div style={{ fontSize: '0.8rem', color: '#71717a', lineHeight: 1.4 }}>
              {scenario.summary}
            </div>
          </div>
        )}
      </div>

      {/* Error alert */}
      {error && <ApiErrorView error={error} context="Conversation" />}

      {/* Performance warnings — shown when latency thresholds are exceeded */}
      <PerformanceWarningBanner warnings={perfWarnings} />

      {/* Event and safety banners */}
      {banners.map((banner) => (
        <div
          key={banner.id}
          role={banner.kind === 'safety' ? 'alert' : 'status'}
          data-testid={`banner-${banner.kind}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '0.6rem 1rem',
            borderRadius: 6,
            border: `1px solid ${banner.kind === 'safety' ? '#7f1d1d' : '#451a03'}`,
            background: banner.kind === 'safety' ? '#450a0a' : '#1c0a00',
            color: banner.kind === 'safety' ? '#fca5a5' : '#fbbf24',
            fontSize: '0.85rem',
          }}
        >
          <span>
            {banner.kind === 'safety' ? 'Safety redirect: ' : 'Scenario event: '}
            {banner.text}
          </span>
          <button
            onClick={() => dismissBanner(banner.id)}
            aria-label="Dismiss"
            style={{
              background: 'none',
              border: 'none',
              color: 'inherit',
              cursor: 'pointer',
              padding: '0 0 0 0.75rem',
              opacity: 0.7,
              fontSize: '1rem',
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
      ))}

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
              <span>Turn {turn.turnNum}</span>
              {' · '}
              <span>{turn.role === 'player' ? 'You' : 'NPC'}</span>
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

        {/* Live streaming NPC response */}
        {streamingText && (
          <div data-testid="streaming-turn">
            <div
              style={{
                fontSize: '0.7rem',
                color: '#6ee7b7',
                marginBottom: 2,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              NPC · Responding…
            </div>
            <div
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: 6,
                background: '#052e16',
                color: '#f4f4f5',
                fontSize: '0.9rem',
                lineHeight: 1.5,
                opacity: 0.85,
              }}
            >
              {streamingText}
            </div>
          </div>
        )}

        {isBusy && !streamingText && (
          <div
            aria-live="polite"
            aria-busy="true"
            style={{ color: '#71717a', fontSize: '0.875rem', fontStyle: 'italic' }}
          >
            {phase === 'submitting' ? 'NPC is responding…' : 'Ending session…'}
          </div>
        )}

        {isSlowResponse && phase === 'submitting' && (
          <div
            data-testid="slow-response-indicator"
            role="status"
            aria-live="polite"
            style={{
              padding: '0.5rem 0.75rem',
              borderRadius: 6,
              border: '1px solid #713f12',
              background: '#1c1000',
              color: '#fde68a',
              fontSize: '0.8rem',
            }}
          >
            {isDemo
              ? 'NPC is taking longer than usual. The model may be slow on this hardware; closing other apps usually helps.'
              : 'NPC is taking longer than usual. The model may be slow on this hardware. You can adjust settings or try a smaller model.'}
            {isVerySlowResponse && (
              // Past half a minute a static line reads as a hung app. Naming the
              // elapsed time shows the app is still waiting on the model rather
              // than stuck, and that the turn has not been thrown away.
              // Hidden from assistive tech: this ticks every second, and the
              // enclosing polite live region would re-announce each tick. The
              // sr-only sibling below carries the same news on a 30 s grid.
              <div
                data-testid="slow-response-elapsed"
                aria-hidden="true"
                style={{ marginTop: 4, color: '#fbbf24' }}
              >
                Still waiting — {formatElapsed(waitElapsedMs)} so far. The reply is
                not lost; slow hardware can take a few minutes per turn.
              </div>
            )}
          </div>
        )}

        {isVerySlowResponse && (
          <span data-testid="slow-response-elapsed-announcement" role="status" aria-live="polite" style={srOnly}>
            Still waiting on the NPC — {formatElapsed(announcedElapsedMs)} so far. The reply is not lost.
          </span>
        )}
      </div>

      {/* State meters — shown only when enabled in setup and hydrated */}
      {showStateMeters && Object.keys(stateVars).length > 0 && (
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
                  role="meter"
                  aria-label={`${key.replace(/_/g, ' ')}: ${value} out of 100`}
                  aria-valuenow={value}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  style={{
                    width: '100%',
                    height: 4,
                    borderRadius: 2,
                    background: '#27272a',
                    marginTop: 4,
                  }}
                >
                  <div
                    aria-hidden="true"
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
      )}

      {allEventFlags.length > 0 && (
        <div
          role="status"
          aria-live="polite"
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

      {devMode && <DebugDrawer entries={debugEntries} latencySnapshot={latencySnapshot} />}

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
            Session ended.
            {endingType ? ` Outcome: ${endingType.replace(/_/g, ' ')}.` : ''}
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
            onClick={() => navigate(isDemo ? '/' : '/library')}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 6,
              border: '1px solid #52525b',
              background: 'transparent',
              color: '#a1a1aa',
              cursor: 'pointer',
            }}
          >
            {isDemo ? 'Back to home' : 'Back to library'}
          </button>
        </div>
      ) : phase === 'error' ? (
        <div style={{ textAlign: 'center' }}>
          <button
            onClick={() => navigate(isDemo ? '/' : '/library')}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 6,
              border: '1px solid #52525b',
              background: 'transparent',
              color: '#a1a1aa',
              cursor: 'pointer',
            }}
          >
            {isDemo ? 'Back to home' : 'Back to library'}
          </button>
        </div>
      ) : (
        <VoiceInput
          onSubmit={(text) => void handleSubmit(text)}
          onRawStt={devMode ? (meta) => { pendingRawSttRef.current = meta } : undefined}
          onSttLatency={(ms) => recordValue('stt_final_ms', ms)}
          onRecordingStart={handleBargeIn}
          disabled={!isIdle}
          language={language}
          inputMode={inputMode}
          backchannelEnabled={ttsEnabled && voiceTimingPrefs.backchannelEnabled}
        />
      )}

    </div>
  )
}
