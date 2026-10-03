// SPDX-License-Identifier: Apache-2.0
import { useParams, useNavigate } from 'react-router-dom'
import { ScenarioSetupPage } from '../pages/ScenarioSetup'
import { useIsDemo } from '../edition'
import type { SessionCreateResponse } from '@convsim/shared'

export default function ScenarioSetup() {
  const { scenarioId } = useParams<{ scenarioId: string }>()
  const navigate = useNavigate()
  const isDemo = useIsDemo()

  function handleSessionCreated(session: SessionCreateResponse) {
    navigate(`/conversation/${session.session_id}`, {
      state: {
        language: session.setup.language,
        show_state_meters: session.setup.show_state_meters,
        scenario_id: session.scenario_id,
        input_mode: session.setup.input_mode,
        tts_enabled: session.setup.tts_enabled,
      },
    })
  }

  function handleBack() {
    navigate(-1)
  }

  function handleInstallModel() {
    navigate('/model-manager')
  }

  function handleSetUpVoice() {
    navigate('/voice-setup')
  }

  return (
    <ScenarioSetupPage
      scenarioId={scenarioId!}
      onSessionCreated={handleSessionCreated}
      onBack={handleBack}
      onInstallModel={handleInstallModel}
      // The demo ships no voice: /voice-setup collapses to Home there and the
      // API refuses the flow, so offering the route would be its own dead end
      // (issue #495). Without the callback the brief states the gap and stops.
      onSetUpVoice={isDemo ? undefined : handleSetUpVoice}
    />
  )
}
