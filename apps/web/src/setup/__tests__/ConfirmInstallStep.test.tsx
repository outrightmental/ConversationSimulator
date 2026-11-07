// SPDX-License-Identifier: Apache-2.0
/**
 * The confirm-install screen's "Saves to" row must show where the engine
 * really writes the model, which only the engine knows (it depends on the
 * platform and on the desktop shell's data root). It used to hard-code a
 * legacy path the engine no longer uses.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ConfirmInstallStep, modelFilePath } from '../steps/ConfirmInstallStep'
import type { UseSetupFlowReturn } from '../useSetupFlow'
import type { ModelRegistryEntry } from '@convsim/shared'

vi.mock('../../api/client', () => ({
  api: {
    getFolders: vi.fn(),
  },
}))

import { api } from '../../api/client'
const mockApi = vi.mocked(api)

const MODEL: ModelRegistryEntry = {
  id: 'example-model',
  name: 'Example model',
  provider: 'test',
  family: 'test',
  role: 'starter',
  format: 'gguf',
  license_spdx: 'Apache-2.0',
  license_url: 'https://www.apache.org/licenses/LICENSE-2.0',
  source_type: 'registry',
  download_url: 'https://example.test/model.gguf',
  sha256: 'a'.repeat(64),
  size_gb: 2.5,
  min_vram_gb: 4,
  recommended_vram_gb: 6,
  context_length: 8192,
  registered_at: '2026-01-01T00:00:00.000Z',
}

const FOLDERS = {
  data: '/srv/convsim',
  logs: '/srv/convsim/logs',
  models: '/srv/convsim/models/llm',
  packs: '/srv/convsim/packs',
  exports: '/srv/convsim/exports',
  cache: '/srv/convsim/cache',
  crash_bundles: '/srv/convsim/crashes',
}

function makeFlow(): UseSetupFlowReturn {
  return {
    selectedModel: MODEL,
    setSelectedModel: vi.fn(),
    setStep: vi.fn(),
    resetAction: vi.fn(),
    handleStartInstall: vi.fn(),
    actionError: null,
    actionLoading: false,
    stepHeadingRef: { current: null },
  } as unknown as UseSetupFlowReturn
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('modelFilePath', () => {
  it('joins with a forward slash for POSIX folders', () => {
    expect(modelFilePath('/srv/convsim/models/llm', 'm.gguf')).toBe('/srv/convsim/models/llm/m.gguf')
    expect(modelFilePath('/srv/convsim/models/llm/', 'm.gguf')).toBe('/srv/convsim/models/llm/m.gguf')
  })

  it('keeps a Windows folder on backslashes', () => {
    expect(modelFilePath('C:\\Users\\p\\AppData\\Local\\convsim\\models\\llm', 'm.gguf'))
      .toBe('C:\\Users\\p\\AppData\\Local\\convsim\\models\\llm\\m.gguf')
  })
})

describe('ConfirmInstallStep storage row', () => {
  it("shows the engine's Models folder joined with the file name once it loads (wizard)", async () => {
    mockApi.getFolders.mockResolvedValue({ ok: true, data: FOLDERS })
    const { container } = render(<ConfirmInstallStep flow={makeFlow()} mode="wizard" />)

    expect(await screen.findByText('/srv/convsim/models/llm/example-model.gguf')).toBeInTheDocument()
    expect(screen.getByText('Saves to')).toBeInTheDocument()
    expect(screen.queryByText('File name')).not.toBeInTheDocument()
    expect(mockApi.getFolders).toHaveBeenCalledTimes(1)
    expect(container.textContent).not.toContain('~/.convsim')
  })

  it('labels the row Storage path in manager mode', async () => {
    mockApi.getFolders.mockResolvedValue({ ok: true, data: FOLDERS })
    render(<ConfirmInstallStep flow={makeFlow()} mode="manager" />)

    expect(await screen.findByText('/srv/convsim/models/llm/example-model.gguf')).toBeInTheDocument()
    expect(screen.getByText('Storage path')).toBeInTheDocument()
  })

  it('shows the file name alone with a neutral label while the folder is loading', () => {
    mockApi.getFolders.mockReturnValue(new Promise(() => { /* never settles */ }))
    const { container } = render(<ConfirmInstallStep flow={makeFlow()} mode="wizard" />)

    expect(screen.getByText('example-model.gguf')).toBeInTheDocument()
    expect(screen.getByText('File name')).toBeInTheDocument()
    expect(screen.queryByText('Saves to')).not.toBeInTheDocument()
    expect(container.textContent).not.toContain('~/.convsim')
  })

  it('falls back to the file name without any path when the folders call fails', async () => {
    mockApi.getFolders.mockResolvedValue({ ok: false, error: { kind: 'network', message: 'unreachable' } })
    const { container } = render(<ConfirmInstallStep flow={makeFlow()} mode="wizard" />)

    await waitFor(() => expect(mockApi.getFolders).toHaveBeenCalledTimes(1))
    // Let the rejected result settle; the row must still carry no path.
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.getByText('example-model.gguf')).toBeInTheDocument()
    expect(screen.getByText('File name')).toBeInTheDocument()
    expect(screen.queryByText(/\//)).not.toBeInTheDocument()
    expect(container.textContent).not.toContain('~/.convsim')
  })

  it('never renders the legacy ~/.convsim prefix, whatever the engine reports', async () => {
    mockApi.getFolders.mockResolvedValue({
      ok: true,
      data: { ...FOLDERS, models: '/home/p/.local/share/convsim/models/llm' },
    })
    const { container } = render(<ConfirmInstallStep flow={makeFlow()} mode="wizard" />)

    expect(await screen.findByText('/home/p/.local/share/convsim/models/llm/example-model.gguf')).toBeInTheDocument()
    expect(container.textContent).not.toContain('~/.convsim')
  })
})
