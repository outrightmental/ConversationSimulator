// SPDX-License-Identifier: Apache-2.0
import { ActionButton } from '../primitives'
import { errorMessage } from '../errorMessage'
import { ApiErrorView } from '../../components/ApiErrorView'
import type { UseSetupFlowReturn } from '../useSetupFlow'
import { TROUBLESHOOTING_DOCS_URL } from '../docsUrls'

const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues'

interface LoadErrorStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function LoadErrorStep({ flow, mode }: LoadErrorStepProps) {
  const errMsg = flow.loadError ? errorMessage(flow.loadError) : 'Something went wrong loading model information. Please try again.'

  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Model Setup</h1>

      {mode === 'manager' && flow.loadError ? (
        <>
          <div style={{ marginTop: '0.5rem' }}>
            <ApiErrorView error={flow.loadError} onRetry={() => flow.setStep('loading')} context="ModelManager" />
          </div>
          <div style={{ marginTop: '0.75rem' }}>
            <ActionButton onClick={() => flow.navigate('/')}>Back to Home</ActionButton>
          </div>
        </>
      ) : (
        <>
          <p role="alert" style={{ color: '#f87171' }}>{errMsg}</p>
          <div style={{ marginTop: '0.5rem', padding: '0.85rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}>
            <p style={{ margin: '0 0 0.4rem', fontWeight: 600, color: '#f87171', fontSize: '0.875rem' }}>Could not connect to the local runtime</p>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
              The API server may not be running. Make sure you launched the app correctly, then try again.
              If your hardware cannot run a full model, the text-only demo works without one.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <a href={TROUBLESHOOTING_DOCS_URL} target="_blank" rel="noreferrer" style={{ fontSize: '0.825rem', color: '#a1a1aa' }}>Troubleshooting docs</a>
              <span style={{ color: '#52525b', fontSize: '0.825rem' }}>·</span>
              <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ fontSize: '0.825rem', color: '#a1a1aa' }}>Report an issue</a>
            </div>
            <ActionButton onClick={() => flow.setStep('welcome')}>Back to welcome</ActionButton>
          </div>
        </>
      )}
    </div>
  )
}
