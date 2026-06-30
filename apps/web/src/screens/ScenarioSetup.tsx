// SPDX-License-Identifier: Apache-2.0
import { useParams } from 'react-router-dom'

export default function ScenarioSetup() {
  const { scenarioId } = useParams<{ scenarioId: string }>()

  return (
    <div>
      <h1>Scenario Setup</h1>
      <p>Configure options before starting scenario <code>{scenarioId}</code>.</p>
      <p><em>Setup options will appear here once a scenario is selected.</em></p>
    </div>
  )
}
