// SPDX-License-Identifier: Apache-2.0
import { useParams } from 'react-router-dom'

export default function Debrief() {
  const { sessionId } = useParams<{ sessionId: string }>()

  return (
    <div>
      <h1>Debrief</h1>
      <p>Session <code>{sessionId}</code></p>
      <p><em>Scorecard, transcript, key moments, and replay suggestions will appear here.</em></p>
    </div>
  )
}
