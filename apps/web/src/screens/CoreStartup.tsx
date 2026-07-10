// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback } from 'react'
import RuntimeRecoveryCard from '../components/RuntimeRecoveryCard'

// ── Tauri global type (Tauri v2 with withGlobalTauri: true) ──────────────────

interface CoreStatusPayload {
  phase: 'starting' | 'ready' | 'error'
  message: string
  error: string | null
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
  'https://github.com/outrightmental/ConversationSimulator/blob/main/docs/troubleshooting.md'
const ISSUES_URL =
  'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'

type FailureKind = 'port-conflict' | 'not-found' | 'crash'

interface ErrorInfo {
  kind: FailureKind
  title: string
  description: string
  anchor: string
}

function classifyError(message: string, error: string | null): ErrorInfo {
  const text = `${message} ${error ?? ''}`.toLowerCase()

  if (/eaddrinuse|address already in use|port.*busy|port.*in use|port conflict/.test(text)) {
    return {
      kind: 'port-conflict',
      title: 'Another app is using a required port',
      description:
        'Close any other applications using port 7355, then restart Conversation Simulator.',
      anchor: '#port-conflicts',
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
    description:
      'Something went wrong when the app tried to start. Check the logs for details.',
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

  const checkHealth = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('http://127.0.0.1:7355/api/health', {
        signal: AbortSignal.timeout(1500),
      })
      return res.ok
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

    const apply = (payload: CoreStatusPayload) => {
      if (cancelled) return
      setStatus(payload)
      if (payload.phase === 'ready') setReady(true)
    }

    // Subscribe to live progress events first. The Rust shell starts emitting
    // core-status from setup(), before this webview has loaded, and Tauri does
    // not replay events — so after subscribing we reconcile with the last-known
    // status via get_core_status to recover any event fired before we attached
    // (e.g. a fast failure like a missing binary).
    tauri.event
      .listen<CoreStatusPayload>('core-status', (e) => apply(e.payload))
      .then((fn) => {
        if (cancelled) {
          fn()
          return
        }
        unlisten = fn
        tauri.core
          ?.invoke<CoreStatusPayload | null>('get_core_status')
          .then((snapshot) => {
            if (snapshot) apply(snapshot)
          })
          .catch(() => {})
      })

    // Independent fast-path: if the core is already serving (e.g. started by
    // dev-desktop.sh) pass through immediately without waiting for an event.
    checkHealth().then((healthy) => {
      if (!cancelled && healthy) setReady(true)
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
            logPath="~/.convsim/logs/app.log"
            troubleshootingHref={`${TROUBLESHOOTING_BASE}${errorInfo.anchor}`}
            troubleshootingLabel="Troubleshooting guide"
            primaryAction={{
              label: 'Restart the app',
              onClick: () => window.location.reload(),
            }}
            secondaryAction={{
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
