// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Support from '../screens/Support'

vi.mock('../api/client', () => ({
  api: {
    createCrashBundle: vi.fn(),
    preflight: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

async function renderSupport() {
  render(
    <MemoryRouter>
      <Support />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Page heading and privacy note
// ---------------------------------------------------------------------------

describe('support screen layout', () => {
  it('renders the Support heading', async () => {
    await renderSupport()
    expect(screen.getByRole('heading', { name: /support/i, level: 1 })).toBeInTheDocument()
  })

  it('shows a privacy reminder that nothing is uploaded automatically', async () => {
    await renderSupport()
    expect(screen.getByText(/nothing is uploaded automatically/i)).toBeInTheDocument()
  })

  it('shows a local-first privacy reminder section', async () => {
    await renderSupport()
    expect(screen.getByText(/local-first/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Issue template links
// ---------------------------------------------------------------------------

describe('issue template links', () => {
  it('renders a link for bug_report template', async () => {
    await renderSupport()
    const link = screen.getByTestId('issue-template-bug_report')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', expect.stringContaining('bug_report.yml'))
  })

  it('renders a link for steam_platform_bug template', async () => {
    await renderSupport()
    const link = screen.getByTestId('issue-template-steam_platform_bug')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', expect.stringContaining('steam_platform_bug.yml'))
  })

  it('renders a link for model_compatibility template', async () => {
    await renderSupport()
    const link = screen.getByTestId('issue-template-model_compatibility')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', expect.stringContaining('model_compatibility.yml'))
  })

  it('renders a link for safety_issue template', async () => {
    await renderSupport()
    const link = screen.getByTestId('issue-template-safety_issue')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', expect.stringContaining('safety_issue.yml'))
  })

  it('all issue template links open externally', async () => {
    await renderSupport()
    const link = screen.getByTestId('issue-template-bug_report')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})

// ---------------------------------------------------------------------------
// Crash bundle
// ---------------------------------------------------------------------------

describe('crash bundle', () => {
  it('shows a Create crash bundle button', async () => {
    await renderSupport()
    expect(screen.getByRole('button', { name: /create crash bundle/i })).toBeInTheDocument()
  })

  it('shows a privacy note that the bundle is never uploaded automatically', async () => {
    await renderSupport()
    expect(screen.getByText(/never transmitted automatically|not uploaded automatically|must attach it.*manually/i)).toBeInTheDocument()
  })

  it('shows a reminder to review the bundle before attaching', async () => {
    await renderSupport()
    expect(screen.getByRole('note', { name: /crash bundle privacy note/i })).toBeInTheDocument()
    expect(screen.getByText(/review the bundle contents/i)).toBeInTheDocument()
  })

  it('calls createCrashBundle when the button is clicked', async () => {
    mockApi.createCrashBundle.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
        notice: 'Crash bundle created locally. It is never transmitted automatically. Review the contents and attach it to a GitHub issue manually.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /create crash bundle/i }))
    await waitFor(() => expect(mockApi.createCrashBundle).toHaveBeenCalledOnce())
  })

  it('shows the bundle path after successful creation', async () => {
    mockApi.createCrashBundle.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
        notice: 'Crash bundle created locally. It is never transmitted automatically.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /create crash bundle/i }))
    await waitFor(() =>
      expect(screen.getByTestId('crash-bundle-path')).toHaveTextContent(
        '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
      ),
    )
  })

  it('shows the notice text after successful creation', async () => {
    mockApi.createCrashBundle.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
        notice: 'It is never transmitted automatically.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /create crash bundle/i }))
    await waitFor(() =>
      expect(screen.getByTestId('crash-bundle-notice')).toHaveTextContent(
        /never transmitted automatically/i,
      ),
    )
  })

  it('disables the button while creating', async () => {
    let resolveBundle!: (v: { ok: true; data: { bundle_path: string; notice: string } }) => void
    mockApi.createCrashBundle.mockReturnValue(
      new Promise<{ ok: true; data: { bundle_path: string; notice: string } }>((r) => { resolveBundle = r }),
    )
    await renderSupport()
    const button = screen.getByRole('button', { name: /create crash bundle/i })
    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    await act(async () => {
      resolveBundle({ ok: true, data: { bundle_path: '/tmp/crash.zip', notice: 'Local only.' } })
    })
  })

  it('shows an error when crash bundle creation fails', async () => {
    mockApi.createCrashBundle.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'Core service unavailable' },
    })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /create crash bundle/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/connection failed/i),
    )
    expect(screen.getByTestId('crash-bundle-error')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Self-test
// ---------------------------------------------------------------------------

const PASS_PREFLIGHT = {
  overall: 'pass' as const,
  ran_at: '2026-01-01T00:00:00.000+00:00',
  checks: [
    { id: 'runtime-handshake', name: 'Runtime handshake', status: 'pass' as const, message: 'convsim-core 0.1.0 is running.', fix_action: null },
    { id: 'llm-present', name: 'Language model', status: 'pass' as const, message: '1 model installed and ready.', fix_action: null },
  ],
}

const FAIL_PREFLIGHT = {
  overall: 'fail' as const,
  ran_at: '2026-01-01T00:00:00.000+00:00',
  checks: [
    { id: 'llama-cpp-binary', name: 'Inference engine', status: 'fail' as const, message: 'llama-server binary not found.', fix_action: { kind: 'open-url' as const, href: 'https://example.com/setup', label: 'Setup guide' } },
    { id: 'llm-present', name: 'Language model', status: 'fail' as const, message: 'No language model installed.', fix_action: { kind: 'navigate' as const, href: '/model-manager', label: 'Open Model Manager' } },
  ],
}

describe('self-test', () => {
  it('shows a Run self-test button', async () => {
    await renderSupport()
    expect(screen.getByRole('button', { name: /run self-test/i })).toBeInTheDocument()
  })

  it('calls preflight when the button is clicked', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: PASS_PREFLIGHT })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /run self-test/i }))
    await waitFor(() => expect(mockApi.preflight).toHaveBeenCalledOnce())
  })

  it('disables the button while running', async () => {
    let resolvePreflight!: (v: { ok: true; data: typeof PASS_PREFLIGHT }) => void
    mockApi.preflight.mockReturnValue(
      new Promise<{ ok: true; data: typeof PASS_PREFLIGHT }>((r) => { resolvePreflight = r }),
    )
    await renderSupport()
    const button = screen.getByRole('button', { name: /run self-test/i })
    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    await act(async () => {
      resolvePreflight({ ok: true, data: PASS_PREFLIGHT })
    })
  })

  it('shows results after a successful self-test', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: PASS_PREFLIGHT })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /run self-test/i }))
    await waitFor(() => expect(screen.getByTestId('preflight-results')).toBeInTheDocument())
  })

  it('shows check results with correct statuses', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: PASS_PREFLIGHT })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /run self-test/i }))
    await waitFor(() => expect(screen.getByTestId('preflight-check-runtime-handshake')).toBeInTheDocument())
  })

  it('shows fix action buttons for failing checks', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: FAIL_PREFLIGHT })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /run self-test/i }))
    await waitFor(() =>
      expect(screen.getByTestId('preflight-fix-llama-cpp-binary')).toBeInTheDocument(),
    )
  })

  it('shows overall fail status when preflight fails', async () => {
    mockApi.preflight.mockResolvedValue({ ok: true, data: FAIL_PREFLIGHT })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /run self-test/i }))
    await waitFor(() =>
      expect(screen.getByText(/overall:.*fail/i)).toBeInTheDocument(),
    )
  })

  it('shows an error when preflight call fails', async () => {
    mockApi.preflight.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'Core service unavailable' },
    })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /run self-test/i }))
    await waitFor(() =>
      expect(screen.getByTestId('self-test-error')).toBeInTheDocument(),
    )
  })
})
