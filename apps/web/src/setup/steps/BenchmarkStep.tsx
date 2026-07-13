// SPDX-License-Identifier: Apache-2.0
import { PrimaryButton } from '../primitives'
import { errorMessage } from '../errorMessage'
import type { UseSetupFlowReturn } from '../useSetupFlow'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'

interface BenchmarkStepProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
  onComplete: () => void
}

export function BenchmarkStep({ flow, mode, onComplete }: BenchmarkStepProps) {
  const errMsg = flow.benchmarkError ? errorMessage(flow.benchmarkError) : null

  return (
    <div style={mode === 'wizard' ? { maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' } : { maxWidth: '640px' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Model benchmark</h1>
      <p style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
        Running a short benchmark to measure generation speed and check hardware compatibility.
      </p>

      {flow.benchmarkRunning && (
        <p role="status" style={{ marginTop: '1rem' }}>
          Running benchmark…
        </p>
      )}

      {flow.benchmarkResult != null && !flow.benchmarkRunning && (
        <div>
          <table style={{ marginTop: '1rem', borderCollapse: 'collapse' }}>
            <tbody>
              <tr>
                <td style={{ color: '#a1a1aa', paddingTop: '0.4rem', paddingBottom: '0.4rem', paddingRight: '1.5rem', whiteSpace: 'nowrap', verticalAlign: 'top' }}>Speed</td>
                <td style={{ paddingTop: '0.4rem', paddingBottom: '0.4rem' }}>{flow.benchmarkResult.tokens_per_sec.toFixed(1)} tokens/sec</td>
              </tr>
              {flow.benchmarkResult.context_length != null && (
                <tr>
                  <td style={{ color: '#a1a1aa', paddingTop: '0.4rem', paddingBottom: '0.4rem', paddingRight: '1.5rem', whiteSpace: 'nowrap', verticalAlign: 'top' }}>Context window</td>
                  <td style={{ paddingTop: '0.4rem', paddingBottom: '0.4rem' }}>{flow.benchmarkResult.context_length.toLocaleString()} tokens</td>
                </tr>
              )}
              <tr>
                <td style={{ color: '#a1a1aa', paddingTop: '0.4rem', paddingBottom: '0.4rem', paddingRight: '1.5rem', whiteSpace: 'nowrap', verticalAlign: 'top' }}>Runtime</td>
                <td style={{ paddingTop: '0.4rem', paddingBottom: '0.4rem' }}>{flow.benchmarkResult.runtime_id}</td>
              </tr>
            </tbody>
          </table>

          {flow.benchmarkResult.warnings.length > 0 && (
            <div
              role="alert"
              aria-label="benchmark warnings"
              style={{ marginTop: '1rem', background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)', borderRadius: '6px', padding: '0.75rem 1rem' }}
            >
              <p style={{ margin: '0 0 0.5rem', fontWeight: 600, color: '#fbbf24', fontSize: '0.875rem' }}>Performance warnings</p>
              <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.875rem', color: '#fde68a' }}>
                {flow.benchmarkResult.warnings.map((w, i) => (
                  <li key={i} style={{ marginBottom: '0.3rem' }}>{w}</li>
                ))}
              </ul>
              <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: '#a1a1aa' }}>
                If generation is slow, try a smaller model or check that GPU acceleration is enabled in your runtime settings.{' '}
                <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer">Setup docs</a>
              </p>
            </div>
          )}
        </div>
      )}

      {errMsg != null && !flow.benchmarkRunning && (
        <div
          role="alert"
          style={{ marginTop: '1rem', padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px' }}
        >
          <p style={{ margin: '0 0 0.4rem', color: '#f87171', fontSize: '0.875rem' }}>Benchmark failed: {errMsg}</p>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#a1a1aa' }}>Your model is still selected and ready to use. The benchmark is optional.</p>
        </div>
      )}

      <div style={{ marginTop: '1.5rem' }}>
        <PrimaryButton disabled={flow.benchmarkRunning} onClick={onComplete}>
          {flow.benchmarkRunning ? 'Running…' : 'Continue to Home'}
        </PrimaryButton>
      </div>
    </div>
  )
}
