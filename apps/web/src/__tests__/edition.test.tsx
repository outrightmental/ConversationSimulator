// SPDX-License-Identifier: Apache-2.0
//
// Demo edition (Steam Next Fest demo, issue #495): the same build narrowed to
// one model and five conversations. These tests cover the edition module
// itself and the demo-specific rendering of the screens it trims.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { HealthResponse, ScenarioInfo } from '@convsim/shared'

// @convsim/ui re-exports FormEditor which transitively imports @convsim/scenario-schema
// (requires zod at runtime).  Stub the package to avoid that peer dependency in tests.
vi.mock('@convsim/ui', () => ({
  StatusBadge: ({ children, status }: { children: React.ReactNode; status: string }) => (
    <span data-status={status}>{children}</span>
  ),
}))

import {
  EDITION_POLL_INTERVAL_MS,
  EditionContext,
  EditionProvider,
  FULL_APP_STEAM_APP_ID,
  FULL_APP_STEAM_URL,
  buildEdition,
  reconcileEdition,
  useEdition,
  type EditionState,
} from '../edition'
import DemoUpsellCard from '../components/DemoUpsellCard'
import DemoConversations, { orderDemoScenarios } from '../components/DemoConversations'
import Home from '../screens/Home'
import AppLayout from '../layout/AppLayout'
import App from '../App'

const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true }

function makeScenario(id: string, title: string, pack: string, extra: Partial<ScenarioInfo> = {}): ScenarioInfo {
  return {
    scenario_id: id,
    title,
    summary: `${title} summary.`,
    content_rating: 'PG',
    pack_id: pack,
    pack_name: pack,
    player_role: { label: 'Player', brief: '' },
    difficulty: { default: 'standard', options: { standard: {} } },
    supported_languages: ['en'],
    duration: { max_turns: 12, soft_time_limit_minutes: 10 },
    state_meters_permitted: true,
    voice_supported: false,
    safety_summary: '',
    estimated_length_label: '10 min',
    ...extra,
  } as ScenarioInfo
}

const FIVE: ScenarioInfo[] = [
  makeScenario('behavioral_interview', 'The Behavioral Interview', 'Job Interview Basics'),
  makeScenario('used_car_negotiation', 'The Used Car Deal', 'Everyday Negotiation'),
  makeScenario('ask_for_raise', 'Making the Case', 'Difficult Conversations'),
  makeScenario('the_ask', 'The Coffee Cart', 'Dating — Confidence & Boundaries'),
  makeScenario('spanish_coffee', 'Coffee at Café Sol', 'Language Café', { supported_languages: ['es'] }),
]
const FIVE_IDS = FIVE.map((s) => s.scenario_id)

function makeHealth(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: 'ok',
    version: '0.1.0',
    runtime: {
      llm_ready: true,
      llm_model_name: 'Qwen3 4B',
      stt_ready: false,
      tts_ready: false,
      tts_voice_name: null,
      network_required: false,
    },
    ...overrides,
  }
}

const DEMO_HEALTH = makeHealth({
  edition: 'demo',
  demo: { model_id: 'qwen3-4b-instruct-q4_k_m', scenario_ids: FIVE_IDS, pack_ids: [] },
})

// What the demo engine's /api/models returns: exactly one registry model.
const DEMO_MODELS = {
  registry: [{
    id: 'qwen3-4b-instruct-q4_k_m', name: 'Qwen3 4B Instruct Q4_K_M', provider: 'huggingface', family: 'qwen3',
    role: 'starter', format: 'gguf', license_spdx: 'Apache-2.0', license_url: null, source_type: 'registry',
    download_url: 'https://example.invalid/q.gguf', sha256: 'a'.repeat(64), size_gb: 2.6, min_vram_gb: 4,
    recommended_vram_gb: 6, context_length: 8192, registered_at: '2026-01-01T00:00:00.000Z',
  }],
  installed: [],
  ollama_models: [],
  active: { runtime_id: null, model_id: null },
  runtime_health: {
    runtime_id: 'none', runtime_name: 'llama.cpp', status: 'unavailable', model_id: null,
    latency_ms: null, message: 'No model configured', checked_at: '2026-01-01T00:00:00.000Z',
  },
  total: 1,
  last_benchmark: null,
}

