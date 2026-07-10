// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ApiErrorView } from '../components/ApiErrorView'
import { ERROR_COPY, type ErrorKind, type ApiError } from '../api/errors'

const ALL_KINDS: ErrorKind[] = [
  'runtime-unreachable',
  'network',
  'http-error',
  'schema-mismatch',
  'timeout',
]

// The offending string from issue #294 — parser internals that once reached the
// DOM ("Could not load packs: Unexpected token '<', "<!doctype "... is not valid
// JSON"). No rendered degraded state may ever contain it.
const FORBIDDEN = ['Unexpected token', '<!doctype', '<html', 'is not valid JSON']

function assertNoRawStrings(html: string) {
  for (const needle of FORBIDDEN) {
    expect(html).not.toContain(needle)
  }
}

describe('ApiErrorView — designed degraded state for every ErrorKind', () => {
  it.each(ALL_KINDS)('renders a designed title, recovery action, and Copy diagnostics for %s', (kind) => {
    const error: ApiError = { kind, message: 'low-level detail that must not be shown raw' }
    render(<ApiErrorView error={error} onRetry={() => {}} />)

    // Plain-language cause (designed title from the single copy module).
    expect(screen.getByText(ERROR_COPY[kind].title)).toBeInTheDocument()
    // Exactly one primary recovery action + a "Copy diagnostics" secondary action.
    expect(screen.getByRole('button', { name: ERROR_COPY[kind].action })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy diagnostics/i })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})

// CI grep gate: for every kind whose ApiError.message carries only low-level text
// (everything except http-error, whose message is a guaranteed-clean server
// business message per the client content-type guard), the raw message must never
// reach the DOM — only the designed copy does. Feed the exact parser leak from
// issue #294 as the message and assert it can never appear in a rendered state.
describe('CI grep gate — parser internals never reach rendered UI', () => {
  const PARSER_LEAK = `Unexpected token '<', "<!doctype "... is not valid JSON`
  const LOW_LEVEL_KINDS = ALL_KINDS.filter((k) => k !== 'http-error')

  it.each(LOW_LEVEL_KINDS)('does not surface parser internals for %s (full view)', (kind) => {
    const { container } = render(
      <ApiErrorView error={{ kind, message: PARSER_LEAK }} onRetry={() => {}} />,
    )
    assertNoRawStrings(container.innerHTML)
  })

  it.each(LOW_LEVEL_KINDS)('does not surface parser internals for %s (compact view)', (kind) => {
    const { container } = render(
      <ApiErrorView error={{ kind, message: PARSER_LEAK }} onRetry={() => {}} compact />,
    )
    assertNoRawStrings(container.innerHTML)
  })
})
