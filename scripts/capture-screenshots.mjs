#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
/**
 * capture-screenshots.mjs — capture the README/docs screenshots and the hero
 * recording from a REAL session against a REAL local model.
 *
 * This is the tool referenced by the replacement checklist in
 * docs/screenshots.md.  It drives the running dev build through a complete
 * playthrough of "Making the Case" (Job Interview Basics pack) and
 * writes:
 *
 *   docs/assets/screenshots/01-home.png
 *   docs/assets/screenshots/02-scenario-library.png
 *   docs/assets/screenshots/03-conversation.png
 *   docs/assets/screenshots/04-debrief.png
 *   docs/assets/screenshots/05-creator-workbench.png
 *   docs/assets/screenshots/06-model-manager.png
 *   docs/assets/demo.gif            (hero recording, mid-session exchange)
 *   docs/assets/demo.mp4            (same segment, video fallback)
 *
 * Every NPC line in the captures is produced by the local model that is
 * actually loaded — the script refuses to run when the active runtime is one
 * of the model-free runtimes (`fake`, `scripted`), so a capture can never
 * quietly ship canned text as if it were gameplay.
 *
 * Prerequisites
 *   1. A local model installed and selected, and the engine running:
 *        curl -s localhost:7355/api/health | grep llm_ready
 *   2. The dev services up (./scripts/dev.sh), UI on 7354, core on 7355.
 *   3. Playwright with Chromium:
 *        npm install playwright && npx playwright install chromium
 *      Playwright is deliberately NOT a repo dependency — it is needed only
 *      when re-capturing.  Install it anywhere and point NODE_PATH at it:
 *        NODE_PATH=/path/to/node_modules node scripts/capture-screenshots.mjs
 *   4. ffmpeg on PATH (hero GIF/MP4 encoding).  Checked before the playthrough
 *      starts; pass --skip-hero to capture the screenshots without it.
 *
 * Usage
 *   node scripts/capture-screenshots.mjs [--skip-hero] [--only=03,06]
 *
 *   --skip-hero  capture the screenshots, skip the recording
 *   --only=NN,NN write only the named outputs — screen numbers and/or `hero`
 *                (the session is still played, since 03, 04 and the hero all
 *                come out of it). Anything left off the list keeps the file
 *                already on disk: `--only=06` re-shoots the Model Manager and
 *                leaves demo.gif alone; `--only=03,hero` redoes both.
 *
 * Exit status is non-zero if any requested output was not written, so a run
 * that lost a screen cannot be mistaken for one that refreshed the whole set.
 *
 * Only `docs/assets` is written here. The 1x web copies under `website/` and
 * `docs-site/` are derived with ImageMagick; a run that rewrote any screenshot
 * ends by printing the one command that remakes them.
 *
 * Environment
 *   CONVSIM_UI_URL      default http://127.0.0.1:7354
 *   CONVSIM_API_URL     default http://127.0.0.1:7355
 *   CONVSIM_SHOT_DIR    default docs/assets/screenshots
 *   CONVSIM_CAPTURE_SEED  variation seed typed into scenario setup (default 455)
 */
import { createRequire } from 'node:module'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdir, mkdtemp, readdir, rm, stat } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const require = createRequire(import.meta.url)

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const UI_URL = process.env.CONVSIM_UI_URL ?? 'http://127.0.0.1:7354'
const API_URL = process.env.CONVSIM_API_URL ?? 'http://127.0.0.1:7355'
const SHOT_DIR = process.env.CONVSIM_SHOT_DIR ?? path.join(REPO_ROOT, 'docs', 'assets', 'screenshots')
const ASSET_DIR = path.dirname(SHOT_DIR)
const SEED = process.env.CONVSIM_CAPTURE_SEED ?? '455'

// The docs site and the marketing site each carry a 1x, 256-colour copy of the
// screenshots, derived by hand (docs/screenshots.md). This script does not write
// them — ImageMagick is not a dependency of a capture run — so it names them at
// the end instead: nothing else reconciles the copies against the originals, and
// a re-capture that stops at docs/assets leaves two sites rendering last month's
// UI beside a README showing this month's.
const SITE_COPY_DIRS = [
  path.join('website', 'static', 'images', 'screenshots'),
  path.join('docs-site', 'public', 'images', 'screenshots'),
]

