// SPDX-License-Identifier: Apache-2.0
//
// The demo edition's one upsell (issue #495): a single card that says what the
// full version adds and links to the paid base app in the store this build is
// sold through (Steam, the Microsoft Store or the App Store). Everything the
// demo hides is "disabled with upsell" through this card rather than through
// greyed-out controls scattered across the UI, so the demo reads as a complete
// small product rather than a crippled large one.
import type { MouseEvent } from 'react'
import { useTranslation } from '../i18n'
import { FULL_APP_STEAM_APP_ID, buildStore, fullAppLink } from '../edition'
import { isDesktopShell, openExternal } from '../lib/openExternal'

type TauriInvoke = <T>(cmd: string, args?: unknown) => Promise<T>
type TauriWindow = { __TAURI__?: { core?: { invoke?: TauriInvoke } } }

/**
 * Open the full game's store page. Under Steam the overlay's store view keeps
 * the player inside the demo (Valve's recommended demo → wishlist/purchase
 * path); anywhere else — the overlay disabled, not launched through Steam, a
 * build for another store, or a plain browser — the page opens in the default
 * browser instead.
 */
export async function openFullAppStorePage(): Promise<void> {
  const invoke = (window as TauriWindow).__TAURI__?.core?.invoke
  if (invoke && buildStore() === 'steam') {
    try {
      const shown = await invoke<boolean>('steam_open_store_page', { appId: FULL_APP_STEAM_APP_ID })
      if (shown) return
    } catch {
      // Not a Steam build (command missing) — fall through to the browser.
    }
  }
  await openExternal(fullAppLink().url)
}

interface DemoUpsellCardProps {
  /** Compact variant for the end of a debrief. */
  compact?: boolean
}

export default function DemoUpsellCard({ compact = false }: DemoUpsellCardProps) {
  const { t } = useTranslation()
  const full = fullAppLink()
  // Voice is not one of them: the demo has it too (issue #464).
  const bullets = ['library', 'workbench', 'models'] as const

  function handleCtaClick(e: MouseEvent<HTMLAnchorElement>) {
    // In a browser the anchor itself is the right thing; only the desktop
    // shell has a Steam overlay to try first.
    if (!isDesktopShell()) return
    e.preventDefault()
    void openFullAppStorePage()
  }

  return (
    <section
      aria-label={t('demo.upsell.heading')}
      data-testid="demo-upsell-card"
      style={{
        padding: compact ? '0.85rem 1rem' : '1.25rem 1.5rem',
        background: 'rgba(99,102,241,0.08)',
        border: '1px solid rgba(99,102,241,0.35)',
        borderRadius: '10px',
      }}
    >
      <p
        style={{
          margin: '0 0 0.25rem',
          fontSize: '0.75rem',
          color: '#a5b4fc',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          fontWeight: 600,
        }}
      >
        {t('demo.upsell.eyebrow')}
      </p>
      <h2 style={{ margin: '0 0 0.5rem', fontSize: compact ? '1rem' : '1.2rem', color: '#f4f4f5' }}>
        {t('demo.upsell.heading')}
      </h2>
      <p style={{ margin: '0 0 0.75rem', fontSize: '0.875rem', color: '#c7d2fe', lineHeight: 1.55 }}>
        {t('demo.upsell.body')}
      </p>
      {!compact && (
        <ul
          style={{
            margin: '0 0 1rem',
            paddingLeft: '1.1rem',
            fontSize: '0.85rem',
            color: '#a1a1aa',
            lineHeight: 1.6,
          }}
        >
          {bullets.map((b) => (
            <li key={b}>{t(`demo.upsell.bullets.${b}`)}</li>
          ))}
        </ul>
      )}
      <a
        href={full.url}
        target="_blank"
        rel="noreferrer"
        data-testid="demo-upsell-link"
        onClick={handleCtaClick}
        style={{
          display: 'inline-block',
          padding: '0.45rem 1rem',
          borderRadius: '4px',
          background: 'rgba(99,102,241,0.85)',
          color: '#fff',
          fontWeight: 600,
          fontSize: '0.875rem',
          textDecoration: 'none',
        }}
      >
        {t('demo.upsell.cta', { store: full.storeName })}
      </a>
      {/* On the Mac App Store the demo and the full app are separate sandboxed
          apps with separate containers, so nothing carries over there. */}
      {buildStore() !== 'mac-app-store' && (
        <p style={{ margin: '0.6rem 0 0', fontSize: '0.75rem', color: '#71717a' }}>
          {t('demo.upsell.carryOver')}
        </p>
      )}
    </section>
  )
}
