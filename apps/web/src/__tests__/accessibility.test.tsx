// SPDX-License-Identifier: Apache-2.0
/**
 * Automated accessibility checks using axe-core.
 *
 * These tests catch common WCAG 2.1 violations (missing labels, landmark
 * structure, ARIA contract mismatches, etc.) at the component level.  They
 * complement—not replace—manual keyboard and screen-reader passes.
 *
 * Known limitations:
 * - Colour-contrast rules depend on computed CSS which jsdom cannot evaluate
 *   from inline styles.  Browser-level contrast checks (e.g. Playwright + axe)
 *   are tracked as a follow-up item.
 * - Dynamic ARIA states that require user interaction (recording, submitting)
 *   are covered in the per-component interaction test suites.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import axe from 'axe-core'

// ── Mocks ────────────────────────────────────────────────────────────────────

// @convsim/ui re-exports FormEditor which pulls in @convsim/scenario-schema
// (needs zod at runtime).  Stub the package to avoid that dependency in tests.
vi.mock('@convsim/ui', () => ({
  StatusBadge: ({ children, status }: { children: React.ReactNode; status: string }) => (
    <span data-status={status}>{children}</span>
  ),
}))

vi.mock('../api/client', () => ({
  api: {
    health: vi.fn().mockResolvedValue({ ok: false, error: { kind: 'network', message: 'unavailable' } }),
    listScenarios: vi.fn().mockResolvedValue({ ok: true, data: [] }),
    getScenario: vi.fn().mockResolvedValue({ ok: false, error: { kind: 'network', message: 'unavailable' } }),
    startSession: vi.fn().mockReturnValue(new Promise(() => {})),
    endSession: vi.fn(),
    submitTurn: vi.fn(),
    generateDebrief: vi.fn().mockReturnValue(new Promise(() => {})),
    exportSession: vi.fn(),
    getLogbookProfile: vi.fn().mockReturnValue(new Promise(() => {})),
    exportLogbook: vi.fn().mockReturnValue(new Promise(() => {})),
    connectSession: vi.fn().mockReturnValue({ close: vi.fn() }),
    listSessions: vi.fn().mockResolvedValue({ ok: true, data: { sessions: [] } }),
    getDataFolder: vi.fn().mockResolvedValue({ ok: true, data: { path: '/tmp/data' } }),
    getFolders: vi.fn().mockResolvedValue({ ok: true, data: { data: '/tmp/data', logs: '/tmp/logs', models: '/tmp/models', packs: '/tmp/packs' } }),
    clearLocalData: vi.fn(),
    deleteSession: vi.fn(),
    listVoices: vi.fn().mockResolvedValue({ ok: true, data: { voices: [] } }),
    listPacks: vi.fn().mockResolvedValue({ ok: true, data: { packs: [], total: 0 } }),
    importPack: vi.fn(),
    getPack: vi.fn(),
    validatePack: vi.fn(),
    preflight: vi.fn().mockResolvedValue({ ok: true, data: { overall: 'pass', checks: [], ran_at: '2026-01-01T00:00:00.000+00:00' } }),
    // RuntimeSettingsPanel
    getModels: vi.fn().mockReturnValue(new Promise(() => {})),
    getRuntimeSettings: vi.fn().mockReturnValue(new Promise(() => {})),
    useModel: vi.fn(),
    updateRuntimeSettings: vi.fn(),
    resetRuntimeSettings: vi.fn(),
    // VoiceSettingsPanel
    getTtsCacheSize: vi.fn().mockReturnValue(new Promise(() => {})),
    clearTtsCache: vi.fn(),
    vadHealth: vi.fn().mockReturnValue(new Promise(() => {})),
    // Steam Cloud settings
    getCloudSettings: vi.fn().mockReturnValue(new Promise(() => {})),
    putCloudSettings: vi.fn(),
    // NPC relationship memory
    listRelationshipMemory: vi.fn().mockResolvedValue({ ok: true, data: { recaps: [], total: 0 } }),
    workbench: {
      listPacks: vi.fn().mockResolvedValue({ ok: true, data: [] }),
      listFiles: vi.fn().mockResolvedValue({ ok: true, data: { tree: [] } }),
      validate: vi.fn().mockResolvedValue({ ok: false, error: { kind: 'network', message: 'unavailable' } }),
      readFile: vi.fn(),
      writeFile: vi.fn(),
      copyToLocal: vi.fn(),
      importPack: vi.fn(),
      exportPack: vi.fn(),
    },
    workshop: {
      listItems: vi.fn().mockResolvedValue({ ok: true, data: { items: [] } }),
      sync: vi.fn(),
      listQuarantine: vi.fn().mockResolvedValue({ ok: true, data: { items: [] } }),
      remove: vi.fn(),
    },
  },
  apiClient: {
    health: vi.fn(),
    uploadAudio: vi.fn().mockResolvedValue({ ok: true, data: { transcript: null, status: 'unavailable' } }),
    vadHealth: vi.fn().mockResolvedValue({ ok: true, data: { worker_id: '', worker_name: '', status: 'unavailable', checked_at: '' } }),
    vadCalibrate: vi.fn(),
  },
}))

vi.mock('../api/useApiHealth', () => ({
  useApiHealth: vi.fn().mockReturnValue({ state: 'loading', healthy: false, runtime: null }),
}))

vi.mock('../api/usePackCount', () => ({
  usePackCount: vi.fn().mockReturnValue({ count: 0, refetch: vi.fn() }),
}))

vi.mock('../api/useLogbookProfile', () => ({
  useLogbookProfile: vi.fn().mockReturnValue({ state: 'loading', profile: null }),
}))

vi.mock('../hooks/useSteamAchievements', () => ({
  useSteamAchievements: () => ({
    unlock: vi.fn(() => Promise.resolve(false)),
    incrementStat: vi.fn(() => Promise.resolve(false)),
  }),
  SteamAchievement: {
    FIRST_SCENARIO: 'ACH_FIRST_SCENARIO',
    FIRST_DEBRIEF: 'ACH_FIRST_DEBRIEF',
    PRACTICE_STREAK: 'ACH_PRACTICE_STREAK',
    PACK_EXPLORER: 'ACH_PACK_EXPLORER',
    CREATOR_FIRST_VALIDATE: 'ACH_CREATOR_FIRST_VALIDATE',
  },
  SteamStat: {
    SCENARIOS_COMPLETED: 'STAT_SCENARIOS_COMPLETED',
    DEBRIEFS_GENERATED: 'STAT_DEBRIEFS_GENERATED',
    PACKS_VALIDATED: 'STAT_PACKS_VALIDATED',
    TEXT_MODE_SESSIONS: 'STAT_TEXT_MODE_SESSIONS',
    VOICE_MODE_SESSIONS: 'STAT_VOICE_MODE_SESSIONS',
  },
}))

// ── Screen imports ────────────────────────────────────────────────────────────

import Home from '../screens/Home'
import ScenarioLibrary from '../screens/ScenarioLibrary'
import Settings from '../screens/Settings'
import Debrief from '../screens/Debrief'
import CreatorWorkbench from '../screens/CreatorWorkbench'
import FirstRunWizard from '../screens/FirstRunWizard'
import AppLayout from '../layout/AppLayout'
import MicButton from '../components/MicButton'
import VadStatusIndicator from '../components/VadStatusIndicator'
import DebugDrawer from '../components/DebugDrawer'
import TranscriptReviewPanel from '../components/TranscriptReviewPanel'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Run axe on `container`, disabling colour-contrast (not computable in jsdom).
 */
