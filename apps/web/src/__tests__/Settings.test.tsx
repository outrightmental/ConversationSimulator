// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Settings from '../screens/Settings'

vi.mock('../api/client', () => ({
  api: {
    getDataFolder: vi.fn(),
    clearLocalData: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

function renderSettings() {
  return render(<Settings />)
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.getDataFolder.mockResolvedValue({ path: '/home/user/.convsim/db' })
})

// ---------------------------------------------------------------------------
// Privacy notice
// ---------------------------------------------------------------------------

describe('privacy notice', () => {
  it('states conversations are not sent to servers', async () => {
    renderSettings()
    expect(
      screen.getByText(/conversations are processed entirely on your device/i),
    ).toBeInTheDocument()
  })

  it('states no conversation data is sent to external servers', async () => {
    renderSettings()
    expect(
      screen.getByText(/no conversation data is ever sent to external servers/i),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Transcript toggle
// ---------------------------------------------------------------------------

describe('transcript saving toggle', () => {
  it('shows the save transcripts checkbox', async () => {
    renderSettings()
    expect(
      screen.getByRole('checkbox', { name: /save transcripts locally/i }),
    ).toBeInTheDocument()
  })

  it('transcript saving is enabled by default', async () => {
    renderSettings()
    const checkbox = screen.getByRole('checkbox', { name: /save transcripts locally/i })
    expect(checkbox).toBeChecked()
  })

  it('shows local-only note when transcript saving is on', async () => {
    renderSettings()
    expect(screen.getByText(/saved to your local data folder only/i)).toBeInTheDocument()
  })

  it('shows not-saved note when transcript saving is toggled off', async () => {
    renderSettings()
    const checkbox = screen.getByRole('checkbox', { name: /save transcripts locally/i })
    fireEvent.click(checkbox)
    expect(checkbox).not.toBeChecked()
    await waitFor(() => expect(screen.getByText(/not saved/i)).toBeInTheDocument())
  })

  it('can be toggled back on after being turned off', async () => {
    renderSettings()
    const checkbox = screen.getByRole('checkbox', { name: /save transcripts locally/i })
    fireEvent.click(checkbox)
    fireEvent.click(checkbox)
    expect(checkbox).toBeChecked()
  })
})

// ---------------------------------------------------------------------------
// TTS cache toggle
// ---------------------------------------------------------------------------

describe('TTS cache toggle', () => {
  it('shows the cache TTS audio checkbox', () => {
    renderSettings()
    expect(
      screen.getByRole('checkbox', { name: /cache tts audio locally/i }),
    ).toBeInTheDocument()
  })

  it('TTS cache is enabled by default', () => {
    renderSettings()
    expect(screen.getByRole('checkbox', { name: /cache tts audio locally/i })).toBeChecked()
  })
})

// ---------------------------------------------------------------------------
// Data folder
// ---------------------------------------------------------------------------

describe('data folder', () => {
  it('displays the data folder path returned by the API', async () => {
    renderSettings()
    await waitFor(() =>
      expect(screen.getByTestId('data-folder-path')).toHaveTextContent('/home/user/.convsim/db'),
    )
  })

  it('shows an error message when the API fails', async () => {
    mockApi.getDataFolder.mockRejectedValue(new Error('network error'))
    renderSettings()
    await waitFor(() =>
      expect(screen.getByText(/could not retrieve data folder path/i)).toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Clear local data — two-step confirmation
// ---------------------------------------------------------------------------

describe('clear local data', () => {
  it('shows the clear all local data button', () => {
    renderSettings()
    expect(
      screen.getByRole('button', { name: /clear all local data/i }),
    ).toBeInTheDocument()
  })

  it('shows a confirmation warning on first click', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/permanently delete all sessions/i),
    )
  })

  it('shows the confirm button after the first click', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /confirm.*delete everything/i }),
      ).toBeInTheDocument(),
    )
  })

  it('shows a cancel button during confirmation', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument(),
    )
  })

  it('cancel dismisses the confirmation without clearing', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /cancel/i }))
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(mockApi.clearLocalData).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('calls clearLocalData API on the second (confirm) click', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 3 })
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() => expect(mockApi.clearLocalData).toHaveBeenCalledOnce())
  })

  it('shows success message with deleted count after clear', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 3 })
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() =>
      expect(screen.getByText(/3 sessions deleted/i)).toBeInTheDocument(),
    )
  })

  it('shows singular "1 session deleted" when exactly one session is removed', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 1 })
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() =>
      expect(screen.getByText(/1 session deleted/i)).toBeInTheDocument(),
    )
  })

  it('shows an error when the clear API call fails', async () => {
    mockApi.clearLocalData.mockRejectedValue(new Error('disk full'))
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/disk full/i),
    )
  })

  it('clicking clear again after success re-enters the confirmation flow', async () => {
    mockApi.clearLocalData.mockResolvedValue({ deleted_sessions: 1 })
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() => screen.getByText(/1 session deleted/i))

    // Second click should restart the two-step flow, not be a no-op
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm.*delete everything/i })).toBeInTheDocument(),
    )
  })

  it('clicking clear again after an error re-enters the confirmation flow', async () => {
    mockApi.clearLocalData.mockRejectedValue(new Error('disk full'))
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() => screen.getByRole('button', { name: /confirm.*delete everything/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm.*delete everything/i }))
    await waitFor(() => screen.getByRole('alert'))

    // Second click should restart the two-step flow, not be a no-op
    fireEvent.click(screen.getByRole('button', { name: /clear all local data/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm.*delete everything/i })).toBeInTheDocument(),
    )
  })
})

// ---------------------------------------------------------------------------
// Advanced — raw audio saving
// ---------------------------------------------------------------------------

describe('advanced: raw audio saving', () => {
  it('advanced section is hidden by default', () => {
    renderSettings()
    expect(
      screen.queryByRole('checkbox', { name: /save raw audio/i }),
    ).not.toBeInTheDocument()
  })

  it('advanced section appears after clicking show advanced', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: /save raw audio recordings/i }),
      ).toBeInTheDocument(),
    )
  })

  it('raw audio saving is off by default', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    expect(screen.getByRole('checkbox', { name: /save raw audio recordings/i })).not.toBeChecked()
  })

  it('shows a warning when raw audio saving is enabled', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    await waitFor(() =>
      expect(screen.getByText(/raw audio saving is on/i)).toBeInTheDocument(),
    )
  })

  it('advanced section collapses when hide advanced is clicked', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /show advanced/i }))
    await waitFor(() => screen.getByRole('checkbox', { name: /save raw audio recordings/i }))
    fireEvent.click(screen.getByRole('button', { name: /hide advanced/i }))
    expect(
      screen.queryByRole('checkbox', { name: /save raw audio recordings/i }),
    ).not.toBeInTheDocument()
  })
})
