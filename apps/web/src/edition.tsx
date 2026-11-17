// SPDX-License-Identifier: Apache-2.0
//
// Product edition: the full app versus the Steam Next Fest demo (issue #495).
//
// The demo is the same build narrowed to one curated model download and five
// curated conversations, with the rest of the surface hidden. Two signals say
// which edition this is, and they are set together by the demo build leg of the
// release workflow:
//
//   • VITE_CONVSIM_EDITION=demo — baked into this bundle at build time. It is
//     the primary signal for the UI, so the demo never flashes full-app chrome
//     before the engine answers.
//   • CONVSIM_EDITION=demo on convsim-core — reported by GET /api/health as
//     `edition` and `demo`. It is the primary signal for *data*: the engine
//     serves only the five conversations and the one model regardless of what
//     the UI asks for, and it tells the UI which five those are.
//
// The curated list is deliberately NOT duplicated here: the UI renders whatever
// the engine reports under `demo.scenario_ids`, so the five are curated in one
// place (convsim_core/edition.py). In dev, running the engine with
// CONVSIM_EDITION=demo is enough to see the demo UI — the build-time flag is
// optional there because the server's answer takes over once it arrives.
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { DemoInfo, Edition, HealthResponse } from '@convsim/shared'
import { api } from './api/client'

/** Steam store page of the paid base app — the demo's single upsell target. */
export const FULL_APP_STEAM_APP_ID = 4963030
export const FULL_APP_STEAM_URL =
  `https://store.steampowered.com/app/${FULL_APP_STEAM_APP_ID}/Conversation_Simulator/`

/** The paid base app on the Microsoft Store (publishing/MICROSOFT_STORE.md). */
export const FULL_APP_MSSTORE_PRODUCT_ID = '9NTNF4X3GQ95'
export const FULL_APP_MSSTORE_URL = `https://apps.microsoft.com/detail/${FULL_APP_MSSTORE_PRODUCT_ID}`

/**
 * The store this build is sold through, baked in as VITE_CONVSIM_STORE by the
 * store's build lane: Steam unless a lane says otherwise. A demo sold through
 * one store must send players to the full game in that same store — a store
 * does not accept a listing that points buyers at another.
 */
export type Store = 'steam' | 'microsoft-store' | 'mac-app-store'

export function buildStore(): Store {
  const raw = (import.meta.env.VITE_CONVSIM_STORE ?? '').toString().trim().toLowerCase()
  if (raw === 'microsoft-store' || raw === 'mac-app-store') return raw
  return 'steam'
}

/** Where the demo's "Get the full game" goes, and the store's name for the button. */
export function fullAppLink(store: Store = buildStore()): { url: string; storeName: string } {
  const override = (import.meta.env.VITE_FULL_APP_URL ?? '').toString().trim()
  switch (store) {
    case 'microsoft-store':
      return { url: override || FULL_APP_MSSTORE_URL, storeName: 'Microsoft Store' }
    case 'mac-app-store':
      // The App Store address exists only once the app record does; the lane
      // passes it in. Until then the site, which lists every store.
      return { url: override || 'https://www.conversationsimulator.com/', storeName: 'App Store' }
    default:
      return { url: FULL_APP_STEAM_URL, storeName: 'Steam' }
  }
}

/** Edition baked into this bundle, or null when the build did not say. */
export function buildEdition(): Edition | null {
  const raw = (import.meta.env.VITE_CONVSIM_EDITION ?? '').toString().trim().toLowerCase()
  if (raw === 'demo') return 'demo'
  if (raw === 'full') return 'full'
  return null
}

export interface EditionState {
  edition: Edition
  /** What the engine reports the demo exposes; null until known or in the full app. */
  demo: DemoInfo | null
  /** Where `edition` came from — useful for diagnostics and tests. */
  source: 'build' | 'server' | 'default'
}

function initialState(): EditionState {
  const built = buildEdition()
  return built
    ? { edition: built, demo: null, source: 'build' }
    : { edition: 'full', demo: null, source: 'default' }
}

/**
 * Fold the engine's health answer into the current state. The build-time
 * edition wins for the UI; the server's demo facts are adopted whenever
 * present so the demo Home knows which five conversations to show.
 */
export function reconcileEdition(state: EditionState, health: HealthResponse): EditionState {
  const serverEdition = health.edition ?? 'full'
  const demo = health.demo ?? null
  if (state.source === 'build') {
    if (serverEdition !== state.edition) {
      // eslint-disable-next-line no-console
      console.warn(
        `[edition] bundle is '${state.edition}' but the engine reports '${serverEdition}'. ` +
          'Set CONVSIM_EDITION and VITE_CONVSIM_EDITION to the same value.',
      )
    }
    return { ...state, demo: state.edition === 'demo' ? demo : null }
  }
  return { edition: serverEdition, demo: serverEdition === 'demo' ? demo : null, source: 'server' }
}

// A sentinel (rather than a default value) so `useEdition()` outside a
// provider — every screen-level test — still reads the build flag at call time.
export const EditionContext = createContext<EditionState | null>(null)

/** How often to re-ask the engine while it is still coming up. */
export const EDITION_POLL_INTERVAL_MS = 3000

export function EditionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EditionState>(initialState)

  // Ask the engine until it answers once. The provider sits above
  // CoreStartupGuard, so in the desktop shell the first call usually lands
  // before the sidecar listens; a single fire-and-forget request would then
  // lose the engine's edition and the demo's curated list for the whole
  // session. Poll at the health hook's cadence and stop after the first
  // successful answer — the edition cannot change while the app is open.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const ask = () => {
      void api.health().then((r) => {
        if (cancelled) return
        if (r.ok) {
          setState((prev) => reconcileEdition(prev, r.data))
          return
        }
        timer = setTimeout(ask, EDITION_POLL_INTERVAL_MS)
      }).catch(() => {
        if (cancelled) return
        timer = setTimeout(ask, EDITION_POLL_INTERVAL_MS)
      })
    }
    ask()
    return () => {
      cancelled = true
      if (timer != null) clearTimeout(timer)
    }
  }, [])

  return <EditionContext.Provider value={state}>{children}</EditionContext.Provider>
}

/** The current edition state; falls back to the build flag outside a provider. */
export function useEdition(): EditionState {
  const ctx = useContext(EditionContext)
  return ctx ?? initialState()
}

/** True when this is the Steam Next Fest demo edition. */
export function useIsDemo(): boolean {
  return useEdition().edition === 'demo'
}
