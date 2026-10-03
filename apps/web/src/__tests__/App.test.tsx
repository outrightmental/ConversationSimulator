// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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

// Typed with an explicit signature (rather than letting the no-arg
// implementation infer one) so `mock.calls` destructures the name argument
// instead of inferring an empty tuple.
const mockUnlock = vi.fn<(name: string) => Promise<boolean>>(() => Promise.resolve(false))
const mockIncrementStat = vi.fn<(name: string) => Promise<boolean>>(() => Promise.resolve(false))
// Only the hook itself is stubbed. This module also exports the achievement and
// stat name maps, the unlock thresholds, and the local progress helpers that the
// screens import directly; a hand-rolled mock of those silently drifts out of
// date every time an achievement is added (and then the screen throws on an
// undefined export), so importOriginal keeps them real.
vi.mock('../hooks/useSteamAchievements', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useSteamAchievements')>()),
  useSteamAchievements: () => ({ unlock: mockUnlock, incrementStat: mockIncrementStat }),
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
    expect(await screen.findByRole('button', { name: /set me up/i })).toBeInTheDocument()
    // The wizard renders outside AppLayout, so no nav chrome is present.
    expect(screen.queryByRole('link', { name: /settings/i })).not.toBeInTheDocument()
  })

  it('redirects a first-time user away from a deep protected route too', async () => {
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'never-run' })
    renderAt('/settings')
    expect(await screen.findByRole('button', { name: /set me up/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^settings$/i })).not.toBeInTheDocument()
  })

  it('does not show the wizard on a working install when localStorage is cleared', async () => {
    // Issue-380 acceptance criterion: a cleared webview cache must not resurrect
    // the wizard — the server-side outcome (ready) wins over the missing mirror.
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'ready' })
    renderAt('/settings')
    expect(await screen.findByRole('heading', { name: /settings/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /set me up/i })).not.toBeInTheDocument()
  })

  it('shows the wizard (and clears the stale mirror) when the data dir was wiped but the cache survived', async () => {
    // Issue-380 acceptance criterion: wiping the data dir must show the wizard.
    // Here the server (authoritative) reports never-run while a stale localStorage
    // mirror still reads 'true' (beforeEach set it). Without clearing the mirror,
    // the guard redirects to /first-run, the wizard reads the stale mirror and
    // bounces straight back to the app — an infinite redirect loop. The guard must
    // clear the mirror so the wizard actually renders.
    expect(localStorage.getItem('convsim.setup.complete')).toBe('true')
    mockSetupStatus({ kind: 'never-run' })
    renderAt('/settings')
    expect(await screen.findByRole('button', { name: /set me up/i })).toBeInTheDocument()
    // The stale mirror was cleared so the wizard no longer bounces back.
    expect(localStorage.getItem('convsim.setup.complete')).toBeNull()
  })

  it('lets a returning user reach protected routes without the wizard', () => {
    // beforeEach already set the completion flag; the localStorage fast-path
    // renders the app synchronously without waiting on the server.
    renderAt('/settings')
    expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /set me up/i })).not.toBeInTheDocument()
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
    expect(await screen.findByRole('button', { name: /set me up/i })).toBeInTheDocument()
    // …and the guard redirected to /first-run while preserving the original
    // destination in `next=` (URL-encoded) so it is never silently swallowed.
    const location = screen.getByTestId('location-probe').textContent ?? ''
    expect(location).toMatch(/^\/first-run\b/)
    expect(decodeURIComponent(location)).toContain('next=/model-manager')
  })
})

// ---------------------------------------------------------------------------
// Steam achievement (issue #494)
// ---------------------------------------------------------------------------

describe('ACH_SETUP_COMPLETE', () => {
  // This file's top-level beforeEach does not reset mocks, so clear the two
  // achievement spies here — otherwise a grant from an earlier test leaks in and
  // the negative case below passes (or fails) for the wrong reason.
  beforeEach(() => {
    mockUnlock.mockClear()
    mockIncrementStat.mockClear()
  })

  // The setup guard, not the wizard, is the authoritative grant point. The
  // wizard runs once per install, so granting only there would put the
  // achievement — and the ACH_CERTIFIED_EXPERT capstone that requires it —
  // permanently out of reach for every player who finished onboarding before
  // this achievement set shipped. Granting from the server's "ready" answer on
  // every launch is what makes it retroactive.
  it('is granted when the server reports setup is ready', async () => {
    mockSetupStatus({ kind: 'ready' })
    renderAt('/')
    await waitFor(() => expect(mockUnlock).toHaveBeenCalledWith('ACH_SETUP_COMPLETE'))
  })

  it('is granted retroactively for a player whose localStorage mirror is gone', async () => {
    // The returning-user mirror is what beforeEach sets; clearing it leaves the
    // server's answer as the only evidence, which is exactly the upgrade case.
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'ready' })
    renderAt('/settings')
    await waitFor(() => expect(mockUnlock).toHaveBeenCalledWith('ACH_SETUP_COMPLETE'))
  })

  it('is not granted while setup has never run', async () => {
    localStorage.removeItem('convsim.setup.complete')
    mockSetupStatus({ kind: 'never-run' })
    renderAt('/')
    await screen.findByRole('button', { name: /set me up/i })
    expect(mockUnlock).not.toHaveBeenCalledWith('ACH_SETUP_COMPLETE')
  })

  it('increments no stat — finishing setup is not a counted event', async () => {
    mockSetupStatus({ kind: 'ready' })
    renderAt('/')
    await waitFor(() => expect(mockUnlock).toHaveBeenCalledWith('ACH_SETUP_COMPLETE'))
    expect(mockIncrementStat).not.toHaveBeenCalled()
  })
})
