// SPDX-License-Identifier: Apache-2.0
import { useParams } from 'react-router-dom'

export default function Conversation() {
  const { sessionId } = useParams<{ sessionId: string }>()

  return (
    <div>
      <h1>Conversation</h1>
      <p>Active session: <code>{sessionId}</code></p>
      <p><em>Conversation interface — NPC panel, transcript, and mic controls will appear here.</em></p>
    </div>
  )
}
