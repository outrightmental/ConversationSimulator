// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import UpdateBanner from '../components/UpdateBanner'

const DEFAULT_PROPS = {
  version: '0.2.0',
  releaseUrl: 'https://github.com/outrightmental/ConversationSimulator/releases/tag/v0.2.0',
  onViewNotes: vi.fn(),
  onInstall: vi.fn(),
  onDismiss: vi.fn(),
}

describe('UpdateBanner', () => {
  it('renders the update-available notice', () => {
    render(<UpdateBanner {...DEFAULT_PROPS} />)
    expect(screen.getByRole('status', { name: /beta update available/i })).toBeInTheDocument()
  })

  it('shows the new version number', () => {
    render(<UpdateBanner {...DEFAULT_PROPS} />)
    expect(screen.getByText(/0\.2\.0/)).toBeInTheDocument()
  })

  it('provides a "View notes" link pointing to the release URL', () => {
    render(<UpdateBanner {...DEFAULT_PROPS} />)
    const link = screen.getByRole('link', { name: /view release notes/i })
    expect(link).toHaveAttribute('href', DEFAULT_PROPS.releaseUrl)
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('calls onViewNotes when the View notes link is clicked', () => {
    const onViewNotes = vi.fn()
    render(<UpdateBanner {...DEFAULT_PROPS} onViewNotes={onViewNotes} />)
    fireEvent.click(screen.getByRole('link', { name: /view release notes/i }))
    expect(onViewNotes).toHaveBeenCalledOnce()
  })

  it('calls onInstall when the Install button is clicked', () => {
    const onInstall = vi.fn()
    render(<UpdateBanner {...DEFAULT_PROPS} onInstall={onInstall} />)
    fireEvent.click(screen.getByRole('button', { name: /install beta update/i }))
    expect(onInstall).toHaveBeenCalledOnce()
  })

  it('calls onDismiss when the dismiss button is clicked', () => {
    const onDismiss = vi.fn()
    render(<UpdateBanner {...DEFAULT_PROPS} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole('button', { name: /dismiss update notice/i }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('opens the release URL in a new tab (rel=noreferrer)', () => {
    render(<UpdateBanner {...DEFAULT_PROPS} />)
    const link = screen.getByRole('link', { name: /view release notes/i })
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })
})