const SCENARIO_ID = 'stretch_role_interview'
const WORKBENCH_PACK = 'Job Interview Basics'
const WORKBENCH_FILE = 'scenarios/stretch_role_interview.yaml'

// Viewport for every capture. Screenshots are taken at deviceScaleFactor 2, so
// a 1280 x H capture lands at 2560 x 2H — the "2x" the checklist asks for. The
// height is fitted to each screen's own content (up to MAX_SHOT_HEIGHT) so no
// screenshot is padded with dead space or cut off mid-panel.
const VIEWPORT = { width: 1280, height: 800 }
const SCALE = 2
const MAX_SHOT_HEIGHT = 2000

// docs/screenshots.md budgets the hero recording at 5 MB; aim under 4 MB so a
// slightly longer turn next time does not blow through it.
const GIF_BUDGET_BYTES = 4 * 1024 * 1024

// Seconds dropped from the end of the hero segment. The last thing in frame
// should be the NPC's finished reply, never the screen the run moves to next.
const HERO_TAIL_TRIM = 0.6

// Runtimes that answer from canned content. A capture taken on one of these
// would be a mockup wearing the UI's clothes (issue #455 acceptance). Keep in
// step with MODEL_FREE_RUNTIME_IDS in
// services/convsim-core/convsim_core/runtime/active.py — a new model-free
// runtime that is not listed here walks straight past this guard.
const MODEL_FREE_RUNTIMES = new Set(['fake', 'scripted'])

// The player's side of the conversation. Written to read like a real
// candidate: concrete, specific, and willing to hold ground under challenge —
// which is what makes the NPC's state variables actually move.
const PLAYER_TURNS = [
  "Two years against a five-year posting — that gap is real and I am not going to talk around it. What I would put next to it is scope: I owned the billing migration end to end last year, forty thousand customers, and I wrote the rollout plan, ran the comms, and made the call to hold it a week when the dry run turned up a tax-rounding bug.",
  "The honest answer is that I have never run a multi-quarter roadmap against a P&L. I have shipped against quarterly goals somebody else set. If you hired me I would want a month watching how you do planning before I owned it, and I would say so in week one rather than bluff through a cycle.",
  "I read your last three release notes and spoke to two of your logistics customers. What surprised me is that the retention story is not the dashboard — it is the CSV export people build their Monday reports on. I would be careful about deprecating that before something replaces the ritual, not just the file.",
  "Because the gap I cannot close with effort is pattern recognition from a dozen launches, and I would rather be the candidate who already knows which mistakes they make. I shipped the wrong onboarding twice before I learned to instrument the first week. That is exactly why I would start with your activation data instead of a roadmap.",
]

// Every output this script can write. `--only` is checked against this list:
// a typo like `--only=3` would otherwise match nothing, play a full real-model
// session, write not one file, and still report success.
const OUTPUT_IDS = ['01', '02', '03', '04', '05', '06', 'hero']

const args = process.argv.slice(2)
const SKIP_HERO = args.includes('--skip-hero')
const ONLY = (args.find((a) => a.startsWith('--only=')) ?? '').replace('--only=', '')
const only = ONLY ? new Set(ONLY.split(',').map((s) => s.trim())) : null
const wanted = (id) => !only || only.has(id)
// The hero is an output like any other, so `--only` gates it too: re-shooting
// one screen must not quietly re-encode the committed 3 MB recording. Name
// `hero` in the list to get it back.
const CAPTURE_HERO = !SKIP_HERO && wanted('hero')

function log(...m) {
  console.log('[capture]', ...m)
}

function fail(message) {
  console.error('\nERROR: ' + message + '\n')
  process.exit(1)
}

if (only) {
  const unknown = [...only].filter((id) => !OUTPUT_IDS.includes(id))
  if (unknown.length) {
    fail(
      `--only names ${unknown.map((id) => `'${id}'`).join(', ')}, which is not an output ` +
        'this script writes.\n' +
        `       Valid values: ${OUTPUT_IDS.join(', ')} (screen numbers are zero-padded).`,
    )
  }
}

