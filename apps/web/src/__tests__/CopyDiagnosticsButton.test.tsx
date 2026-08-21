// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CopyDiagnosticsButton } from '../components/CopyDiagnosticsButton'
import { fetchLogExcerpt, EXCERPT_UNAVAILABLE_NOTE } from '../api/diag'
import type { ApiError } from '../api/errors'

const EXCERPT_PAYLOAD = {
  excerpt: 'ConversationSimulator log excerpt\n── runtime.log ──\nllama-server exited early (code 137)',
  sources: ['runtime.log'],
  notice: 'Log excerpt assembled locally. It is never transmitted automatically.',
}

function mockFetchOk() {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(EXCERPT_PAYLOAD),
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

function mockFetchFail() {
  const fn = vi.fn().mockRejectedValue(new TypeError('fetch failed'))
  vi.stubGlobal('fetch', fn)
  return fn
}

function mockClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  })
  return writeText
}

const SAMPLE_ERROR: ApiError = {
  kind: 'http-error',
  message: 'Model downloaded but failed to start: llama-server exited early (code 137).',
  status: 500,
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

afterEach(() => {
  vi.unstubAllGlobals()
  // Remove the per-test clipboard stub so tests stay independent.
  delete (navigator as unknown as { clipboard?: unknown }).clipboard
})

describe('CopyDiagnosticsButton', () => {
  it('renders the default label', () => {
    mockFetchOk()
    render(<CopyDiagnosticsButton error={SAMPLE_ERROR} />)
    expect(screen.getByRole('button', { name: 'Copy diagnostics' })).toBeInTheDocument()
  })

  it('copies error header plus fetched log excerpt, then confirms', async () => {
    const fetchMock = mockFetchOk()
    const writeText = mockClipboard()
    render(<CopyDiagnosticsButton error={SAMPLE_ERROR} context="setup-install:warmup" />)

    fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostics' }))
    expect(await screen.findByText('Copied!')).toBeInTheDocument()

    // Requested the excerpt endpoint with the context tag.
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/diag/log-excerpt')
    expect(url).toContain(encodeURIComponent('setup-install:warmup'))

    const copied = String(writeText.mock.calls[0][0])
    // Client-side error details lead the report…
    expect(copied).toContain('kind: http-error')
    expect(copied).toContain('Model downloaded but failed to start')
    expect(copied).toContain('context: setup-install:warmup')
    // …followed by the server-assembled log excerpt.
    expect(copied).toContain('llama-server exited early (code 137)')
  })

  it('falls back to a logs-folder pointer when the core service is unreachable', async () => {
    mockFetchFail()
    const writeText = mockClipboard()
    render(<CopyDiagnosticsButton error={SAMPLE_ERROR} />)

    fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostics' }))
    expect(await screen.findByText('Copied!')).toBeInTheDocument()

    const copied = String(writeText.mock.calls[0][0])
    expect(copied).toContain('kind: http-error')
    expect(copied).toContain('log excerpts unavailable')
    expect(copied).toContain('Logs folder:')
  })

  it('prefers an explicit header over the error prop', async () => {
    mockFetchOk()
    const writeText = mockClipboard()
    render(
      <CopyDiagnosticsButton
        header={'ConversationSimulator diagnostics\nkind: render-error\nmessage: boom'}
        error={SAMPLE_ERROR}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostics' }))
    expect(await screen.findByText('Copied!')).toBeInTheDocument()

    const copied = String(writeText.mock.calls[0][0])
    expect(copied).toContain('kind: render-error')
    expect(copied).not.toContain('kind: http-error')
  })

  it('shows a failure state when no clipboard mechanism works', async () => {
    mockFetchOk()
    // No navigator.clipboard, and execCommand is unavailable in this test.
    render(<CopyDiagnosticsButton error={SAMPLE_ERROR} />)

    fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostics' }))
    expect(await screen.findByText('Copy failed')).toBeInTheDocument()
  })

  it('supports a custom label', () => {
    mockFetchOk()
    render(<CopyDiagnosticsButton error={SAMPLE_ERROR} label="Copy log excerpt" />)
    expect(screen.getByRole('button', { name: 'Copy log excerpt' })).toBeInTheDocument()
  })
})

describe('fetchLogExcerpt', () => {
  it('returns the payload on success', async () => {
    mockFetchOk()
    const result = await fetchLogExcerpt('test-context')
    expect(result).not.toBeNull()
    expect(result!.excerpt).toContain('llama-server exited early')
    expect(result!.sources).toEqual(['runtime.log'])
  })

  it('returns null on network failure', async () => {
    mockFetchFail()
    expect(await fetchLogExcerpt()).toBeNull()
  })

  it('returns null on a non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) }))
    expect(await fetchLogExcerpt()).toBeNull()
  })

  it('returns null on a malformed payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ nope: true }) }),
    )
    expect(await fetchLogExcerpt()).toBeNull()
  })

  it('exposes a fallback note that names the logs folder per platform', () => {
    expect(EXCERPT_UNAVAILABLE_NOTE).toContain('macOS')
    expect(EXCERPT_UNAVAILABLE_NOTE).toContain('Windows')
    expect(EXCERPT_UNAVAILABLE_NOTE).toContain('Linux')
  })
})
