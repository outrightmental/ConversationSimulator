// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Home from '../screens/Home'

// @convsim/ui re-exports FormEditor which transitively imports @convsim/scenario-schema
// (requires zod at runtime).  Stub the package to avoid that peer dependency in tests.
vi.mock('@convsim/ui', () => ({
  StatusBadge: ({ children, status }: { children: React.ReactNode; status: string }) => (
    <span data-status={status}>{children}</span>
  ),
}))
import type { HealthResponse, LogbookProfile } from '@convsim/shared'
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

function makeLogbook(overrides: Partial<LogbookProfile> = {}): LogbookProfile {
  return {
    total_sessions: 0,
    total_practice_seconds: 0,
    streak_days: 0,
    last_session_date: null,
    dimension_scores: [],
    personal_records: [],
    strongest_dimension: null,
    weakest_dimension: null,
    last_session_delta: null,
    ...overrides,
  }
}

// Returns a testing-library function matcher that checks an element's full textContent
// against a list item whose content matches `expected`.
function liText(expected: string) {
  return (_content: string, el: Element | null): boolean =>
    el?.tagName === 'LI' && el.textContent?.trim() === expected
}

// Stub fetch: routes by URL pattern to the appropriate response.
// Includes text() because handleResponse now reads the body as text first.
function stubFetches(healthResp: object, packsResp: object, logbookResp: object = makeLogbook(), scenariosResp: object[] = []) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      let body: object = healthResp
      if (url.includes('/packs')) body = packsResp
      else if (url.includes('/logbook')) body = logbookResp
      else if (url.includes('/scenarios')) body = scenariosResp
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

  it('shows Checking while pack count fetch is in flight', () => {
    // fetch never resolves — packCount stays null
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderHome()
    expect(screen.getAllByText('Checking…').length).toBeGreaterThanOrEqual(1)
  })

  it('does not flash missing-pack notice before the pack count is known', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderHome()
    expect(screen.queryByRole('status', { name: /no scenario packs installed/i })).toBeNull()
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

  it('Local runtime badge links to the recovery section when offline', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    const runtimeLink = screen.getAllByRole('link').find(
      (el) => el.getAttribute('href') === '#runtime-recovery',
    )
    expect(runtimeLink).toBeDefined()
  })
})

describe('Home — runtime-error state', () => {
  it('shows Local runtime: Unavailable list item when API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    expect(await screen.findByText(liText('Local runtime: Unavailable'))).toBeInTheDocument()
  })

  it('shows a recovery alert when runtime is down', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).toBeInTheDocument()
  })

  it('shows plain-language title in the unreachable recovery card', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/the conversation engine is not responding/i)
  })

  it('does not contain API-server jargon in the unreachable card', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    const alert = await screen.findByRole('alert')
    expect(alert).not.toHaveTextContent(/api server/i)
    expect(alert).not.toHaveTextContent(/local runtime/i)
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
    expect(alert).toHaveTextContent(/another app is using a required port/i)
  })

  it('shows port troubleshooting guidance for port conflict errors', async () => {
    stubFetches(makeHealth({ last_error: 'EADDRINUSE port 7356 in use' }), makePacks(0))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByText(/close the conflicting app/i)).toBeInTheDocument()
  })

  it('shows the unreachable alert with troubleshooting docs link', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: /troubleshooting docs/i })).toBeInTheDocument()
  })

  it('shows a report-an-issue link in the help section', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    const links = screen.getAllByRole('link', { name: /report an issue/i })
    expect(links.length).toBeGreaterThanOrEqual(1)
  })
})

