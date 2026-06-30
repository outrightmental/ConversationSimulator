// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

// Prevent real fetch calls; return a promise that never resolves so the
// pending-state async health check never triggers a post-render state update.
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
})

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App shell', () => {
  it('renders Home screen at /', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: /conversation simulator/i })).toBeInTheDocument()
  })

  it('renders Scenario Library at /library', () => {
    renderAt('/library')
    expect(screen.getByRole('heading', { name: /scenario library/i })).toBeInTheDocument()
  })

  it('renders Scenario Setup at /setup/:id', () => {
    renderAt('/setup/behavioral-interview')
    expect(screen.getByRole('heading', { name: /scenario setup/i })).toBeInTheDocument()
    expect(screen.getByText(/behavioral-interview/)).toBeInTheDocument()
  })

  it('renders Conversation at /conversation/:id', () => {
    renderAt('/conversation/sess-001')
    expect(screen.getByRole('heading', { name: /conversation/i })).toBeInTheDocument()
    expect(screen.getByText(/sess-001/)).toBeInTheDocument()
  })

  it('renders Debrief at /debrief/:id', () => {
    renderAt('/debrief/sess-001')
    expect(screen.getByRole('heading', { name: /debrief/i })).toBeInTheDocument()
  })

  it('renders Creator Workbench at /workbench', () => {
    renderAt('/workbench')
    expect(screen.getByRole('heading', { name: /creator workbench/i })).toBeInTheDocument()
  })

  it('renders Settings at /settings', () => {
    renderAt('/settings')
    expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument()
  })

  it('shows navigation links on every screen', () => {
    renderAt('/')
    expect(screen.getByRole('link', { name: /scenarios/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /workbench/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument()
  })
})
