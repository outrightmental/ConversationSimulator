// SPDX-License-Identifier: Apache-2.0

interface UpdateBannerProps {
  version: string
  releaseUrl: string
  onViewNotes: () => void
  onInstall: () => void
  onDismiss: () => void
}

// Non-nagging beta update banner. Only shown on the Home screen — never
// during an active Conversation session. The "View notes" and "Install"
// actions both open the GitHub release page so the user can download
// the latest build manually (auto-install via the Tauri updater requires
// signing infrastructure from #235; this is a safe fallback in the interim).
export default function UpdateBanner({
  version,
  releaseUrl,
  onViewNotes,
  onInstall,
  onDismiss,
}: UpdateBannerProps) {
  return (
    <div
      role="status"
      aria-label="Beta update available"
      data-testid="update-banner"
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '0.5rem',
        padding: '0.65rem 1rem',
        borderRadius: 6,
        border: '1px solid rgba(99,102,241,0.35)',
        background: 'rgba(99,102,241,0.07)',
        fontSize: '0.875rem',
        marginBottom: '1rem',
      }}
    >
      <span style={{ color: '#c7d2fe' }}>
        Beta update available —{' '}
        <strong style={{ color: '#e0e7ff' }}>v{version}</strong>
      </span>
      <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
        <a
          href={releaseUrl}
          target="_blank"
          rel="noreferrer"
          onClick={onViewNotes}
          aria-label={`View release notes for v${version}`}
          style={{
            padding: '0.25rem 0.65rem',
            borderRadius: 4,
            border: '1px solid rgba(99,102,241,0.4)',
            background: 'transparent',
            color: '#a5b4fc',
            fontSize: '0.8rem',
            textDecoration: 'none',
            cursor: 'pointer',
          }}
        >
          View notes
        </a>
        <button
          onClick={onInstall}
          aria-label={`Install beta update v${version}`}
          style={{
            padding: '0.25rem 0.65rem',
            borderRadius: 4,
            border: '1px solid rgba(99,102,241,0.5)',
            background: 'rgba(99,102,241,0.18)',
            color: '#c7d2fe',
            fontSize: '0.8rem',
            cursor: 'pointer',
          }}
        >
          Install
        </button>
        <button
          onClick={onDismiss}
          aria-label="Dismiss update notice"
          style={{
            background: 'none',
            border: 'none',
            color: '#6366f1',
            cursor: 'pointer',
            padding: '0 0.25rem',
            fontSize: '1rem',
            lineHeight: 1,
            opacity: 0.7,
          }}
        >
          ×
        </button>
      </div>
    </div>
  )
}
