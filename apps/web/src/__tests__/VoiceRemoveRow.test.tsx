// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import VoiceRemoveRow from '../components/VoiceRemoveRow'
import type { UseVoiceInstall } from '../hooks/useVoiceInstall'
import { readyPlan, voiceJob, voicePlan } from './voiceFixtures'

function voice(overrides: Partial<UseVoiceInstall> = {}): UseVoiceInstall {
  return {
    status: { ...readyPlan(), installed_bytes: 540_000_000 },
    job: null,
    installing: false,
    busy: false,
    error: null,
    install: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(true),
    ...overrides,
  }
}

describe('VoiceRemoveRow', () => {
  it('asks before removing, then says what was freed', async () => {
    const v = voice()
    render(<VoiceRemoveRow voice={v} />)
    expect(screen.getByText('540 MB on disk')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Remove voice' }))
    expect(v.remove).not.toHaveBeenCalled()
    expect(screen.getByText(/It frees 540 MB/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(screen.getByTestId('voice-removed')).toHaveTextContent('540 MB freed'))
    expect(v.remove).toHaveBeenCalledTimes(1)
  })

  it('keeps voice when the player changes their mind', () => {
    const v = voice()
    render(<VoiceRemoveRow voice={v} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove voice' }))
    fireEvent.click(screen.getByRole('button', { name: 'Keep voice' }))
    expect(v.remove).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Remove voice' })).toBeInTheDocument()
  })

  it('shows nothing when the in-app install has nothing on disk', () => {
    const { container } = render(<VoiceRemoveRow voice={voice({ status: { ...voicePlan(), installed_bytes: 0 } })} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows nothing while an install runs', () => {
    const { container } = render(<VoiceRemoveRow voice={voice({ installing: true, job: voiceJob() })} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('reports a refusal and keeps the button', async () => {
    const v = voice({
      remove: vi.fn().mockResolvedValue(false),
      error: { kind: 'http-error', status: 409, message: 'Part of voice is in use.' },
    })
    render(<VoiceRemoveRow voice={v} />)
    expect(screen.getByText('Part of voice is in use.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove voice' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove voice' })).toBeInTheDocument())
    expect(screen.queryByTestId('voice-removed')).not.toBeInTheDocument()
  })
})
