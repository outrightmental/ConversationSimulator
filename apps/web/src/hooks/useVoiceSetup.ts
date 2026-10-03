// SPDX-License-Identifier: Apache-2.0
/**
 * useVoiceSetup — the state behind the guided voice setup screen (issue #487).
 *
 * Holds the server's plan (what voice needs here, what is already satisfied),
 * polls an in-flight download job, and exposes the three actions the flow can
 * take: start a download, cancel it, start a present-but-stopped engine.
 *
 * The plan is re-fetched after every action and whenever the window regains
 * focus, because the two native engines are installed *outside* the app — a
 * player who runs `brew install whisper.cpp` in a terminal and switches back
 * should see the step tick over without hunting for a refresh button.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import type { VoiceInstallJob, VoiceSetupPlan } from '@convsim/shared'

const POLL_INTERVAL_MS = 1000
const TERMINAL = new Set(['complete', 'failed', 'cancelled'])

export interface UseVoiceSetupReturn {
  plan: VoiceSetupPlan | null
  planError: ApiError | null
  loading: boolean
  job: VoiceInstallJob | null
  actionError: ApiError | null
  /** Message from the last engine-start attempt, success or failure. */
  engineMessage: string | null
  busy: boolean
  refresh: () => void
  startInstall: (assetIds: string[]) => Promise<void>
  cancelInstall: () => Promise<void>
  startEngine: (engineId: string) => Promise<void>
}

export function useVoiceSetup(): UseVoiceSetupReturn {
  const [plan, setPlan] = useState<VoiceSetupPlan | null>(null)
  const [planError, setPlanError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [jobId, setJobId] = useState<number | null>(null)
  const [job, setJob] = useState<VoiceInstallJob | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [engineMessage, setEngineMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Guards the post-completion refresh: the plan must be re-read once a job
  // lands so the capability rows flip to ready, but only once per job.
  const settledJobRef = useRef<number | null>(null)

  const refresh = useCallback(() => {
    void api.getVoiceSetupPlan().then((r) => {
      if (r.ok) {
        setPlan(r.data)
        setPlanError(null)
        // Reattach to a download started earlier (another tab, or before a
        // navigation away) rather than showing an idle screen over a live job.
        setJobId((current) => current ?? r.data.active_job_id)
      } else {
        setPlanError(r.error)
      }
      setLoading(false)
    })
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    function onFocus() { refresh() }
    window.addEventListener('focus', onFocus)
    return () => { window.removeEventListener('focus', onFocus) }
  }, [refresh])

  useEffect(() => {
    if (jobId == null) {
      setJob(null)
      return
    }

    function stopPoll() {
      if (pollRef.current != null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }

    async function poll() {
      const r = await api.getVoiceInstallStatus(jobId!)
      if (!r.ok) return
      setJob(r.data)
      if (TERMINAL.has(r.data.status)) {
        stopPoll()
        if (settledJobRef.current !== r.data.id) {
          settledJobRef.current = r.data.id
          refresh()
        }
      }
    }

    void poll()
    pollRef.current = setInterval(() => { void poll() }, POLL_INTERVAL_MS)
    return stopPoll
  }, [jobId, refresh])

  const startInstall = useCallback(async (assetIds: string[]) => {
    setBusy(true)
    setActionError(null)
    const r = await api.startVoiceInstall(assetIds)
    if (r.ok) {
      settledJobRef.current = null
      setJob(r.data)
      setJobId(r.data.id)
    } else {
      setActionError(r.error)
    }
    setBusy(false)
  }, [])

  const cancelInstall = useCallback(async () => {
    if (jobId == null) return
    setBusy(true)
    const r = await api.cancelVoiceInstall(jobId)
    if (!r.ok) setActionError(r.error)
    setBusy(false)
  }, [jobId])

  const startEngine = useCallback(async (engineId: string) => {
    setBusy(true)
    setActionError(null)
    setEngineMessage(null)
    const r = await api.startVoiceEngine(engineId)
    if (r.ok) {
      setEngineMessage(r.data.message)
      refresh()
    } else {
      setActionError(r.error)
    }
    setBusy(false)
  }, [refresh])

  return {
    plan,
    planError,
    loading,
    job,
    actionError,
    engineMessage,
    busy,
    refresh,
    startInstall,
    cancelInstall,
    startEngine,
  }
}