// What this invocation would actually write, after `--only` and `--skip-hero`
// have both had their say. `--skip-hero --only=hero` cancels out to nothing:
// without this the run would play a full real-model session, write not one
// file, and still report success — the same failure the `--only` name check
// above exists to prevent.
const REQUESTED = OUTPUT_IDS.filter((id) => (id === 'hero' ? CAPTURE_HERO : wanted(id)))
if (!REQUESTED.length) {
  fail(
    'no output is left to write: --only names only the hero recording, and ' +
      '--skip-hero turns it off.\n' +
      '       Drop one of the two flags.',
  )
}

function loadPlaywright() {
  for (const spec of ['playwright', 'playwright-core']) {
    try {
      return require(spec)
    } catch {
      /* try the next one */
    }
  }
  fail(
    'Playwright is not resolvable from this process.\n' +
      '       Install it and re-run with NODE_PATH pointing at it:\n' +
      '         npm install playwright && npx playwright install chromium\n' +
      '         NODE_PATH="$PWD/node_modules" node scripts/capture-screenshots.mjs',
  )
}

async function getJson(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`GET ${url} -> HTTP ${resp.status}`)
  return resp.json()
}

/** Refuse to capture anything unless a real model is answering. */
async function preflight() {
  let health
  try {
    health = await getJson(`${API_URL}/api/health`)
  } catch (err) {
    fail(
      `convsim-core is not reachable at ${API_URL} (${err.message}).\n` +
        '       Start the dev services first: ./scripts/dev.sh',
    )
  }
  const runtimeId = health.llm_runtime?.runtime_id ?? null
  if (MODEL_FREE_RUNTIMES.has(runtimeId)) {
    fail(
      `the active runtime is '${runtimeId}', which answers from canned content.\n` +
        '       Install and select a local model first — screenshots must show real\n' +
        '       model output (issue #455).',
    )
  }
  if (!health.runtime?.llm_ready) {
    fail(
      'the local AI engine is not ready, so no NPC turn would be real.\n' +
        `       Runtime '${runtimeId}' reported: ${health.llm_runtime?.message ?? 'unavailable'}`,
    )
  }
  try {
    const resp = await fetch(UI_URL)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  } catch (err) {
    fail(`the UI is not reachable at ${UI_URL} (${err.message}). Start ./scripts/dev.sh`)
  }
  // Checked here rather than at encode time: the recording is only usable
  // while the browser context holds it, so discovering a missing encoder after
  // the playthrough would throw away the run that produced the hero.
  if (CAPTURE_HERO && !haveFfmpeg()) {
    fail(
      'ffmpeg is not on PATH, so the hero recording could not be encoded.\n' +
        '       Stopping before the playthrough rather than after it.\n' +
        '       Install it (brew install ffmpeg), or pass --skip-hero to capture\n' +
        '       the screenshots without it.',
    )
  }
  log(`runtime ${runtimeId} ready — model: ${health.runtime.llm_model_name}`)
  return health
}

