// SPDX-License-Identifier: Apache-2.0
import { Routes, Route } from 'react-router-dom'
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

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/library" element={<ScenarioLibrary />} />
          <Route path="/setup/:scenarioId" element={<ScenarioSetup />} />
          <Route path="/conversation/:sessionId" element={<Conversation />} />
          <Route path="/debrief/:sessionId" element={<Debrief />} />
          <Route path="/workbench" element={<CreatorWorkbench />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/model-manager" element={<ModelManager />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}
