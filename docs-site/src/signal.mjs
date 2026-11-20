// SPDX-License-Identifier: Apache-2.0
// Signal: Outright Mental's own first-party, aggregate-only analytics, for this
// docs site only (the app sends nothing). Every page carries a ladder of 1x1
// images, counted by Signal's server with no script, cookie or id
// (src/components/SkipLink.astro); the client script, added to <head> by
// astro.config.mjs, adds journeys only after a visitor says yes. Described for
// visitors at /trust/privacy/#these-websites.

export const SIGNAL = {
  key: 'conversationsimulator-docs.bb8475e06925341a21a0f7f2',
  ingest: 'https://in.signal.outright.io',
  script: 'https://signal.outright.io/w/signal.js',
  host: 'docs.conversationsimulator.com',
  privacy: '/trust/privacy/#these-websites',
  // The studio's hosts a journey may cross (a link to one carries `#sx=`).
  // The same list, in the same order, on every studio site and in
  // website/hugo.toml; outrightmental.com/privacy/ lists them for visitors.
  studio: [
    'outrightmental.com',
    'nickcharneykaye.com',
    'apescorporation.com',
    'fevertilt.com',
    'starharvester.com',
    'zero.starharvester.com',
    'umlaut-hero.com',
    'conversationsimulator.com',
    'docs.conversationsimulator.com',
    'xjmusic.com',
    'docs.xjmusic.com',
    'podcast.xjmusic.com',
    'outright.io',
    'agendar.outright.io',
    'wetware.outright.io',
    'etymolution.com',
    'makeitmoreinteresting.com',
    'interesting.outright.io',
    'ascendinglark.com',
    'garden.ascendinglark.com',
  ],
}

/**
 * Whether this build counts into Signal's production stream: only the build
 * the deploy workflow makes (it alone sets SIGNAL_DEPLOY=production) for the
 * production host. `astro dev`, a local `astro build` / `astro preview` and a
 * build for any other site render no ladder and no script.
 */
export function signalOn(site) {
  return process.env.SIGNAL_DEPLOY === 'production' && new URL(site).host === SIGNAL.host
}

const BAND_PX = 200
const RUNGS = 47

/** A page's path as Signal keeps it (ladderPath in Signal's sdk/web/ladder.mjs). */
export function ladderPath(pathname) {
  let text = String(pathname || '/')
    .toLowerCase()
    .split(/[?#]/)[0]
    .replace(/\/{2,}/g, '/')
    .replace(/\/index\.html?$/, '/')
  if (text.length > 1) text = text.replace(/\/$/, '')
  return text
}

const attr = (text) => String(text).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

/**
 * The depth ladder's HTML for one page: the same markup as `ladderHtml` in
 * Signal's sdk/web/ladder.mjs. One 1x1 image every 200 px down the page (the
 * first loads with the page and is the view; the rest are lazy, so the browser
 * asks for each as the reader nears it) and one at its foot. It must be the
 * first thing inside <body>, and body is `position: relative`
 * (src/styles/custom.css), so it spans the page and clips to it.
 */
export function ladderHtml(path) {
  const base = `${SIGNAL.ingest.replace(/\/+$/, '')}/v1/d?k=${encodeURIComponent(SIGNAL.key)}&p=${encodeURIComponent(ladderPath(path))}`
  const img = (query, style, lazy) =>
    `<img src="${attr(`${base}&${query}`)}" alt="" width="1" height="1"${lazy ? ' loading="lazy"' : ''} decoding="async" referrerpolicy="no-referrer" style="${style}">`
  const rung = (at) => img(`b=${at}-${at}`, `position:absolute;left:0;top:${at * BAND_PX}px`, at > 0)
  return [
    '<div data-signal-depth aria-hidden="true" style="position:absolute;top:0;bottom:0;left:0;width:1px;overflow:hidden;pointer-events:none;opacity:0">',
    ...Array.from({ length: RUNGS + 1 }, (_, at) => rung(at)),
    img('e=1', 'position:absolute;left:0;bottom:0', true),
    '</div>',
  ].join('')
}
