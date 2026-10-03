// SPDX-License-Identifier: Apache-2.0
import { SectionCard, CardHeading, CardDescription, ActionButton } from '../primitives'
import type { UseSetupFlowReturn } from '../useSetupFlow'
import { useIsDemo } from '../../edition'

interface SpeedClass { label: string; color: string; detail: string }

function modelSpeedClass(role: string | null): SpeedClass {
  switch (role) {
    // The sub-starter tier: smallest download, lowest VRAM floor, least
    // consistent NPC. No measured TTFT range is quoted because it has not been
    // through the latency smoke the other tiers' numbers come from.
    case 'lightweight': return { label: 'Fastest', color: '#6ee7b7', detail: 'Smallest download; runs on 2 GB VRAM' }
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
  // Demo edition (issue #495): the curated model is the only option.
  const isDemo = useIsDemo()
  // Whether the recommended model is already installed and ready. In the demo
  // the manager is reachable with the model live (Home's LLM badge, the
  // finish-setup banner), and offering to "Install" it again would run a
  // no-op pipeline and bounce the player home.
  const recommendedInstalled =
    flow.recommendedModel != null &&
    (flow.modelsData?.installed ?? []).some(
      (m) =>
        m.registry_id === flow.recommendedModel!.id &&
        (m.install_status === 'ready' || m.install_status === 'complete'),
    )

  return (
    <div style={{ maxWidth: '640px', margin: mode === 'wizard' ? '2rem auto' : undefined, padding: mode === 'wizard' ? '0 1rem' : undefined }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>
        {mode === 'wizard' ? 'Choose how to get started' : 'Set up your model'}
      </h1>
      <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
        {isDemo
          ? 'The demo uses one AI model. It downloads once and then runs entirely on your computer.'
          : mode === 'wizard' ? 'Pick an option below. You can change it later in Settings.' : 'Choose how to get started. You can change this later in Settings.'}
      </p>

      {isDemo && !flow.recommendedModel && (
        <p role="alert" style={{ marginTop: '1rem', color: '#f87171', fontSize: '0.875rem' }}>
          The demo model is not available from the conversation engine. Restart the app and try again.
        </p>
      )}

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
                    // Block-level flex, not inline-flex: as an inline box this
                    // row shared a line with the install button below it, and
                    // the button painted over the tail of the speed detail.
                    style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem', fontSize: '0.8rem' }}
                  >
                    <span style={{ padding: '0.1rem 0.45rem', borderRadius: 4, border: `1px solid ${sc.color}55`, background: `${sc.color}18`, color: sc.color, fontWeight: 600 }}>{sc.label}</span>
                    <span style={{ color: '#71717a' }}>{sc.detail}</span>
                  </div>
                )
              })()}
              {isDemo && recommendedInstalled ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <span data-testid="demo-model-installed" style={{ color: '#6ee7b7', fontSize: '0.875rem', fontWeight: 600 }}>
                    ✓ Installed and ready
                  </span>
                  <ActionButton onClick={() => flow.navigate('/')}>Back to Home</ActionButton>
                </div>
              ) : (
                <ActionButton onClick={() => { flow.setSelectedModel(flow.recommendedModel); flow.resetAction(); flow.setStep('confirm-install') }}>
                  Install {flow.recommendedModel.name}
                </ActionButton>
              )}
            </SectionCard>
          </li>
        )}

        {!isDemo && (
        <li>
          <SectionCard>
            <CardHeading>Use existing Ollama model</CardHeading>
            <CardDescription>Select from models already installed in your local Ollama instance.</CardDescription>
            <ActionButton onClick={() => { flow.resetAction(); flow.setStep('ollama-select') }}>Browse Ollama models</ActionButton>
          </SectionCard>
        </li>
        )}

        {!isDemo && (
        <li>
          <SectionCard>
            <CardHeading>Use a local GGUF file</CardHeading>
            <CardDescription>Point to a GGUF model file already on your machine. Compatible with llama.cpp.</CardDescription>
            <ActionButton onClick={() => { flow.setGgufPath(''); flow.setGgufPathError(null); flow.resetAction(); flow.setStep('gguf-path') }}>Use a GGUF file</ActionButton>
          </SectionCard>
        </li>
        )}
      </ul>

      {mode === 'manager' && (
        <div style={{ marginTop: '1.5rem' }}>
          <ActionButton onClick={() => flow.navigate('/')}>Back to Home</ActionButton>
        </div>
      )}
    </div>
  )
}
