// SPDX-License-Identifier: Apache-2.0
import { ActionButton, PrimaryButton } from '../primitives'
import type { UseSetupFlowReturn } from '../useSetupFlow'

interface DemoConfirmStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function DemoConfirmStep({ flow, mode }: DemoConfirmStepProps) {
  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Text-only demo</h1>

      <div role="note" aria-label="demo mode disclaimer" style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)', borderRadius: '6px', padding: '1rem 1.25rem', marginTop: '1rem' }}>
        <p style={{ margin: 0, fontWeight: 600, color: '#fbbf24' }}>This is a demo, not production quality.</p>
        <p style={{ margin: '0.6rem 0 0', fontSize: '0.875rem', color: '#fde68a' }}>
          Text-only demo mode uses scripted responses instead of a real AI model. NPC behaviour
          is hard-coded and does not represent the response quality you will experience with a
          local model installed. It is intended only to explore the interface before committing
          to a model download.
        </p>
      </div>

      {mode === 'wizard' && (
        <p style={{ marginTop: '1rem', fontSize: '0.875rem', color: '#a1a1aa' }}>
          You can return to model setup at any time from <strong>Settings → Model</strong>.
        </p>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
        <PrimaryButton
          disabled={flow.actionLoading}
          onClick={() => void flow.handleConfirmDemo(mode === 'wizard')}
        >
          {flow.actionLoading ? 'Starting…' : 'I understand — continue with text-only demo'}
        </PrimaryButton>
        <ActionButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Cancel</ActionButton>
      </div>
    </div>
  )
}
