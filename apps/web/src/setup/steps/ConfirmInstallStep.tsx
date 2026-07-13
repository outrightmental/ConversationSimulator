// SPDX-License-Identifier: Apache-2.0
import { ActionButton, PrimaryButton, DetailRow } from '../primitives'
import { errorMessage } from '../errorMessage'
import { ApiErrorView } from '../../components/ApiErrorView'
import type { UseSetupFlowReturn } from '../useSetupFlow'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'

interface ConfirmInstallStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function ConfirmInstallStep({ flow, mode }: ConfirmInstallStepProps) {
  if (!flow.selectedModel) return null
  const m = flow.selectedModel
  const sha256Display = m.sha256 ?? 'Not available'
  const sha256IsPending = sha256Display.toUpperCase() === 'PENDING'
  const needsMoreVram = m.min_vram_gb != null && m.min_vram_gb > 4

  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Confirm model install</h1>
      <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
        Review the details below before starting the download. No download begins until you click{' '}
        <strong>Confirm &amp; install</strong>.
      </p>

      <table style={{ marginTop: '1rem', borderCollapse: 'collapse', width: '100%' }}>
        {mode === 'wizard' && (
          <caption style={{ textAlign: 'left', fontSize: '0.8rem', color: '#71717a', paddingBottom: '0.4rem', captionSide: 'top' }}>
            Model details
          </caption>
        )}
        <tbody>
          <DetailRow label="Model">{m.name}</DetailRow>
          <DetailRow label="Size">{m.size_gb != null ? `${m.size_gb} GB` : 'Unknown'}</DetailRow>
          <DetailRow label="License">
            {m.license_url
              ? <a href={m.license_url} target="_blank" rel="noreferrer">{m.license_spdx ?? 'View license'}</a>
              : (m.license_spdx ?? 'Unknown')}
          </DetailRow>
          <DetailRow label="Min VRAM">{m.min_vram_gb != null ? `${m.min_vram_gb} GB` : 'Unknown'}</DetailRow>
          <DetailRow label="Recommended VRAM">{m.recommended_vram_gb != null ? `${m.recommended_vram_gb} GB` : 'Unknown'}</DetailRow>
          <DetailRow label={mode === 'wizard' ? 'Integrity checksum' : 'SHA-256 checksum'}>
            <span style={{ fontFamily: 'monospace', fontSize: '0.8rem', wordBreak: 'break-all', color: sha256IsPending ? '#fbbf24' : 'inherit' }}>
              {sha256Display}
            </span>
            {sha256IsPending ? (
              <span style={{ display: 'block', fontSize: '0.8rem', color: '#fbbf24', marginTop: '0.2rem' }}>
                {mode === 'wizard'
                  ? 'Checksum not yet confirmed — the download will be rejected if verification fails.'
                  : 'Checksum not yet confirmed — install may be rejected by the runtime.'}
              </span>
            ) : mode === 'wizard' ? (
              <span style={{ display: 'block', fontSize: '0.75rem', color: '#71717a', marginTop: '0.2rem' }}>
                SHA-256 — the app checks this after download to confirm the file was not corrupted.
              </span>
            ) : null}
          </DetailRow>
          <DetailRow label={mode === 'wizard' ? 'Saves to' : 'Storage path'}>
            <code style={{ fontSize: '0.8rem' }}>~/.convsim/models/llm/{m.id}.gguf</code>
          </DetailRow>
          {mode === 'manager' && (
            <DetailRow label="Source">
              {m.source_type === 'registry' ? 'Official registry' : (m.source_type ?? 'Unknown')}
            </DetailRow>
          )}
        </tbody>
      </table>

      {mode === 'wizard' && (
        <div role="note" aria-label="offline-play explanation" style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '6px', padding: '0.85rem 1rem', marginTop: '1rem' }}>
          <p style={{ margin: 0, fontWeight: 600, color: '#a5b4fc', fontSize: '0.875rem' }}>Plays offline after install</p>
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.825rem', color: '#c7d2fe' }}>
            Once downloaded, this model runs entirely on your machine. You can disconnect from the
            internet and the game will work exactly the same. No data is sent to any server.
          </p>
        </div>
      )}

      {flow.actionError && (
        mode === 'manager'
          ? <div style={{ marginTop: '1rem' }}><ApiErrorView error={flow.actionError} context="ModelManager" /></div>
          : (
            <div role="alert" style={{ marginTop: '1rem' }}>
              <p style={{ color: '#f87171', margin: 0 }}>{errorMessage(flow.actionError)}</p>
              <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginTop: '0.4rem' }}>
                {needsMoreVram
                  ? `This model requires ${m.min_vram_gb} GB VRAM. If your hardware is limited, try a smaller model or `
                  : 'If your hardware or runtime cannot install this model, try a smaller model or '}
                check the <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">setup docs</a>.
              </p>
            </div>
          )
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
        <PrimaryButton
          disabled={flow.actionLoading}
          onClick={() => void flow.handleStartInstall(m.id)}
        >
          {flow.actionLoading ? 'Starting…' : 'Confirm & install'}
        </PrimaryButton>
        <ActionButton onClick={() => { flow.setSelectedModel(null); flow.resetAction(); flow.setStep('choose') }}>
          Cancel
        </ActionButton>
      </div>
    </div>
  )
}
