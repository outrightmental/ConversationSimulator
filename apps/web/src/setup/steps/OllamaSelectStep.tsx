// SPDX-License-Identifier: Apache-2.0
import { ActionButton } from '../primitives'
import { errorMessage } from '../errorMessage'
import { ApiErrorView } from '../../components/ApiErrorView'
import type { UseSetupFlowReturn } from '../useSetupFlow'

interface OllamaSelectStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function OllamaSelectStep({ flow, mode }: OllamaSelectStepProps) {
  const ollamaModels = flow.modelsData?.ollama_models ?? []
  const errMsg = flow.actionError ? errorMessage(flow.actionError) : null

  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Use Ollama model</h1>

      {ollamaModels.length === 0 ? (
        <div>
          <p role="status">No Ollama models detected.</p>
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
            Install Ollama and pull at least one model, then return here.{' '}
            <a href="https://ollama.com" target="_blank" rel="noreferrer">ollama.com</a>
          </p>
        </div>
      ) : (
        <div>
          <p style={{ color: '#a1a1aa', fontSize: '0.9rem', marginBottom: '1rem' }}>Select a model from your local Ollama installation.</p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {ollamaModels.map((m) => (
              <li key={m.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', padding: '0.75rem', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px' }}>
                <span>
                  <strong>{m.name}</strong>
                  {m.size_category && <span style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.8rem' }}>{m.size_category}</span>}
                </span>
                <ActionButton disabled={flow.actionLoading} onClick={() => void flow.handleSelectOllama(m)}>Use this model</ActionButton>
              </li>
            ))}
          </ul>
        </div>
      )}

      {flow.actionError && (
        mode === 'manager'
          ? <div style={{ marginTop: '0.75rem' }}><ApiErrorView error={flow.actionError} context="ModelManager" /></div>
          : <p role="alert" style={{ color: '#f87171', marginTop: '0.75rem', fontSize: '0.875rem' }}>{errMsg}</p>
      )}

      <div style={{ marginTop: '1.5rem' }}>
        <ActionButton onClick={() => { flow.resetAction(); flow.setStep('choose') }}>Back</ActionButton>
      </div>
    </div>
  )
}
