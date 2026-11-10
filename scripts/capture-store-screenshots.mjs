#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
/**
 * capture-store-screenshots.mjs — the demo app's Steam store screenshots,
 * from a REAL demo-edition session against a REAL local model.
 *
 * publishing/STEAM_NEXT_FEST_DEMO.md §4.2 asks for demo screenshots taken from
 * a demo build, showing nothing the demo cannot reach: the first-run "Set me
 * up" screen, the demo Home with its five cards, the Coffee at Café Sol card,
 * one conversation mid-session and one debrief with scores. Steam wants at
 * least five, 1920 x 1080 (publishing/STEAM_ASSETS_SPEC.md § Screenshots).
 * docs/screenshots.md's README set is a different thing: full edition, 2x,
 * heights fitted to each screen.
 *
 * Every frame is exactly 1920 x 1080: a 1440 x 810 CSS-pixel viewport at
 * deviceScaleFactor 4/3, so the UI reads at about the size a player sees it
 * rather than as a narrow column on a 1920-wide page, and the conversation
 * frame holds the meters panel, the whole transcript box and the composer.
 *
 * Writes publishing/assets/screenshots/demo/:
 *   01-first-run.png      Welcome, "Set me up" (needs a fresh profile)
 *   02-home.png           the five conversations and the upsell card
 *   03-cafe-sol-brief.png Coffee at Café Sol's Conversation Brief
 *   04-conversation.png   one conversation three exchanges in (CONVSIM_STORE_PLAY,
 *                         default The Behavioral Interview)
 *   05-debrief.png        that session's debrief, scorecard in frame
 *
 * Prerequisites
 *   1. Dev services in the demo edition on a FRESH data root, so the welcome
 *      screen is reachable and the one-click install is the real one:
 *        CONVSIM_EDITION=demo CONVSIM_DATA_ROOT=/tmp/demo-capture ./scripts/dev.sh
 *   2. Network for the model download (the "Set me up" click installs it).
 *   3. Playwright with Chromium, as for scripts/capture-screenshots.mjs:
 *        NODE_PATH=/path/to/node_modules node scripts/capture-store-screenshots.mjs
 *
 * The script refuses to run unless /api/health reports edition "demo", and
 * refuses to play once set-up is done unless a real model is answering (the
 * same model-free runtime guard as capture-screenshots.mjs). On a profile that
 * is already set up, 01 is skipped with a warning and the rest are shot.
 *
 * Exit status is non-zero if any frame was not written.
 */
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { mkdir, stat } from 'node:fs/promises'
import path from 'node:path'

const require = createRequire(import.meta.url)
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const UI_URL = process.env.CONVSIM_UI_URL ?? 'http://127.0.0.1:7354'
const API_URL = process.env.CONVSIM_API_URL ?? 'http://127.0.0.1:7355'
const OUT_DIR =
  process.env.CONVSIM_STORE_SHOT_DIR ?? path.join(REPO_ROOT, 'publishing', 'assets', 'screenshots', 'demo')
const SEED = process.env.CONVSIM_CAPTURE_SEED ?? '495'

const VIEWPORT = { width: 1440, height: 810 }
const SCALE = 4 / 3 // 1440 x 810 CSS px -> 1920 x 1080 device px

// Keep in step with MODEL_FREE_RUNTIME_IDS in convsim_core/runtime/active.py.
const MODEL_FREE_RUNTIMES = new Set(['fake', 'scripted'])

