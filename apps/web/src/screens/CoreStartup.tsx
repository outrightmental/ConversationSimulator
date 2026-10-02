// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback, useRef } from 'react'
import RuntimeRecoveryCard from '../components/RuntimeRecoveryCard'

// ── Tauri global type (Tauri v2 with withGlobalTauri: true) ──────────────────

interface CoreStatusPayload {
  // 'restarting' is emitted when the Rust shell caught the engine exiting under
  // a running window and is bringing a replacement up (bounded attempts, see
  // supervise_core in apps/desktop/src-tauri/src/lib.rs). It is a non-ready
  // phase: nothing is serving 127.0.0.1:7355 until the replacement binds, so an
  // app left mounted would fail every request with nothing on screen to say
  // why. The app is unmounted and remounted when the replacement reports ready.
  //
  // The remount is also what resumes an in-progress conversation. A session's
  // live state (flow state, state vars, transcript) is in the engine's SQLite
  // database, not its memory, so the replacement reads it back: Conversation's
  // start call gets 409 INVALID_TRANSITION and rehydrates from the transcript.
  phase: 'starting' | 'restarting' | 'ready' | 'error'
  message: string
  error: string | null
  log_dir?: string | null
}

interface TauriGlobal {
  event: {
    listen<T>(
      event: string,
      handler: (e: { payload: T }) => void,
    ): Promise<() => void>
  }
  core?: {
    invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T>
  }
}

declare global {
  interface Window {
    __TAURI__?: TauriGlobal
  }
}

const TROUBLESHOOTING_BASE =
  'https://docs.conversationsimulator.com/start/troubleshooting/'
const ISSUES_URL =
  'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'

type FailureKind =
  | 'edition-conflict'
  | 'already-running'
  | 'port-conflict'
  | 'not-found'
  | 'keeps-stopping'
  | 'crash'

interface ErrorInfo {
  kind: FailureKind
  title: string
  description: string
  anchor: string
}

function classifyError(message: string, error: string | null): ErrorInfo {
  const text = `${message} ${error ?? ''}`.toLowerCase()

  // Checked before the port-conflict branch it is a special case of. The demo
  // and the full app share port 7355 and one data directory, so the shell
  // refuses to attach to the other edition's engine (`foreign_edition_error` in
  // apps/desktop/src-tauri/src/lib.rs) — and the port-conflict card's advice,
  // "close any other applications using port 7355", names the wrong culprit:
  // the other application IS Conversation Simulator, and the player has to
  // close the right window. Falling through to 'crash' was worse still: an
  // engine is running perfectly well, just the wrong one.
  if (/another edition/.test(text)) {
    return {
      kind: 'edition-conflict',
      title: 'Another edition of Conversation Simulator is running',
      description:
        'The demo and the full version share one conversation engine, so they cannot run at the ' +
        'same time. Close the other one, then start this one again.',
      anchor: '#engine-startup-failure',
    }
  }

  // After the edition branch, whose message also says "already running", and
  // before the port-conflict branch. The shell sends this when the engine it
  // spawned could not bind because a convsim-core of the SAME edition already
  // held the port — a second copy of the app launched while this one was still
  // starting (`ALREADY_RUNNING_MESSAGE` in apps/desktop/src-tauri/src/lib.rs).
  // The port-conflict card would tell the player to close whatever program is
  // using port 7355; that program is the engine serving the window they already
  // have, so following the advice would break the launch that worked.
  if (/already running/.test(text)) {
    return {
      kind: 'already-running',
      title: 'Conversation Simulator is already running',
      description:
        'Another window is already using the conversation engine, so this one could not ' +
        'start a second. Switch to that window — you do not need this one.',
      anchor: '#engine-startup-failure',
    }
  }

  if (/eaddrinuse|address already in use|port.*busy|port.*in use|port conflict/.test(text)) {
    return {
      kind: 'port-conflict',
      title: 'Another app is using a required port',
      description:
        'Close any other applications using port 7355, then restart Conversation Simulator.',
      anchor: '#port-conflicts',
    }
  }

  // Checked before the not-found/crash branches: the shell only sends this
  // after the engine started, served, and then died MAX_RESTARTS times in a
  // row (KEEPS_STOPPING_MESSAGE in apps/desktop/src-tauri/src/lib.rs). It used
  // to fall through to 'crash', which heads the card "The conversation engine
  // didn't start" — the one thing that demonstrably did happen.
  if (/keeps stopping/.test(text)) {
    return {
      kind: 'keeps-stopping',
      title: 'The conversation engine keeps stopping',
      description:
        'It started but shut down repeatedly, so the app stopped restarting it. ' +
        'A lighter model often fixes this — your packs, models, and past sessions are safe.',
      anchor: '#engine-startup-failure',
    }
  }

  if (/not found|no such file|executable|binary|cannot locate/.test(text)) {
    return {
      kind: 'not-found',
      title: "The conversation engine couldn't be found",
      description:
        'The app may be installed incorrectly. Try reinstalling from Steam or running setup again.',
      anchor: '#engine-startup-failure',
    }
  }

  return {
    kind: 'crash',
    title: "The conversation engine didn't start",
    description: 'Something went wrong when the app tried to start.',
    anchor: '#engine-startup-failure',
  }
}

