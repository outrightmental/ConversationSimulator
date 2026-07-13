// SPDX-License-Identifier: Apache-2.0
import { ActionButton, PrimaryButton } from '../primitives'
import { errorMessage } from '../errorMessage'
import { ApiErrorView } from '../../components/ApiErrorView'
import type { UseSetupFlowReturn } from '../useSetupFlow'

interface GgufPathStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function GgufPathStep({ flow, mode }: GgufPathStepProps) {
  const errMsg = flow.actionError ? errorMessage(flow.actionError) : null

  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Use a GGUF file</h1>

      <div role="note" aria-label="license responsibility notice" style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)', borderRadius: '6px', padding: '0.85rem 1rem', marginTop: '1rem' }}>
        <p style={{ margin: 0, fontWeight: 600, color: '#fbbf24', fontSize: '0.875rem' }}>You are responsible for this model's license and hardware fit.</p>
        <p style={{ margin: '0.4rem 0 0', fontSize: '0.825rem', color: '#fde68a' }}>
          This app does not claim the model you provide is official, licensed for redistribution,
          or suitable for your hardware. Review the model's license before use. The file will not be copied — only its path is stored.
        </p>
      </div>

      <div style={{ marginTop: '1.25rem' }}>
        <label htmlFor="gguf-path" style={{ display: 'block', marginBottom: '0.4rem', fontSize: '0.875rem' }}>File path</label>
        <input
          id="gguf-path"
          type="text"
          value={flow.ggufPath}
          onChange={(e) => { flow.setGgufPath(e.target.value); flow.setGgufPathError(null) }}
          placeholder="/path/to/model.gguf"
          aria-describedby="gguf-path-hint"
          aria-invalid={flow.ggufPathError != null}
          style={{ width: '100%', padding: '0.5rem 0.75rem', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', border: flow.ggufPathError ? '1px solid rgba(239,68,68,0.6)' : '1px solid rgba(255,255,255,0.15)', color: 'inherit', fontFamily: 'monospace', fontSize: '0.875rem', boxSizing: 'border-box' }}
        />
        <p id="gguf-path-hint" style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.3rem' }}>
          {mode === 'wizard'
            ? <>Full file path including the filename, e.g. <code style={{ fontFamily: 'monospace' }}>/home/you/Downloads/model.gguf</code> — must be compatible with llama.cpp.</>
            : 'Absolute path to a GGUF model file compatible with llama.cpp. Paths with spaces are supported.'}
        </p>
        {flow.ggufPathError && (
          <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', margin: '0.3rem 0 0' }}>{flow.ggufPathError}</p>
        )}
      </div>

      {flow.actionError && (
        mode === 'manager'
          ? <div style={{ marginTop: '0.75rem' }}><ApiErrorView error={flow.actionError} context="ModelManager" /></div>
          : <p role="alert" style={{ color: '#f87171', marginTop: '0.75rem', fontSize: '0.875rem' }}>{errMsg}</p>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
        <PrimaryButton disabled={flow.actionLoading} onClick={() => void flow.handleUseGguf()}>
          {flow.actionLoading ? 'Activating…' : 'Use this file'}
        </PrimaryButton>
        <ActionButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Back</ActionButton>
      </div>
    </div>
  )
}
