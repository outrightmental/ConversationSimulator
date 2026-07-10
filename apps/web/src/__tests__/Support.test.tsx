// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Support from '../screens/Support'

vi.mock('../api/client', () => ({
  api: {
    createCrashBundle: vi.fn(),
    createBetaReport: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

const BETA_MANIFEST = [
  'versions.json — app, Python, and OS versions',
  'system.txt — OS name, release, architecture',
  'config.json — settings (home directory replaced with ~)',
  'preflight.json — runtime / STT / TTS health snapshot',
  'recent_errors.txt — last log lines at WARNING or above (no conversation content)',
  'README.txt — privacy notice',
]

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
// Report a problem (beta one-click flow)
// ---------------------------------------------------------------------------

describe('report a problem', () => {
  it('shows a Report a problem button', async () => {
    await renderSupport()
    expect(screen.getByTestId('report-problem-button')).toBeInTheDocument()
  })

  it('clicking Report a problem opens the consent screen', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    expect(screen.getByTestId('beta-report-consent')).toBeInTheDocument()
  })

  it('consent screen shows a preview of the bundle manifest', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    expect(screen.getByTestId('beta-report-manifest-preview')).toBeInTheDocument()
    expect(screen.getByTestId('beta-report-manifest-preview')).toHaveTextContent(/versions\.json/i)
    expect(screen.getByTestId('beta-report-manifest-preview')).toHaveTextContent(/preflight\.json/i)
  })

  it('consent screen shows the privacy note', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    expect(screen.getByRole('note', { name: /beta report privacy note/i })).toBeInTheDocument()
  })

  it('session metadata checkbox is unchecked by default', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    const checkbox = screen.getByTestId('include-session-metadata-checkbox') as HTMLInputElement
    expect(checkbox.checked).toBe(false)
  })

  it('session_metadata.json appears in preview when checkbox is checked', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    const checkbox = screen.getByTestId('include-session-metadata-checkbox')
    fireEvent.click(checkbox)
    expect(screen.getByTestId('beta-report-manifest-preview')).toHaveTextContent(/session_metadata\.json/i)
  })

  it('session_metadata.json does not appear in preview when checkbox is unchecked', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    expect(screen.getByTestId('beta-report-manifest-preview')).not.toHaveTextContent(/session_metadata\.json/i)
  })

  it('Cancel button hides the consent screen', async () => {
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('cancel-beta-report-button'))
    expect(screen.queryByTestId('beta-report-consent')).not.toBeInTheDocument()
    expect(screen.getByTestId('report-problem-button')).toBeInTheDocument()
  })

  it('clicking Create bundle calls createBetaReport with include_session_metadata=false by default', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/tmp/beta-report.zip',
        manifest: BETA_MANIFEST,
        notice: 'Beta report bundle created locally. It is never transmitted automatically.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() => expect(mockApi.createBetaReport).toHaveBeenCalledWith(false))
  })

  it('clicking Create bundle with opt-in passes include_session_metadata=true', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/tmp/beta-report.zip',
        manifest: [...BETA_MANIFEST, 'session_metadata.json — last session metadata'],
        notice: 'Beta report bundle created locally.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('include-session-metadata-checkbox'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() => expect(mockApi.createBetaReport).toHaveBeenCalledWith(true))
  })

  it('shows the bundle path after successful creation', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/home/user/.convsim/crashes/beta-report-2026.zip',
        manifest: BETA_MANIFEST,
        notice: 'Beta report bundle created locally.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() =>
      expect(screen.getByTestId('beta-report-path')).toHaveTextContent(
        '/home/user/.convsim/crashes/beta-report-2026.zip',
      ),
    )
  })

  it('shows the bundle manifest after successful creation', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/tmp/beta-report.zip',
        manifest: BETA_MANIFEST,
        notice: 'Beta report bundle created locally.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() =>
      expect(screen.getByTestId('beta-report-manifest')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('beta-report-manifest')).toHaveTextContent(/versions\.json/i)
  })

  it('shows an Open GitHub issue link after successful creation', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/tmp/beta-report.zip',
        manifest: BETA_MANIFEST,
        notice: 'Beta report bundle created locally.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() =>
      expect(screen.getByTestId('open-beta-issue-link')).toBeInTheDocument(),
    )
    const link = screen.getByTestId('open-beta-issue-link')
    expect(link).toHaveAttribute('href', expect.stringContaining('beta-report.yml'))
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows an error when beta report creation fails', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'Core service unavailable' },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() =>
      expect(screen.getByTestId('beta-report-error')).toBeInTheDocument(),
    )
  })

  it('success screen has a "Done" button that resets the flow', async () => {
    mockApi.createBetaReport.mockResolvedValue({
      ok: true,
      data: {
        bundle_path: '/tmp/beta-report.zip',
        manifest: BETA_MANIFEST,
        notice: 'Beta report bundle created locally.',
      },
    })
    await renderSupport()
    fireEvent.click(screen.getByTestId('report-problem-button'))
    fireEvent.click(screen.getByTestId('create-beta-report-button'))
    await waitFor(() => expect(screen.getByTestId('beta-report-success')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /done/i }))
    await waitFor(() => expect(screen.getByTestId('report-problem-button')).toBeInTheDocument())
  })
})