describe('Home — recovery card actions', () => {
  it('shows a Restart button in the unreachable recovery card', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: /restart the app/i })).toBeInTheDocument()
  })

  it('shows a Get support bundle link in the unreachable recovery card', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: /get support bundle/i })).toBeInTheDocument()
  })

  it('shows Restart conversation engine button for port conflict errors', async () => {
    stubFetches(makeHealth({ last_error: 'EADDRINUSE: address already in use :::7355' }), makePacks(0))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: /restart conversation engine/i })).toBeInTheDocument()
  })

  it('shows Restart conversation engine button for generic last_error', async () => {
    stubFetches(makeHealth({ last_error: 'Model crashed unexpectedly' }), makePacks(0))
    renderHome()
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: /restart conversation engine/i })).toBeInTheDocument()
  })

  it('calls sidecar stop then start when Restart conversation engine is clicked', async () => {
    const mockFetch = vi.fn((url: string) => {
      if (url.includes('/packs')) {
        const body = makePacks(0)
        return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify(body)) })
      }
      if (url.includes('/sidecar/status')) {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve(JSON.stringify({ state: 'crashed', model_path: '/models/test.gguf', error: null, log_path: '/tmp/log', host: '127.0.0.1', port: 7356 })),
        })
      }
      if (url.includes('/sidecar/stop') || url.includes('/sidecar/start')) {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve(JSON.stringify({ state: 'running', message: 'ok' })),
        })
      }
      // Health returns last_error to trigger the recovery card
      const body = makeHealth({ last_error: 'Sidecar crashed' })
      return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify(body)) })
    })
    vi.stubGlobal('fetch', mockFetch)

    renderHome()
    const restartBtn = await screen.findByRole('button', { name: /restart conversation engine/i })
    fireEvent.click(restartBtn)

    await waitFor(() => {
      const calls = mockFetch.mock.calls.map((c) => c[0] as string)
      expect(calls.some((u) => u.includes('/sidecar/stop'))).toBe(true)
    })
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

  it('shows Restore official packs button in the missing-pack section', async () => {
    stubFetches(makeHealth({ llm_ready: true, llm_model_name: 'TestModel' }), makePacks(0))
    renderHome()
    await screen.findByText('TestModel')
    await screen.findByRole('status', { name: /no scenario packs installed/i })
    expect(
      screen.getByRole('button', { name: /restore official packs/i }),
    ).toBeInTheDocument()
  })

  it('clears the missing-pack notice after a successful restore', async () => {
    // /packs starts at 0, then reports 1 after the reseed POST succeeds.
    let packsTotal = 0
    const mockFetch = vi.fn((url: string, init?: RequestInit) => {
      let body: object
      if (url.includes('/packs/reseed')) {
        packsTotal = 1
        body = { seeded: 1 }
      } else if (url.includes('/packs')) {
        body = { packs: [], total: packsTotal }
      } else if (url.includes('/logbook')) {
        body = makeLogbook()
      } else {
        body = makeHealth({ llm_ready: true, llm_model_name: 'TestModel' })
      }
      void init
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      })
    })
    vi.stubGlobal('fetch', mockFetch)

    renderHome()
    await screen.findByText('TestModel')
    await screen.findByRole('status', { name: /no scenario packs installed/i })

    fireEvent.click(screen.getByRole('button', { name: /restore official packs/i }))

    // Once the refreshed count reports a pack, the notice must disappear.
    await waitFor(() => {
      expect(
        screen.queryByRole('status', { name: /no scenario packs installed/i }),
      ).toBeNull()
    })
  })

  it('shows a retry affordance when restoring official packs fails', async () => {
    const mockFetch = vi.fn((url: string) => {
      let body: object
      if (url.includes('/packs/reseed')) {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ detail: 'internal error' }),
          text: () => Promise.resolve('internal error'),
        })
      } else if (url.includes('/packs')) {
        body = { packs: [], total: 0 }
      } else if (url.includes('/logbook')) {
        body = makeLogbook()
      } else {
        body = makeHealth({ llm_ready: true, llm_model_name: 'TestModel' })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      })
    })
    vi.stubGlobal('fetch', mockFetch)

    renderHome()
    await screen.findByRole('status', { name: /no scenario packs installed/i })

    fireEvent.click(screen.getByRole('button', { name: /restore official packs/i }))

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /retry/i }),
      ).toBeInTheDocument(),
    )
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

