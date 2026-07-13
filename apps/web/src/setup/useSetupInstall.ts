// SPDX-License-Identifier: Apache-2.0
/**
 * useSetupInstall — polls GET /api/setup/install/{jobId} for live pipeline
 * progress and returns the current job snapshot.
 *
 * Used in InstallingStep (wizard + manager) and in the persistent header pill
 * so the user can roam the app during a long download without losing sight of
 * progress.
 */
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { SetupInstallJob } from '@convsim/shared'

const POLL_INTERVAL_MS = 1000

const _TERMINAL = new Set(['complete', 'failed', 'cancelled'])

export function useSetupInstall(jobId: number | null): SetupInstallJob | null {
  const [job, setJob] = useState<SetupInstallJob | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (jobId == null) {
      setJob(null)
      return
    }

    function stopPoll() {
      if (intervalRef.current != null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    async function poll() {
      const r = await api.getSetupInstallStatus(jobId!)
      if (!r.ok) return
      setJob(r.data)
      if (_TERMINAL.has(r.data.status)) {
        stopPoll()
      }
    }

    void poll() // initial fetch immediately
    intervalRef.current = setInterval(() => { void poll() }, POLL_INTERVAL_MS)

    return stopPoll
  }, [jobId])

  return job
}

/**
 * Compute a combined download percentage across all stages that carry bytes.
 * Returns null when no byte data is available yet.
 */
export function computeSetupInstallPct(job: SetupInstallJob | null): number | null {
  if (job == null) return null
  let totalBytes = 0
  let downloadedBytes = 0
  let hasByteData = false
  for (const s of job.stages) {
    if (s.bytes_total != null && s.bytes_total > 0) {
      hasByteData = true
      totalBytes += s.bytes_total
      downloadedBytes += Math.min(s.bytes_downloaded ?? 0, s.bytes_total)
    }
  }
  if (!hasByteData || totalBytes === 0) return null
  return Math.min(100, Math.round((downloadedBytes / totalBytes) * 100))
}
