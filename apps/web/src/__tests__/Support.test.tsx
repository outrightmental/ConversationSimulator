// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Support from '../screens/Support'

vi.mock('../api/client', () => ({
  api: {
    createCrashBundle: vi.fn(),
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
      bundle_path: '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
      notice: 'Crash bundle created locally. It is never transmitted automatically. Review the contents and attach it to a GitHub issue manually.',
    })
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /create crash bundle/i }))
    await waitFor(() => expect(mockApi.createCrashBundle).toHaveBeenCalledOnce())
  })

  it('shows the bundle path after successful creation', async () => {
    mockApi.createCrashBundle.mockResolvedValue({
      bundle_path: '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
      notice: 'Crash bundle created locally. It is never transmitted automatically.',
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
      bundle_path: '/home/user/.convsim/logs/crash-reports/crash-2026.zip',
      notice: 'It is never transmitted automatically.',
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
    let resolveBundle!: (v: { bundle_path: string; notice: string }) => void
    mockApi.createCrashBundle.mockReturnValue(
      new Promise<{ bundle_path: string; notice: string }>((r) => { resolveBundle = r }),
    )
    await renderSupport()
    const button = screen.getByRole('button', { name: /create crash bundle/i })
    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    await act(async () => {
      resolveBundle({ bundle_path: '/tmp/crash.zip', notice: 'Local only.' })
    })
  })

  it('shows an error when crash bundle creation fails', async () => {
    mockApi.createCrashBundle.mockRejectedValue(new Error('Core service unavailable'))
    await renderSupport()
    fireEvent.click(screen.getByRole('button', { name: /create crash bundle/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/core service unavailable/i),
    )
    expect(screen.getByTestId('crash-bundle-error')).toBeInTheDocument()
  })
})
