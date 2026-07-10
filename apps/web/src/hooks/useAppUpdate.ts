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

// Session-scoped record of the version the user has dismissed. Persisted so
// the banner stays dismissed across Home re-mounts (React Router unmounts the
// Home route on navigation), keeping it non-nagging within a single app run.
// A newer version key re-shows the banner; a full app restart clears it.
const DISMISSED_STORAGE_KEY = 'convsim.betaUpdateDismissedVersion'

function readDismissedVersion(): string | null {
  try {
    return window.sessionStorage.getItem(DISMISSED_STORAGE_KEY)
  } catch {
    return null
  }
}

function rememberDismissedVersion(version: string): void {
  try {
    window.sessionStorage.setItem(DISMISSED_STORAGE_KEY, version)
  } catch {
    // sessionStorage unavailable — dismissal just won't persist across remounts.
  }
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
          const alreadyDismissed = readDismissedVersion() === info.version
          setUpdate({
            status: alreadyDismissed ? 'dismissed' : 'available',
            version: info.version,
            releaseUrl: info.release_url,
          })
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
    setUpdate((prev) => {
      if (prev.version) rememberDismissedVersion(prev.version)
      return { ...prev, status: 'dismissed' }
    })
  }

  function install() {
    const tauri = (window as { __TAURI__?: { core?: { invoke<T>(cmd: string): Promise<T> } } }).__TAURI__
    if (!tauri?.core) return
    tauri.core.invoke('install_update').catch(() => {})
  }

  return { update, dismiss, install }
}
