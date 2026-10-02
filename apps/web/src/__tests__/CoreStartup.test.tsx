// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

// CoreStartupGuard uses Link (for the "Get support bundle" action) so it needs
// a router context.
function renderGuard(child: React.ReactNode = APP_CHILD) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <CoreStartupGuard>{child}</CoreStartupGuard>
    </MemoryRouter>,
  )
}

// ── Non-Tauri (browser) context ───────────────────────────────────────────────

describe('CoreStartupGuard — non-Tauri context', () => {
  it('renders children immediately when __TAURI__ is not present', () => {
    renderGuard()
    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })

  it('does not show a startup heading in browser context', () => {
    renderGuard()
    expect(screen.queryByRole('heading', { name: /conversation simulator/i })).not.toBeInTheDocument()
  })
})

// ── Tauri context ─────────────────────────────────────────────────────────────

describe('CoreStartupGuard — Tauri context, core not yet ready', () => {
  it('shows the app heading while waiting', async () => {
    stubTauri(() => Promise.resolve(() => {}))
    await act(async () => {
      renderGuard()
    })
    expect(screen.getByRole('heading', { name: /conversation simulator/i })).toBeInTheDocument()
  })

  it('does not render children while waiting', async () => {
    stubTauri(() => Promise.resolve(() => {}))
    await act(async () => {
      renderGuard()
    })
    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('shows a status live region while starting', async () => {
    stubTauri(() => Promise.resolve(() => {}))
    await act(async () => {
      renderGuard()
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
      renderGuard()
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
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'starting', message: 'Waiting for core service to be ready…', error: null },
      })
    })

    expect(screen.getByRole('status')).toHaveTextContent(/waiting for core service/i)
  })
})

describe('CoreStartupGuard — engine restart under a running window', () => {
  it('hides the app and reports progress while the engine is restarting', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'ready', message: 'Core service is ready.', error: null },
      })
    })
    expect(screen.getByText('App content loaded')).toBeInTheDocument()

    await act(async () => {
      handler?.({
        payload: {
          phase: 'restarting',
          message: 'The conversation engine stopped unexpectedly. Restarting… (attempt 1 of 3)',
          error: null,
        },
      })
    })

    // The engine lost its in-memory state, so the app must not stay mounted
    // over a dead port — and the player needs to be told what is happening.
    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/restarting/i)
  })

  it('remounts the app when the replacement engine reports ready', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    for (const payload of [
      { phase: 'ready', message: 'Core service is ready.', error: null },
      { phase: 'restarting', message: 'Restarting… (attempt 1 of 3)', error: null },
      { phase: 'ready', message: 'Core service is ready.', error: null },
    ]) {
      await act(async () => {
        handler?.({ payload })
      })
    }

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })

  it('shows the recovery card when the engine stops for good after ready', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'ready', message: 'Core service is ready.', error: null },
      })
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          message: 'The conversation engine keeps stopping.',
          error: 'It stopped 3 times in a row and will not be restarted again.',
        },
      })
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
    // Not "didn't start": this engine started and served before it died, and a
    // card headed with the one thing that did not happen sends the player off
    // looking for a bad install.
    const card = screen.getByRole('alert')
    expect(card).toHaveTextContent(/keeps stopping/i)
    expect(card).not.toHaveTextContent(/didn't start/i)
  })

  it('does not let a stale health success overrule a reported restart', async () => {
    // The health fast-path resolves on its own schedule; a success that lands
    // after the shell reported a restart must not mount the app anyway.
    let resolveHealth: ((value: unknown) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise((resolve) => {
        resolveHealth = resolve
      })),
    )

    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'restarting', message: 'Restarting… (attempt 2 of 3)', error: null },
      })
    })

    await act(async () => {
      resolveHealth?.({ ok: true, json: () => Promise.resolve({}) })
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })
})

