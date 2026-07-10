// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react'
import { apiClient } from './client'

export interface PackCount {
  /** Number of installed packs, or null while the initial fetch is in flight. */
  count: number | null
  /** Re-fetch the installed pack count (e.g. after restoring official packs). */
  refetch: () => void
}

/**
 * Returns the number of installed packs, or null while the initial fetch is in
 * flight.  Returning null (rather than defaulting to 0) prevents the UI from
 * briefly flashing "None installed" on screens that render before the first
 * API round-trip completes.  The returned `refetch` lets callers refresh the
 * count after an action that changes it (e.g. restoring official packs) so the
 * UI does not remain stale.
 */
export function usePackCount(): PackCount {
  const [count, setCount] = useState<number | null>(null)

  const load = useCallback(() => {
    let cancelled = false
    void apiClient.packs().then((r) => {
      if (!cancelled) setCount(r.ok ? (r.data?.total ?? 0) : 0)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => load(), [load])

  return { count, refetch: load }
}
