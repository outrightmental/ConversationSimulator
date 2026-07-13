// SPDX-License-Identifier: Apache-2.0
// Shared UI primitives used by both the FirstRunWizard and ModelManager setup flows.

export function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '1rem' }}>
      {children}
    </div>
  )
}

export function CardHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: '1rem', fontWeight: 600, marginTop: 0, marginBottom: '0.4rem' }}>
      {children}
    </h2>
  )
}

export function CardDescription({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: '0.875rem', color: '#a1a1aa', margin: '0 0 0.75rem' }}>{children}</p>
  )
}

export function ActionButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '0.45rem 1rem',
        borderRadius: '4px',
        border: '1px solid rgba(255,255,255,0.2)',
        background: 'rgba(255,255,255,0.06)',
        color: 'inherit',
        cursor: disabled ? 'wait' : 'pointer',
        fontSize: '0.875rem',
        fontWeight: 500,
      }}
    >
      {children}
    </button>
  )
}

export function PrimaryButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '0.45rem 1rem',
        borderRadius: '4px',
        border: 'none',
        background: disabled ? 'rgba(99,102,241,0.4)' : 'rgba(99,102,241,0.85)',
        color: '#fff',
        cursor: disabled ? 'wait' : 'pointer',
        fontSize: '0.875rem',
        fontWeight: 500,
      }}
    >
      {children}
    </button>
  )
}

export function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <tr>
      <td
        style={{
          color: '#a1a1aa',
          paddingTop: '0.4rem',
          paddingBottom: '0.4rem',
          paddingRight: '1.5rem',
          whiteSpace: 'nowrap',
          verticalAlign: 'top',
        }}
      >
        {label}
      </td>
      <td style={{ paddingTop: '0.4rem', paddingBottom: '0.4rem' }}>{children}</td>
    </tr>
  )
}
