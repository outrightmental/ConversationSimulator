// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RuntimeRecoveryCard from '../components/RuntimeRecoveryCard'

const TROUBLESHOOTING_HREF = 'https://example.com/docs/troubleshooting.md#engine-startup-failure'

describe('RuntimeRecoveryCard — basic rendering', () => {
  it('renders as an ARIA alert region', () => {
    render(
      <RuntimeRecoveryCard
        title="Test title"
        description="Test description"
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('shows the title', () => {
    render(
      <RuntimeRecoveryCard
        title="The conversation engine didn't start"
        description="Something went wrong."
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/the conversation engine didn't start/i)
  })

  it('shows the description', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Close other apps and restart."
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/close other apps and restart/i)
  })

  it('shows errorDetail when provided', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        errorDetail="Port 7355 is already in use."
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/port 7355 is already in use/i)
  })

  it('omits errorDetail section when not provided', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    // No "Port" text in the card
    expect(screen.queryByText(/port/i)).not.toBeInTheDocument()
  })

  it('shows the log folder path when provided', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        logPath="/home/user/.local/share/convsim/logs"
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    expect(screen.getByText('/home/user/.local/share/convsim/logs')).toBeInTheDocument()
  })

  it('shows "Logs folder:" label with the path', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        logPath="/home/user/.local/share/convsim/logs"
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/logs folder:/i)
  })
})

describe('RuntimeRecoveryCard — troubleshooting link', () => {
  it('renders a troubleshooting docs link', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
      />,
    )
    const link = screen.getByRole('link', { name: /troubleshooting docs/i })
    expect(link).toHaveAttribute('href', TROUBLESHOOTING_HREF)
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('uses a custom troubleshooting label when provided', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        troubleshootingLabel="Port conflict guide"
      />,
    )
    expect(screen.getByRole('link', { name: /port conflict guide/i })).toBeInTheDocument()
  })
})

describe('RuntimeRecoveryCard — primary action', () => {
  it('renders a primary action button', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{ label: 'Restart the app', onClick: vi.fn() }}
      />,
    )
    expect(screen.getByRole('button', { name: /restart the app/i })).toBeInTheDocument()
  })

  it('calls onClick when the primary action button is clicked', () => {
    const onClick = vi.fn()
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{ label: 'Restart the app', onClick }}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /restart the app/i }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('shows loading label when action is in loading state', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{
          label: 'Restart conversation engine',
          loadingLabel: 'Restarting…',
          loading: true,
          onClick: vi.fn(),
        }}
      />,
    )
    expect(screen.getByRole('button', { name: /restarting/i })).toBeInTheDocument()
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('renders an external link when href is provided instead of onClick', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{ label: 'Get support bundle', href: '/support' }}
      />,
    )
    const link = screen.getByRole('link', { name: /get support bundle/i })
    expect(link).toHaveAttribute('href', '/support')
  })
})

describe('RuntimeRecoveryCard — secondary and tertiary actions', () => {
  it('renders a secondary action', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{ label: 'Restart', onClick: vi.fn() }}
        secondaryAction={{ label: 'Get support bundle', href: '/support' }}
      />,
    )
    expect(screen.getByRole('link', { name: /get support bundle/i })).toBeInTheDocument()
  })

  it('renders a tertiary action', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{ label: 'Restart', onClick: vi.fn() }}
        secondaryAction={{ label: 'Bundle', href: '/support' }}
        tertiaryAction={{ label: 'Report an issue', href: 'https://github.com' }}
      />,
    )
    expect(screen.getByRole('link', { name: /report an issue/i })).toBeInTheDocument()
  })

  it('renders all three actions alongside the troubleshooting link', () => {
    render(
      <RuntimeRecoveryCard
        title="Title"
        description="Desc"
        troubleshootingHref={TROUBLESHOOTING_HREF}
        primaryAction={{ label: 'Restart', onClick: vi.fn() }}
        secondaryAction={{ label: 'Bundle', href: '/support' }}
        tertiaryAction={{ label: 'Report', href: 'https://github.com' }}
      />,
    )
    // 4 interactive elements: primary button + secondary + tertiary + troubleshooting link
    const links = screen.getAllByRole('link')
    const buttons = screen.getAllByRole('button')
    expect(links.length + buttons.length).toBeGreaterThanOrEqual(4)
  })
})
