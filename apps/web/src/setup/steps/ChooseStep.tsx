// SPDX-License-Identifier: Apache-2.0
import { SectionCard, CardHeading, CardDescription, ActionButton } from '../primitives'
import type { UseSetupFlowReturn } from '../useSetupFlow'

interface SpeedClass { label: string; color: string; detail: string }

function modelSpeedClass(role: string | null): SpeedClass {
  switch (role) {
    case 'starter': return { label: 'Fast', color: '#6ee7b7', detail: '~0.8–2.4 s TTFT on recommended tier' }
    case 'standard': return { label: 'Standard', color: '#93c5fd', detail: '~1.5–5 s TTFT on recommended tier' }
    case 'high-quality': return { label: 'Slower', color: '#fbbf24', detail: '~3–10 s TTFT; high-end GPU recommended' }
    case 'user-supplied': return { label: 'Varies', color: '#a1a1aa', detail: 'Speed depends on model size and your hardware' }
    default: return { label: 'Unknown', color: '#71717a', detail: 'Speed varies by hardware' }
  }
}

interface ChooseStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function ChooseStep({ flow, mode }: ChooseStepProps) {
  const lb = flow.modelsData?.last_benchmark ?? null

  return (
    <div style={{ maxWidth: '640px', margin: mode === 'wizard' ? '2rem auto' : undefined, padding: mode === 'wizard' ? '0 1rem' : undefined }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>
        {mode === 'wizard' ? 'Choose how to get started' : 'Set up your model'}
      </h1>
      <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
        {mode === 'wizard' ? 'Pick an option below. You can change it later in Settings.' : 'Choose how to get started. You can change this later in Settings.'}
      </p>

      {lb && (
        <div
          aria-label="last benchmark result"
          style={{ marginTop: '1rem', padding: '0.6rem 0.9rem', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', fontSize: '0.85rem', color: '#a1a1aa' }}
        >
          Last benchmark:{' '}
          <span style={{ color: 'inherit', fontWeight: 500 }}>{lb.tokens_per_sec.toFixed(1)} tok/s</span>
          {lb.context_length != null && <span style={{ marginLeft: '0.75rem' }}>· context {lb.context_length.toLocaleString()} tokens</span>}
          {lb.warnings.length > 0 && (
            <span style={{ color: '#fbbf24', marginLeft: '0.75rem' }}>
              · {lb.warnings.length} warning{lb.warnings.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}

      <ul role="list" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1.5rem', listStyle: 'none', padding: 0, margin: '1.5rem 0 0' }}>
        {flow.recommendedModel && (
          <li>
            <SectionCard>
              <CardHeading>Install recommended model</CardHeading>
              <CardDescription>
                {flow.recommendedModel.name} · {flow.recommendedModel.size_gb} GB ·{' '}
                {flow.recommendedModel.license_spdx} · Requires {flow.recommendedModel.min_vram_gb} GB VRAM
              </CardDescription>
              {mode === 'manager' && (() => {
                const sc = modelSpeedClass(flow.recommendedModel!.role ?? null)
                return (
                  <div
                    aria-label="expected speed class"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem', fontSize: '0.8rem' }}
                  >
                    <span style={{ padding: '0.1rem 0.45rem', borderRadius: 4, border: `1px solid ${sc.color}55`, background: `${sc.color}18`, color: sc.color, fontWeight: 600 }}>{sc.label}</span>
                    <span style={{ color: '#71717a' }}>{sc.detail}</span>
                  </div>
                )
              })()}
              <ActionButton onClick={() => { flow.setSelectedModel(flow.recommendedModel); flow.resetAction(); flow.setStep('confirm-install') }}>
                Install {flow.recommendedModel.name}
              </ActionButton>
            </SectionCard>
          </li>
        )}

        <li>
          <SectionCard>
            <CardHeading>Use existing Ollama model</CardHeading>
            <CardDescription>Select from models already installed in your local Ollama instance.</CardDescription>
            <ActionButton onClick={() => { flow.resetAction(); flow.setStep('ollama-select') }}>Browse Ollama models</ActionButton>
          </SectionCard>
        </li>

        <li>
          <SectionCard>
            <CardHeading>Use a local GGUF file</CardHeading>
            <CardDescription>Point to a GGUF model file already on your machine. Compatible with llama.cpp.</CardDescription>
            <ActionButton onClick={() => { flow.setGgufPath(''); flow.setGgufPathError(null); flow.resetAction(); flow.setStep('gguf-path') }}>Use a GGUF file</ActionButton>
          </SectionCard>
        </li>

        <li>
          <SectionCard>
            <CardHeading>{mode === 'wizard' ? 'Continue without a model' : 'Text-only demo'}</CardHeading>
            <CardDescription>
              {mode === 'wizard'
                ? 'Try the interface without a model. NPC responses will be scripted — not AI-generated. Response quality is limited compared to a real local model.'
                : 'Try the interface without a model. NPC responses are scripted — not real AI quality.'}
            </CardDescription>
            <ActionButton onClick={() => { flow.resetAction(); flow.setStep('demo-warning') }}>
              {mode === 'wizard' ? 'Continue in text-only demo' : 'Try text-only demo'}
            </ActionButton>
          </SectionCard>
        </li>
      </ul>

      {mode === 'manager' && (
        <div style={{ marginTop: '1.5rem' }}>
          <ActionButton onClick={() => flow.navigate('/')}>Back to Home</ActionButton>
        </div>
      )}
    </div>
  )
}
