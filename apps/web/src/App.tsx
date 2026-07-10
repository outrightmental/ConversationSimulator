// SPDX-License-Identifier: Apache-2.0
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
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
import FirstRunWizard from './screens/FirstRunWizard'
import CoreStartupGuard from './screens/CoreStartup'
import { SETUP_KEYS } from './privacyPrefs'

// Redirects to /first-run until the setup wizard has been completed once.
function FirstRunGuard() {
  const complete = localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true'
  if (!complete) {
    return <Navigate to="/first-run" replace />
  }
  return <Outlet />
}

export default function App() {
  return (
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
            </Route>
          </Route>
        </Routes>
      </CoreStartupGuard>
    </ErrorBoundary>
  )
}