function okResponse(body: object) {
  const text = JSON.stringify(body)
  return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(body), text: () => Promise.resolve(text) })
}

// Route fetch by URL so Home's health / packs / logbook / scenarios calls all resolve.
function stubFetches(health: object, scenarios: object[] = [], packsTotal = 5) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      let body: object = health
      if (url.includes('/packs')) body = { packs: [], total: packsTotal }
      else if (url.includes('/logbook')) body = {
        total_sessions: 0, total_practice_seconds: 0, streak_days: 0, last_session_date: null,
        dimension_scores: [], personal_records: [], strongest_dimension: null, weakest_dimension: null,
        last_session_delta: null,
      }
      else if (url.includes('/scenarios')) body = scenarios
      const text = JSON.stringify(body)
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(body), text: () => Promise.resolve(text) })
    }),
  )
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

// ── buildEdition / reconcileEdition ───────────────────────────────────────────

describe('buildEdition', () => {
  it('is null when the bundle carries no edition', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', '')
    expect(buildEdition()).toBeNull()
  })

  it('reads demo from VITE_CONVSIM_EDITION (case-insensitive)', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'Demo')
    expect(buildEdition()).toBe('demo')
  })

  it('reads full from VITE_CONVSIM_EDITION', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'full')
    expect(buildEdition()).toBe('full')
  })

  it('ignores unknown values', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'trial')
    expect(buildEdition()).toBeNull()
  })
})

describe('reconcileEdition', () => {
  const noBuild: EditionState = { edition: 'full', demo: null, source: 'default' }

  it('adopts the server edition when the bundle did not say', () => {
    const next = reconcileEdition(noBuild, DEMO_HEALTH)
    expect(next.edition).toBe('demo')
    expect(next.source).toBe('server')
    expect(next.demo?.scenario_ids).toEqual(FIVE_IDS)
  })

  it('treats an older core with no edition field as the full app', () => {
    const next = reconcileEdition(noBuild, makeHealth())
    expect(next.edition).toBe('full')
    expect(next.demo).toBeNull()
  })

  it('keeps the build-time edition and takes the demo facts from the server', () => {
    const built: EditionState = { edition: 'demo', demo: null, source: 'build' }
    const next = reconcileEdition(built, DEMO_HEALTH)
    expect(next.edition).toBe('demo')
    expect(next.source).toBe('build')
    expect(next.demo?.model_id).toBe('qwen3-4b-instruct-q4_k_m')
  })

  it('warns (but keeps the bundle edition) when the engine disagrees', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const built: EditionState = { edition: 'demo', demo: null, source: 'build' }
    const next = reconcileEdition(built, makeHealth({ edition: 'full' }))
    expect(next.edition).toBe('demo')
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })

  it('never carries demo facts into the full edition', () => {
    const built: EditionState = { edition: 'full', demo: null, source: 'build' }
    const next = reconcileEdition(built, DEMO_HEALTH)
    expect(next.edition).toBe('full')
    expect(next.demo).toBeNull()
  })
})

