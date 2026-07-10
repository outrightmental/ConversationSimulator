// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react'

export interface UpdateState {
  status: 'idle' | 'checking' | 'available' | 'dismissed'
  version: string | null
  releaseUrl: string | null
}

interface TauriUpdateInfo {
  version: string
  release_url: string
}

// Checks for a beta update once on mount (Tauri desktop only).
// Fails silently when offline or when the manifest is unavailable.
// The banner never appears in a plain browser context (no __TAURI__).
export function useAppUpdate(): {
  update: UpdateState
  dismiss: () => void
  install: () => void
} {
  const [update, setUpdate] = useState<UpdateState>({
    status: 'idle',
    version: null,
    releaseUrl: null,
  })

  useEffect(() => {
    const tauri = (window as { __TAURI__?: { core?: { invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> } } }).__TAURI__
    if (!tauri?.core) return

    setUpdate((prev) => ({ ...prev, status: 'checking' }))

    tauri.core
      .invoke<TauriUpdateInfo | null>('check_for_update')
      .then((info) => {
        if (info) {
          setUpdate({ status: 'available', version: info.version, releaseUrl: info.release_url })
        } else {
          setUpdate({ status: 'idle', version: null, releaseUrl: null })
        }
      })
      .catch(() => {
        // Fail silently — offline guard
        setUpdate({ status: 'idle', version: null, releaseUrl: null })
      })
  // Run once on mount; no deps needed
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function dismiss() {
    setUpdate((prev) => ({ ...prev, status: 'dismissed' }))
  }

  function install() {
    const tauri = (window as { __TAURI__?: { core?: { invoke<T>(cmd: string): Promise<T> } } }).__TAURI__
    if (!tauri?.core) return
    tauri.core.invoke('install_update').catch(() => {})
  }

  return { update, dismiss, install }
}
