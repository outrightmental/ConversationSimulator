// SPDX-License-Identifier: Apache-2.0
import { useEffect } from 'react'
import { ActionButton, PrimaryButton } from '../primitives'
import { errorMessage } from '../errorMessage'
import type { UseSetupFlowReturn } from '../useSetupFlow'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'

interface InstallingStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function InstallingStep({ flow, mode }: InstallingStepProps) {
  // Manager mode: return to confirm-install so ApiErrorView can show the error there
  useEffect(() => {
    if (mode === 'manager' && flow.actionError != null) {
      flow.setStep('confirm-install')
    }
  }, [mode, flow.actionError, flow.setStep])

  const status = flow.installRecord?.install_status ?? 'pending'
  const progressBytes = flow.installRecord?.progress_bytes ?? 0
  const totalBytes = flow.installRecord?.size_bytes ?? null
  const pct = totalBytes != null && totalBytes > 0
    ? Math.min(100, Math.round((progressBytes / totalBytes) * 100))
    : null

  const statusLabel: Record<string, string> = { pending: 'Queued…', downloading: 'Downloading…' }
  const errMsg = flow.actionError ? errorMessage(flow.actionError) : null

  const wrapper = mode === 'wizard'
    ? { style: { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } }
    : { style: { maxWidth: '640px' } }

  // Download error recovery (wizard-only detailed errors; manager shows generic)
  if (errMsg != null) {
    const isNetworkError = /no[\s_-]?network|network[\s_-]?unavailable|network[\s_-]?error|connection[\s_-]?refused|failed[\s_-]?to[\s_-]?connect|offline|timed[\s_-]?out/i.test(errMsg)
    const isDiskError = /insufficient[\s_-]?disk|not[\s_-]?enough[\s_-]?disk|disk[\s_-]?space|no[\s_-]?space[\s_-]?left|storage[\s_-]?full/i.test(errMsg)

    if (mode === 'wizard') {
      return (
        <div {...wrapper}>
          <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Installing model</h1>

          {isNetworkError && (
            <div role="alert" aria-label="network error" style={{ marginTop: '1rem', padding: '0.85rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}>
              <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontWeight: 600, fontSize: '0.875rem' }}>Network connection lost</p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                The download could not complete. Check your internet connection and try again, or choose a different option that does not require a download.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton onClick={() => { flow.resetAction(); flow.setStep('confirm-install') }}>Retry download</PrimaryButton>
                <ActionButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Choose a different option</ActionButton>
              </div>
            </div>
          )}

          {isDiskError && !isNetworkError && (
            <div role="alert" aria-label="insufficient disk space" style={{ marginTop: '1rem', padding: '0.85rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}>
              <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontWeight: 600, fontSize: '0.875rem' }}>Not enough disk space</p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                {flow.selectedModel != null ? `This model requires approximately ${flow.selectedModel.size_gb} GB of free disk space. ` : ''}
                Free up space on your drive and try again, or use a smaller model or Ollama instead.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton onClick={() => { flow.resetAction(); flow.setStep('confirm-install') }}>Try again</PrimaryButton>
                <ActionButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Choose a different option</ActionButton>
              </div>
            </div>
          )}

          {!isNetworkError && !isDiskError && (
            <div role="alert" style={{ marginTop: '1rem', padding: '0.85rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}>
              <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontSize: '0.875rem' }}>{errMsg}</p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: '#a1a1aa' }}>
                Check the <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">setup docs</a> if the problem persists.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton onClick={() => { flow.resetAction(); flow.setStep('confirm-install') }}>Try again</PrimaryButton>
                <ActionButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Choose a different option</ActionButton>
              </div>
            </div>
          )}
        </div>
      )
    }
  }

  return (
    <div {...wrapper}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Installing model</h1>
      <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
        {statusLabel[status] ?? 'Downloading…'} Download time depends on your {mode === 'wizard' ? 'internet speed.' : 'connection speed.'}
        {mode === 'wizard' ? ' The app will be ready as soon as the download completes.' : ''}
      </p>

      <div
        role="progressbar"
        aria-valuenow={pct ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Download progress"
        style={{ marginTop: '1rem', height: '8px', borderRadius: '4px', background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}
      >
        <div style={{ height: '100%', width: pct != null ? `${pct}%` : '0%', background: 'rgba(99,102,241,0.85)', borderRadius: '4px', transition: 'width 0.4s ease' }} />
      </div>

      <p aria-live="polite" style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.4rem' }}>
        {pct != null ? `${pct}% — ${(progressBytes / 1_073_741_824).toFixed(2)} GB` : 'Waiting for progress data…'}
      </p>

      {mode === 'wizard' && (
        <div role="note" aria-label="play tutorial while downloading" style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '8px', padding: '1rem 1.25rem', marginTop: '1.5rem' }}>
          <p style={{ margin: 0, fontWeight: 600, color: '#a5b4fc', fontSize: '0.9rem' }}>No need to wait — try the tutorial now</p>
          <p style={{ margin: '0.4rem 0 0.75rem', fontSize: '0.825rem', color: '#c7d2fe' }}>
            Play the 3–5 minute First Words tutorial while your model downloads.
            It uses scripted (not AI) responses and teaches state meters, scenario
            events, and the debrief rubric — no model needed.
          </p>
          <PrimaryButton onClick={() => flow.setStep('tutorial-prompt')}>Play the tutorial while you wait</PrimaryButton>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginTop: mode === 'wizard' ? '1rem' : '1.5rem' }}>
        <ActionButton onClick={() => void flow.handleCancelInstall()}>Cancel and go home</ActionButton>
      </div>
    </div>
  )
}
