// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback } from 'react'

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

      {isError ? (
        <div
          role="alert"
          style={{
            maxWidth: 520,
            textAlign: 'center',
            background: '#fff3f3',
            border: '1px solid #f5c6cb',
            borderRadius: 8,
            padding: '1.25rem 1.5rem',
          }}
        >
          <p style={{ fontWeight: 600, color: '#c0392b', margin: '0 0 0.5rem' }}>
            {status!.message}
          </p>
          {status!.error && (
            <p
              style={{
                color: '#555',
                fontSize: '0.875rem',
                whiteSpace: 'pre-wrap',
                margin: '0 0 0.75rem',
              }}
            >
              {status!.error}
            </p>
          )}
          <p style={{ fontSize: '0.8125rem', color: '#888', margin: 0 }}>
            Restart the app to try again. If the problem persists, check the
            logs at <code>~/.convsim/logs</code>.
          </p>
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
