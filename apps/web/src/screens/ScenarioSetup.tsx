// SPDX-License-Identifier: Apache-2.0
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
      },
    })
  }

  function handleBack() {
    navigate(-1)
  }

  return (
    <ScenarioSetupPage
      scenarioId={scenarioId!}
      onSessionCreated={handleSessionCreated}
      onBack={handleBack}
    />
  )
}
