<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Next Fest Demo — Registration, Build and Submission Runbook

> **Purpose:** the operational runbook for shipping the free demo edition of
> Conversation Simulator to Steam and entering it in Steam Next Fest. It
> covers the one-time Steamworks setup for the demo app, the GitHub variables
> CI needs, how a demo build is produced and uploaded, the store-page work a
> demo requires, and the Next Fest registration timeline.
>
> **What the demo is** — and every product decision behind it — lives in
> [`docs/steam-next-fest-demo.md`](../docs/steam-next-fest-demo.md). Read that
> first; this document assumes it.
>
> **Audience:** platform team (Steamworks + CI), publishing owner (store page,
> Next Fest registration), QA (the demo gate).

---

## At a glance

| Item | Value |
|------|-------|
| Demo app name | `Conversation Simulator Demo` |
| Relationship to the base app | Steam **demo** of App **4963030** (created from the base app's Steamworks page); free; attached to the base store page |
| Registered | 2026-09-27, as a child app of publisher 342628 |
| Demo App ID | **5343430** (`STEAM_DEMO_APP_ID`) — store page `https://store.steampowered.com/app/5343430/` once live |
| Packages | Store package **1846149** (free, what "Download Demo" grants) · beta-testing package **1846148** (tester keys) · developer-comp package **1846147** (auto-granted to the publisher) |
| Store item | **1348530** |
| Depots | Three, one per platform, mirroring the base app: **5343431** Windows (reshaped from Valve's auto-created all-OS depot), **5343432** macOS, **5343433** Linux/SteamOS — configured and published 2026-09-28 (step 1.2) |
| Branches | `default` (what Next Fest players get), `beta` (internal verification) |
| Build source | `release.yml` → **Run workflow** → `edition: demo`, from an existing release tag |
| Upload | `steam-deploy.yml` with `edition: demo` (chained automatically from the demo build) |
| Payload | Same depot layout as the base app; the binaries are compiled as the demo edition |
| Store assets | Its own client icon and app icon (purple plate + "DEMO" ribbon, §4.2); capsules still to get the matching ribbon; demo-edition screenshots; base trailer |
| Next Fest target | First edition whose registration is open ≥ 6 weeks after the demo gate passes (see [Timeline](#52-next-fest-timeline)) |

---

## 1. One-time Steamworks setup

Do this once, before the first demo upload. Everything here is done by a
partner-portal user with **Developer** (or higher) permissions on App 4963030.

### 1.1 Create the demo app — done 2026-09-27

1. Open **Steamworks → App Admin → 4963030 → Store Presence → Demo**
   (the "Manage Demo" tool on the base app's landing page).
2. Choose **Create Demo**. Valve creates a new app with its own App ID, named
   `Conversation Simulator Demo`, already linked to the base app as its demo.
   Record the demo App ID in the Identifiers table of
   [`STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md#identifiers).
3. Do **not** try to make a `demo` branch of the paid app instead: a branch of
   a paid app is not free, cannot carry a separate store presence, and cannot
   be entered in Next Fest.

What Valve created for us (partner-portal log, 2026-09-27):

| Created | ID | Purpose |
|---------|----|---------|
| Child app of publisher 342628 | **5343430** | The demo app itself; goes into `STEAM_DEMO_APP_ID`. |
| Depot `Conversation Simulator Demo Content` (OS = All) | **5343431** | Auto-created and attached to all three packages. Reshaped into the Windows depot in step 1.2. |
| Package `Conversation Simulator Demo` | 1846149 | The free store package — what the **Download Demo** button grants. Nothing to price. |
| Package `Conversation Simulator Demo for Beta Testing` | 1846148 | Generate Steam keys from this package for testers of the demo's `beta` branch (Steamworks → Packages → 1846148 → Generate Steam Product Codes). |
| Package `Conversation Simulator Demo Developer Comp` | 1846147 | Auto-granted to publisher 342628: every partner account already owns the demo, so the team can install staged builds without keys. |
| Store item | 1348530 | The demo's store presence (its own page and the button on the base page). |

The App ID is not printed in that log; it is on the demo's landing page (and
in the URL of every demo App Admin page): **5343430**. It is recorded in
[`STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md#identifiers) and goes
into the `STEAM_DEMO_APP_ID` repository variable.

### 1.2 Depots, launch options, install script

On the **demo** app (not the base app):

- **Depots — done 2026-09-28:** exactly three — Windows x86-64, macOS,
  Linux/SteamOS — in the same order as the base app. Valve auto-created a
  single all-OS depot,
  **5343431** `Conversation Simulator Demo Content`, attached to all three
  packages; do not upload to it as-is (every player would download every
  platform's binaries). Instead:
  1. Edit 5343431: rename `Conversation Simulator Demo — Windows`, OS =
     Windows. This is `STEAM_DEMO_DEPOT_WINDOWS_ID`.
  2. Add `Conversation Simulator Demo — macOS` (OS = macOS) and
     `Conversation Simulator Demo — Linux` (OS = Linux) — IDs **5343432**
     (macOS) and **5343433** (Linux), confirmed in the portal.
  3. Attach both new depots to packages 1846147, 1846148 and 1846149.
  4. Publish the app configuration (App Admin → Publish). Depot changes are
     not live — and `steamcmd` cannot target them — until published.
     Published 2026-09-28.
  Record the three IDs in [`STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md#identifiers).
- **Launch options — done 2026-09-28** (the macOS path is still to be
  confirmed against the first uploaded build, below) — are the same shape as
  the base app's (no arguments on any platform). The demo's `.app` bundle is
  named after its product name, but the executable inside it keeps Tauri's
  main binary name — the Cargo package name `convsim-desktop`, which Tauri
  does not rename to the product name — so only the bundle part of the macOS
  path differs:

  | Platform | Executable | Working directory |
  |----------|-----------|-------------------|
  | Windows | `ConversationSimulator.exe` | *(depot root)* |
  | macOS | `Conversation Simulator Demo.app/Contents/MacOS/convsim-desktop` | *(depot root)* |
  | Linux | `ConversationSimulator.AppImage` | *(depot root)* |

  Before saving the macOS row, confirm it against the first uploaded build:
  Steamworks → Builds → *View Manifest* on the macOS depot lists the exact
  path, and `CFBundleExecutable` in the `.app`'s `Contents/Info.plist` (from
  the `demo-desktop-macOS-*` artifact) must read `convsim-desktop`. A launch
  option naming a file that does not exist is a demo that never starts on
  macOS (gate D-03).

  The Windows executable keeps the base app's name: the depot packaging step
  renames the Rust binary regardless of edition, and the artifact-inspection
  tests expect it.
- **Install script:** the Windows depot template registers
  `installscript.vdf` (WebView2 bootstrapper) for the demo exactly as for the
  base app — nothing to configure by hand.
- **Steam Cloud:** leave **off** for the demo. Cloud settings sync is a base-app
  feature; the demo shares its data directory with the base app locally
  instead (see the decision record).
- **Achievements / stats:** none on the demo app.

### 1.3 Packages and release state

- Valve auto-created the **free** store package (1846149) with the demo;
  nothing to price. Tester keys come from the beta-testing package (1846148);
  the developer-comp package (1846147) is already granted to the publisher.
- Set the demo's release state to **Coming Soon** until the demo gate passes,
  then release it (a demo may be live before the base app is — Next Fest, in
  fact, requires the demo to be playable during the fest while the base app is
  still Coming Soon).

### 1.4 GitHub repository variables

These are declared in `local.steam_variables` in
[`infra/github.tf`](../infra/github.tf) and applied with Terraform (done
2026-09-28) — never set them in the GitHub UI or with `gh variable set`.
They are non-secret (App and depot IDs appear in store URLs) and deliberately
separate from the paid app's `STEAM_*` variables, so a demo upload can never
fall through to the paid app's depots — `steam-deploy.yml` refuses to run
`edition: demo` while any of them is unset.

| Variable | Value |
|----------|-------|
| `STEAM_DEMO_APP_ID` | `5343430` |
| `STEAM_DEMO_DEPOT_WINDOWS_ID` | `5343431` (reconfigured as the Windows depot in step 1.2) |
| `STEAM_DEMO_DEPOT_MACOS_ID` | `5343432` (the macOS depot added in step 1.2) |
| `STEAM_DEMO_DEPOT_LINUX_ID` | `5343433` (the Linux/SteamOS depot added in step 1.2) |

The CI build account (`STEAM_USERNAME`) needs **Developer** permissions on
App 5343430 as well as on 4963030 — Valve does not inherit app permissions
from the base app to its demo. Add them under **Users & Permissions** or the
first upload fails at `+login` / `run_app_build` with a permission error.

---

## 2. Building a demo

A demo build is made **from a release tag that already exists** — the demo is
always the demo *of* a specific base version, and it reuses that tag's
validated source, version stamp and docs-freshness check.

1. **Actions → Release → Run workflow.**
2. `tag`: the base release tag (e.g. `v0.2.8`). `edition`: **`demo`**. Under
   *Use workflow from*, pick **that tag**, not `main`: a dispatch builds the
   ref it was started from, and the Validate job refuses a demo run whose
   commit is not the tag's.
3. The run builds all three platforms with:
   - `VITE_CONVSIM_EDITION=demo` baked into the web bundle;
   - `CONVSIM_EDITION=demo` compiled into the Tauri shell (validated by
     `build.rs`; passed to `convsim-core` at launch);
   - the `tauri.demo.conf.json` overlay (product name, bundle identifier,
     window title, and the `icons-demo/` icon set) on top of the Steam overlay;
   - the same signing, notarisation, malware scan, and depot packaging steps
     as a full build — a demo is under Valve review like any build.
4. Artifacts upload as **`demo-desktop-*`**. No GitHub release is published
   (the `release` job is skipped by design for demos).
5. The `steam` job chains automatically with `edition: demo` and **stages**
   the build on the demo app (no branch is set live). The `steam-release`
   environment approval still gates it.

To verify locally before a CI build, run the engine as the demo edition and
open the web UI — it adopts the engine's edition from `/api/health`:

```sh
CONVSIM_EDITION=demo ./scripts/dev.sh
```

`services/convsim-core/tests/test_edition.py` and
`apps/web/src/__tests__/edition.test.tsx` are the automated half of the demo
gate (D-01, D-02).

---

## 3. Uploading and setting live

`steam-deploy.yml` takes an `edition` input on both trigger paths.

| Situation | How |
|-----------|-----|
| Stage a demo build (dry run) | Chained automatically from the demo Release run, or **Actions → Steam Deploy → Run workflow** with `release_tag`, `run_id` of the demo Release run, `edition: demo`, `set_live_branch` **empty** |
| Put a demo build on the internal `beta` branch | Same, with `set_live_branch: beta` (create the branch on the demo app first: **App Admin → Builds → Branches**) |
| Make the demo public (`default`) | `workflow_dispatch` only, `set_live_branch: default`, **after the demo gate passes** — the same rule as the base app |

What the workflow does differently for `edition: demo`:

- resolves `STEAM_DEMO_APP_ID` and the three `STEAM_DEMO_DEPOT_*_ID` variables
  (and fails early if any is missing);
- downloads only `demo-desktop-*` artifacts;
- labels the build `Conversation Simulator Demo <tag>` in Steamworks;
- renders the **same** depot templates (`steam/depot_*.vdf.tpl`,
  `steam/app_build.vdf.tpl`) with the demo IDs — there is no second set of
  templates to keep in sync.

Everything else — depot audit, artifact inspection, macOS signature check,
the `default`-on-automatic-runs refusal — applies unchanged.

**Verifying a staged demo build:** Steamworks → App Admin → *the demo app* →
Builds. The build description reads `Conversation Simulator Demo <tag>`, three
depots have file counts, and **View Manifest** shows the tag's version. Then
install it through Steam on each platform and run the manual rows of the
[demo gate](../docs/steam-next-fest-demo.md#demo-gate) (D-03 to D-10).

---

## 4. Store page work for the demo

A Steam demo attached to a base app gets a **Download Demo** button on the
base store page and, optionally, its own page. Next Fest features the base
page; the demo needs enough of its own presence to be reviewed.

### 4.1 Copy

Use the demo section of [`STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md#demo-edition)
verbatim. The rules that matter most:

- Say exactly what the demo contains: **five conversations, one AI model
  download (~2.5 GB), text only, unlimited replay**.
- Say what the full game adds, in the same words the in-app upsell uses.
- No claim that the paid app is free; the open-source wording of the base page
  applies unchanged.
- No AI-therapy / diagnosis / advice language (G4-04 applies to the demo page).

### 4.2 Assets

| Asset | Demo treatment |
|-------|----------------|
| **Client icon** (32 × 32 `.ico`) | `publishing/assets/icons/demo_client_icon.ico`, generated by `publishing/assets/source/gen_icons.py` as a single uncompressed 32-bit frame, the encoding every ICO reader handles. Upload under **Steamworks → the demo app → Store Presence → Graphical Assets → Client Icon**. This is the one Steam draws beside the app name in the library list; while it was missing, the demo and the full game were indistinguishable there (issue #499). |
| App icon in the build | `apps/desktop/src-tauri/icons-demo/`, referenced by `bundle.icon` in `tauri.demo.conf.json`. Same mark as the client icon, so the Steam entry and the installed app agree in the dock, the taskbar and Alt-Tab. |
| Header, small, main, library capsules | **Outstanding.** The intended treatment is the base capsules with a **"DEMO"** ribbon in the lower-right corner, matching the icon's; `gen_capsules.py` does not draw it yet, and the ribbon geometry to reuse is `_ribbon()` in `gen_icons.py`. Store-asset rules are unchanged (artwork + name only, no taglines). |
| Screenshots (min 5) | Taken from a **demo build**: the demo Home (five cards), the first-run "Set me up" screen, one conversation mid-session, one debrief with scores, the Coffee at Café Sol card. Nothing that the demo cannot reach. Production rules in [`STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md#screenshot-production-rules) apply. |
| Trailer | The base trailer, unchanged. |

### 4.3 Content questionnaire and IARC

Answer the demo's content questionnaire identically to the base app's
([`STEAM_REVIEW_SUBMISSION.md`](STEAM_REVIEW_SUBMISSION.md)): the demo's five
conversations are a subset of the base content and the ceiling is PG-13 (the
dating pack). `test_edition.py` enforces that ceiling.

### 4.4 Review

Submit the demo for **build review** and **store review** like the base app.
Valve reviews demos with the same checklist — the overlay must work
(Shift+Tab, F12), the app must launch on a clean machine, and the store
content must match the build. The demo inherits the base app's overlay
surface and Steamworks bridge on Windows.

Before approving the `steam-release` environment for a demo upload, read the
Defender-for-Storage verdict the same way as for a base release
([`WINDOWS_MALWARE_SCANNING.md`](WINDOWS_MALWARE_SCANNING.md)): the demo run's
`defender-scan` job uploads the Windows payload as `<tag>-demo-signed-build.zip`
and prints the portal link in its log. There is no GitHub release to carry the
note for a demo, so record the verdict on this section's review row instead.

---

## 5. Next Fest registration

### 5.1 Eligibility (Valve's rules, summarised — confirm in Steamworks)

- The base app must be **Coming Soon** (not released) and must never have
  been in a previous Next Fest. A game participates once.
- The base store page must be approved and public with a release date or
  window.
- The demo must be **released and playable** (its `default` branch live) by
  the fest's demo deadline, and must stay playable throughout the fest.
- Registration happens in **Steamworks → Marketing & Visibility → Steam Next
  Fest** while the edition's registration window is open. The window closes
  weeks before the fest and cannot be reopened.

### 5.2 Next Fest timeline

Valve publishes each edition's dates in Steamworks. Back-plan from the demo
deadline:

| When | What |
|------|------|
| Fest − 10 weeks | Demo gate D-01…D-10 passing on a staged build. Demo store copy and assets drafted. |
| Fest − 8 weeks | Demo app in store review; base store page approved and public (Coming Soon). |
| Fest − 6 weeks | Register in **Marketing & Visibility → Steam Next Fest** (before the window closes). Demo `default` branch live. |
| Fest − 4 weeks | Register at least one developer livestream slot (optional, recommended). Announce the demo on the base page (Steam event post). |
| Fest − 1 week | Freeze: no demo build changes unless a demo blocker is found. Re-run D-03 on all three platforms against the live build. |
| Fest week | Monitor the Support channels daily; treat every "failed setup" or "incoherent NPC" report as P0. Post one update mid-fest. |
| Fest + 1 week | Retro: wishlists, demo installs → session completions (from Steamworks demo stats, not telemetry — the app has none), top support themes. |

The **February 2027** edition is the working target as of this document
(see the decision record). When the actual dates are known, copy them into
[`STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md) alongside the registration
confirmation.

### 5.3 Promotion record

Record the demo's `default` set-live and the Next Fest registration in
[`STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md) with the demo App ID, the
build ID, the tag, and the fest edition.

---

## 6. Support during the fest

The demo ships the full Support screen (crash bundles, beta report) and the
same troubleshooting docs. Issues arrive through the usual channels
([`docs/steam-triage.md`](../docs/steam-triage.md)); tag them `area:steam` and
mention "demo" in the title so they can be separated at the retro. A player
who reports a stalled download, a failed first run, an incoherent character or
a missing debrief in the demo has hit a demo blocker — those go to P0 for the
duration of the fest.

Shared data directory reminder for support answers: the demo and the full app
use the same local data folder, so "the full game found my demo model /
sessions" is expected, and "Clear local data" in either edition clears both.

---

## Links

- [`docs/steam-next-fest-demo.md`](../docs/steam-next-fest-demo.md) — scope, decisions, cut list, demo gate
- [`STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — identifiers (demo App ID and depot IDs)
- [`STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — SteamPipe and the deploy workflow
- [`STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md#demo-edition) — demo store copy
- [`STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) — asset specifications
- [`STEAM_REVIEW_SUBMISSION.md`](STEAM_REVIEW_SUBMISSION.md) — review submission runbook (base app)
- `.github/workflows/release.yml` — `edition` input
- `.github/workflows/steam-deploy.yml` — `edition` input and the `STEAM_DEMO_*` variables