describe('EditionProvider', () => {
  function Probe() {
    const { edition, source, demo } = useEdition()
    return <span data-testid="probe">{`${edition}/${source}/${demo?.scenario_ids.length ?? 0}`}</span>
  }

  it('defaults to full outside a provider and without a build flag', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', '')
    render(<Probe />)
    expect(screen.getByTestId('probe').textContent).toBe('full/default/0')
  })

  it('reads the build flag outside a provider', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'demo')
    render(<Probe />)
    expect(screen.getByTestId('probe').textContent).toBe('demo/build/0')
  })

  it('adopts the engine-reported demo edition once health answers', async () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', '')
    stubFetches(DEMO_HEALTH)
    render(
      <EditionProvider>
        <Probe />
      </EditionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('demo/server/5'))
  })

  it('keeps asking until the engine answers, then stops', async () => {
    // In the desktop shell the first call usually lands before the sidecar
    // listens; the provider must not give up on the engine's edition then.
    vi.stubEnv('VITE_CONVSIM_EDITION', '')
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      let calls = 0
      vi.stubGlobal('fetch', vi.fn(() => {
        calls += 1
        if (calls === 1) return Promise.reject(new Error('engine not up yet'))
        return okResponse(DEMO_HEALTH)
      }))
      render(
        <EditionProvider>
          <Probe />
        </EditionProvider>,
      )
      await vi.advanceTimersByTimeAsync(EDITION_POLL_INTERVAL_MS + 50)
      await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('demo/server/5'))
      const settled = calls
      await vi.advanceTimersByTimeAsync(EDITION_POLL_INTERVAL_MS * 3)
      expect(calls).toBe(settled)
    } finally {
      vi.useRealTimers()
    }
  })
})

// ── Demo components ───────────────────────────────────────────────────────────

describe('orderDemoScenarios', () => {
  it('orders by the curated list and drops anything not in it', () => {
    const extra = makeScenario('hostile_executive_interview', 'Gauntlet', 'Job Interview Basics')
    const shuffled = [FIVE[4], extra, FIVE[0], FIVE[2]]
    expect(orderDemoScenarios(shuffled, FIVE_IDS).map((s) => s.scenario_id)).toEqual([
      'behavioral_interview', 'ask_for_raise', 'spanish_coffee',
    ])
  })

  it('falls back to the server list (minus the tutorial) when no curated list is known', () => {
    const tutorial = makeScenario('first_words_tutorial', 'First Words', 'Tutorial')
    expect(orderDemoScenarios([tutorial, ...FIVE], null).map((s) => s.scenario_id)).toEqual(FIVE_IDS)
  })
})

describe('DemoUpsellCard', () => {
  it('links to the paid base app on Steam in a new tab', () => {
    render(<DemoUpsellCard />)
    const link = screen.getByTestId('demo-upsell-link')
    expect(link).toHaveAttribute('href', FULL_APP_STEAM_URL)
    expect(link).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('heading', { name: /get the full game/i })).toBeInTheDocument()
  })

  it('lists what the full version adds', () => {
    render(<DemoUpsellCard />)
    expect(screen.getByText(/creator workbench/i)).toBeInTheDocument()
    expect(screen.getByText(/complete scenario library/i)).toBeInTheDocument()
  })

  it('compact variant omits the bullet list', () => {
    render(<DemoUpsellCard compact />)
    expect(screen.queryByText(/creator workbench/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('demo-upsell-link')).toBeInTheDocument()
  })

  it('describes the full library accurately (five player-facing packs, twenty conversations)', () => {
    render(<DemoUpsellCard />)
    expect(screen.getByText(/20 conversations across five packs/i)).toBeInTheDocument()
  })

  describe('in the desktop shell', () => {
    function installTauri(overlayShown: boolean) {
      const invoke = vi.fn(async (cmd: string) => (cmd === 'steam_open_store_page' ? overlayShown : undefined))
      Object.defineProperty(window, '__TAURI__', { value: { core: { invoke } }, configurable: true })
      return invoke
    }
    afterEach(() => {
      delete (window as { __TAURI__?: unknown }).__TAURI__
    })

    it('opens the store page in the Steam overlay when Steam shows it', async () => {
      const invoke = installTauri(true)
      render(<DemoUpsellCard />)
      fireEvent.click(screen.getByTestId('demo-upsell-link'))
      await waitFor(() =>
        expect(invoke).toHaveBeenCalledWith('steam_open_store_page', { appId: FULL_APP_STEAM_APP_ID }),
      )
      expect(invoke).not.toHaveBeenCalledWith('plugin:shell|open', expect.anything())
    })

    it('falls back to the browser when there is no overlay to show', async () => {
      const invoke = installTauri(false)
      render(<DemoUpsellCard />)
      fireEvent.click(screen.getByTestId('demo-upsell-link'))
      await waitFor(() => expect(invoke).toHaveBeenCalledWith('plugin:shell|open', { path: FULL_APP_STEAM_URL }))
    })
  })
})