describe('CoreStartupGuard — error state', () => {
  it('shows a recovery alert when core reports an error', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
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
  })

  it('shows a plain-language title for port conflict errors', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
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
    expect(alert).toHaveTextContent(/another app is using a required port/i)
  })

  it('names the other edition instead of blaming an unrelated program', async () => {
    // The demo and the full app share port 7355 and one data directory, so the
    // shell refuses to attach to the other edition's engine. That is a port
    // conflict, but the port-conflict card tells the player to close whatever
    // unrelated program is holding the port — and the engine holding it is
    // Conversation Simulator. Falling through to 'crash' was worse: an engine
    // is running perfectly well here, just the wrong one.
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          // Verbatim from `foreign_edition_error` in
          // apps/desktop/src-tauri/src/lib.rs, which a Rust test pins.
          message: 'Another edition of Conversation Simulator is already running.',
          error:
            'Conversation Simulator Demo is using the conversation engine on port 7355. ' +
            'Close it, then start the full version again.',
        },
      })
    })

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/another edition of conversation simulator is running/i)
    expect(alert).not.toHaveTextContent(/didn't start/i)
    expect(alert).not.toHaveTextContent(/another app is using a required port/i)
    // The hint is still shown verbatim, so the player learns WHICH one to close.
    expect(alert).toHaveTextContent(/conversation simulator demo is using/i)
  })

  it('shows the error detail in the alert', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
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

  it('shows a plain-language title for binary-not-found errors', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          message: 'Could not locate core service.',
          error: 'convsim-core executable not found.',
        },
      })
    })

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/the conversation engine couldn't be found/i)
  })

  it('shows a "Restart the app" action button in the error card', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'error', message: 'Failed.', error: null },
      })
    })

    expect(screen.getByRole('button', { name: /restart the app/i })).toBeInTheDocument()
  })

  it('shows a troubleshooting guide link in the error card', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'error', message: 'Failed.', error: null },
      })
    })

    expect(screen.getByRole('link', { name: /troubleshooting guide/i })).toBeInTheDocument()
  })

  it('does not render children on error', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'error', message: 'Failed.', error: null },
      })
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('shows the resolved log directory from the event payload', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          message: 'Failed.',
          error: null,
          log_dir: 'C:\\Users\\test\\AppData\\Local\\com.outrightmental.convsim\\logs',
        },
      })
    })

    expect(screen.getByRole('alert')).toHaveTextContent(
      'C:\\Users\\test\\AppData\\Local\\com.outrightmental.convsim\\logs',
    )
  })

  it('shows "Open logs folder" button when log_dir is present in error payload', async () => {
    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'error',
          message: 'Failed.',
          error: null,
          log_dir: '/home/user/.local/share/convsim/logs',
        },
      })
    })

    expect(screen.getByRole('button', { name: /open logs folder/i })).toBeInTheDocument()
  })
})

describe('CoreStartupGuard — health check fast-path', () => {
  it('passes through immediately when the health endpoint is already up', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) }),
      ),
    )
    stubTauri(() => Promise.resolve(() => {}))

    await act(async () => {
      renderGuard()
    })

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })

  it('does not pass through when a stranger on port 7355 answers 200', async () => {
    // The shell's probe requires the body to look like a convsim-core health
    // response precisely because anything can be holding the port; the
    // fast-path has to apply the same test or it mounts the app over a
    // stranger's socket for the whole port-conflict grace period.
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ hello: 'world' }) }),
      ),
    )
    stubTauri(() => Promise.resolve(() => {}))

    await act(async () => {
      renderGuard()
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('does not pass through when the shell has reported a non-ready phase', async () => {
    // 'starting' covers "Something is already using port 7355 — checking
    // whether it is the engine…", and that occupant can be the other edition's
    // engine: it answers with a real convsim-core health body, so the
    // fast-path's own test passes and mounting on it shows the wrong library
    // (issue #495). The shell decides readiness; this only beats its first event.
    let resolveHealth: ((value: unknown) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise((resolve) => {
        resolveHealth = resolve
      })),
    )

    let handler: TauriListenHandler | undefined
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    })

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: {
          phase: 'starting',
          message: 'Something is already using port 7355 — checking whether it is the engine…',
          error: null,
        },
      })
    })

    await act(async () => {
      resolveHealth?.({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('does not pass through when the health response is not JSON at all', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.reject(new SyntaxError('not json')) }),
      ),
    )
    stubTauri(() => Promise.resolve(() => {}))

    await act(async () => {
      renderGuard()
    })

    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
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
      renderGuard()
    })

    expect(invoke).toHaveBeenCalledWith('get_core_status')
    const alert = screen.getByRole('alert')
    // Plain-language title for binary-not-found class.
    expect(alert).toHaveTextContent(/the conversation engine couldn't be found/i)
    // Technical detail is still shown for diagnostics.
    expect(alert).toHaveTextContent(/convsim-core executable not found/i)
    expect(screen.queryByText('App content loaded')).not.toBeInTheDocument()
  })

  it('recovers a ready state emitted before the listener attached', async () => {
    const invoke = vi.fn(() =>
      Promise.resolve({ phase: 'ready', message: 'Core service is ready.', error: null }),
    )
    stubTauri(() => Promise.resolve(() => {}), invoke)

    await act(async () => {
      renderGuard()
    })

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })

  it('does not let a stale snapshot unmount an app a live event already readied', async () => {
    // The snapshot is read on the Rust side and resolved asynchronously, so it
    // can describe an older phase than an event already delivered to the
    // listener. Readiness follows the reported phase, so applying it anyway
    // would unmount a running app back to the progress screen — and no further
    // event is coming to put it back.
    let handler: TauriListenHandler | undefined
    let resolveSnapshot: ((value: unknown) => void) | undefined
    const invoke = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveSnapshot = resolve
        }),
    )
    stubTauri((_event, h) => {
      handler = h
      return Promise.resolve(() => {})
    }, invoke)

    await act(async () => {
      renderGuard()
    })

    await act(async () => {
      handler?.({
        payload: { phase: 'ready', message: 'Core service is ready.', error: null },
      })
    })
    expect(screen.getByText('App content loaded')).toBeInTheDocument()

    await act(async () => {
      resolveSnapshot?.({
        phase: 'starting',
        message: 'Waiting for core service to be ready…',
        error: null,
      })
    })

    expect(screen.getByText('App content loaded')).toBeInTheDocument()
  })
})