function run(cmd, cmdArgs) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, cmdArgs, { stdio: ['ignore', 'pipe', 'pipe'] })
    let stderr = ''
    child.stderr.on('data', (d) => (stderr += d))
    child.on('error', reject)
    child.on('close', (code) =>
      code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}\n${stderr.slice(-2000)}`)),
    )
  })
}

function haveFfmpeg() {
  // Windows splits PATH on `;`, may quote entries, and spells the binary
  // `ffmpeg.exe`. Probing for a bare `ffmpeg` on a `:`-split PATH finds nothing
  // there, so the preflight would abort a capture on a machine that has ffmpeg.
  const exts =
    process.platform === 'win32'
      ? (process.env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';').filter(Boolean)
      : ['']
  const dirs = (process.env.PATH ?? '').split(path.delimiter)
  return dirs.some((d) => {
    const dir = d.replace(/^"|"$/g, '')
    return dir && exts.some((ext) => existsSync(path.join(dir, `ffmpeg${ext}`)))
  })
}

// Outputs this run actually wrote. Reconciled against REQUESTED at the end and
// reflected in the exit status: a skipped screen leaves the previous capture
// on disk, which looks exactly like a successful re-capture until someone
// notices the committed PNG still shows last month's UI.
//
// Successes are tracked rather than failures because an output can go missing
// without anything throwing: 03 and the hero both fire from inside the
// playthrough loop, keyed off PLAYER_TURNS — shorten that list to two turns and
// neither step is ever reached, so an error-keyed list would stay empty and the
// run would report a full re-capture it did not do.
const written = new Set()

/**
 * Run one screen's capture. A failure here is logged and skipped rather than
 * thrown: losing the Model Manager shot must not also throw away a four-turn
 * playthrough and the hero recording that are already on disk.
 */
async function step(id, fn) {
  if (!wanted(id)) return
  try {
    await fn()
    written.add(id)
  } catch (err) {
    log(`WARNING: screen ${id} failed — ${err.message.split('\n')[0]}`)
  }
}

async function shot(page, name, { until } = {}) {
  const file = path.join(SHOT_DIR, name)
  // Fit the viewport to the page so the capture is the screen, not a crop of
  // it, then put the viewport back for the rest of the run. `until` ends a
  // long page at a section boundary instead of mid-card.
  const content = await page.evaluate((sel) => {
    if (sel) {
      const el = document.querySelector(sel)
      if (el) return Math.ceil(el.getBoundingClientRect().bottom + window.scrollY + 24)
    }
    return document.documentElement.scrollHeight
  }, until ?? null)
  const height = Math.min(Math.max(content, 600), MAX_SHOT_HEIGHT)
  // Past the clamp the screenshot is a crop, not the screen. Say so: a screen
  // that grows past MAX_SHOT_HEIGHT would otherwise ship truncated with
  // nothing in the log to catch it.
  if (content > MAX_SHOT_HEIGHT) {
    log(
      `WARNING: ${name} is ${content} px tall, past the ${MAX_SHOT_HEIGHT} px cap — ` +
        'capturing the top of it. Pass `until` to end the frame on a section boundary.',
    )
  }
  await page.setViewportSize({ width: VIEWPORT.width, height })
  try {
    // This is a viewport screenshot, not a full-page one. When the viewport grew
    // to the whole page the browser clamps the scroll to 0 for us, but a page
    // past MAX_SHOT_HEIGHT is still scrollable — and 03 scrolls the state meters
    // into view just before firing. Without this the clamped capture would start
    // at that offset, which is not "the top of it" the warning above promises.
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(600)
    await page.screenshot({ path: file })
  } finally {
    // Restore even when the screenshot threw. `step` swallows that throw, so
    // without this the run would carry on at the grown height: 03 fires inside
    // the playthrough, and the hero crop it is followed by reads
    // `window.innerHeight` while the recording is fixed at VIEWPORT — a crop
    // taller than its own input, which loses the hero too. Exactly the cascade
    // wrapping 03 in `step` exists to prevent.
    await page.setViewportSize(VIEWPORT).catch(() => {})
  }
  await page.waitForTimeout(300)
  const { size } = await stat(file)
  log(
    `wrote ${path.relative(REPO_ROOT, file)} ` +
      `(${VIEWPORT.width * SCALE}x${height * SCALE}, ${(size / 1024).toFixed(0)} KB)`,
  )
}

/** Settle animations/fetches before a capture. */
async function settle(page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}

async function main() {
  const { chromium } = loadPlaywright()
  await preflight()
  await mkdir(SHOT_DIR, { recursive: true })

  const videoDir = await mkdtemp(path.join(tmpdir(), 'convsim-capture-'))
  const browser = await chromium.launch({
    args: ['--force-color-profile=srgb', '--hide-scrollbars'],
  })
  const marks = {}
  // Marks are offsets into the recording, so the clock has to start where the
  // recording does: Playwright begins capturing when the page opens, not when
  // the browser launches. Starting it any earlier shifts the encoded window
  // later than the marks and lets whatever came next leak into the tail.
  let t0 = Date.now()
  const mark = (name) => {
    marks[name] = (Date.now() - t0) / 1000
    log(`mark ${name} @ ${marks[name].toFixed(1)}s`)
  }

  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    colorScheme: 'dark',
    reducedMotion: 'reduce',
    recordVideo: CAPTURE_HERO ? { dir: videoDir, size: VIEWPORT } : undefined,
  })
  const page = await context.newPage()
  t0 = Date.now()
  page.on('pageerror', (e) => log('page error:', e.message))

  try {
    // ── 01 Home ───────────────────────────────────────────────────────────
    await page.goto(UI_URL, { waitUntil: 'domcontentloaded' })
    await page.getByRole('heading', { level: 1 }).first().waitFor({ timeout: 30_000 })
    await settle(page, 1500)
    // Wrapped like every screen after it: a failed capture here is one lost
    // output, not a reason to throw away the playthrough that follows.
    await step('01', () => shot(page, '01-home.png'))

    // ── 02 Scenario Library ───────────────────────────────────────────────
    await page.goto(`${UI_URL}/library`, { waitUntil: 'domcontentloaded' })
    await page.getByTestId(`launch-${SCENARIO_ID}`).waitFor({ timeout: 30_000 })
    // The unfiltered library is ~5000 px of packs. Search the way a player
    // would, so one pack's cards — including the one we are about to play —
    // fill the frame under the live filter controls.
    await page.getByLabel('Search scenarios').fill('interview')
    await page.getByTestId(`launch-${SCENARIO_ID}`).waitFor({ timeout: 30_000 })
    await settle(page)
    await step('02', () => shot(page, '02-scenario-library.png'))

    // ── Play a real session ───────────────────────────────────────────────
    await page.getByTestId(`launch-${SCENARIO_ID}`).click()
    await page.getByTestId('setup-page').waitFor({ timeout: 30_000 })
    // The setup form renders in stages: `setup-page` is present while the
    // scenario is still loading, and the options below only exist once it
    // resolves. Waiting for the submit button is what makes the toggles
    // findable — querying earlier silently matched nothing and produced a
    // session with meters off.
    const startButton = page.getByRole('button', { name: 'Start scenario' })
    await startButton.waitFor({ timeout: 60_000 })

    // The meters are opt-in per session and off by default; the conversation
    // capture is required to show them (issue #455).
    const metersToggle = page.getByLabel(/Show NPC state meters/i)
    if (await metersToggle.count()) {
      await metersToggle.check()
    } else {
      log('WARNING: state-meter toggle not found — capture will have no meters')
    }
    // A fixed variation seed makes the playthrough re-runnable.
    const seedField = page.getByLabel('Variation seed value')
    if (await seedField.count()) {
      await seedField.fill(SEED)
    } else {
      log('WARNING: seed field not found — playthrough will not be reproducible')
    }
    await settle(page, 500)
    await startButton.click()

    await page.getByTestId('conversation-page').waitFor({ timeout: 60_000 })
    await page.waitForSelector('[data-role="npc_opening"]', { timeout: 120_000 })
    log('session started — opening line received')

    const composer = page.getByLabel('Your response')
    const submit = page.getByRole('button', { name: 'Submit' })

    for (let i = 0; i < PLAYER_TURNS.length; i++) {
      const isHero = CAPTURE_HERO && i === PLAYER_TURNS.length - 1
      const before = await page.locator('[data-role="npc"]').count()
      await composer.waitFor({ state: 'visible', timeout: 120_000 })
      await page.waitForFunction(
        () => {
          const el = document.querySelector('input[aria-label="Your response"]')
          return !!el && !el.disabled
        },
        { timeout: 180_000 },
      )

      if (isHero) {
        // Frame the loop the hero is meant to show: transcript tail, state
        // meters, composer. Then type at human speed so the recording shows a
        // turn being played, not a jump cut.
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
        await settle(page, 1200)
        // The conversation is a 760 px column on a 1280 px page; remember its
        // box so the recording is cropped to the conversation, not to a field
        // of empty chrome.
        marks.crop = await page.evaluate(() => {
          const el = document.querySelector('[data-testid="conversation-page"]')
          if (!el) return null
          const r = el.getBoundingClientRect()
          const pad = 24
          return {
            x: Math.max(0, Math.floor(r.left - pad)),
            y: 0,
            width: Math.ceil(r.width + pad * 2),
            height: window.innerHeight,
          }
        })
        mark('heroStart')
        await composer.click()
        await composer.type(PLAYER_TURNS[i], { delay: 18 })
        await page.waitForTimeout(400)
      } else {
        await composer.fill(PLAYER_TURNS[i])
      }

      await submit.click()
      log(`turn ${i + 1}/${PLAYER_TURNS.length} submitted — waiting for the model`)
      await page.waitForFunction(
        (n) => document.querySelectorAll('[data-role="npc"]').length > n,
        before,
        { timeout: 300_000 },
      )
      // Let the meters animate to their new values and the banner land.
      await page.waitForTimeout(isHero ? 2600 : 800)
      if (isHero) mark('heroEnd')

      // Mid-session capture: three exchanges in, meters have moved and the
      // transcript has enough context to read as a conversation. Wrapped in
      // `step` like the screens after it — this one fires mid-playthrough, so
      // an unwrapped failure here would abort the loop and take the hero turn
      // and the debrief down with it.
      if (i === 2) {
        await step('03', async () => {
          await page.getByTestId('state-vars').scrollIntoViewIfNeeded().catch(() => {})
          await settle(page, 1200)
          await shot(page, '03-conversation.png')
        })
      }
    }

    const sessionUrl = page.url()
    const sessionId = sessionUrl.split('/conversation/')[1]
    log(`session ${sessionId}`)

    // ── 04 Debrief ────────────────────────────────────────────────────────
    await step('04', async () => {
      await page.getByRole('button', { name: 'End session' }).click()
      await page.getByRole('button', { name: 'Generate debrief' }).waitFor({ timeout: 120_000 })
      await page.getByRole('button', { name: 'Generate debrief' }).click()
      await page.getByTestId('debrief-page').waitFor({ timeout: 60_000 })
      await page
        .getByTestId('scorecard-section')
        .waitFor({ timeout: 300_000 })
        .catch(() => log('WARNING: no scorecard section — capturing the debrief as rendered'))
      await settle(page, 1500)
      // The debrief runs past 3000 px with the transcript and replay panels;
      // end the frame on the improvements section so the capture closes on a
      // section boundary instead of halfway through a card.
      await shot(page, '04-debrief.png', {
        until: 'section[aria-labelledby="improvements-heading"]',
      })
    })

    // ── 05 Creator Workbench ──────────────────────────────────────────────
    await step('05', async () => {
      await page.goto(`${UI_URL}/workbench`, { waitUntil: 'domcontentloaded' })
      await settle(page, 1200)
      // Select the official pack, open a scenario, make it editable with the
      // real "create local copy" flow, then re-open the file in the copy.
      await page.getByRole('button', { name: WORKBENCH_PACK, exact: false }).first().click()
      await settle(page, 600)
      await openWorkbenchFile(page, WORKBENCH_FILE)
      const copyBtn = page.getByTestId('copy-to-local-button')
      if (await copyBtn.count()) {
        await copyBtn.click()
        await page.getByTestId('copy-to-local-button').waitFor({ state: 'detached', timeout: 60_000 }).catch(() => {})
        await settle(page, 1200)
        await openWorkbenchFile(page, WORKBENCH_FILE)
      }
      await page.getByTestId('validation-panel').first().waitFor({ timeout: 60_000 }).catch(() => {})
      await settle(page, 1200)
      await shot(page, '05-creator-workbench.png')
    })

    // ── 06 Model Manager ──────────────────────────────────────────────────
    await step('06', async () => {
      await page.goto(`${UI_URL}/model-manager`, { waitUntil: 'domcontentloaded' })
      await settle(page, 2000)
      await shot(page, '06-model-manager.png')
    })
  } finally {
    await context.close()
    await browser.close()
  }

  // ── Hero recording ──────────────────────────────────────────────────────
  if (CAPTURE_HERO) {
    await step('hero', async () => {
      if (marks.heroStart == null || marks.heroEnd == null) {
        throw new Error('the hero turn was never marked — the playthrough did not reach it')
      }
      const name = (await readdir(videoDir)).find((f) => f.endsWith('.webm'))
      if (!name) throw new Error('no video file was produced by the browser context')
      await encodeHero(path.join(videoDir, name), marks)
    })
  }

  await rm(videoDir, { recursive: true, force: true }).catch(() => {})

  // Printed before the exit-status check, because a partial run that still
  // rewrote one screen has still desynced the site copies for that screen.
  const reshot = written.has('hero') ? [...written].filter((id) => id !== 'hero') : [...written]
  if (reshot.length) {
    const rel = path.relative(REPO_ROOT, SHOT_DIR)
    log(`${reshot.length} screenshot(s) rewritten — regenerate the 1x web copies before committing:`)
    log(
      `  for f in ${rel}/*.png; do for d in ${SITE_COPY_DIRS.join(' ')}; do ` +
        'magick "$f" -resize 1280x -colors 256 -strip "$d/$(basename "$f")"; done; done',
    )
  }

  const missed = REQUESTED.filter((id) => !written.has(id))
  if (missed.length) {
    // Exit non-zero so a partial run is not committed as a full re-capture.
    log(`FAILED: ${missed.join(', ')} were not written — the files already on disk are unchanged`)
    process.exitCode = 1
    return
  }
  log('done')
}

/**
 * Open `relPath` in the workbench editor. Directories render expanded, so a
 * node is only clicked when it is actually collapsed ("Expand <dir>"); the
 * leaf is always clicked ("Open <file>").
 */
