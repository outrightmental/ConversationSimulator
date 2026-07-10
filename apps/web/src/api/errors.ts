// SPDX-License-Identifier: Apache-2.0

export type ErrorKind =
  | 'runtime-unreachable'
  | 'http-error'
  | 'schema-mismatch'
  | 'timeout'
  | 'network'

export interface ApiError {
  kind: ErrorKind
  message: string
  status?: number
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError }

interface ErrorCopy {
  title: string
  description: string
  action: string
}

export const ERROR_COPY: Record<ErrorKind, ErrorCopy> = {
  'runtime-unreachable': {
    title: 'Local runtime is unavailable',
    description:
      'The local service is not responding. Make sure the application started correctly, then try again.',
    action: 'Try again',
  },
  network: {
    title: 'Connection failed',
    description:
      'Could not reach the local service. Check that the application is running, then try again.',
    action: 'Try again',
  },
  'http-error': {
    title: 'Request failed',
    description: 'The local service returned an error. Copy diagnostics for details.',
    action: 'Try again',
  },
  'schema-mismatch': {
    title: 'Unexpected response format',
    description:
      'The service returned data in an unexpected format. This may be a version mismatch between the UI and the runtime.',
    action: 'Try again',
  },
  timeout: {
    title: 'Request timed out',
    description:
      'The service did not respond in time. It may be busy starting up — wait a moment and try again.',
    action: 'Try again',
  },
}

// A single-line, plain-language headline for an error, used by compact inline
// surfaces that render their own markup instead of a full ApiErrorView. Mirrors
// ApiErrorView's logic: an http-error carries a clean server message worth
// showing; every other kind maps to its designed title (never a raw string).
export function errorHeadline(error: ApiError): string {
  if (error.kind === 'http-error' && error.message) return error.message
  return ERROR_COPY[error.kind].title
}


export function buildDiagnosticsText(error: ApiError, context?: string): string {
  const lines: string[] = ['ConversationSimulator diagnostics', `kind: ${error.kind}`]
  if (error.status !== undefined) lines.push(`status: ${error.status}`)
  lines.push(`message: ${error.message}`)
  if (context) lines.push(`context: ${context}`)
  lines.push(`time: ${new Date().toISOString()}`)
  return lines.join('\n')
}
