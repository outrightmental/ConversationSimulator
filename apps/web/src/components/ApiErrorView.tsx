// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import type { ApiError } from '../api/errors'
import { ERROR_COPY, buildDiagnosticsText } from '../api/errors'

interface ApiErrorViewProps {
  error: ApiError
  onRetry?: () => void
  context?: string
  compact?: boolean
}

export function ApiErrorView({ error, onRetry, context, compact = false }: ApiErrorViewProps) {
  const [copied, setCopied] = useState(false)
  const copy = ERROR_COPY[error.kind]
  // For an http-error the server sent a clean, human-readable business message
  // (e.g. "Unknown scenario_id" or "SHA-256 checksum mismatch"). The content-type
  // guard in client.ts guarantees parser internals never reach this path, so it is
  // safe — and more useful — to surface that message as the cause. Other kinds
  // (network, runtime-unreachable, timeout, schema-mismatch) carry only low-level
  // text, so we keep the designed plain-language description instead.
  const detail =
    error.kind === 'http-error' && error.message ? error.message : copy.description

  function handleCopyDiagnostics() {
    void (async () => {
      try {
        await navigator.clipboard.writeText(buildDiagnosticsText(error, context))
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch {
        // clipboard unavailable in non-secure contexts
      }
    })()
  }

  if (compact) {
    return (
      <span
        role="alert"
        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}
      >
        <span style={{ color: '#f87171', fontSize: '0.8rem' }}>{copy.title}</span>
        {error.kind === 'http-error' && error.message && (
          <span style={{ color: '#a1a1aa', fontSize: '0.8rem' }}>{error.message}</span>
        )}
        {onRetry && (
          <button
            onClick={onRetry}
            style={{
              padding: '0.1rem 0.4rem',
              borderRadius: '3px',
              border: '1px solid rgba(239,68,68,0.4)',
              background: 'transparent',
              color: '#f87171',
              fontSize: '0.72rem',
              cursor: 'pointer',
            }}
          >
            {copy.action}
          </button>
        )}
        <button
          onClick={handleCopyDiagnostics}
          style={{
            padding: '0.1rem 0.4rem',
            borderRadius: '3px',
            border: '1px solid rgba(255,255,255,0.12)',
            background: 'transparent',
            color: '#71717a',
            fontSize: '0.72rem',
            cursor: 'pointer',
          }}
        >
          {copied ? 'Copied!' : 'Copy diagnostics'}
        </button>
      </span>
    )
  }

  return (
    <div
      role="alert"
      style={{
        padding: '0.85rem 1rem',
        background: 'rgba(239,68,68,0.08)',
        border: '1px solid rgba(239,68,68,0.3)',
        borderRadius: '6px',
      }}
    >
      <p style={{ margin: '0 0 0.3rem', fontWeight: 600, color: '#f87171', fontSize: '0.875rem' }}>
        {copy.title}
      </p>
      <p style={{ margin: '0 0 0.75rem', fontSize: '0.825rem', color: '#a1a1aa' }}>
        {detail}
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
        {onRetry && (
          <button
            onClick={onRetry}
            style={{
              padding: '0.3rem 0.75rem',
              borderRadius: '4px',
              border: '1px solid rgba(239,68,68,0.4)',
              background: 'transparent',
              color: '#f87171',
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
          >
            {copy.action}
          </button>
        )}
        <button
          onClick={handleCopyDiagnostics}
          style={{
            padding: '0.3rem 0.75rem',
            borderRadius: '4px',
            border: '1px solid rgba(255,255,255,0.12)',
            background: 'transparent',
            color: '#71717a',
            fontSize: '0.8rem',
            cursor: 'pointer',
          }}
        >
          {copied ? 'Copied!' : 'Copy diagnostics'}
        </button>
      </div>
    </div>
  )
}
