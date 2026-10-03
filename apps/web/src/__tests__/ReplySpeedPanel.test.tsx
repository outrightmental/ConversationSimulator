// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { I18nProvider } from '../i18n'
import ReplySpeedPanel from '../components/ReplySpeedPanel'
import type { ReplySpeed, RuntimeSettingsResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    getRuntimeSettings: vi.fn(),
    updateRuntimeSettings: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

function settings(replySpeed: ReplySpeed | null): RuntimeSettingsResponse {
  const nulls = {
    context_length: null,
    gpu_layers: null,
    threads: null,
    temperature: null,
    top_p: null,
    repeat_penalty: null,
  }
  return {
    settings: { ...nulls, reply_speed: replySpeed },
    recommended: { ...nulls, reply_speed: 'balanced' },
    requires_restart: false,
  }
}

function renderPanel() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <ReplySpeedPanel />
      </MemoryRouter>
    </I18nProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

/**
 * Issue #501 §1: "I'm currently … trying to change my settings to attempt to
 * speed the model up. I was a little unclear on how to do that in the Settings
 * tab." Nothing in Settings was named after what they wanted.
 */
describe('ReplySpeedPanel', () => {
  it('offers three named speeds, each with a short descriptor', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings(null) })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('reply-speed-options')).toBeInTheDocument())
    expect(screen.getByTestId('reply-speed-fast')).toHaveTextContent('Quick replies')
    expect(screen.getByTestId('reply-speed-fast')).toHaveTextContent('Shortest answers')
    expect(screen.getByTestId('reply-speed-balanced')).toHaveTextContent('Balanced')
    expect(screen.getByTestId('reply-speed-detailed')).toHaveTextContent('Fuller replies')
  })

  it('shows balanced as the choice when none was ever made', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings(null) })
    renderPanel()
    await waitFor(() =>
      expect(screen.getByTestId('reply-speed-balanced')).toHaveAttribute('aria-checked', 'true'),
    )
    expect(screen.getByTestId('reply-speed-fast')).toHaveAttribute('aria-checked', 'false')
  })

  it('reflects the persisted choice', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings('detailed') })
    renderPanel()
    await waitFor(() =>
      expect(screen.getByTestId('reply-speed-detailed')).toHaveAttribute('aria-checked', 'true'),
    )
  })

  it('persists a new choice and says it applies to the next message', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings(null) })
    mockApi.updateRuntimeSettings.mockResolvedValue({ ok: true, data: settings('fast') })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('reply-speed-fast')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('reply-speed-fast'))
    await waitFor(() =>
      expect(mockApi.updateRuntimeSettings).toHaveBeenCalledWith({ reply_speed: 'fast' }),
    )
    await waitFor(() =>
      expect(screen.getByText(/next message uses the new speed/i)).toBeInTheDocument(),
    )
  })

  it('does not re-save the choice that is already active', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings('fast') })
    renderPanel()
    await waitFor(() =>
      expect(screen.getByTestId('reply-speed-fast')).toHaveAttribute('aria-checked', 'true'),
    )
    fireEvent.click(screen.getByTestId('reply-speed-fast'))
    expect(mockApi.updateRuntimeSettings).not.toHaveBeenCalled()
  })

  it('rolls the selection back when saving fails', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings('balanced') })
    mockApi.updateRuntimeSettings.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'nope' },
    })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('reply-speed-fast')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('reply-speed-fast'))
    await waitFor(() =>
      expect(screen.getByTestId('reply-speed-balanced')).toHaveAttribute('aria-checked', 'true'),
    )
    expect(screen.getByTestId('reply-speed-fast')).toHaveAttribute('aria-checked', 'false')
  })

  it('names the bigger lever honestly and links to it', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({ ok: true, data: settings(null) })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('reply-speed-options')).toBeInTheDocument())
    expect(screen.getByText(/a smaller model is the biggest change/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /choose a model/i })).toHaveAttribute(
      'href',
      '/model-manager',
    )
  })

  it('steps aside on a bundled runtime that predates the settings endpoint', async () => {
    // RuntimeSettingsPanel already explains the 404 and points at the update;
    // a second notice saying the same thing is noise.
    mockApi.getRuntimeSettings.mockResolvedValue({
      ok: false,
      error: { kind: 'http-error', status: 404, message: 'Not Found' },
    })
    const { container } = renderPanel()
    await waitFor(() => expect(mockApi.getRuntimeSettings).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('surfaces a real load failure with a retry', async () => {
    mockApi.getRuntimeSettings.mockResolvedValue({
      ok: false,
      error: { kind: 'network', message: 'unreachable' },
    })
    renderPanel()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })
})
