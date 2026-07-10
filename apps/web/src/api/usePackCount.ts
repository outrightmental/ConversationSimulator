// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { apiClient } from './client'

/**
 * Returns the number of installed packs, or null while the initial fetch is in
 * flight.  Returning null (rather than defaulting to 0) prevents the UI from
 * briefly flashing "None installed" on screens that render before the first
 * API round-trip completes.
 */
export function usePackCount(): number | null {
  const [count, setCount] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    void apiClient.packs().then((r) => {
      if (!cancelled) setCount(r.ok ? (r.data?.total ?? 0) : 0)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return count
}
