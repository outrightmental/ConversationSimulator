// SPDX-License-Identifier: Apache-2.0
//
// Small calculations behind the voice install card
// (components/VoiceInstallCard.tsx), kept apart from the component so a screen
// can ask them without importing it.
import type { VoiceInstallJob } from '@convsim/shared'
import type { UseVoiceInstall } from '../hooks/useVoiceInstall'

/** A download size the way a store page states it: decimal, rounded. */
export function formatDownloadSize(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e7) return `${Math.round(bytes / 1e6)} MB`
  if (bytes >= 1e5) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1e3))} KB`
}

/** Overall progress, weighted by bytes so the bar moves at download speed. */
export function jobPercent(job: VoiceInstallJob): number {
  let total = 0
  let done = 0
  for (const stage of job.stages) {
    const size = stage.bytes_total ?? 0
    total += size
    done += stage.state === 'complete' ? size : Math.min(stage.bytes_downloaded ?? 0, size)
  }
  if (total <= 0) return job.status === 'complete' ? 100 : 0
  return Math.min(100, Math.round((done / total) * 100))
}

/**
 * Whether the card has anything to show. A screen that gives the card a row
 * of its own asks first, so an empty card does not leave an empty row.
 */
export function voiceInstallCardVisible(voice: UseVoiceInstall): boolean {
  const { status, job, installing } = voice
  if (status == null) return false
  const allReady = status.components.every((c) => c.ready)
  return !allReady || installing || job?.status === 'complete'
}
