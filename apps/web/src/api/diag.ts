// SPDX-License-Identifier: Apache-2.0
// Diagnostics helpers for the "Copy diagnostics" action on error surfaces.
//
// Every error card in the app offers a one-click copy of the client-side
// error details PLUS the most relevant local log excerpts, so a user can
// paste a complete, triage-able report into a GitHub issue without hunting
// for log files. The excerpt comes from GET /api/diag/log-excerpt (assembled
// and redacted locally by convsim-core; never transmitted anywhere).
//
// This module must be safe to call while the system is unhealthy: the fetch
// is bounded by a short timeout and every failure resolves to a fallback
// note instead of throwing into the error surface that invoked it.
import { getLogExcerptRaw } from './client'

export interface LogExcerptResponse {
  excerpt: string
  sources: string[]
  notice: string
}

const EXCERPT_TIMEOUT_MS = 4000

// Where the logs live per platform (mirrors convsim_core/paths.py). Shown
// only when the core service cannot be reached, so the copied report still
// tells the user where to find logs by hand.
const LOGS_FOLDER_HINTS = [
  'macOS:   ~/Library/Application Support/com.outrightmental.convsim/logs',
  'Windows: %LOCALAPPDATA%\\outrightmental\\convsim\\logs',
  'Linux:   ~/.local/share/convsim/logs',
]

export const EXCERPT_UNAVAILABLE_NOTE = [
  '(log excerpts unavailable — the local service could not be reached)',
  'Logs folder:',
  ...LOGS_FOLDER_HINTS.map((hint) => `  ${hint}`),
].join('\n')

/**
 * Fetch the redacted local log excerpt, or null when the core service is
 * unreachable, slow, or returns an unexpected payload. Never throws.
 */
export async function fetchLogExcerpt(
  context?: string,
): Promise<LogExcerptResponse | null> {
  const data = await getLogExcerptRaw(context, EXCERPT_TIMEOUT_MS)
  if (
    typeof data === 'object' &&
    data !== null &&
    typeof (data as { excerpt?: unknown }).excerpt === 'string' &&
    Array.isArray((data as { sources?: unknown }).sources)
  ) {
    const payload = data as { excerpt: string; sources: unknown[]; notice?: unknown }
    return {
      excerpt: payload.excerpt,
      sources: payload.sources.filter((s): s is string => typeof s === 'string'),
      notice: typeof payload.notice === 'string' ? payload.notice : '',
    }
  }
  return null
}

/**
 * Build the full diagnostics report placed on the clipboard: the caller's
 * client-side header followed by the local log excerpt (or a fallback note
 * pointing at the logs folder when the core service is unreachable).
 */
export async function buildDiagnosticsReport(
  header: string,
  context?: string,
): Promise<string> {
  const excerpt = await fetchLogExcerpt(context)
  const body = excerpt != null ? excerpt.excerpt : EXCERPT_UNAVAILABLE_NOTE
  return `${header}\n\n${body}`
}