async function runAxe(container: HTMLElement) {
  const results = await axe.run(container, {
    rules: {
      'color-contrast': { enabled: false },
    },
  })
  return results.violations
}

function renderInRouter(ui: React.ReactElement) {
  const { container } = render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>,
  )
  return container
}

function formatViolations(violations: axe.Result[]): string {
  if (violations.length === 0) return ''
  return violations
    .map(
      (v) =>
        `[${v.impact}] ${v.id}: ${v.description}\n  ` +
        v.nodes
          .slice(0, 2)
          .map((n) => n.html)
          .join('\n  '),
    )
    .join('\n')
}

// ── Tests ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Accessibility: AppLayout', () => {
  it('has no axe violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div><h1>Test page</h1></div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('includes a skip-to-main-content link', () => {
    const { container } = render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div><h1>Test page</h1></div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(container.querySelector('a[href="#main-content"]')).not.toBeNull()
  })

  it('has a labelled main navigation landmark', () => {
    const { container } = render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div><h1>Test page</h1></div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(container.querySelector('nav[aria-label]')).not.toBeNull()
  })

  it('renders a translated Logbook nav link (not a raw i18n key)', () => {
    const { container } = render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div><h1>Test page</h1></div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const logbookLink = container.querySelector('a[href="/logbook"]')
    expect(logbookLink).not.toBeNull()
    expect(logbookLink?.textContent).toBe('Logbook')
  })

  it('main element has the id targeted by the skip link', () => {
    const { container } = render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div><h1>Test page</h1></div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(container.querySelector('#main-content')).not.toBeNull()
  })

  it('moves focus to the main landmark on route change (but not on initial mount)', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div><h1>Home</h1><Link to="/next">Next</Link></div>} />
            <Route path="next" element={<h1>Next page</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const main = container.querySelector('#main-content')
    // Initial mount must not steal focus.
    expect(document.activeElement).not.toBe(main)

    fireEvent.click(container.querySelector('a[href="/next"]')!)
    expect(document.activeElement).toBe(main)
  })
})