describe('DemoConversations', () => {
  it('renders one card per curated conversation, in curated order, each linking to setup', async () => {
    stubFetches(DEMO_HEALTH, [FIVE[3], FIVE[1], FIVE[0], FIVE[4], FIVE[2]])
    const state: EditionState = { edition: 'demo', demo: DEMO_HEALTH.demo!, source: 'server' }
    render(
      <EditionContext.Provider value={state}>
        <MemoryRouter future={ROUTER_FUTURE}>
          <DemoConversations />
        </MemoryRouter>
      </EditionContext.Provider>,
    )
    const cards = await screen.findAllByTestId('demo-conversation-card')
    expect(cards).toHaveLength(5)
    expect(cards.map((c) => within(c).getByRole('heading', { level: 3 }).textContent)).toEqual(
      FIVE.map((s) => s.title),
    )
    // WebKit drops list semantics from `list-style: none` lists unless the
    // role is explicit; this list is the demo's navigation.
    expect(within(screen.getByTestId('demo-conversations')).getByRole('list')).toHaveAttribute('role', 'list')
    expect(within(cards[0]).getByRole('link', { name: /start the behavioral interview/i })).toHaveAttribute(
      'href',
      '/setup/behavioral_interview',
    )
  })

  it('labels a non-English conversation with its language name, never the code', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    render(
      <MemoryRouter future={ROUTER_FUTURE}>
        <DemoConversations />
      </MemoryRouter>,
    )
    const cards = await screen.findAllByTestId('demo-conversation-card')
    expect(cards[4]).toHaveTextContent(/in Spanish/)
    expect(cards[4]).not.toHaveTextContent(/in es\b/)
    expect(cards[0]).not.toHaveTextContent(/in English/)
  })

  it('shows an error when the scenario list cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('down'))))
    render(
      <MemoryRouter future={ROUTER_FUTURE}>
        <DemoConversations />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

// ── Home in the demo edition ──────────────────────────────────────────────────

describe('Home — demo edition', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'demo')
  })

  function renderHome() {
    return render(
      <MemoryRouter future={ROUTER_FUTURE}>
        <Home />
      </MemoryRouter>,
    )
  }

  it('shows the demo title and the five conversations instead of the primary actions', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    renderHome()
    expect(screen.getByRole('heading', { name: /conversation simulator — demo/i })).toBeInTheDocument()
    expect(await screen.findAllByTestId('demo-conversation-card')).toHaveLength(5)
    expect(screen.queryByRole('link', { name: /start a scenario/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /create \/ edit/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /import pack/i })).not.toBeInTheDocument()
  })

  it('never links to the library, workbench or logbook', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    renderHome()
    await screen.findAllByTestId('demo-conversation-card')
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href') ?? '')
    expect(hrefs.some((h) => h.startsWith('/library'))).toBe(false)
    expect(hrefs.some((h) => h.startsWith('/workbench'))).toBe(false)
    expect(hrefs.some((h) => h.startsWith('/logbook'))).toBe(false)
  })

  it('shows the single upsell card', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    renderHome()
    expect(await screen.findByTestId('demo-upsell-card')).toBeInTheDocument()
  })

  it('hides the training sections and the voice/pack status rows', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    renderHome()
    await screen.findAllByTestId('demo-conversation-card')
    expect(screen.queryByRole('heading', { name: /training plan/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /your training/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/^Voice input:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Voice output:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Packs:/)).not.toBeInTheDocument()
  })

  it('offers a single "install the demo model" path when no model is ready', async () => {
    stubFetches(makeHealth({ edition: 'demo', runtime: { ...makeHealth().runtime, llm_ready: false, llm_model_name: null } }), FIVE)
    renderHome()
    const link = await screen.findByTestId('demo-install-model-link')
    expect(link).toHaveAttribute('href', '/model-manager')
    expect(screen.queryByRole('heading', { name: /no model configured/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/connect ollama/i)).not.toBeInTheDocument()
    // The download comes first on the page: the five Start buttons below it
    // cannot do anything until the model is installed.
    await screen.findAllByTestId('demo-conversation-card')
    expect(screen.getAllByRole('link')[0]).toBe(link)
    // Until then the LLM badge is the same repair path.
    expect(screen.getByRole('link', { name: /not installed/i })).toHaveAttribute('href', '/model-manager')
  })

  it('shows a ready model as a plain badge, not a link to a manager that would only reinstall it', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    renderHome()
    await screen.findAllByTestId('demo-conversation-card')
    expect(screen.getByText('Qwen3 4B')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Qwen3 4B' })).not.toBeInTheDocument()
  })

  it('keeps the engine status and help sections', async () => {
    stubFetches(DEMO_HEALTH, FIVE)
    renderHome()
    expect(await screen.findByText((_, el) => el?.tagName === 'LI' && el.textContent?.trim() === 'AI engine: Ready')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^help$/i })).toBeInTheDocument()
  })
})

