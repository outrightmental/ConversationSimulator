// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { apiClient } from './client'

export function usePackCount(): number {
  const [count, setCount] = useState(0)

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
