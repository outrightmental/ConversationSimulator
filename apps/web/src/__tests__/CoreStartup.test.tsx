// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import CoreStartupGuard from '../screens/CoreStartup'

const APP_CHILD = <div>App content loaded</div>

// Default: health check fails (core not running) so the guard blocks.
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('unavailable'))))
})

afterEach(() => {
  vi.unstubAllGlobals()
  // Clear the Tauri global so tests don't bleed into each other.
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
})

// ── Helper ────────────────────────────────────────────────────────────────────

type TauriListenHandler = (e: { payload: unknown }) => void

function stubTauri(
  onListen: (event: string, handler: TauriListenHandler) => Promise<() => void>,
  invoke?: (cmd: string) => Promise<unknown>,
) {
  const win = window as { __TAURI__?: unknown }
  win.__TAURI__ = {
    event: { listen: onListen },
    ...(invoke ? { core: { invoke } } : {}),
  }
}

// ── Non-Tauri (browser) context ───────────────────────────────────────────────

describe('CoreStartupGuard — non-Tauri context', () => {
  it('renders children immediately when __TAURI__ is not present', () => {
    render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })

  it('does not show a startup heading in browser context', () => {
    render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    expect(screen.queryByRole('heading', { name: /conversation simulator/i })).not.toBeInTheDocument()
  })
})

// ── Tauri context ─────────────────────────────────────────────────────────────

describe('CoreStartupGuard — Tauri context, core not yet ready', () => {
  it('shows the app heading while waiting', async () => {
    stubTauri(() => Promise.resolve(() => {}))
    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })
    expect(screen.getByRole('heading', { name: /conversation simulator/i })).toBeInTheDocument()
  })

  it('does not render children while waiting', async () => {
    stubTauri(() => Promise.resolve(() => {}))
    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })
    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('shows a status live region while starting', async () => {
    stubTauri(() => Promise.resolve(() => {}))
    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })
    // Either a role="status" or a live region is present.
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})

describe('CoreStartupGuard — core becomes ready via event', () => {
  it('renders children after a ready event', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()

    await act(async () => {
      handler?.({
        payload: { phase: 'ready', message: 'Core service is ready.', error: null },
      })
    })

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })

  it('updates the status message on a starting event', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'starting', message: 'Waiting for core service to be ready…', error: null },
      })
    })

    expect(screen.getByRole('status')).toHaveTextContent(/waiting for core service/i)
  })
})

describe('CoreStartupGuard — error state', () => {
  it('shows an alert when core reports an error', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          message: 'Core service did not start.',
          error: 'Port 7355 is already in use.',
        },
      })
    })

    const alert = screen.getByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent(/core service did not start/i)
  })

  it('shows the error detail in the alert', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          message: 'Core service did not start.',
          error: 'Port 7355 is already in use.',
        },
      })
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/port 7355 is already in use/i)
  })

  it('does not render children on error', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'error', message: 'Failed.', error: null },
      })
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })
})

describe('CoreStartupGuard — health check fast-path', () => {
  it('passes through immediately when the health endpoint is already up', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
    )
    stubTauri(() => Promise.resolve(() => {}))

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })
})

describe('CoreStartupGuard — snapshot recovery of missed events', () => {
  it('recovers an error emitted before the listener attached via get_core_status', async () => {
    // Listener attaches but the terminal event already fired, so no event is
    // ever delivered to the handler — only get_core_status knows the state.
    const invoke = vi.fn(() =>
      Promise.resolve({
        phase: 'error',
        message: 'Could not locate core service.',
        error: 'convsim-core executable not found.',
      }),
    )
    stubTauri(() => Promise.resolve(() => {}), invoke)

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    expect(invoke).toHaveBeenCalledWith('get_core_status')
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/could not locate core service/i)
    expect(alert).toHaveTextContent(/convsim-core executable not found/i)
    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('recovers a ready state emitted before the listener attached', async () => {
    const invoke = vi.fn(() =>
      Promise.resolve({ phase: 'ready', message: 'Core service is ready.', error: null }),
    )
    stubTauri(() => Promise.resolve(() => {}), invoke)

    await act(async () => {
      render(<CoreStartupGuard>{APP_CHILD}</CoreStartupGuard>)
    })

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })
})
