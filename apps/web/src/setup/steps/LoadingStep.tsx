// SPDX-License-Identifier: Apache-2.0
import type { UseSetupFlowReturn } from '../useSetupFlow'

interface LoadingStepProps {
  flow: UseSetupFlowReturn
  mode?: 'wizard' | 'manager'
}

export function LoadingStep({ flow, mode = 'wizard' }: LoadingStepProps) {
  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Model Setup</h1>
      <p aria-live="polite" aria-busy="true">
        {mode === 'wizard' ? 'Checking your system…' : 'Loading model information…'}
      </p>
    </div>
  )
}
