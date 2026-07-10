// SPDX-License-Identifier: Apache-2.0

export interface RecoveryAction {
  label: string
  loadingLabel?: string
  onClick?: () => void
  href?: string
  loading?: boolean
  disabled?: boolean
}

interface RuntimeRecoveryCardProps {
  title: string
  description: string
  errorDetail?: string | null
  /** Path to the log file shown to advanced users. */
  logPath?: string | null
  /** URL of the troubleshooting guide anchor for this failure class. */
  troubleshootingHref: string
  /** Label for the troubleshooting guide link. */
  troubleshootingLabel?: string
  /** Primary action — e.g. "Restart conversation engine". */
  primaryAction?: RecoveryAction
  /** Secondary action — e.g. "Run self-test" or "Get support bundle". */
  secondaryAction?: RecoveryAction
  /** Tertiary action — e.g. "Get support bundle". */
  tertiaryAction?: RecoveryAction
}

const cardStyle: React.CSSProperties = {
  marginTop: '0.75rem',
  padding: '1rem 1.125rem',
  background: 'rgba(239,68,68,0.08)',
  border: '1px solid rgba(239,68,68,0.3)',
  borderRadius: '8px',
}

const titleStyle: React.CSSProperties = {
  margin: '0 0 0.35rem',
  fontWeight: 600,
  color: '#f87171',
  fontSize: '0.875rem',
}

const bodyStyle: React.CSSProperties = {
  margin: '0 0 0.5rem',
  fontSize: '0.825rem',
  color: '#a1a1aa',
}

const detailStyle: React.CSSProperties = {
  margin: '0 0 0.75rem',
  fontSize: '0.8rem',
  color: '#71717a',
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}

const actionRowStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '0.5rem',
  alignItems: 'center',
  marginTop: '0.75rem',
}

const buttonStyle: React.CSSProperties = {
  padding: '0.3rem 0.7rem',
  borderRadius: '4px',
  fontSize: '0.8rem',
  cursor: 'pointer',
  border: '1px solid rgba(239,68,68,0.4)',
  background: 'rgba(239,68,68,0.15)',
  color: '#f87171',
  textDecoration: 'none',
  display: 'inline-block',
}

const buttonDisabledStyle: React.CSSProperties = {
  ...buttonStyle,
  opacity: 0.5,
  cursor: 'wait',
}

const linkStyle: React.CSSProperties = {
  fontSize: '0.8rem',
  color: '#71717a',
}

function ActionButton({ action }: { action: RecoveryAction }) {
  const label = action.loading && action.loadingLabel ? action.loadingLabel : action.label
  const style = action.loading || action.disabled ? buttonDisabledStyle : buttonStyle

  if (action.href) {
    return (
      <a href={action.href} target="_blank" rel="noreferrer" style={style}>
        {label}
      </a>
    )
  }

  return (
    <button
      onClick={action.onClick}
      disabled={action.loading || action.disabled}
      style={style}
    >
      {label}
    </button>
  )
}

export default function RuntimeRecoveryCard({
  title,
  description,
  errorDetail,
  logPath,
  troubleshootingHref,
  troubleshootingLabel = 'Troubleshooting docs',
  primaryAction,
  secondaryAction,
  tertiaryAction,
}: RuntimeRecoveryCardProps) {
  return (
    <div role="alert" style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      <p style={bodyStyle}>{description}</p>
      {errorDetail && <p style={detailStyle}>{errorDetail}</p>}
      {logPath && (
        <p style={{ ...bodyStyle, marginBottom: '0' }}>
          Logs:{' '}
          <code style={{ fontSize: '0.8rem', color: '#71717a' }}>{logPath}</code>
        </p>
      )}

      <div style={actionRowStyle}>
        {primaryAction && <ActionButton action={primaryAction} />}
        {secondaryAction && <ActionButton action={secondaryAction} />}
        {tertiaryAction && <ActionButton action={tertiaryAction} />}
        <a href={troubleshootingHref} target="_blank" rel="noreferrer" style={linkStyle}>
          {troubleshootingLabel}
        </a>
      </div>
    </div>
  )
}
