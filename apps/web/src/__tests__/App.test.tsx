// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import App from '../App'

// Surfaces the in-memory router location so tests can assert on it. `window.location`
// is NOT updated by MemoryRouter (it stays http://localhost/), so asserting against
// it would be vacuous — read the router location via useLocation instead.
function LocationProbe() {
  const location = useLocation()
  return <span data-testid="location-probe">{location.pathname + location.search}</span>
}

// @convsim/ui re-exports FormEditor which transitively imports @convsim/scenario-schema
// (requires zod at runtime).  Stub the package to avoid that peer dependency in tests.
vi.mock('@convsim/ui', () => ({
  StatusBadge: ({ children, status }: { children: React.ReactNode; status: string }) => (
    <span data-status={status}>{children}</span>
  ),
}))

function mockFetch(response: object) {
  // The API client reads the body via res.text() and then JSON.parses it (so an
  // HTML body from a downed runtime becomes a typed error instead of a parser
  // crash), so the mock must provide text(), not just json().
  const body = JSON.stringify(response)
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(response), text: () => Promise.resolve(body) }),
  ))
}

// Resolve only the server-authoritative /setup/status endpoint (consumed by the
// FirstRunGuard); leave every other call pending so screens that render behind
// the guard don't receive this status shape as their own payload.
function mockSetupStatus(status: object) {
  const body = JSON.stringify(status)
  vi.stubGlobal('fetch', vi.fn((input: unknown) => {
    const url = String(input)
    if (url.includes('/setup/status')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(status), text: () => Promise.resolve(body) })
    }
    return new Promise(() => {})
  }))
}

// Prevent real fetch calls; return a promise that never resolves so the
// pending-state async health check never triggers a post-render state update.
// Simulate a returning user so the FirstRunGuard allows access to all routes.
beforeEach(() => {
  localStorage.setItem('convsim.setup.complete', 'true')
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
})

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter
      initialEntries={[initialPath]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  )
}

describe('App shell', () => {
  it('renders Home screen at /', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: /conversation simulator/i })).toBeInTheDocument()
  })

  it('renders Scenario Library at /library', () => {
    renderAt('/library')
    expect(screen.getByRole('heading', { name: /scenario library/i })).toBeInTheDocument()
  })

  it('renders Scenario Setup at /setup/:id', () => {
    renderAt('/setup/behavioral-interview')
    expect(screen.getByTestId('setup-page')).toBeInTheDocument()
    expect(screen.getByText(/behavioral-interview/)).toBeInTheDocument()
  })

  it('renders Conversation at /conversation/:id', () => {
    renderAt('/conversation/sess-001')
    expect(screen.getByRole('heading', { name: /conversation/i })).toBeInTheDocument()
    expect(screen.getByText(/sess-001/)).toBeInTheDocument()
  })

  it('renders Debrief at /debrief/:id', () => {
    renderAt('/debrief/sess-001')
    expect(screen.getByRole('heading', { name: /debrief/i })).toBeInTheDocument()
  })

  it('renders Creator Workbench at /workbench', () => {
    renderAt('/workbench')
    expect(screen.getByRole('heading', { name: /creator workbench/i })).toBeInTheDocument()
  })

  it('renders Settings at /settings', () => {
    renderAt('/settings')
    expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument()
  })

  it('shows navigation links on every screen', () => {
    renderAt('/')
    expect(screen.getByRole('link', { name: /scenarios/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Workbench' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument()
  })

  it('shows healthy status when backend returns ok', async () => {
    mockFetch({ status: 'ok' })
    renderAt('/')
    expect(await screen.findByText('Local runtime: Ready')).toBeInTheDocument()
  })

  it('shows unavailable status when backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderAt('/')
    expect(await screen.findByText('Local runtime: Unavailable')).toBeInTheDocument()
  })
})

describe('First-run guard', () => {
  it('redirects a first-time user from a protected route to the setup wizard', async () => {
    // A fresh install has no completion flag; beforeEach sets it, so clear it here.
    // The guard is server-authoritative: it waits for /setup/status (never-run)
    // before redirecting, so the wizard appears asynchronously.
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'never-run' })
    renderAt('/')
    // …the welcome step's "Get started" call to action is shown instead.
    expect(await screen.findByRole('button', { name: /get started/i })).toBeInTheDocument()
    // The wizard renders outside AppLayout, so no nav chrome is present.
    expect(screen.queryByRole('link', { name: /settings/i })).not.toBeInTheDocument()
  })

  it('redirects a first-time user away from a deep protected route too', async () => {
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'never-run' })
    renderAt('/settings')
    expect(await screen.findByRole('button', { name: /get started/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^settings$/i })).not.toBeInTheDocument()
  })

  it('does not show the wizard on a working install when localStorage is cleared', async () => {
    // Issue-380 acceptance criterion: a cleared webview cache must not resurrect
    // the wizard — the server-side outcome (ready) wins over the missing mirror.
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'ready' })
    renderAt('/settings')
    expect(await screen.findByRole('heading', { name: /settings/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /get started/i })).not.toBeInTheDocument()
  })

  it('lets a returning user reach protected routes without the wizard', () => {
    // beforeEach already set the completion flag; the localStorage fast-path
    // renders the app synchronously without waiting on the server.
    renderAt('/settings')
    expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /get started/i })).not.toBeInTheDocument()
  })

  it('preserves the intended destination in a next= query param when redirecting to first-run', async () => {
    // Issue-378 defense-in-depth: the guard must never silently discard navigation
    // intent — any future fix_action pointing at a guarded route should be recorded
    // (in `next=`) rather than looped away to welcome.
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'never-run' })
    render(
      <MemoryRouter
        initialEntries={['/model-manager']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
        <LocationProbe />
      </MemoryRouter>,
    )
    // The wizard is shown (guard redirected us)…
    expect(await screen.findByRole('button', { name: /get started/i })).toBeInTheDocument()
    // …and the guard redirected to /first-run while preserving the original
    // destination in `next=` (URL-encoded) so it is never silently swallowed.
    const location = screen.getByTestId('location-probe').textContent ?? ''
    expect(location).toMatch(/^\/first-run\b/)
    expect(decodeURIComponent(location)).toContain('next=/model-manager')
  })
})
