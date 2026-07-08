// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { apiClient } from './client'

export function usePackCount(): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    apiClient
      .packs()
      .then((data) => {
        if (!cancelled) setCount(data?.total ?? 0)
      })
      .catch(() => {
        if (!cancelled) setCount(0)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return count
}