// ── CoreStartupGuard ──────────────────────────────────────────────────────────
//
// Renders a startup progress screen in the Tauri desktop shell until convsim-core
// signals that it is ready.  In a browser context (no __TAURI__ global) this is a
// no-op and children are rendered immediately.
//
// isTauri is evaluated inside the render function (not at module load time) so
// that tests can set window.__TAURI__ before rendering without module-cache issues.

export default function CoreStartupGuard({ children }: { children: React.ReactNode }) {
  const isTauri = typeof window !== 'undefined' && '__TAURI__' in window

  const [ready, setReady] = useState(() => !isTauri)
  const [status, setStatus] = useState<CoreStatusPayload | null>(null)
  // Mirrors `status` for the health fast-path below, which resolves on its own
  // schedule and must not promote a phase the shell has already moved past.
  const statusRef = useRef<CoreStatusPayload | null>(null)

  const checkHealth = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('http://127.0.0.1:7355/api/health', {
        signal: AbortSignal.timeout(1500),
      })
      if (!res.ok) return false
      // A 200 is not proof the engine answered. Anything can be holding 7355,
      // which is why the shell's own probe requires the body to look like a
      // convsim-core health response (`probe_core` in
      // apps/desktop/src-tauri/src/lib.rs). Without the same test here this
      // fast-path mounts the app over a stranger's socket for the whole
      // port-conflict grace period, before the shell's error event arrives.
      // `status` is a required field of HealthResponse.
      const body: unknown = await res.json()
      return typeof (body as { status?: unknown } | null)?.status === 'string'
    } catch {
      return false
    }
  }, [])

  useEffect(() => {
    if (!isTauri) return

    const tauri = window.__TAURI__
    if (!tauri) return

    let cancelled = false
    let unlisten: (() => void) | undefined
    // Whether a live `core-status` event has already been handled. Guards the
    // snapshot reconciliation below, which can otherwise deliver an older phase.
    let liveEventSeen = false

    // Readiness tracks the shell's own state machine rather than latching on
    // first success: the engine can stop under a running window, and an app left
    // mounted over a dead port fails every request with nothing on screen to
    // explain why.
    const apply = (payload: CoreStatusPayload) => {
      if (cancelled) return
      statusRef.current = payload
      setStatus(payload)
      setReady(payload.phase === 'ready')
    }

    // Subscribe to live progress events first. The Rust shell starts emitting
    // core-status from setup(), before this webview has loaded, and Tauri does
    // not replay events — so after subscribing we reconcile with the last-known
    // status via get_core_status to recover any event fired before we attached
    // (e.g. a fast failure like a missing binary).
    tauri.event
      .listen<CoreStatusPayload>('core-status', (e) => {
        liveEventSeen = true
        apply(e.payload)
      })
      .then((fn) => {
        if (cancelled) {
          fn()
          return
        }
        unlisten = fn
        tauri.core
          ?.invoke<CoreStatusPayload | null>('get_core_status')
          .then((snapshot) => {
            // Only to recover an event emitted before we subscribed. Once a live
            // event has arrived the snapshot is redundant — and applying it then
            // would move the UI BACKWARDS, because readiness now follows the
            // reported phase: a snapshot read a moment before the shell emitted
            // `ready` would unmount a running app back to "Starting…", and no
            // further event is coming to undo it.
            if (liveEventSeen) return
            if (snapshot) apply(snapshot)
          })
          .catch(() => {})
      })

    // Independent fast-path: if the core is already serving (e.g. started by
    // dev-desktop.sh) pass through immediately without waiting for an event.
    // It races the events above, so it must not overrule a phase the shell has
    // already reported as not-ready — a stale success arriving after a crash or
    // a port conflict would mount the app over an engine that is not there.
    checkHealth().then((healthy) => {
      if (cancelled || !healthy) return
      // Any phase the shell has already reported wins, not just the terminal
      // ones. 'starting' includes "Something is already using port 7355 —
      // checking whether it is the engine…", and the occupant can be the OTHER
      // edition's engine: a convsim-core health body, so this check passes, and
      // mounting on it shows the wrong library (issue #495) until the shell's
      // own probe reaches the same socket and rejects it. The shell is the
      // authority on readiness; this is only a shortcut for beating its first
      // event, so it may act only when there is no event yet.
      const phase = statusRef.current?.phase
      if (phase && phase !== 'ready') return
      setReady(true)
    })

    return () => {
      cancelled = true
      unlisten?.()
    }
  // isTauri is stable for the lifetime of the component (window.__TAURI__ doesn't
  // change at runtime), so it's safe to include in the dep array.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkHealth])

  if (ready) return <>{children}</>

  const isError = status?.phase === 'error'
  const errorInfo = isError ? classifyError(status!.message, status!.error) : null

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: '1.25rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        padding: '2rem',
        color: '#1a1a1a',
        background: '#fafafa',
      }}
    >
      <h1 style={{ fontSize: '1.5rem', fontWeight: 600, margin: 0 }}>
        Conversation Simulator
      </h1>

      {isError && errorInfo ? (
        <div style={{ maxWidth: 540, width: '100%' }}>
          <RuntimeRecoveryCard
            title={errorInfo.title}
            description={errorInfo.description}
            errorDetail={status!.error}
            logPath={status!.log_dir ?? null}
            troubleshootingHref={`${TROUBLESHOOTING_BASE}${errorInfo.anchor}`}
            troubleshootingLabel="Troubleshooting guide"
            primaryAction={{
              label: 'Restart the app',
              onClick: () => window.location.reload(),
            }}
            secondaryAction={
              status!.log_dir
                ? {
                    label: 'Open logs folder',
                    onClick: () => {
                      const logDir = status!.log_dir!
                      void window.__TAURI__?.core?.invoke('plugin:shell|open', { path: logDir })
                    },
                  }
                : undefined
            }
            tertiaryAction={{
              // The in-app support/crash-bundle screen is behind CoreStartupGuard
              // and needs the (currently down) core API, so it is unreachable
              // during a startup failure. Point players at the report-issue flow
              // instead, which works without the core running.
              label: 'Report a problem',
              href: ISSUES_URL,
            }}
          />
        </div>
      ) : (
        <p
          role="status"
          aria-live="polite"
          style={{ color: '#555', fontSize: '0.9375rem', margin: 0 }}
        >
          {status?.message ?? 'Starting Conversation Simulator…'}
        </p>
      )}
    </div>
  )
}
