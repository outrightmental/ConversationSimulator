// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Home from '../screens/Home'

// @convsim/ui re-exports FormEditor which transitively imports @convsim/scenario-schema
// (requires zod at runtime).  Stub the package to avoid that peer dependency in tests.
vi.mock('@convsim/ui', () => ({
  StatusBadge: ({ children, status }: { children: React.ReactNode; status: string }) => (
    <span data-status={status}>{children}</span>
  ),
}))
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

// Stub fetch: routes /health → healthResp and /packs → packsResp by URL.
// Includes text() because handleResponse now reads the body as text first.
function stubFetches(healthResp: object, packsResp: object) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const body = url.includes('/packs') ? packsResp : healthResp
      const text = JSON.stringify(body)
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve(text) })
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

  it('offers text-only demo option linking to the library', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    const link = await screen.findByRole('link', { name: /text-only demo/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/library')
  })

  it('hides no-model section when LLM is ready', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'TestModel' }), makePacks(1))
    renderHome()
    // Wait for LLM badge to show the model name, then check heading is gone.
    await screen.findByText('TestModel')
    expect(screen.queryByRole('heading', { name: /no model configured/i })).toBeNull()
  })
})

describe('Home — no-model links lead to model manager', () => {
  it('GGUF model link goes to /model-manager', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    const link = await screen.findByRole('link', { name: /install a gguf model/i })
    expect(link).toHaveAttribute('href', '/model-manager')
  })

  it('Ollama link goes to /model-manager', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    const link = await screen.findByRole('link', { name: /connect ollama/i })
    expect(link).toHaveAttribute('href', '/model-manager')
  })
})

describe('Home — no-pack state', () => {
  it('shows None installed when pack count is zero', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    expect(await screen.findByText('None installed')).toBeInTheDocument()
  })
})

describe('Home — offline readiness', () => {
  it('shows network required as No when network_required is false', async () => {
    stubFetches(makeHealth({ network_required: false }), makePacks(0))
    renderHome()
    expect(await screen.findByText(liText('Network required to play: No'))).toBeInTheDocument()
  })

  it('shows network required as Yes when network_required is true', async () => {
    stubFetches(makeHealth({ network_required: true }), makePacks(0))
    renderHome()
    expect(await screen.findByText(liText('Network required to play: Yes'))).toBeInTheDocument()
  })
})

describe('Home — status card links', () => {
  it('has at least five links to /settings covering LLM, STT, TTS, install, and import', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    await screen.findByText(liText('Local runtime: Ready'))
    const settingsLinks = screen
      .getAllByRole('link')
      .filter((el) => el.getAttribute('href') === '/settings')
    // Install model, Import pack, LLM badge, STT badge, TTS badge = 5
    expect(settingsLinks.length).toBeGreaterThanOrEqual(5)
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

  it('shows last_error from the runtime when present', async () => {
    stubFetches(makeHealth({ last_error: 'Model failed to load: out of memory' }), makePacks(0))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/model failed to load: out of memory/i)
  })

  it('does not show a last_error alert when last_error is null', async () => {
    stubFetches(makeHealth({ last_error: null }), makePacks(0))
    renderHome()
    await screen.findByText(liText('Local runtime: Ready'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows a port conflict card when last_error mentions EADDRINUSE', async () => {
    stubFetches(makeHealth({ last_error: 'EADDRINUSE: address already in use :::7355' }), makePacks(0))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/port conflict/i)
  })

  it('shows port troubleshooting guidance for port conflict errors', async () => {
    stubFetches(makeHealth({ last_error: 'EADDRINUSE port 7356 in use' }), makePacks(0))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByText(/a required port is already in use/i)).toBeInTheDocument()
  })

  it('shows the unreachable alert with troubleshooting docs link', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: /troubleshooting docs/i })).toBeInTheDocument()
  })

  it('shows a report-an-issue link in the unreachable alert', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    const links = screen.getAllByRole('link', { name: /report an issue/i })
    expect(links.length).toBeGreaterThanOrEqual(1)
  })
})

describe('Home — no-model recovery cards', () => {
  it('shows Install a GGUF model as a styled recovery card', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    await screen.findByRole('heading', { name: /no model configured/i })
    expect(screen.getByText(/download a local model file/i)).toBeInTheDocument()
  })

  it('shows Connect Ollama as a styled recovery card', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    await screen.findByRole('heading', { name: /no model configured/i })
    expect(screen.getByText(/use an existing ollama installation/i)).toBeInTheDocument()
  })

  it('shows text-only demo as a styled recovery card', async () => {
    stubFetches(makeHealth(), makePacks(0))
    renderHome()
    await screen.findByRole('heading', { name: /no model configured/i })
    expect(screen.getByText(/explore the interface now/i)).toBeInTheDocument()
  })
})

describe('Home — missing-pack section', () => {
  it('shows missing-pack notice when model is ready but no packs installed', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'TestModel' }), makePacks(0))
    renderHome()
    await screen.findByText('TestModel')
    expect(
      await screen.findByRole('status', { name: /no scenario packs installed/i }),
    ).toBeInTheDocument()
  })

  it('hides missing-pack notice when packs are installed', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'TestModel' }), makePacks(3))
    renderHome()
    await screen.findByText('TestModel')
    expect(
      screen.queryByRole('status', { name: /no scenario packs installed/i }),
    ).toBeNull()
  })

  it('hides missing-pack notice when no model is configured', async () => {
    stubFetches(makeHealth({ llm_ready: false }), makePacks(0))
    renderHome()
    await screen.findByText(liText('LLM: Not installed'))
    expect(
      screen.queryByRole('status', { name: /no scenario packs installed/i }),
    ).toBeNull()
  })

  it('links to the library from the missing-pack section', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'TestModel' }), makePacks(0))
    renderHome()
    await screen.findByText('TestModel')
    const section = await screen.findByRole('status', { name: /no scenario packs installed/i })
    const link = section.querySelector('a, [href]')
    expect(link).not.toBeNull()
  })
})

describe('Home — help section', () => {
  it('shows a Help section heading', () => {
    renderHome()
    expect(screen.getByRole('heading', { name: /^help$/i })).toBeInTheDocument()
  })

  it('shows a Documentation link', () => {
    renderHome()
    const link = screen.getByRole('link', { name: /^documentation$/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('shows a Report an issue link', () => {
    renderHome()
    // may be multiple (also appears in alerts); check at least one exists
    const links = screen.getAllByRole('link', { name: /report an issue/i })
    expect(links.length).toBeGreaterThanOrEqual(1)
    expect(links[0]).toHaveAttribute('target', '_blank')
  })

  it('shows the logs folder path', () => {
    renderHome()
    expect(screen.getByText(/\.convsim\/logs/)).toBeInTheDocument()
  })

  it('shows the data folder path', () => {
    renderHome()
    expect(screen.getByText(/~\/\.convsim$/)).toBeInTheDocument()
  })
})
