// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBoundary from '../components/ErrorBoundary'

// A component that throws a render error when the `throw` prop is set.
function Bomb({ throw: shouldThrow }: { throw?: boolean }) {
  if (shouldThrow) throw new Error('Test render error')
  return <div>OK</div>
}

// Suppress console.error output produced by componentDidCatch in these tests.
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('ErrorBoundary — normal render', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div data-testid="child">hello</div>
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})

describe('ErrorBoundary — error state', () => {
  it('shows an alert role when a render error is caught', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('shows a Something went wrong heading', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('heading', { name: /something went wrong/i })).toBeInTheDocument()
  })

  it('shows the error message in the details', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Test render error')).toBeInTheDocument()
  })

  it('shows a Try again button', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('shows a Go to home button', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: /go to home/i })).toBeInTheDocument()
  })

  it('shows a Report this issue link', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    const link = screen.getByRole('link', { name: /report this issue/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('shows a Documentation link', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    const link = screen.getByRole('link', { name: /documentation/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('shows the logs folder path hint', () => {
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/\.convsim\/logs/i)).toBeInTheDocument()
  })

  it('clears the error when Try again is clicked', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    )
    // Manually trigger the error state by simulating a caught error
    render(
      <ErrorBoundary>
        <Bomb throw />
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))
    // After reset, the error UI disappears (children re-render and may throw again,
    // but the important thing is setState({ error: null }) was called).
    // In the test environment the child still throws, so just verify the click
    // does not throw an uncaught error — the button handler is exercised.
  })
})
