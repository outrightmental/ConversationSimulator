// SPDX-License-Identifier: Apache-2.0
import { useEffect } from 'react'
import { ActionButton, PrimaryButton } from '../primitives'
import { errorMessage } from '../errorMessage'
import { computeSetupInstallPct } from '../useSetupInstall'
import type { UseSetupFlowReturn } from '../useSetupFlow'
import type { SetupInstallStage } from '@convsim/shared'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'

interface InstallingStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

function StageIcon({ state }: { state: SetupInstallStage['state'] }) {
  const base: React.CSSProperties = {
    display: 'inline-block',
    width: '1em',
    textAlign: 'center',
    marginRight: '0.4rem',
    fontSize: '0.85em',
  }
  if (state === 'complete') return <span style={{ ...base, color: '#4ade80' }}>✓</span>
  if (state === 'skipped')  return <span style={{ ...base, color: '#71717a' }}>–</span>
  if (state === 'failed')   return <span style={{ ...base, color: '#f87171' }}>✗</span>
  if (state === 'running')  return <span style={{ ...base, color: '#a5b4fc' }}>▸</span>
  return <span style={{ ...base, color: '#52525b' }}>○</span>
}

function StageList({ stages }: { stages: SetupInstallStage[] }) {
  return (
    <ol
      aria-label="Installation stages"
      style={{ listStyle: 'none', margin: '1rem 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}
    >
      {stages.map((s) => (
        <li
          key={s.id}
          style={{
            fontSize: '0.85rem',
            color: s.state === 'running' ? '#e4e4e7' : s.state === 'failed' ? '#f87171' : '#71717a',
            display: 'flex',
            alignItems: 'baseline',
            gap: '0.2rem',
          }}
        >
          <StageIcon state={s.state} />
          <span>{s.label}</span>
          {s.state === 'running' && s.bytes_total != null && s.bytes_total > 0 && (
            <span style={{ marginLeft: '0.4rem', color: '#71717a', fontSize: '0.8em' }}>
              {((s.bytes_downloaded ?? 0) / 1_073_741_824).toFixed(2)} /{' '}
              {(s.bytes_total / 1_073_741_824).toFixed(2)} GB
            </span>
          )}
          {s.state === 'failed' && s.error && (
            <span style={{ marginLeft: '0.4rem', fontSize: '0.8em', color: '#fca5a5' }}>
              — {s.error}
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}

export function InstallingStep({ flow, mode }: InstallingStepProps) {
  // Manager mode: return to confirm-install so ApiErrorView can show the error there
  useEffect(() => {
    if (mode === 'manager' && flow.actionError != null) {
      flow.setStep('confirm-install')
    }
  }, [mode, flow.actionError, flow.setStep])

  const job = flow.setupInstallJob
  const stages = job?.stages ?? null
  const pct = computeSetupInstallPct(job)

  const currentStage = stages?.find((s) => s.state === 'running') ?? null
  const statusLabel = currentStage?.label ?? (job?.status === 'pending' ? 'Queued…' : 'Setting up…')

  const errMsg = flow.actionError ? errorMessage(flow.actionError) : null

  const wrapper = mode === 'wizard'
    ? { style: { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } }
    : { style: { maxWidth: '640px' } }

  // Download error recovery (wizard-only detailed errors; manager shows generic)
  if (errMsg != null) {
    const isNetworkError = /no[\s_-]?network|network[\s_-]?unavailable|network[\s_-]?error|connection[\s_-]?refused|failed[\s_-]?to[\s_-]?connect|offline|timed[\s_-]?out/i.test(errMsg)
    const isDiskError = /insufficient[\s_-]?disk|not[\s_-]?enough[\s_-]?disk|disk[\s_-]?space|no[\s_-]?space[\s_-]?left|storage[\s_-]?full/i.test(errMsg)
    const isWarmupError = /warmup|failed[\s_-]?to[\s_-]?start|insufficient[\s_-]?ram/i.test(errMsg)

    if (mode === 'wizard') {
      return (
        <div {...wrapper}>
          <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Setting up your AI</h1>

          {isNetworkError && (
            <div role="alert" aria-label="network error" style={{ marginTop: '1rem', padding: '0.85rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}>
              <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontWeight: 600, fontSize: '0.875rem' }}>Network connection lost</p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                The download could not complete. Check your internet connection and try again,
                or choose a different option that does not require a download.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton onClick={() => { flow.resetAction(); flow.setStep('confirm-install') }}>Retry</PrimaryButton>
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

          {isWarmupError && !isNetworkError && !isDiskError && (
            <div role="alert" aria-label="model warmup error" style={{ marginTop: '1rem', padding: '0.85rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}>
              <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontWeight: 600, fontSize: '0.875rem' }}>Model loaded but could not start</p>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
                The model was downloaded successfully but the AI engine could not start it.
                This usually means your machine doesn't have enough RAM to run this model.
                Try a smaller model, or check the{' '}
                <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">setup docs</a>.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <PrimaryButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Choose a smaller model</PrimaryButton>
              </div>
            </div>
          )}

          {!isNetworkError && !isDiskError && !isWarmupError && (
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
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Setting up your AI</h1>
      <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
        {statusLabel} Download time depends on your {mode === 'wizard' ? 'internet speed.' : 'connection speed.'}
        {mode === 'wizard' ? ' The app will be ready as soon as all stages complete.' : ''}
      </p>

      <div
        role="progressbar"
        aria-valuenow={pct ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Overall install progress"
        style={{ marginTop: '1rem', height: '8px', borderRadius: '4px', background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}
      >
        <div style={{ height: '100%', width: pct != null ? `${pct}%` : '0%', background: 'rgba(99,102,241,0.85)', borderRadius: '4px', transition: 'width 0.4s ease' }} />
      </div>

      <p aria-live="polite" style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.4rem' }}>
        {pct != null ? `${pct}% complete` : 'Waiting for progress data…'}
      </p>

      {stages != null && <StageList stages={stages} />}

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