describe('Accessibility: Home', () => {
  it('has no axe violations', async () => {
    const container = renderInRouter(<Home />)
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })
})

describe('Accessibility: ScenarioLibrary', () => {
  it('has no axe violations in loading state', async () => {
    const container = renderInRouter(<ScenarioLibrary />)
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })
})

describe('Accessibility: Settings', () => {
  it('has no axe violations', async () => {
    const container = renderInRouter(<Settings />)
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('advanced toggle button exposes aria-controls pointing to its panel', () => {
    const { container } = render(
      <MemoryRouter><Settings /></MemoryRouter>,
    )
    const btn = container.querySelector('button[aria-expanded]')
    expect(btn?.getAttribute('aria-controls')).toBe('settings-advanced-section')
  })
})

describe('Accessibility: Debrief (loading state)', () => {
  it('has no axe violations while loading', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/debrief/sess-001']}>
        <Routes>
          <Route path="/debrief/:sessionId" element={<Debrief />} />
        </Routes>
      </MemoryRouter>,
    )
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })
})

describe('Accessibility: CreatorWorkbench', () => {
  it('has no axe violations in initial state (no pack selected)', async () => {
    const container = renderInRouter(<CreatorWorkbench />)
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })
})

describe('Accessibility: MicButton', () => {
  it('has no axe violations when permission is granted and not recording', async () => {
    const { container } = render(
      <MicButton
        permission="granted"
        isRecording={false}
        recordingSeconds={0}
        isSubmitting={false}
        onRequestPermission={vi.fn()}
        onRecordStart={vi.fn()}
        onRecordStop={vi.fn()}
      />,
    )
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('has no axe violations while recording', async () => {
    const { container } = render(
      <MicButton
        permission="granted"
        isRecording={true}
        recordingSeconds={5}
        isSubmitting={false}
        onRequestPermission={vi.fn()}
        onRecordStart={vi.fn()}
        onRecordStop={vi.fn()}
      />,
    )
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('sets aria-pressed=true on the record button while recording', () => {
    const { container } = render(
      <MicButton
        permission="granted"
        isRecording={true}
        recordingSeconds={3}
        isSubmitting={false}
        onRequestPermission={vi.fn()}
        onRecordStart={vi.fn()}
        onRecordStop={vi.fn()}
      />,
    )
    expect(container.querySelector('button[aria-pressed="true"]')).not.toBeNull()
  })
})

describe('Accessibility: VadStatusIndicator', () => {
  const states = ['idle', 'listening', 'speech', 'silence', 'stopping'] as const

  for (const state of states) {
    it(`has no axe violations in ${state} state`, async () => {
      const { container } = render(<VadStatusIndicator state={state} />)
      const violations = await runAxe(container)
      expect(violations, formatViolations(violations)).toHaveLength(0)
    })
  }

  it('exposes an aria-label that names the current VAD state', () => {
    const { container } = render(<VadStatusIndicator state="listening" />)
    const el = container.querySelector('[aria-label]')
    expect(el?.getAttribute('aria-label')).toMatch(/listening/i)
  })
})

describe('Accessibility: DebugDrawer', () => {
  it('has no axe violations with no entries', async () => {
    const { container } = render(<DebugDrawer entries={[]} />)
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('the details element carries an aria-label', () => {
    const { container } = render(<DebugDrawer entries={[]} />)
    const details = container.querySelector('details')
    expect(details?.getAttribute('aria-label')).toBeTruthy()
  })
})

describe('Accessibility: TranscriptReviewPanel', () => {
  it('has no axe violations', async () => {
    const { container } = render(
      <TranscriptReviewPanel
        transcript="Hello, how are you?"
        language="en"
        confidence={0.92}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        onRetry={vi.fn()}
      />,
    )
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('moves focus to the transcript textarea on mount', () => {
    const { container } = render(
      <TranscriptReviewPanel
        transcript="Test transcript."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        onRetry={vi.fn()}
      />,
    )
    const textarea = container.querySelector('textarea')
    expect(document.activeElement).toBe(textarea)
  })
})

describe('Accessibility: FirstRunWizard', () => {
  beforeEach(() => {
    // Prevent a previous test's localStorage state from triggering the "already complete" redirect.
    localStorage.clear()
  })

  it('welcome step has no axe violations', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div data-testid="home" />} />
        </Routes>
      </MemoryRouter>,
    )
    const violations = await runAxe(container)
    expect(violations, formatViolations(violations)).toHaveLength(0)
  })

  it('does not steal focus on initial welcome-step mount', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )
    const h1 = container.querySelector('h1')
    expect(document.activeElement).not.toBe(h1)
  })

  it('moves focus to the step heading when the step advances', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )
    // Clicking "Get started" transitions from welcome → loading; getModels is a pending
    // promise in this test suite so the wizard stays on the loading step.
    fireEvent.click(container.querySelector('button')!)
    const newH1 = container.querySelector('h1')
    expect(document.activeElement).toBe(newH1)
  })

  it('loading step announces busy state', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(container.querySelector('button')!)
    const busyEl = container.querySelector('[aria-busy="true"]')
    expect(busyEl).not.toBeNull()
  })

  it('welcome step has a privacy toggle button', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )
    // Privacy is behind a disclosure toggle; the toggle button must be present.
    const privacyBtn = container.querySelector('button[aria-controls="welcome-privacy-details"]')
    expect(privacyBtn).not.toBeNull()
  })

  it('welcome step privacy note is accessible when expanded', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )
    // Expand the privacy disclosure.
    const toggle = container.querySelector('button[aria-controls="welcome-privacy-details"]')!
    fireEvent.click(toggle)
    expect(container.querySelector('[role="note"][aria-label*="privacy"]')).not.toBeNull()
  })

  it('choose step option cards are presented as a list', async () => {
    // Override getModels to resolve for all calls (pre-fetch + loading step).
    // An empty registry causes handleSetMeUp to fall back to the choose step.
    const { api: mockApi } = await import('../api/client')
    vi.mocked(mockApi.getModels).mockResolvedValue({ ok: true, data: {
      registry: [],
      installed: [],
      ollama_models: [],
      active: { runtime_id: null, model_id: null },
      runtime_health: {
        runtime_id: 'none',
        runtime_name: 'llama.cpp',
        status: 'unavailable',
        model_id: null,
        latency_ms: null,
        message: 'No model configured',
        checked_at: '2026-01-01T00:00:00.000Z',
      },
      total: 0,
      last_benchmark: null,
    } })

    const { container } = render(
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunWizard />} />
          <Route path="/" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )

    // Click "Set me up" — with an empty registry there is no starter model,
    // so the loading step falls back to the choose step.
    fireEvent.click(container.querySelector('button')!)

    // Wait for the choose step to appear.
    await vi.waitFor(() => {
      expect(container.querySelector('h1')?.textContent).toMatch(/choose how to get started/i)
    })

    // Option cards must be rendered as a list so assistive technologies can count them.
    expect(container.querySelector('ul[role="list"]')).not.toBeNull()
  })
})
