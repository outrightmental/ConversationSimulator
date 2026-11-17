// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nProvider, LOCALE_KEY } from '../i18n'
import GraphicsCardPanel from '../components/GraphicsCardPanel'
import EngineFallbackNotice from '../components/EngineFallbackNotice'
import { en } from '../i18n/locales/en'
import { de } from '../i18n/locales/de'
import type { EngineStatusResponse, RuntimeSettingsResponse } from '@convsim/shared'

vi.mock('../api/client', () => ({
  api: {
    getEngineStatus: vi.fn(),
    markEngineNoticeSeen: vi.fn(),
    restartEngine: vi.fn(),
    retryGraphicsCard: vi.fn(),
    updateRuntimeSettings: vi.fn(),
  },
}))

import { api } from '../api/client'
const mockApi = vi.mocked(api)

function status(overrides: Partial<EngineStatusResponse> = {}): EngineStatusResponse {
  return {
    setting: 'auto',
    running: 'vulkan',
    available: ['cpu', 'vulkan'],
    device: 'NVIDIA GeForce RTX 4080 Laptop GPU',
    reason: 'discrete device listed',
    devices: [],
    gpu_failure: null,
    notice_pending: false,
    ...overrides,
  }
}

const FAILURE = { rung: 'load' as const, detail: 'ErrorDeviceLost', device: 'GPU', at: '2026-11-16T10:00:00Z' }

function renderPanel() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <GraphicsCardPanel />
      </MemoryRouter>
    </I18nProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('GraphicsCardPanel (issue #531)', () => {
  it('says the graphics card is writing the replies, and names it', async () => {
    mockApi.getEngineStatus.mockResolvedValue({ ok: true, data: status() })
    renderPanel()
    await waitFor(() =>
      expect(screen.getByTestId('graphics-card-status')).toHaveTextContent(
        'Your graphics card is writing the replies (NVIDIA GeForce RTX 4080 Laptop GPU).',
      ),
    )
    expect(screen.getByTestId('graphics-card-auto')).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByTestId('graphics-card-retry')).not.toBeInTheDocument()
  })

  it('after a fallback, says so and offers "Try the graphics card again"', async () => {
    mockApi.getEngineStatus.mockResolvedValue({
      ok: true,
      data: status({ running: 'cpu', device: null, gpu_failure: FAILURE }),
    })
    mockApi.retryGraphicsCard.mockResolvedValue({ ok: true, data: status() })
    renderPanel()
    await waitFor(() =>
      expect(screen.getByTestId('graphics-card-status')).toHaveTextContent('stopped working with the app'),
    )
    fireEvent.click(screen.getByTestId('graphics-card-retry'))
    await waitFor(() => expect(screen.getByText(/It worked/)).toBeInTheDocument())
    expect(mockApi.retryGraphicsCard).toHaveBeenCalledTimes(1)
  })

  it('a retry that fails again is reported here and not announced a second time', async () => {
    mockApi.getEngineStatus.mockResolvedValue({
      ok: true,
      data: status({ running: 'cpu', device: null, gpu_failure: FAILURE }),
    })
    const failedAgain = status({ running: 'cpu', device: null, gpu_failure: FAILURE, notice_pending: true })
    mockApi.retryGraphicsCard.mockResolvedValue({ ok: true, data: failedAgain })
    mockApi.markEngineNoticeSeen.mockResolvedValue({ ok: true, data: { ...failedAgain, notice_pending: false } })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('graphics-card-retry')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('graphics-card-retry'))
    await waitFor(() => expect(screen.getByText(/still did not work/)).toBeInTheDocument())
    expect(mockApi.markEngineNoticeSeen).toHaveBeenCalledTimes(1)
  })

  it('choosing the processor saves the choice and restarts the AI model', async () => {
    mockApi.getEngineStatus.mockResolvedValue({ ok: true, data: status() })
    mockApi.updateRuntimeSettings.mockResolvedValue({ ok: true, data: {} as RuntimeSettingsResponse })
    mockApi.restartEngine.mockResolvedValue({
      ok: true,
      data: status({ setting: 'cpu', running: 'cpu', device: null }),
    })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('graphics-card-cpu')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('graphics-card-cpu'))
    await waitFor(() => expect(screen.getByText(/restarted with your choice/)).toBeInTheDocument())
    expect(mockApi.updateRuntimeSettings).toHaveBeenCalledWith({ engine_variant: 'cpu' })
    expect(mockApi.restartEngine).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('graphics-card-cpu')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('graphics-card-status')).toHaveTextContent('Your processor is writing the replies.')
  })

  it('offers no choice on a build with only one engine', async () => {
    mockApi.getEngineStatus.mockResolvedValue({
      ok: true,
      data: status({ running: 'metal', available: ['metal'], device: null }),
    })
    renderPanel()
    await waitFor(() =>
      expect(screen.getByTestId('graphics-card-status')).toHaveTextContent('graphics chip'),
    )
    expect(screen.queryByTestId('graphics-card-options')).not.toBeInTheDocument()
  })

  it('renders nothing when the core predates the endpoint', async () => {
    mockApi.getEngineStatus.mockResolvedValue({
      ok: false,
      error: { kind: 'http-error', status: 404, message: 'Not Found' } as never,
    })
    const { container } = renderPanel()
    await waitFor(() => expect(mockApi.getEngineStatus).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('speaks German', async () => {
    localStorage.setItem(LOCALE_KEY, 'de')
    mockApi.getEngineStatus.mockResolvedValue({
      ok: true,
      data: status({ running: 'cpu', device: null, gpu_failure: FAILURE }),
    })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('graphics-card-retry')).toHaveTextContent('Grafikkarte erneut versuchen'))
  })
})