async function openWorkbenchFile(page, relPath) {
  const parts = relPath.split('/')
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  for (let i = 0; i < parts.length - 1; i++) {
    const collapsed = page.getByRole('button', { name: new RegExp(`^Expand ${esc(parts[i])}$`) })
    if (await collapsed.count()) {
      await collapsed.first().click()
      await page.waitForTimeout(400)
    }
  }
  const leaf = page.getByRole('button', { name: new RegExp(`^Open ${esc(parts.at(-1))}$`) })
  if (!(await leaf.count())) {
    log(`WARNING: workbench file not found in the tree: ${relPath}`)
    return false
  }
  await leaf.first().click()
  await page.waitForTimeout(1500)
  return true
}

/**
 * Trim the recorded session down to the marked exchange and encode both a
 * GIF (README hero) and an MP4 fallback. The GIF is palette-optimised and
 * checked against the 5 MB budget from docs/screenshots.md.
 */
async function encodeHero(webm, marks) {
  const start = Math.max(0, marks.heroStart - 0.4)
  // Stop short of the mark. `heroEnd` is taken after the reply has settled and
  // the run then leaves the conversation screen; the hero loops, so a few
  // frames of the next screen read as a flash of blank page on every repeat.
  const duration = Math.max(2, marks.heroEnd - start - HERO_TAIL_TRIM)
  const gif = path.join(ASSET_DIR, 'demo.gif')
  const mp4 = path.join(ASSET_DIR, 'demo.mp4')
  const c = marks.crop
  // Even crop dimensions keep libx264's yuv420p happy.
  const crop = c
    ? `crop=${c.width - (c.width % 2)}:${c.height - (c.height % 2)}:${c.x}:${c.y},`
    : ''
  log(`encoding hero segment ${start.toFixed(1)}s +${duration.toFixed(1)}s`)

  await run('ffmpeg', [
    '-y', '-loglevel', 'error',
    '-ss', String(start), '-t', String(duration), '-i', webm,
    '-vf', `${crop}scale=900:-2:flags=lanczos`,
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '26', '-movflags', '+faststart',
    '-an', mp4,
  ])

  // Two-pass palette: a flat dark UI quantises cleanly at ~96 colours, which
  // is what keeps a 20-second capture inside the 5 MB budget from
  // docs/screenshots.md. Each rung trades frame rate and width for size; the
  // first one under GIF_BUDGET_BYTES wins.
  let gifSize = 0
  for (const [fps, width, colors] of [[10, 880, 96], [10, 800, 64], [8, 760, 48]]) {
    const filter =
      `${crop}fps=${fps},scale=${width}:-1:flags=lanczos,split[a][b];` +
      `[a]palettegen=max_colors=${colors}:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4`
    await run('ffmpeg', [
      '-y', '-loglevel', 'error',
      '-ss', String(start), '-t', String(duration), '-i', webm,
      '-vf', filter, '-loop', '0', gif,
    ])
    const { size } = await stat(gif)
    gifSize = size
    log(`demo.gif ${fps}fps/${width}px/${colors}c -> ${(size / 1048576).toFixed(2)} MB`)
    if (size <= GIF_BUDGET_BYTES) break
  }
  // Past the last rung the GIF ships over budget. Say so: the sizes above are
  // easy to read as progress rather than as three failures in a row.
  if (gifSize > GIF_BUDGET_BYTES) {
    log(
      `WARNING: demo.gif is ${(gifSize / 1048576).toFixed(2)} MB, past the ` +
        `${(GIF_BUDGET_BYTES / 1048576).toFixed(0)} MB budget even at the lowest rung — ` +
        'shorten the hero turn or add a smaller fps/width/colour step.',
    )
  }

  for (const f of [gif, mp4]) {
    const { size } = await stat(f)
    log(`wrote ${path.relative(REPO_ROOT, f)} (${(size / 1048576).toFixed(2)} MB)`)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
