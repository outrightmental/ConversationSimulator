// SPDX-License-Identifier: Apache-2.0
import { useEffect } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
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

// Redirects to /first-run until the setup wizard has been completed once.
// Preserves the intended destination in a `next` query param so that any future
// fix_action pointing at a guarded route degrades gracefully instead of silently
// discarding the navigation intent.
function FirstRunGuard() {
  const location = useLocation()
  const complete = localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true'
  if (!complete) {
    return <Navigate to={`/first-run?next=${encodeURIComponent(location.pathname)}`} replace />
  }
  return <Outlet />
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
