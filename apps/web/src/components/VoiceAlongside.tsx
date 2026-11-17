// SPDX-License-Identifier: Apache-2.0
//
// Voice, installed alongside the first download (issue #464).
//
// Talking out loud is the point of a conversation simulator, so the first-run
// Welcome offers voice with the model, and this row on the install screen
// says how far it has got. A player who left it out is offered it again here,
// while they wait anyway, so their first conversation can still be spoken.
import type { VoiceInstallJob } from '@convsim/shared'
import { useTranslation } from '../i18n'
import type { UseVoiceInstall } from '../hooks/useVoiceInstall'
import { formatDownloadSize, jobPercent } from '../lib/voiceInstall'

function bytesOf(job: VoiceInstallJob): { done: number; total: number } {
  let done = 0
  let total = 0
  for (const stage of job.stages) {
    const size = stage.bytes_total ?? 0
    total += size
    done += stage.state === 'complete' || stage.state === 'skipped'
      ? size
      : Math.min(stage.bytes_downloaded ?? 0, size)
  }
  return { done, total }
}

const rowStyle: React.CSSProperties = {
  marginTop: '0.9rem',
  padding: '0.6rem 0.85rem',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.03)',
  fontSize: '0.85rem',
  color: '#d4d4d8',
}

const buttonStyle: React.CSSProperties = {
  marginLeft: '0.6rem',
  padding: '0.25rem 0.7rem',
  borderRadius: '4px',
  border: '1px solid rgba(99,102,241,0.6)',
  background: 'rgba(99,102,241,0.15)',
  color: '#e0e7ff',
  fontSize: '0.8rem',
  cursor: 'pointer',
}

export default function VoiceAlongside({ voice }: { voice: UseVoiceInstall }) {
  const { t } = useTranslation()
  const { status, job, installing, busy, install } = voice
  if (status == null || !status.supported) return null

  const label = <strong style={{ color: '#e4e4e7', marginRight: '0.5rem' }}>{t('setup.installing.voice.label')}</strong>

  if (installing && job != null) {
    const running = job.stages.find((s) => s.state === 'running')
    if (running?.id === 'check') {
      return (
        <div data-testid="voice-alongside" role="status" style={rowStyle}>
          {label}
          {t('setup.installing.voice.checking')}
        </div>
      )
    }
    const { done, total } = bytesOf(job)
    const pct = jobPercent(job)
    return (
      <div data-testid="voice-alongside" role="status" style={rowStyle}>
        {label}
        {t('setup.installing.voice.downloading', {
          done: formatDownloadSize(done),
          total: formatDownloadSize(total),
        })}
        <div
          role="progressbar"
          aria-label={t('setup.installing.voice.label')}
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          style={{ marginTop: '0.4rem', height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}
        >
          <div style={{ width: `${pct}%`, height: '100%', background: 'rgba(110,231,183,0.8)', transition: 'width 0.4s ease' }} />
        </div>
      </div>
    )
  }

  const allReady = status.components.every((c) => c.ready)
  if (job?.status === 'complete' || allReady) {
    return (
      <div data-testid="voice-alongside" role="status" style={rowStyle}>
        <span aria-hidden="true" style={{ color: '#4ade80', marginRight: '0.4rem' }}>✓</span>
        {label}
        {t('setup.installing.voice.ready')}
      </div>
    )
  }

  const addButton = (
    <button type="button" style={buttonStyle} disabled={busy} onClick={() => void install()}>
      {t('setup.installing.voice.add')}
    </button>
  )

  if (job?.status === 'failed') {
    return (
      <div data-testid="voice-alongside" role="alert" style={{ ...rowStyle, borderColor: 'rgba(239,68,68,0.3)' }}>
        {label}
        {t('setup.installing.voice.failed', { reason: job.error_message ?? '' })}
        {addButton}
      </div>
    )
  }

  return (
    <div data-testid="voice-alongside" style={rowStyle}>
      {t('setup.installing.voice.offer', { size: formatDownloadSize(status.download_bytes) })}
      {addButton}
    </div>
  )
}
