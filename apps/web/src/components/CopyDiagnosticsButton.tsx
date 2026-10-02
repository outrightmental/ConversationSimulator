// SPDX-License-Identifier: Apache-2.0
// One-click "copy the most relevant log excerpts" affordance for error
// surfaces. Renders a small button that assembles a diagnostics report —
// the client-side error details plus a redacted excerpt of the local logs
// (via GET /api/diag/log-excerpt) — and places it on the clipboard.
//
// Design contract: every error the app shows should render one of these
// (directly, or via ApiErrorView / RuntimeRecoveryCard) so a user never has
// to hunt for log files to report a problem. The button must keep working
// when the system is unhealthy: if the core service is unreachable the
// copied report falls back to the client-side details plus a pointer to the
// on-disk logs folder.
import { useEffect, useRef, useState } from 'react'
import type { ApiError } from '../api/errors'
import { buildDiagnosticsText } from '../api/errors'
import { buildDiagnosticsReport } from '../api/diag'
import { copyTextToClipboard } from '../lib/clipboard'

// Re-exported because this module is the documented home of the copy
// affordance; the mechanism itself lives in lib/clipboard.ts, which also has
// to work in the packaged macOS build where neither web clipboard API does
// (issue #508).
export { copyTextToClipboard }

export interface CopyDiagnosticsButtonProps {
  /** Error whose details lead the report (header built via buildDiagnosticsText). */
  error?: ApiError | null
  /** Pre-assembled header — wins over `error` when provided (e.g. render crashes). */
  header?: string
  /** Short tag naming the surface, embedded in the excerpt (e.g. "setup-install:warmup"). */
  context?: string
  label?: string
  compact?: boolean
  style?: React.CSSProperties
}

function defaultHeader(context?: string): string {
  const lines = ['ConversationSimulator diagnostics']
  if (context) lines.push(`context: ${context}`)
  lines.push(`time: ${new Date().toISOString()}`)
  return lines.join('\n')
}

export function CopyDiagnosticsButton({
  error,
  header,
  context,
  label = 'Copy diagnostics',
  compact = false,
  style,
}: CopyDiagnosticsButtonProps) {
  const [status, setStatus] = useState<'idle' | 'busy' | 'copied' | 'failed'>('idle')
  const mounted = useRef(true)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      if (resetTimer.current != null) clearTimeout(resetTimer.current)
    }
  }, [])

  function scheduleReset() {
    if (resetTimer.current != null) clearTimeout(resetTimer.current)
    resetTimer.current = setTimeout(() => {
      if (mounted.current) setStatus('idle')
    }, 2000)
  }

  function handleCopy() {
    void (async () => {
      setStatus('busy')
      // Every path out of here has to reach a verdict. The button is the
      // escape hatch a user reaches for once something has already gone
      // wrong, so a throw while assembling the report must not leave it
      // sitting disabled on "busy" with nothing copied (issue #508) — the
      // client-side header on its own is still worth more to a bug report
      // than an unresponsive button.
      let head = defaultHeader(context)
      let ok = false
      try {
        head =
          header != null && header !== ''
            ? header
            : error != null
              ? buildDiagnosticsText(error, context)
              : head
        ok = await copyTextToClipboard(await buildDiagnosticsReport(head, context))
      } catch {
        try {
          ok = await copyTextToClipboard(head)
        } catch {
          ok = false
        }
      }
      if (!mounted.current) return
      setStatus(ok ? 'copied' : 'failed')
      scheduleReset()
    })()
  }

  const text =
    status === 'copied' ? 'Copied!' : status === 'failed' ? 'Copy failed' : label

  const baseStyle: React.CSSProperties = compact
    ? {
        padding: '0.1rem 0.4rem',
        borderRadius: '3px',
        border: '1px solid rgba(255,255,255,0.12)',
        background: 'transparent',
        color: '#71717a',
        fontSize: '0.72rem',
        cursor: 'pointer',
      }
    : {
        padding: '0.3rem 0.75rem',
        borderRadius: '4px',
        border: '1px solid rgba(255,255,255,0.12)',
        background: 'transparent',
        color: '#71717a',
        fontSize: '0.8rem',
        cursor: 'pointer',
      }

  return (
    <button
      onClick={handleCopy}
      disabled={status === 'busy'}
      data-testid="copy-diagnostics"
      style={{ ...baseStyle, ...style }}
    >
      {text}
    </button>
  )
}
