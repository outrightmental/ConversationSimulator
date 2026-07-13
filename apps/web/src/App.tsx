// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
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

function useSetupStatus(): SetupStatus {
  const localComplete = (() => {
    try { return localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true' } catch { return false }
  })()

  // Fast-path: derive status from localStorage synchronously to avoid any
  // redirect flash. Server response then overwrites this with the authoritative value.
  const [status, setStatus] = useState<SetupStatus>(
    localComplete ? { kind: 'ready' } : { kind: 'never-run' },
  )

  useEffect(() => {
    void api.getSetupStatus().then((r) => {
      if (!r.ok) return
      const derived = deriveSetupStatus(r.data)
      setStatus(derived)
      if (derived.kind === 'ready') {
        try { localStorage.setItem(SETUP_KEYS.firstRunComplete, 'true') } catch { /* ignore */ }
      }
    })
  }, [])

  return status
}

function FinishSetupBanner() {
  const navigate = useNavigate()
  return (
    <div
      role="banner"
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
  const status = useSetupStatus()

  if (status.kind === 'never-run') {
    return <Navigate to={`/first-run?next=${encodeURIComponent(location.pathname)}`} replace />
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
