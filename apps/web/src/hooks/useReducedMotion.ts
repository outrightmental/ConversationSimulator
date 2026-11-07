// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

/** Whether the player asked the operating system for less motion (issue #539). */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
    try {
      return window.matchMedia(QUERY).matches
    } catch {
      return false
    }
  })
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    let media: MediaQueryList
    try {
      media = window.matchMedia(QUERY)
    } catch {
      return
    }
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    setReduced(media.matches)
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    }
    return undefined
  }, [])
  return reduced
}
