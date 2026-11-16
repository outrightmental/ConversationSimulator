// SPDX-License-Identifier: Apache-2.0
//
// The one place a player installs voice: what they get, what it costs in
// megabytes, one button, then progress they can cancel. It is the voice
// counterpart of "Set me up" for the AI model, and it follows the same rule
// (docs/model-download-policy.md): nothing is fetched until the player presses
// a button on a screen that states the size, the source and the licence.
//
// It renders nothing when there is nothing to say: voice already works, or the
// engine has no installer to offer.
import { forwardRef } from 'react'
import type {
  VoiceAssetStatus,
  VoiceInstallStage,
  VoiceSetupStatus,
} from '@convsim/shared'
import type { UseVoiceInstall } from '../hooks/useVoiceInstall'
import { formatDownloadSize, jobPercent, voiceInstallCardVisible } from '../lib/voiceInstall'
import { ApiErrorView } from './ApiErrorView'
import './VoiceInstallCard.css'

/** What the missing pieces add up to, in the player's terms. */
function offer(status: VoiceSetupStatus): { title: string; pitch: string; action: string } {
  const missing = status.components.filter((c) => !c.ready).map((c) => c.id)
  if (missing.length === 1 && missing[0] === 'stt') {
    return {
      title: 'Add voice input',
      pitch: 'Speak your turns instead of typing them.',
      action: 'Install voice input',
    }
  }
  if (missing.length === 1 && missing[0] === 'tts') {
    return {
      title: 'Add the character’s voice',
      pitch: 'Hear the other person’s replies out loud.',
      action: 'Install character voice',
    }
  }
  return {
    title: 'Add voice',
    pitch: 'Talk out loud and hear the replies spoken.',
    action: 'Install voice',
  }
}

function stagePercent(stage: VoiceInstallStage): number | null {
  if (stage.bytes_total == null || stage.bytes_total <= 0) return null
  return Math.min(100, Math.round(((stage.bytes_downloaded ?? 0) / stage.bytes_total) * 100))
}

function stageNote(stage: VoiceInstallStage): string {
  if (stage.state === 'failed') return stage.error ?? 'Failed'
  if (stage.state === 'complete') return 'Done'
  if (stage.state === 'skipped') return 'Already installed'
  if (stage.state === 'pending') return 'Waiting'
  if (stage.detail === 'unpacking') return 'Verifying and unpacking…'
  const pct = stagePercent(stage)
  if (pct == null || stage.bytes_total == null) return 'Working…'
  return `${formatDownloadSize(stage.bytes_downloaded ?? 0)} of ${formatDownloadSize(stage.bytes_total)}`
}

function StageRow({ stage }: { stage: VoiceInstallStage }) {
  const pct = stage.state === 'complete' ? 100 : stagePercent(stage)
  return (
    <li className={`voice-install-stage is-${stage.state}`}>
      <span className="voice-install-stage-mark" aria-hidden="true">
        {stage.state === 'complete' ? '✓' : stage.state === 'failed' ? '✗' : stage.state === 'running' ? '▸' : '○'}
      </span>
      <span className="voice-install-stage-label">{stage.label}</span>
      <span className="voice-install-stage-note">{stageNote(stage)}</span>
      {stage.state === 'running' && pct != null && (
        <span className="voice-install-bar" aria-hidden="true">
          <span className="voice-install-bar-fill" style={{ width: `${pct}%` }} />
        </span>
      )}
    </li>
  )
}

function AssetRow({ asset }: { asset: VoiceAssetStatus }) {
  return (
    <li className="voice-install-asset">
      <span className="voice-install-asset-name">{asset.label}</span>
      <span className="voice-install-asset-size">{formatDownloadSize(asset.download_bytes)}</span>
      <span className="voice-install-asset-meta">
        {asset.source_name} · {asset.license}
        {asset.license_note ? ` · ${asset.license_note}` : ''}
      </span>
      <span className="voice-install-asset-meta voice-install-asset-url">{asset.source_url}</span>
    </li>
  )
}

interface Props {
  voice: UseVoiceInstall
  /** Draws attention to the card for a moment (a disabled option was clicked). */
  highlighted?: boolean
}