const BRIEF_SCENARIO = 'spanish_coffee'
// Three player turns per demo conversation, written against each scenario's
// own setup (the Civic is listed at $15,500, comparables at $13,500-$14,200).
const PLAYS = {
  used_car_negotiation: [
    "Thanks for having it ready. I've driven it and I like it. Before we talk numbers: what's been replaced on it, and do you have the service records?",
    "The listing says fifteen-five. Comparable Civics at this mileage are selling for thirteen-five to fourteen-two within fifty miles, and it needs tires soon. I can do twelve thousand eight hundred out the door today.",
    "I'm not trying to lowball you. My financing is approved and I can sign this afternoon. Thirteen thousand four hundred out the door with new tires and we have a deal.",
  ],
  behavioral_interview: [
    "Sure. Last winter our checkout service started timing out under holiday load. I was the on-call lead. I traced it to an N+1 query in the pricing call, shipped a batched query behind a flag that night, and p95 latency went from four seconds to three hundred milliseconds.",
    "Afterwards I added a load test to CI so it could not come back, and wrote up the incident so the next on-call knew where to look first.",
    "Another one: I disagreed with my tech lead about rewriting our auth service. I wrote a one-page comparison with our incident data, we chose incremental fixes, and closed the top three incident causes in six weeks.",
  ],
  ask_for_raise: [
    "Thanks for making the time. I want to talk about my compensation. In the last six months I led the cross-team migration, onboarded two new hires, and we shipped three weeks early.",
    "Market data for this role in our city puts it about fifteen percent above what I'm paid now. I'm asking for an adjustment that brings me into that range.",
    "I understand budgets are tight. If the full amount isn't possible this cycle, could we agree on part of it now and the rest at the next review, in writing?",
  ],
}
const PLAY_SCENARIO = process.env.CONVSIM_STORE_PLAY ?? 'behavioral_interview'
if (!PLAYS[PLAY_SCENARIO]) {
  console.error(`CONVSIM_STORE_PLAY must be one of: ${Object.keys(PLAYS).join(', ')}`)
  process.exit(1)
}
const PLAYER_TURNS = PLAYS[PLAY_SCENARIO]

const written = new Set()
const wanted = ['01', '02', '03', '04', '05']

const log = (...m) => console.log('[store-capture]', ...m)
function fail(message) {
  console.error('\nERROR: ' + message + '\n')
  process.exit(1)
}

async function getJson(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`GET ${url} -> HTTP ${resp.status}`)
  return resp.json()
}

async function shot(page, id, name) {
  const file = path.join(OUT_DIR, name)
  await page.waitForTimeout(700)
  await page.screenshot({ path: file })
  const { size } = await stat(file)
  written.add(id)
  log(`wrote ${path.relative(REPO_ROOT, file)} (1920x1080, ${(size / 1024).toFixed(0)} KB)`)
}

async function step(id, fn) {
  try {
    await fn()
  } catch (err) {
    log(`WARNING: ${id} failed — ${err.message.split('\n')[0]}`)
  }
}

async function settle(page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}

async function waitForSetup(timeoutMs) {
  const until = Date.now() + timeoutMs
  while (Date.now() < until) {
    const s = await getJson(`${API_URL}/api/setup/status`).catch(() => null)
    if (s?.kind === 'ready') return
    await new Promise((r) => setTimeout(r, 5000))
  }
  throw new Error(`set-up did not finish within ${Math.round(timeoutMs / 60000)} min`)
}

async function waitForTurn(page, before) {
  await page.waitForFunction(
    (n) => document.querySelectorAll('[data-role="npc"]').length > n,
    before,
    { timeout: 300_000 },
  )
  // The staged panel, then "Updating the scene…" while the state delta is still
  // out: the turn is committed only when both are gone.
  for (const id of ['npc-turn-progress', 'turn-finishing-indicator']) {
    await page
      .locator(`[data-testid="${id}"]`)
      .waitFor({ state: 'detached', timeout: 300_000 })
      .catch(() => log(`WARNING: ${id} was still up`))
  }
  await page.waitForTimeout(1200)
}

