// SPDX-License-Identifier: Apache-2.0
/**
 * RemediationCard — shown for any preflight check with severity === 'needs-human'.
 *
 * Renders the check's name, plain-language message, a primary fix action (from
 * the check's fix_action), a universal "Try text-only instead" escape hatch, and
 * a collapsible Details section with a copy-ready bug-report block.
 *
 * Vocabulary contract: this component never renders the words "binary", "llama",
 * "sidecar", or "preflight" — those are filtered at the backend before the check
 * reaches this component.
 */
import { useState } from 'react'
import type { PreflightCheck, PreflightFixAction } from '@convsim/shared'
import { useTranslation } from '../i18n'

export interface RemediationCardProps {
  check: PreflightCheck
  /** Called when the primary fix action is triggered. */
  onAction: (action: PreflightFixAction) => void
  /** Called when the user chooses "Try text-only instead". */
  onTextOnly: () => void
  /** Version string shown in the copy block (e.g. from the runtime-handshake check). */
  coreVersion?: string
}

const cardStyle: React.CSSProperties = {
  padding: '1rem 1.125rem',
  marginBottom: '0.75rem',
  background: 'rgba(239,68,68,0.08)',
  border: '1px solid rgba(239,68,68,0.3)',
  borderRadius: '8px',
}

const titleStyle: React.CSSProperties = {
  margin: '0 0 0.4rem',
  fontWeight: 600,
  color: '#f87171',
  fontSize: '1rem',
}

const bodyStyle: React.CSSProperties = {
  margin: '0 0 0.75rem',
  fontSize: '0.875rem',
  color: '#d4d4d8',
  lineHeight: 1.5,
}

const actionRowStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '0.5rem',
  alignItems: 'center',
}

const primaryBtnStyle: React.CSSProperties = {
  padding: '0.4rem 0.9rem',
  borderRadius: '6px',
  border: 'none',
  background: '#3b82f6',
  color: '#fff',
  fontSize: '0.875rem',
  fontWeight: 500,
  cursor: 'pointer',
}

const escapeBtnStyle: React.CSSProperties = {
  padding: '0.4rem 0.9rem',
  borderRadius: '6px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'rgba(255,255,255,0.06)',
  color: '#a1a1aa',
  fontSize: '0.875rem',
  cursor: 'pointer',
}

const detailsToggleStyle: React.CSSProperties = {
  marginTop: '0.75rem',
  background: 'none',
  border: 'none',
  color: '#71717a',
  fontSize: '0.8rem',
  cursor: 'pointer',
  padding: 0,
  textDecoration: 'underline',
}

const detailBoxStyle: React.CSSProperties = {
  marginTop: '0.5rem',
  padding: '0.75rem',
  background: 'rgba(0,0,0,0.25)',
  borderRadius: '6px',
  fontSize: '0.75rem',
  color: '#a1a1aa',
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}

const copyBtnStyle: React.CSSProperties = {
  marginTop: '0.5rem',
  padding: '0.25rem 0.6rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'rgba(255,255,255,0.06)',
  color: '#93c5fd',
  fontSize: '0.75rem',
  cursor: 'pointer',
}

function buildCopyBlock(check: PreflightCheck, coreVersion?: string): string {
  const lines = [
    '--- Bug report ---',
    `Check ID: ${check.id}`,
    `Status: ${check.status}`,
    `Details: ${check.message}`,
  ]
  if (check.detail) {
    lines.push(`Data: ${JSON.stringify(check.detail)}`)
  }
  if (coreVersion) {
    lines.push(`Core version: ${coreVersion}`)
  }
  lines.push(`Platform: ${navigator.platform}`)
  lines.push(`User agent: ${navigator.userAgent}`)
  return lines.join('\n')
}

export function RemediationCard({ check, onAction, onTextOnly, coreVersion }: RemediationCardProps) {
  const { t } = useTranslation()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    const block = buildCopyBlock(check, coreVersion)
    void navigator.clipboard.writeText(block).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div role="alert" style={cardStyle} data-testid={`remediation-card-${check.id}`}>
      <p style={titleStyle}>{check.name}</p>
      <p style={bodyStyle}>{check.message}</p>

      <div style={actionRowStyle}>
        {check.fix_action && (
          <button
            style={primaryBtnStyle}
            onClick={() => onAction(check.fix_action!)}
            data-testid={`remediation-action-${check.id}`}
          >
            {check.fix_action.label}
          </button>
        )}
        <button
          style={escapeBtnStyle}
          onClick={onTextOnly}
          data-testid={`remediation-text-only-${check.id}`}
        >
          {t('setup.remediation.textOnly')}
        </button>
      </div>

      <button
        style={detailsToggleStyle}
        onClick={() => setDetailsOpen((o) => !o)}
        aria-expanded={detailsOpen}
        data-testid={`remediation-details-toggle-${check.id}`}
      >
        {detailsOpen ? t('setup.remediation.detailsOpen') : t('setup.remediation.detailsClosed')}
      </button>

      {detailsOpen && (
        <div>
          <div style={detailBoxStyle} data-testid={`remediation-details-${check.id}`}>
            {buildCopyBlock(check, coreVersion)}
          </div>
          <button
            style={copyBtnStyle}
            onClick={handleCopy}
            data-testid={`remediation-copy-${check.id}`}
          >
            {copied ? t('setup.remediation.copied') : t('setup.remediation.copy')}
          </button>
        </div>
      )}
    </div>
  )
}
