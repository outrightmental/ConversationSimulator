// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { SessionCreateResponse } from '@convsim/shared'

/**
 * The conversation the player walked away from, if there is one (issue #501 §1).
 *
 * A player partway through the tutorial opened Settings to speed the model up,
 * then "couldn't easily figure out how to resume my ongoing scenario and
 * resorted to starting a new one" — because nothing in the app knew the session
 * existed. convsim-core has known all along: the row sits in `turn_sessions`
 * with a non-terminal `flow_state`. This asks for it.
 *
 * Deliberately the *newest* in-progress session rather than a list: more than
 * one is possible (every abandoned session stays in-progress until it is ended),
 * but "take me back to what I was just doing" has exactly one answer. The
 * others remain reachable from Settings → Your sessions.
 */
export type ResumableSessionState =
  | { state: 'loading' }
  | { state: 'none' }
  | { state: 'ready'; session: SessionCreateResponse }

export function useResumableSession(enabled = true): {
  result: ResumableSessionState
  refetch: () => void
} {
  const [result, setResult] = useState<ResumableSessionState>(
    enabled ? { state: 'loading' } : { state: 'none' },
  )

  const refetch = useCallback(() => {
    if (!enabled) {
      setResult({ state: 'none' })
      return
    }
    void api.listSessions('in_progress', 1).then((r) => {
      if (!r.ok) {
        // An unreachable core is reported by the status panel and the startup
        // guard; a resume affordance that cannot be loaded is simply absent
        // rather than another error card on top of those.
        setResult({ state: 'none' })
        return
      }
      // Tolerate a core that answers a shape this build does not expect (an
      // older bundled runtime, a proxy): no resumable session is the safe read.
      const session = r.data?.sessions?.[0]
      setResult(session ? { state: 'ready', session } : { state: 'none' })
    })
  }, [enabled])

  useEffect(() => {
    refetch()
  }, [refetch])

  // Ending a conversation, or starting one, happens on another screen. Refresh
  // when the window regains focus so the banner never offers to resume a
  // session that has since ended (mirrors the setup-status revalidation in
  // App.tsx, added for the same reason in issue #380).
  useEffect(() => {
    if (!enabled) return
    function onFocus() {
      refetch()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
    }
  }, [enabled, refetch])

  return { result, refetch }
}
