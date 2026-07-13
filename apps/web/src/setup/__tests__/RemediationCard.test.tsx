// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { RemediationCard } from '../RemediationCard'
import type { PreflightCheck } from '@convsim/shared'

const DISK_SPACE_CHECK: PreflightCheck = {
  id: 'disk-space',
  name: 'Not enough disk space',
  status: 'fail',
  message: 'The AI model needs 5.0 GB and this disk has 1.0 GB free.',
  severity: 'needs-human',
  autofix: false,
  fix_action: { kind: 'navigate', href: '/settings', label: 'Choose another location' },
  detail: { free_gb: 1.0, required_gb: 5.0 },
}

const DATA_DIR_CHECK: PreflightCheck = {
  id: 'data-dir-writable',
  name: 'Data folder',
  status: 'fail',
  message: "The app can't write to its data folder. You may need to check your disk permissions.",
  severity: 'needs-human',
  autofix: false,
  fix_action: { kind: 'navigate', href: '/settings', label: 'Open Settings' },
}

beforeEach(() => {
  // Mock clipboard
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    writable: true,
    configurable: true,
  })
})

describe('RemediationCard', () => {
  it('renders the check name as title', () => {
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
      />,
    )
    expect(screen.getByText('Not enough disk space')).toBeTruthy()
  })

  it('renders the check message as body', () => {
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
      />,
    )
    expect(screen.getByText(/The AI model needs 5\.0 GB/)).toBeTruthy()
  })

  it('renders the primary fix action button', () => {
    const onAction = vi.fn()
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={onAction}
        onTextOnly={vi.fn()}
      />,
    )
    const btn = screen.getByTestId('remediation-action-disk-space')
    expect(btn.textContent).toBe('Choose another location')
    fireEvent.click(btn)
    expect(onAction).toHaveBeenCalledWith(DISK_SPACE_CHECK.fix_action)
  })

  it('renders the text-only escape hatch', () => {
    const onTextOnly = vi.fn()
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={vi.fn()}
        onTextOnly={onTextOnly}
      />,
    )
    const btn = screen.getByTestId('remediation-text-only-disk-space')
    expect(btn.textContent).toBe('Try text-only instead')
    fireEvent.click(btn)
    expect(onTextOnly).toHaveBeenCalledOnce()
  })

  it('shows Details collapsible when toggled', () => {
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
        coreVersion="convsim-core 1.2.3 is running."
      />,
    )
    // Details section should not be visible initially
    expect(screen.queryByTestId('remediation-details-disk-space')).toBeNull()

    // Open details
    fireEvent.click(screen.getByTestId('remediation-details-toggle-disk-space'))
    const details = screen.getByTestId('remediation-details-disk-space')
    expect(details.textContent).toContain('disk-space')
    expect(details.textContent).toContain('The AI model needs 5.0 GB')
  })

  it('Details block includes check id, status, and message', () => {
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('remediation-details-toggle-disk-space'))
    const details = screen.getByTestId('remediation-details-disk-space').textContent ?? ''
    expect(details).toContain('Check ID: disk-space')
    expect(details).toContain('Status: fail')
    expect(details).toContain('Details: The AI model needs 5.0 GB')
  })

  it('copy button writes bug-report block to clipboard', async () => {
    render(
      <RemediationCard
        check={DISK_SPACE_CHECK}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('remediation-details-toggle-disk-space'))
    fireEvent.click(screen.getByTestId('remediation-copy-disk-space'))
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledOnce()
      const written = vi.mocked(navigator.clipboard.writeText).mock.calls[0][0]
      expect(written).toContain('disk-space')
      expect(written).toContain('--- Bug report ---')
    })
  })

  it('renders without a fix_action when check has none', () => {
    const noAction: PreflightCheck = { ...DISK_SPACE_CHECK, fix_action: null }
    render(
      <RemediationCard
        check={noAction}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
      />,
    )
    // Primary action button must not render
    expect(screen.queryByTestId('remediation-action-disk-space')).toBeNull()
    // Text-only escape still renders
    expect(screen.getByTestId('remediation-text-only-disk-space')).toBeTruthy()
  })

  it('does not contain banned vocabulary in the card surface', () => {
    const { container } = render(
      <RemediationCard
        check={DATA_DIR_CHECK}
        onAction={vi.fn()}
        onTextOnly={vi.fn()}
      />,
    )
    const text = container.textContent ?? ''
    // Visible surface must not expose jargon (the Details block is hidden initially)
    for (const banned of ['binary', 'llama', 'sidecar', 'System Check']) {
      expect(text.toLowerCase()).not.toContain(banned.toLowerCase())
    }
  })
})
