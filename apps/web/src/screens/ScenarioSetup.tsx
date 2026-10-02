// SPDX-License-Identifier: Apache-2.0
import { useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ScenarioSetupPage } from '../pages/ScenarioSetup'
import type { SessionCreateResponse } from '@convsim/shared'

export default function ScenarioSetup() {
  const { scenarioId } = useParams<{ scenarioId: string }>()
  const navigate = useNavigate()

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

  // A flyting scenario is played on its own screens. Arriving here means a
  // stale link or a recommendation that did not know the mode, so forward with
  // `replace` — Back should return wherever the player came from, not to a
  // setup form this scenario can never use.
  const handleOtherMode = useCallback(() => {
    navigate(`/flyting/setup/${scenarioId}`, { replace: true })
  }, [navigate, scenarioId])

  return (
    <ScenarioSetupPage
      scenarioId={scenarioId!}
      onSessionCreated={handleSessionCreated}
      onBack={handleBack}
      onInstallModel={handleInstallModel}
      onOtherMode={handleOtherMode}
    />
  )
}