describe('Home — your training panel', () => {
  it('shows a "Your training" section heading', () => {
    renderHome()
    expect(screen.getByRole('heading', { name: /your training/i })).toBeInTheDocument()
  })

  it('shows empty state message when no sessions exist', async () => {
    stubFetches(makeHealth(), makePacks(0), makeLogbook({ total_sessions: 0 }))
    renderHome()
    expect(await screen.findByText(/no sessions yet/i)).toBeInTheDocument()
  })

  it('shows session count when sessions exist', async () => {
    stubFetches(makeHealth(), makePacks(1), makeLogbook({ total_sessions: 5, streak_days: 2 }))
    renderHome()
    expect(await screen.findByText(/sessions:/i)).toBeInTheDocument()
    expect(await screen.findByText(/streak:/i)).toBeInTheDocument()
  })

  it('links to the logbook when sessions exist', async () => {
    stubFetches(makeHealth(), makePacks(1), makeLogbook({ total_sessions: 3, streak_days: 1 }))
    renderHome()
    const link = await screen.findByRole('link', { name: /view full logbook/i })
    expect(link).toHaveAttribute('href', '/logbook')
  })

  it('shows start-now link in empty state pointing to library', async () => {
    stubFetches(makeHealth(), makePacks(0), makeLogbook({ total_sessions: 0 }))
    renderHome()
    const link = await screen.findByRole('link', { name: /start now/i })
    expect(link).toHaveAttribute('href', '/library')
  })
})

describe('Home — training plan section', () => {
  it('shows the Training plan heading', () => {
    renderHome()
    expect(screen.getByRole('heading', { name: /training plan/i })).toBeInTheDocument()
  })

  it('shows no-suggestions message when scenario list is empty', async () => {
    stubFetches(makeHealth(), makePacks(0), makeLogbook(), [])
    renderHome()
    expect(await screen.findByText(/install a scenario pack/i)).toBeInTheDocument()
  })

  it('shows a recommended scenario title when scenarios are available with no profile', async () => {
    const scenarios = [
      {
        scenario_id: 's_intro',
        pack_id: 'p1',
        title: 'Starter Chat',
        summary: 'An intro scenario.',
        content_rating: 'G',
        player_role: { label: 'You', brief: 'You talk.' },
        difficulty: { default: 'standard', options: {} },
        supported_languages: ['en'],
        duration: { max_turns: 10, soft_time_limit_minutes: 15 },
        state_meters_permitted: false,
        voice_supported: false,
        safety_summary: '',
        estimated_length_label: '~10 min',
        ladder_position: 'intro',
      },
    ]
    stubFetches(makeHealth(), makePacks(1), makeLogbook({ total_sessions: 0 }), scenarios)
    renderHome()
    const link = await screen.findByText('Starter Chat')
    // Recommendation links to the scenario setup screen, not the generic library.
    expect(link.closest('a')).toHaveAttribute('href', '/setup/s_intro')
  })

  it('recommends a scenario targeting the weakest dimension with an active profile', async () => {
    const scenarios = [
      {
        scenario_id: 's_listen',
        pack_id: 'p1',
        title: 'Listening drill',
        summary: 'Practice listening.',
        content_rating: 'G',
        player_role: { label: 'You', brief: 'You listen.' },
        difficulty: { default: 'standard', options: {} },
        supported_languages: ['en'],
        duration: { max_turns: 10, soft_time_limit_minutes: 15 },
        state_meters_permitted: false,
        voice_supported: false,
        safety_summary: '',
        estimated_length_label: '~10 min',
        tested_dimensions: ['active_listening'],
        ladder_position: 'practice',
      },
    ]
    const profile = makeLogbook({
      total_sessions: 5,
      dimension_scores: [
        { dimension_id: 'active_listening', rolling_score: 20, session_count: 5, trajectory: [20] },
      ],
    })
    stubFetches(makeHealth(), makePacks(1), profile, scenarios)
    renderHome()
    expect(await screen.findByText('Listening drill')).toBeInTheDocument()
  })
})
