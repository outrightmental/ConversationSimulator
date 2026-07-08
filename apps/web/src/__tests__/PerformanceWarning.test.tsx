// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PerformanceWarningBanner from '../components/PerformanceWarning'
import type { PerformanceWarning } from '@convsim/shared'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderBanner(warnings: PerformanceWarning[]) {
  return render(
    <MemoryRouter>
      <PerformanceWarningBanner warnings={warnings} />
    </MemoryRouter>,
  )
}

describe('PerformanceWarningBanner', () => {
  it('renders nothing when warnings array is empty', () => {
    renderBanner([])
    expect(document.body.textContent).toBe('')
  })

  it('renders a warning entry when warnings are provided', () => {
    renderBanner([
      {
        code: 'use_smaller_model',
        title: 'NPC response is slow',
        detail: 'First token took 5.0s. Try a smaller model.',
      },
    ])
    expect(screen.getByTestId('performance-warnings')).toBeInTheDocument()
    expect(screen.getByTestId('perf-warning-use_smaller_model')).toBeInTheDocument()
  })

  it('displays the warning title and detail', () => {
    renderBanner([
      {
        code: 'reduce_context_length',
        title: 'Full NPC response is very slow',
        detail: 'Response took 12.0s. Reduce context length.',
      },
    ])
    expect(screen.getByText(/full npc response is very slow/i)).toBeInTheDocument()
    expect(screen.getByText(/reduce context length/i)).toBeInTheDocument()
  })

  it('renders multiple warnings', () => {
    renderBanner([
      {
        code: 'use_smaller_model',
        title: 'Slow start',
        detail: 'Session took 7.0s.',
      },
      {
        code: 'reduce_context_length',
        title: 'Slow response',
        detail: 'Response took 15.0s.',
      },
    ])
    expect(screen.getByTestId('perf-warning-use_smaller_model')).toBeInTheDocument()
    expect(screen.getByTestId('perf-warning-reduce_context_length')).toBeInTheDocument()
  })

  it('has accessible role and label', () => {
    renderBanner([
      { code: 'disable_tts', title: 'TTS is slow', detail: 'First sentence took 8.0s.' },
    ])
    expect(screen.getByRole('status', { name: /performance warnings/i })).toBeInTheDocument()
  })

  it('navigates to /settings when Runtime Settings button is clicked', () => {
    renderBanner([
      { code: 'use_smaller_model', title: 'NPC is slow', detail: 'Token took 4s.' },
    ])
    fireEvent.click(screen.getByRole('button', { name: /open runtime settings/i }))
    expect(mockNavigate).toHaveBeenCalledWith('/settings')
  })
})