/**
 * The ref lands on the primary button, so a screen can hand focus to it when
 * the player reaches for a voice option that is not installed yet.
 */
export const VoiceInstallCard = forwardRef<HTMLButtonElement, Props>(function VoiceInstallCard(
  { voice, highlighted = false },
  ref,
) {
  const { status, job, installing, busy, error, install, cancel } = voice
  // Voice works and this screen did not just install it, or the engine has
  // no installer: nothing to offer.
  if (status == null || !voiceInstallCardVisible(voice)) return null

  const allReady = status.components.every((c) => c.ready)
  const justInstalled = job?.status === 'complete'

  const className = `voice-install${highlighted ? ' is-highlighted' : ''}`

  if (!status.supported) {
    return (
      <div className={className} data-testid="voice-install">
        <p className="voice-install-title">Voice</p>
        <p className="voice-install-text">
          {status.unsupported_reason ?? 'Voice is not available on this computer yet.'}{' '}
          Typing always works.
        </p>
      </div>
    )
  }

  if (installing && job != null) {
    const pct = jobPercent(job)
    return (
      <div className={className} data-testid="voice-install" aria-busy="true">
        <div className="voice-install-head">
          <p className="voice-install-title">Installing voice</p>
          <span className="voice-install-pct">{pct}%</span>
        </div>
        <div
          className="voice-install-bar is-overall"
          role="progressbar"
          aria-label="Voice install progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
        >
          <span className="voice-install-bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <ol className="voice-install-stages" aria-label="Voice install steps">
          {job.stages.map((stage) => (
            <StageRow key={stage.id} stage={stage} />
          ))}
        </ol>
        <div className="voice-install-actions">
          <p className="voice-install-text">
            You can keep setting up the conversation, or start it in text, while this runs.
          </p>
          <button
            type="button"
            className="voice-install-btn-quiet"
            onClick={() => void cancel()}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  if (allReady && justInstalled) {
    return (
      <div className={`${className} is-done`} data-testid="voice-install" role="status">
        <p className="voice-install-title">Voice is installed</p>
        <p className="voice-install-text">
          It runs on this device and works offline. Choose how you talk and whether to hear
          replies below.
        </p>
      </div>
    )
  }

  const { title, pitch, action } = offer(status)
  const failed = job?.status === 'failed'
  const cancelled = job?.status === 'cancelled'
  const toDownload = status.assets.filter((a) => !a.installed)

  return (
    <div className={className} data-testid="voice-install">
      <div className="voice-install-head">
        <p className="voice-install-title">{title}</p>
      </div>
      <p className="voice-install-text">
        {pitch} One download of {formatDownloadSize(status.download_bytes)}. It stays on this
        device and works offline afterwards.
      </p>

      {failed && (
        <p className="voice-install-problem" role="alert">
          <strong>The install did not finish.</strong>{' '}
          {job?.error_message ?? 'Something went wrong.'}{' '}
          {job?.error_code === 'NETWORK'
            ? 'What already downloaded is kept, so trying again continues from there.'
            : ''}
        </p>
      )}
      {cancelled && !failed && (
        <p className="voice-install-text" role="status">
          Install cancelled. No partial download was kept.
        </p>
      )}
      {error && <ApiErrorView error={error} compact context="VoiceInstall" />}

      <div className="voice-install-actions">
        <button
          ref={ref}
          type="button"
          className="voice-install-btn"
          onClick={() => void install()}
          disabled={busy}
        >
          {failed ? 'Try again' : action}
          <span className="voice-install-btn-size">
            {formatDownloadSize(status.download_bytes)}
          </span>
        </button>
        <details className="voice-install-details">
          <summary>What gets downloaded</summary>
          <ul className="voice-install-assets">
            {toDownload.map((asset) => (
              <AssetRow key={asset.id} asset={asset} />
            ))}
          </ul>
          <p className="voice-install-text">
            Every file is checked against a pinned SHA-256 before it is used. Saved to{' '}
            <span className="voice-install-path">{status.install_dir}</span>
          </p>
        </details>
      </div>
    </div>
  )
})
