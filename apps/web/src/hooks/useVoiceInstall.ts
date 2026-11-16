// SPDX-License-Identifier: Apache-2.0
//
// One-click voice install, as state a screen can render: what voice needs,
// whether an install is running, and the two things a player can do about it
// (install, cancel). See docs/voice-setup.md.
import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  VoiceComponentId,
  VoiceInstallJob,
  VoiceSetupStatus,
} from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'

const POLL_INTERVAL_MS = 700

export interface UseVoiceInstall {
  /**
   * The engine's plan. null while it loads, and null for good when the engine
   * has no voice installer to offer (an older engine): callers then keep
   * whatever they showed before this existed.
   */
  status: VoiceSetupStatus | null
  /** The running job, or the most recent one this screen knows about. */
  job: VoiceInstallJob | null
  /** A job is pending or running. */
  installing: boolean
  /** The request to start or cancel is in flight. */
  busy: boolean
  /** A failure to start or cancel (a failed *job* is on `job`). */
  error: ApiError | null
  /** Start installing. No arguments = everything that is not ready. */
  install: (components?: VoiceComponentId[]) => Promise<void>
  cancel: () => Promise<void>
  /** Delete the in-app install. Resolves true when it is gone. */
  remove: () => Promise<boolean>
}

function isActive(job: VoiceInstallJob | null): boolean {
  return job != null && (job.status === 'pending' || job.status === 'running')
}

/**
 * @param onChanged Called when an install reaches an end that may have changed
 *   what is installed (complete, or cancelled part-way): the caller re-reads
 *   whatever it derives from voice readiness.
 */
export function useVoiceInstall(onChanged?: () => void): UseVoiceInstall {
  const [status, setStatus] = useState<VoiceSetupStatus | null>(null)
  const [job, setJob] = useState<VoiceInstallJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const onChangedRef = useRef(onChanged)
  onChangedRef.current = onChanged
  const mountedRef = useRef(true)

  const loadStatus = useCallback(async (): Promise<VoiceSetupStatus | null> => {
    try {
      const r = await api.getVoiceSetup()
      if (!mountedRef.current) return null
      if (!r.ok) return null
      setStatus(r.data)
      return r.data
    } catch {
      // An engine (or a test double) without the endpoint: no installer.
      return null
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    void loadStatus().then((loaded) => {
      // Reattach to an install started before this screen was opened, and
      // show the outcome of one that just ended.
      if (loaded?.job && mountedRef.current) setJob(loaded.job)
    })
    return () => {
      mountedRef.current = false
    }
  }, [loadStatus])

  const activeJobId = isActive(job) ? job!.id : null

  useEffect(() => {
    if (activeJobId == null) return
    let stopped = false
    // One request at a time, and the end of the job is handled once: a slow
    // answer must not overlap the next tick and report the same ending twice.
    let inFlight = false
    let finished = false
    const timer = setInterval(() => {
      if (inFlight || finished) return
      inFlight = true
      void (async () => {
        try {
          const r = await api.getVoiceInstallJob(activeJobId)
          if (stopped || !mountedRef.current || !r.ok) return
          setJob(r.data)
          if (!isActive(r.data)) {
            finished = true
            clearInterval(timer)
            await loadStatus()
            if (r.data.status === 'complete' || r.data.status === 'cancelled') {
              onChangedRef.current?.()
            }
          }
        } finally {
          inFlight = false
        }
      })()
    }, POLL_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [activeJobId, loadStatus])

  const install = useCallback(async (components?: VoiceComponentId[]) => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.startVoiceInstall(components)
      if (!mountedRef.current) return
      if (r.ok) setJob(r.data)
      else setError(r.error)
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }, [])

  const cancel = useCallback(async () => {
    if (activeJobId == null) return
    setBusy(true)
    setError(null)
    try {
      const r = await api.cancelVoiceInstall(activeJobId)
      if (!mountedRef.current) return
      // A 409 means it finished first; the poll picks that up.
      if (!r.ok && r.error.status !== 409) setError(r.error)
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }, [activeJobId])

  const remove = useCallback(async (): Promise<boolean> => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.removeVoice()
      if (!mountedRef.current) return r.ok
      if (!r.ok) {
        setError(r.error)
        return false
      }
      setJob(null)
      await loadStatus()
      onChangedRef.current?.()
      return true
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }, [loadStatus])

  return { status, job, installing: isActive(job), busy, error, install, cancel, remove }
}