async function main() {
  let chromium
  for (const spec of ['playwright', 'playwright-core']) {
    try {
      ;({ chromium } = require(spec))
      break
    } catch {
      /* next */
    }
  }
  if (!chromium) fail('Playwright is not resolvable; set NODE_PATH (see the header).')

  const health = await getJson(`${API_URL}/api/health`).catch((e) =>
    fail(`convsim-core is not reachable at ${API_URL} (${e.message}).`),
  )
  if (health.edition !== 'demo') {
    fail(`the engine reports edition '${health.edition}'. Start it with CONVSIM_EDITION=demo.`)
  }
  await mkdir(OUT_DIR, { recursive: true })

  const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--hide-scrollbars'] })
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    colorScheme: 'dark',
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  page.on('pageerror', (e) => log('page error:', e.message))

  try {
    // ── 01 First run ──────────────────────────────────────────────────────
    await page.goto(UI_URL, { waitUntil: 'domcontentloaded' })
    await settle(page, 1500)
    const setMeUp = page.getByText('Set me up').first()
    if (await setMeUp.isVisible().catch(() => false)) {
      await step('01', () => shot(page, '01', '01-first-run.png'))
      await setMeUp.click()
      log('"Set me up" clicked — waiting for the one-click install')
      await waitForSetup(30 * 60_000)
      log('set-up complete')
    } else {
      log('WARNING: no welcome screen — this profile is already set up, so 01 is not shot')
    }

    const ready = await getJson(`${API_URL}/api/health`)
    const runtimeId = ready.llm_runtime?.runtime_id ?? null
    if (MODEL_FREE_RUNTIMES.has(runtimeId) || !ready.runtime?.llm_ready) {
      fail(`no real model is answering (runtime '${runtimeId}'); the frames would not show real output.`)
    }
    log(`runtime ${runtimeId} ready — model: ${ready.runtime.llm_model_name}`)

    // ── 02 Home ───────────────────────────────────────────────────────────
    await step('02', async () => {
      await page.goto(UI_URL, { waitUntil: 'domcontentloaded' })
      await page.getByTestId('demo-conversation-card').nth(4).waitFor({ timeout: 60_000 })
      await settle(page, 1200)
      const n = await page.getByTestId('demo-conversation-card').count()
      if (n !== 5) throw new Error(`the demo Home shows ${n} cards, not five`)
      await page.getByTestId('demo-conversations').scrollIntoViewIfNeeded()
      await page.evaluate(() => window.scrollBy(0, -80))
      await shot(page, '02', '02-home.png')
    })

    // ── 03 Coffee at Café Sol ─────────────────────────────────────────────
    await step('03', async () => {
      await page.goto(`${UI_URL}/setup/${BRIEF_SCENARIO}`, { waitUntil: 'domcontentloaded' })
      await page.getByRole('button', { name: 'Start conversation' }).waitFor({ timeout: 60_000 })
      await settle(page, 1200)
      await page.evaluate(() => window.scrollTo(0, 0))
      await shot(page, '03', '03-cafe-sol-brief.png')
    })

    // ── 04 Conversation ───────────────────────────────────────────────────
    let sessionReady = false
    await step('04', async () => {
      await page.goto(`${UI_URL}/setup/${PLAY_SCENARIO}`, { waitUntil: 'domcontentloaded' })
      const start = page.getByRole('button', { name: 'Start conversation' })
      await start.waitFor({ timeout: 60_000 })
      const meters = page.getByLabel(/Show the conversation meters/i)
      if (await meters.count()) await meters.check()
      const seed = page.getByLabel('Variation seed value')
      if (await seed.count()) await seed.fill(SEED)
      await settle(page, 500)
      await start.click()
      await page.getByTestId('conversation-page').waitFor({ timeout: 60_000 })
      await page.waitForSelector('[data-role="npc_opening"]', { timeout: 180_000 })
      const composer = page.getByLabel('Your response')
      for (let i = 0; i < PLAYER_TURNS.length; i++) {
        await page.waitForFunction(
          () => {
            const el = document.querySelector('input[aria-label="Your response"]')
            return !!el && !el.disabled
          },
          null,
          { timeout: 300_000 },
        )
        const before = await page.locator('[data-role="npc"]').count()
        await composer.fill(PLAYER_TURNS[i])
        await page.getByRole('button', { name: 'Submit' }).click()
        log(`turn ${i + 1}/${PLAYER_TURNS.length} submitted`)
        await waitForTurn(page, before)
      }
      sessionReady = true
      // The meters panel at the top of the frame, then the transcript box
      // (scrolled to its newest exchange) and the composer under it.
      await page.evaluate(() => {
        const meters = document.querySelector('[data-testid="state-vars"]')
        const top = meters ? meters.getBoundingClientRect().top + window.scrollY - 12 : document.body.scrollHeight
        window.scrollTo(0, top)
      })
      await settle(page, 800)
      await shot(page, '04', '04-conversation.png')
    })

    // ── 05 Debrief ────────────────────────────────────────────────────────
    await step('05', async () => {
      if (!sessionReady) throw new Error('no session was played')
      await page.getByRole('button', { name: 'End session' }).click()
      const gen = page.getByRole('button', { name: 'Generate debrief' })
      await gen.waitFor({ timeout: 120_000 })
      await gen.click()
      await page.getByTestId('debrief-page').waitFor({ timeout: 60_000 })
      await page.getByTestId('scorecard-section').waitFor({ timeout: 300_000 })
      await settle(page, 1500)
      await page.evaluate(() => window.scrollTo(0, 0))
      await shot(page, '05', '05-debrief.png')
    })
  } finally {
    await context.close()
    await browser.close()
  }

  const missed = wanted.filter((id) => !written.has(id))
  if (missed.length) {
    log(`FAILED: ${missed.join(', ')} were not written`)
    process.exitCode = 1
    return
  }
  log('done')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