describe('EngineFallbackNotice (issue #531)', () => {
  function renderNotice() {
    return render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<EngineFallbackNotice />} />
            <Route path="/settings" element={<p>Settings screen</p>} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    )
  }

  it('says it once, and dismissing it marks it seen', async () => {
    mockApi.getEngineStatus.mockResolvedValue({
      ok: true,
      data: status({ running: 'cpu', gpu_failure: FAILURE, notice_pending: true }),
    })
    mockApi.markEngineNoticeSeen.mockResolvedValue({ ok: true, data: status() })
    renderNotice()
    await waitFor(() => expect(screen.getByTestId('engine-fallback-notice')).toBeInTheDocument())
    expect(screen.getByTestId('engine-fallback-notice')).toHaveTextContent('replies now come from your processor')
    fireEvent.click(screen.getByTestId('engine-fallback-dismiss'))
    await waitFor(() => expect(screen.queryByTestId('engine-fallback-notice')).not.toBeInTheDocument())
    expect(mockApi.markEngineNoticeSeen).toHaveBeenCalledTimes(1)
  })

  it('opens Settings', async () => {
    mockApi.getEngineStatus.mockResolvedValue({
      ok: true,
      data: status({ running: 'cpu', gpu_failure: FAILURE, notice_pending: true }),
    })
    mockApi.markEngineNoticeSeen.mockResolvedValue({ ok: true, data: status() })
    renderNotice()
    await waitFor(() => expect(screen.getByTestId('engine-fallback-open-settings')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('engine-fallback-open-settings'))
    await waitFor(() => expect(screen.getByText('Settings screen')).toBeInTheDocument())
  })

  it('renders nothing when nothing is pending, or when the core cannot be asked', async () => {
    mockApi.getEngineStatus.mockResolvedValue({ ok: true, data: status() })
    const { container, unmount } = renderNotice()
    await waitFor(() => expect(mockApi.getEngineStatus).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
    unmount()

    mockApi.getEngineStatus.mockRejectedValue(new TypeError('not a function'))
    const second = renderNotice()
    await waitFor(() => expect(mockApi.getEngineStatus).toHaveBeenCalledTimes(2))
    expect(second.container).toBeEmptyDOMElement()
  })
})

describe('the graphics-card strings', () => {
  it('exist in English and German', () => {
    expect(Object.keys(de.settings.graphicsCard).sort()).toEqual(Object.keys(en.settings.graphicsCard).sort())
    expect(Object.keys(de.engineNotice).sort()).toEqual(Object.keys(en.engineNotice).sort())
    expect(de.settings.graphicsCard.retry).not.toEqual(en.settings.graphicsCard.retry)
  })

  it('never tell the player to enable a graphics card', () => {
    const all = JSON.stringify([en.settings.graphicsCard, en.engineNotice])
    expect(all).not.toMatch(/enable|GPU layers|acceleration/i)
  })
})
