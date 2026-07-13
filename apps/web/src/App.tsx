// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { I18nProvider } from './i18n'
import { installExternalLinkHandler } from './lib/openExternal'
import AppLayout from './layout/AppLayout'
import ErrorBoundary from './components/ErrorBoundary'
import Home from './screens/Home'
import ScenarioLibrary from './screens/ScenarioLibrary'
import ScenarioSetup from './screens/ScenarioSetup'
import Conversation from './screens/Conversation'
import Debrief from './screens/Debrief'
import CreatorWorkbench from './screens/CreatorWorkbench'
import Settings from './screens/Settings'
import ModelManager from './screens/ModelManager'
import Support from './screens/Support'
import FirstRunWizard from './screens/FirstRunWizard'
import CoreStartupGuard from './screens/CoreStartup'
import Logbook from './screens/Logbook'
import { SETUP_KEYS } from './privacyPrefs'
import { api } from './api/client'
import { deriveSetupStatus } from './setup'
import type { SetupStatus } from './setup'

type GuardStatus = SetupStatus | { kind: 'loading' }

function useSetupStatus(): { status: GuardStatus; pendingInstallId: number | null } {
  const localComplete = (() => {
    try { return localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true' } catch { return false }
  })()

  // Fast-path only in the direction that cannot lie: a localStorage mirror of
  // 'true' means onboarding was completed here, so render the app immediately to
  // avoid a redirect flash. The absence of the mirror is NOT authoritative — a
  // cleared webview cache on a working install must not resurrect the wizard —
  // so we hold in 'loading' until the server answers rather than assuming
  // never-run and redirecting synchronously.
  const [status, setStatus] = useState<GuardStatus>(
    localComplete ? { kind: 'ready' } : { kind: 'loading' },
  )
  const [pendingInstallId, setPendingInstallId] = useState<number | null>(null)

  const revalidate = useCallback(() => {
    void api.getSetupStatus().then((r) => {
      if (!r.ok) {
        // Server unreachable: fall back to the localStorage mirror so we never
        // hang on a blank screen. Without a mirror, treat as never-run. Only the
        // initial 'loading' state falls through to never-run — a revalidation
        // that fails keeps the last known status rather than downgrading it.
        setStatus((prev) => (prev.kind === 'loading' ? { kind: 'never-run' } : prev))
        return
      }
      // Prefer the new pipeline job ID; fall back to legacy per-model install id.
      setPendingInstallId(r.data.pending_setup_job_id ?? r.data.pending_install_id ?? null)
      const derived = deriveSetupStatus(r.data)
      setStatus(derived)
      if (derived.kind === 'ready') {
        try { localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true') } catch { /* ignore */ }
      } else if (derived.kind === 'never-run') {
        // The server (authoritative) has no recorded outcome, so a lingering
        // 'true' mirror is stale — e.g. the data dir was wiped but the webview
        // cache survived. Clear it, otherwise the wizard we are about to
        // redirect to would read the stale mirror and bounce straight back to
        // the app, producing an infinite redirect loop.
        try { localStorage.removeItem(SETUP_KEYS.firstRunComplete) } catch { /* ignore */ }
      }
    })
  }, [])

  useEffect(() => { revalidate() }, [revalidate])

  // Per issue #380, setup status is derived, not stored, so it must be
  // revalidated when the app regains focus — otherwise the "finish setup" banner
  // (or a resolved-in-the-background completion) goes stale until a full reload.
  // A user who finishes setup in the model manager and switches back sees the
  // banner clear on the next focus rather than being stuck with a wrong banner.
  useEffect(() => {
    function onFocus() { revalidate() }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
    }
  }, [revalidate])

  return { status, pendingInstallId }
}

function FinishSetupBanner() {
  const navigate = useNavigate()
  return (
    <div
      role="status"
      aria-label="finish setup"
      style={{
        background: 'rgba(251,191,36,0.1)',
        borderBottom: '1px solid rgba(251,191,36,0.3)',
        padding: '0.5rem 1rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        fontSize: '0.875rem',
      }}
    >
      <span style={{ color: '#fde68a', flex: 1 }}>
        Setup is incomplete — some features may not be available.
      </span>
      <button
        onClick={() => { navigate('/model-manager') }}
        style={{
          padding: '0.3rem 0.75rem',
          borderRadius: '4px',
          border: '1px solid rgba(251,191,36,0.4)',
          background: 'rgba(251,191,36,0.15)',
          color: '#fde68a',
          cursor: 'pointer',
          fontSize: '0.8rem',
          fontWeight: 500,
        }}
      >
        Finish setup
      </button>
    </div>
  )
}

// Guards guarded routes using server-authoritative SetupStatus.
// - never-run  → redirect to /first-run (first-time wizard)
// - incomplete → show app with a non-blocking "finish setup" banner
// - ready      → show app normally
// The fast-path localStorage value is used synchronously; server result updates it.
function FirstRunGuard() {
  const location = useLocation()
  const { status, pendingInstallId } = useSetupStatus()

  // Awaiting the authoritative server status. Render nothing briefly rather than
  // redirect to the wizard on a stale/cleared localStorage mirror.
  if (status.kind === 'loading') {
    return null
  }

  if (status.kind === 'never-run') {
    // Forward any pending install so the wizard resumes the download instead of
    // restarting at Welcome.
    const resume = pendingInstallId != null ? `&resume_install=${pendingInstallId}` : ''
    return <Navigate to={`/first-run?next=${encodeURIComponent(location.pathname)}${resume}`} replace />
  }

  return (
    <>
      {status.kind === 'incomplete' && <FinishSetupBanner />}
      <Outlet />
    </>
  )
}

export default function App() {
  // In the desktop shell, route external-link clicks through the OS browser;
  // the webview swallows target="_blank" navigations otherwise. No-op in a
  // plain browser.
  useEffect(() => installExternalLinkHandler(), [])

  return (
    <I18nProvider>
    <ErrorBoundary>
      <CoreStartupGuard>
        <Routes>
          {/* First-run wizard shown outside the main app layout */}
          <Route path="/first-run" element={<FirstRunWizard />} />

          <Route element={<AppLayout />}>
            <Route element={<FirstRunGuard />}>
              <Route path="/" element={<Home />} />
              <Route path="/library" element={<ScenarioLibrary />} />
              <Route path="/setup/:scenarioId" element={<ScenarioSetup />} />
              <Route path="/conversation/:sessionId" element={<Conversation />} />
              <Route path="/debrief/:sessionId" element={<Debrief />} />
              <Route path="/workbench" element={<CreatorWorkbench />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/model-manager" element={<ModelManager />} />
              <Route path="/support" element={<Support />} />
              <Route path="/logbook" element={<Logbook />} />
            </Route>
          </Route>
        </Routes>
      </CoreStartupGuard>
    </ErrorBoundary>
    </I18nProvider>
  )
}
