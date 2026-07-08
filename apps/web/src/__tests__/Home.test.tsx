// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Home from '../screens/Home'
import type { HealthResponse } from '@convsim/shared'
import type { PacksResponse } from '../api/client'

function makeHealth(overrides: Partial<HealthResponse['runtime']> = {}): HealthResponse {
  return {
    status: 'ok',
    version: '0.1.0',
    runtime: {
      llm_ready: false,
      llm_model_name: null,
      stt_ready: false,
      tts_ready: false,
      tts_voice_name: null,
      network_required: false,
      ...overrides,
    },
  }
}

function makePacks(total = 0): PacksResponse {
  return { packs: [], total }
}

// Returns a testing-library function matcher that checks an element's full textContent
// against a list item whose content matches `expected`.
function liText(expected: string) {
  return (_content: string, el: Element | null): boolean =>
    el?.tagName === 'LI' && el.textContent?.trim() === expected
}

// Stub fetch so the first call returns healthResp and subsequent calls return packsResp.
function stubFetches(healthResp: object, packsResp: object) {
  let calls = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(() => {
      const body = calls++ === 0 ? healthResp : packsResp
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    }),
  )
}

function renderHome() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Home />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
})

describe('Home — ready state', () => {
  it('shows the page heading', () => {
    renderHome()
    expect(screen.getByRole('heading', { name: /conversation simulator/i })).toBeInTheDocument()
  })

  it('shows Local runtime: Ready list item when health is ok', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByText(liText('Local runtime: Ready'))).toBeInTheDocument()
  })

  it('shows the active model name when LLM is ready', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'Llama 3 8B' }), makePacks(1))
    renderHome()
    // StatusBadge renders the model name as a direct text node.
    expect(await screen.findByText('Llama 3 8B')).toBeInTheDocument()
  })

  it('shows pack count when packs are installed', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'x' }), makePacks(3))
    renderHome()
    expect(await screen.findByText('3 installed')).toBeInTheDocument()
  })

  it('links to the library for Start a scenario', () => {
    renderHome()
    expect(screen.getByRole('link', { name: /start a scenario/i })).toHaveAttribute('href', '/library')
  })

  it('links to the workbench for Create / edit', () => {
    renderHome()
    expect(screen.getByRole('link', { name: /create \/ edit/i })).toHaveAttribute('href', '/workbench')
  })

  it('links to settings for Install model', () => {
    renderHome()
    expect(screen.getByRole('link', { name: /install model/i })).toHaveAttribute('href', '/settings')
  })

  it('links to settings for Import pack', () => {
    renderHome()
    expect(screen.getByRole('link', { name: /import pack/i })).toHaveAttribute('href', '/settings')
  })

  it('provides a link to external docs', () => {
    renderHome()
    const docsLink = screen.getByRole('link', { name: /read docs/i })
    expect(docsLink).toHaveAttribute('target', '_blank')
  })
})

describe('Home — no-model state', () => {
  it('shows no-model section heading when LLM is not ready', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByRole('heading', { name: /no model configured/i })).toBeInTheDocument()
  })

  it('shows LLM list item as Not installed', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByText(liText('LLM: Not installed'))).toBeInTheDocument()
  })

  it('offers Install a GGUF model option', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByRole('link', { name: /install a gguf model/i })).toBeInTheDocument()
  })

  it('offers Ollama connection option', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByRole('link', { name: /connect ollama/i })).toBeInTheDocument()
  })

  it('offers text-only demo option', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByRole('link', { name: /text-only demo/i })).toBeInTheDocument()
  })

  it('hides no-model section when LLM is ready', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'TestModel' }), makePacks(1))
    renderHome()
    // Wait for LLM badge to show the model name, then check heading is gone.
    await screen.findByText('TestModel')
    expect(screen.queryByRole('heading', { name: /no model configured/i })).toBeNull()
  })
})

describe('Home — no-pack state', () => {
  it('shows None installed when pack count is zero', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByText('None installed')).toBeInTheDocument()
  })
})

describe('Home — runtime-error state', () => {
  it('shows Local runtime: Unavailable list item when API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    expect(await screen.findByText(liText('Local runtime: Unavailable'))).toBeInTheDocument()
  })

  it('shows an actionable error alert when runtime is down', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent(/ensure the api server is running/i)
  })

  it('does not show the no-model section when runtime is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /no model configured/i })).toBeNull()
  })
})