// ── App shell in the demo edition ─────────────────────────────────────────────

describe('AppLayout — demo edition', () => {
  it('shows only Home, Settings and Support plus a Demo badge', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'demo')
    render(
      <MemoryRouter future={ROUTER_FUTURE}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const nav = screen.getByRole('navigation', { name: /main navigation/i })
    const labels = within(nav).getAllByRole('link').map((a) => a.textContent)
    expect(labels).toEqual(['Home', 'Settings', 'Support'])
    expect(screen.getByTestId('edition-badge')).toHaveTextContent(/demo/i)
  })

  it('shows the full navigation and no badge in the full edition', () => {
    vi.stubEnv('VITE_CONVSIM_EDITION', '')
    render(
      <MemoryRouter future={ROUTER_FUTURE}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const nav = screen.getByRole('navigation', { name: /main navigation/i })
    expect(within(nav).getAllByRole('link')).toHaveLength(6)
    expect(screen.queryByTestId('edition-badge')).not.toBeInTheDocument()
  })
})

describe('App routes — demo edition', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_CONVSIM_EDITION', 'demo')
    localStorage.setItem('convsim.setup.complete', 'true')
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
  })

  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
        <App />
      </MemoryRouter>,
    )
  }

  it.each(['/library', '/workbench', '/logbook'])('collapses %s to the demo Home', (path) => {
    renderAt(path)
    expect(screen.getByRole('heading', { name: /conversation simulator — demo/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /scenario library/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /creator workbench/i })).not.toBeInTheDocument()
  })

  it.each([
    ['/settings', /^settings$/i],
    ['/support', /^support$/i],
  ])('still serves %s', (path, heading) => {
    renderAt(path)
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
  })

  it("still serves the model manager — the demo's one repair path", async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/models')) return okResponse(DEMO_MODELS)
      if (url.includes('/preflight')) return okResponse({ overall: 'pass', checks: [], ran_at: '2026-01-01T00:00:00.000+00:00' })
      return new Promise(() => {})
    }))
    renderAt('/model-manager')
    expect(await screen.findByRole('heading', { name: /set up your model/i })).toBeInTheDocument()
    expect(screen.getByText(/the demo uses one ai model/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /install qwen3 4b/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /browse ollama models/i })).not.toBeInTheDocument()
  })
})
