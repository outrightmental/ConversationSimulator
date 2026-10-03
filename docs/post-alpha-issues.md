<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Post-alpha issues

This document lists work items that were explicitly **triaged out of the
v0.1.0-alpha.1 release** and deferred to a later milestone. Each item includes
the reason it was deferred and the milestone where it belongs.

This is not a backlog of launch blockers — the alpha ships without these items
by design. If you want to work on one, open or claim the linked issue.

> **Scope rule:** Do not add new items to this list without a corresponding
> GitHub issue and a milestone assignment. The purpose of this document is
> to make the deferred set visible, not to expand it silently.

> **Status (2026-08-21):** every open item below now has a tracking issue on the
> [delivery board](https://github.com/orgs/outrightmental/projects/12). The near-term
> items ([#455](https://github.com/outrightmental/ConversationSimulator/issues/455),
> [#456](https://github.com/outrightmental/ConversationSimulator/issues/456),
> [#457](https://github.com/outrightmental/ConversationSimulator/issues/457)) sit in the
> *06 · Release polish* phase and are open to the implementation factory; the rest sit in
> *07 · Future* with the `manual` label until deliberately released — see
> [governance.md](governance.md) for how that throttle works.

---

## Deferred from alpha: high priority (Milestone 1 polish)

### 1. Real screenshots and demo assets — done

**What:** Replace the SVG mockups in the README and `docs/screenshots.md` with
real screen captures and a short recording of an actual gameplay session.

**Why deferred:** Capturing them required a stable real-model playthrough,
which in turn required coordinated hardware access. It was a polish step, not
a functional blocker.

**Outcome:** Landed — six PNGs and a GIF/MP4 hero captured from one
local-model playthrough on an Apple M1 Pro, with
[`scripts/capture-screenshots.mjs`](../scripts/capture-screenshots.mjs) to
remake them. Capture environment and alt text: [screenshots.md](screenshots.md).

**Milestone:** 1 (polish)  
**Tracking:** [#455](https://github.com/outrightmental/ConversationSimulator/issues/455) · see [screenshots.md](screenshots.md) for the capture checklist.

---

### 2. Desktop app with bundled backend

**What:** Package `convsim-core` inside the Tauri desktop build so users
can launch a single `.dmg` / `.exe` / `.AppImage` without running
`./scripts/dev.sh` separately.

**Why deferred:** Bundling a Python runtime and FastAPI server inside Tauri
requires a sidecar packaging pattern that was scoped out of the alpha to
keep the initial surface area small. The source install path is fully
functional.

**Milestone:** 1 (desktop packaging)  
**Status:** ✅ **Shipped** ([#456](https://github.com/outrightmental/ConversationSimulator/issues/456)). `convsim-core` is built by
`scripts/build-core.sh` into a single PyInstaller executable and packaged into
the installer as a Tauri bundle resource; the shell starts it, waits for
`GET /api/health` on 127.0.0.1:7355 before showing the app, restarts it if it
crashes, and drains it rather than killing it on exit — see
[apps/desktop/README.md](../apps/desktop/README.md), "Core sidecar lifecycle".
`scripts/packaged-core-smoke.sh` runs the packaged engine in CI and asserts
health readiness, loopback-only binding, official-pack seeding, an offline
`convsim offline-smoke-test`, and a clean shutdown.

One part of the original acceptance list was deliberately not implemented:
"CI produces the bundled artifact … as a release asset". Conversation Simulator
ships prebuilt binaries through **Steam only** — a GitHub release is a changelog
and a tag, and `release.yml` says so at length. CI does produce the bundled
installer for all three platforms as build artifacts, and the Steam depot takes
its payload from them.

---

### 3. Code signing

**What:** Sign the macOS (`.dmg`) and Windows (`.exe`) installers so that
Gatekeeper and SmartScreen do not warn users.

**Why deferred:** Code signing requires Apple Developer Program enrollment
and a Windows EV certificate. Both have a cost and setup process that is
not worth completing before the alpha has proven its audience.

**Milestone:** 2 (distribution)  
**Status:** ✅ **Shipped** during the Hardening phase — Windows Authenticode ([#404](https://github.com/outrightmental/ConversationSimulator/issues/404)) and Apple Developer ID signing + notarization ([#406](https://github.com/outrightmental/ConversationSimulator/issues/406)); see `publishing/` for the runbooks. Auto-update (item 4) is now unblocked.

---

### 4. Auto-update

**What:** Add an in-app update check and download path so users are notified
when a new release is available.

**Why deferred:** Tauri supports Sparkle / NSIS auto-update but it requires
a signed update manifest hosted at a stable URL. Blocked on code signing
(item 3 above) and a hosting decision.

**Milestone:** 2 (distribution)  
**Tracking:** [#461](https://github.com/outrightmental/ConversationSimulator/issues/461) — unblocked now that code signing (item 3) has shipped.

---

## Deferred from alpha: medium priority (Milestone 2+)

### 5. Community pack browser

**What:** An in-app discovery feed for community packs — browse, preview,
and install packs published by other creators without leaving the app.

**Why deferred:** Requires a pack registry backend (CDN or P2P) and
moderation tooling, which are significant infrastructure additions that
would compromise the MVP's "no server" principle.

**Milestone:** 3 (community)  
**Tracking:** [#465](https://github.com/outrightmental/ConversationSimulator/issues/465) · design baseline: `docs/marketplace-architecture.md`

---

### 6. Automated real-model smoke test in CI

**What:** Add a CI job that downloads the Qwen3 4B starter model and runs
a scripted end-to-end session with real inference, verifying response
latency and output quality signals.

**Why deferred:** Model downloads are large (~2.6 GB), slow, and
cache-unfriendly in most CI environments. The fake runtime provides full
structural coverage; real-model CI is a quality-of-life improvement.

**Milestone:** 2 (CI hardening)  
**Status:** ✅ **Shipped** ([#457](https://github.com/outrightmental/ConversationSimulator/issues/457)),
pulled forward into the Milestone-1 polish set rather than waiting for
Milestone 2. `.github/workflows/model-smoke-nightly.yml` runs nightly: it
resolves the registry's `starter` model from one lookup, downloads it with
SHA-256 verification (cached between runs and re-verified before the weights
load, so a drifted cache hit fails loudly), starts `llama-server` and
`convsim-core` on it, plays a scripted multi-turn conversation and asserts a
*scored* debrief — inside a documented budget under 30 min. Every failure is
attributed to one of six classes with its own exit code, so a red nightly is
triageable from the job summary; the harness's own decision logic is unit-tested
per-PR. See [real-model-smoke.md](real-model-smoke.md).  
**Tracking:** [#457](https://github.com/outrightmental/ConversationSimulator/issues/457)

---

### 7. Accessibility audit (WCAG 2.1 AA)

**What:** A systematic audit of the browser UI against WCAG 2.1 Level AA
criteria, followed by remediation of any failing items (color contrast,
focus management, keyboard traps, ARIA labels, screen reader order).

**Why deferred:** The alpha UI is functional but has not been audited by an
accessibility specialist. The automated `accessibility.test.tsx` covers
obvious violations; manual audit is needed for full compliance.

**Milestone:** 1 (polish) / 2 (hardening)  
**Tracking:** [#462](https://github.com/outrightmental/ConversationSimulator/issues/462) · `apps/web/src/__tests__/accessibility.test.tsx`

---

### 8. Performance benchmarks and optimization

**What:** Establish latency targets for the turn pipeline on reference
hardware (Apple M2, Intel i7 CPU-only, mid-spec Linux x86) and address
any regressions against those targets.

**Why deferred:** Performance profiling requires stable real-model
infrastructure. The fake runtime cannot measure inference latency. See
`docs/performance.md` for guidance in the meantime.

**Milestone:** 2 (hardening)  
**Tracking:** [#463](https://github.com/outrightmental/ConversationSimulator/issues/463) — sequenced after #457 provides real-model infrastructure in CI.

---

### 9. Voice I/O polished integration

**What:** Streamline the whisper.cpp and Kokoro runtime setup so that a
user can enable voice input/output from the Model Manager UI without
touching the command line.

**Why deferred:** The runtimes are implemented and tested, but the
first-run download and configuration flow requires UX work. The text-only
path is the recommended alpha experience.

**Milestone:** 2 (voice polish)  
**Tracking:** [#464](https://github.com/outrightmental/ConversationSimulator/issues/464) · `runtimes/whisper_cpp/`, `runtimes/kokoro/`

---

### 10. Pack signing and trust tiers

**What:** A cryptographic signing mechanism for official and community packs
so the validator can distinguish first-party content (Apache-2.0 / CC BY 4.0)
from unverified community submissions and enforce appropriate trust levels.

**Why deferred:** Signing infrastructure is only meaningful once the
community pack distribution path (item 5) exists.

**Milestone:** 3 (community)  
**Tracking:** [#466](https://github.com/outrightmental/ConversationSimulator/issues/466) — sequenced after the community pack browser (item 5).

---

## Items that will NOT be addressed post-alpha

These items were evaluated and explicitly placed in the "not now" category
in [ROADMAP.md](../ROADMAP.md). Raising them as issues will be closed with
a reference to the roadmap unless a compelling new argument is presented.

- VR / AR integration
- Multiplayer or shared sessions
- Cloud inference backend
- Mobile apps (iOS / Android)
- Marketplace or paid content
- NSFW / above-PG-13 content
- Celebrity or public-figure packs
- Complex character animation
- Clinical / therapy / legal positioning

---

## How to claim a post-alpha item

1. Find or open a GitHub issue for the item.
2. Assign the issue to the correct milestone.
3. Comment on the issue to claim it so others know it is in progress.
4. When the item ships, remove it from this document (or update its status).

Keep this list honest: if something is no longer deferred, remove it.
If something new is deferred, add it with a reason and a milestone.
