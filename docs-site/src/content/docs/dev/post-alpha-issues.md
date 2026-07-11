---
title: "Post-alpha issues"
description: "Work items triaged out of the v0.1.0-alpha.1 release and deferred to later milestones, with reasons and milestone assignments."
sidebar:
  order: 22
---

This document lists work items that were explicitly **triaged out of the
v0.1.0-alpha.1 release** and deferred to a later milestone. Each item includes
the reason it was deferred and the milestone where it belongs.

This is not a backlog of launch blockers — the alpha ships without these items
by design. If you want to work on one, open or claim the linked issue.

> **Scope rule:** Do not add new items to this list without a corresponding
> GitHub issue and a milestone assignment. The purpose of this document is
> to make the deferred set visible, not to expand it silently.

---

## Deferred from alpha: high priority (Milestone 1 polish)

### 1. Real screenshots and demo assets

**What:** Replace the SVG placeholder images in the README and
[`docs/screenshots.md`](/dev/screenshots/) with real screen captures or a short animated GIF
showing an actual gameplay session.

**Why deferred:** Capturing real screenshots requires a stable real-model
playthrough, which in turn requires coordinated hardware access. This is a
polish step, not a functional blocker.

**Milestone:** 1 (polish)  
**Tracking:** See [`docs/screenshots.md`](/dev/screenshots/) for the replacement checklist.

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
**Tracking:** [`apps/desktop/`](https://github.com/outrightmental/ConversationSimulator/tree/main/apps/desktop) contains the Tauri skeleton; sidecar config
is the remaining work.

---

### 3. Code signing

**What:** Sign the macOS (`.dmg`) and Windows (`.exe`) installers so that
Gatekeeper and SmartScreen do not warn users.

**Why deferred:** Code signing requires Apple Developer Program enrollment
and a Windows EV certificate. Both have a cost and setup process that is
not worth completing before the alpha has proven its audience.

**Milestone:** 2 (distribution)

---

### 4. Auto-update

**What:** Add an in-app update check and download path so users are notified
when a new release is available.

**Why deferred:** Tauri supports Sparkle / NSIS auto-update but it requires
a signed update manifest hosted at a stable URL. Blocked on code signing
(item 3 above) and a hosting decision.

**Milestone:** 2 (distribution)

---

## Deferred from alpha: medium priority (Milestone 2+)

### 5. Community pack browser

**What:** An in-app discovery feed for community packs — browse, preview,
and install packs published by other creators without leaving the app.

**Why deferred:** Requires a pack registry backend (CDN or P2P) and
moderation tooling, which are significant infrastructure additions that
would compromise the MVP's "no server" principle.

**Milestone:** 3 (community)

---

### 6. Automated real-model smoke test in CI

**What:** Add a CI job that downloads the Qwen3 4B starter model and runs
a scripted end-to-end session with real inference, verifying response
latency and output quality signals.

**Why deferred:** Model downloads are large (~2.6 GB), slow, and
cache-unfriendly in most CI environments. The fake runtime provides full
structural coverage; real-model CI is a quality-of-life improvement.

**Milestone:** 2 (CI hardening)

---

### 7. Accessibility audit (WCAG 2.1 AA)

**What:** A systematic audit of the browser UI against WCAG 2.1 Level AA
criteria, followed by remediation of any failing items (color contrast,
focus management, keyboard traps, ARIA labels, screen reader order).

**Why deferred:** The alpha UI is functional but has not been audited by an
accessibility specialist. The automated `accessibility.test.tsx` covers
obvious violations; manual audit is needed for full compliance.

**Milestone:** 1 (polish) / 2 (hardening)  
**Tracking:** [`apps/web/src/__tests__/accessibility.test.tsx`](https://github.com/outrightmental/ConversationSimulator/blob/main/apps/web/src/__tests__/accessibility.test.tsx)

---

### 8. Performance benchmarks and optimization

**What:** Establish latency targets for the turn pipeline on reference
hardware (Apple M2, Intel i7 CPU-only, mid-spec Linux x86) and address
any regressions against those targets.

**Why deferred:** Performance profiling requires stable real-model
infrastructure. The fake runtime cannot measure inference latency. See
[`docs/performance.md`](/play/performance/) for guidance in the meantime.

**Milestone:** 2 (hardening)

---

### 9. Voice I/O polished integration

**What:** Streamline the whisper.cpp and Kokoro runtime setup so that a
user can enable voice input/output from the Model Manager UI without
touching the command line.

**Why deferred:** The runtimes are implemented and tested, but the
first-run download and configuration flow requires UX work. The text-only
path is the recommended alpha experience.

**Milestone:** 2 (voice polish)  
**Tracking:** [`runtimes/whisper_cpp/`](https://github.com/outrightmental/ConversationSimulator/tree/main/runtimes/whisper_cpp), [`runtimes/kokoro/`](https://github.com/outrightmental/ConversationSimulator/tree/main/runtimes/kokoro)

---

### 10. Pack signing and trust tiers

**What:** A cryptographic signing mechanism for official and community packs
so the validator can distinguish first-party content (Apache-2.0 / CC BY 4.0)
from unverified community submissions and enforce appropriate trust levels.

**Why deferred:** Signing infrastructure is only meaningful once the
community pack distribution path (item 5) exists.

**Milestone:** 3 (community)

---

## Items that will NOT be addressed post-alpha

These items were evaluated and explicitly placed in the "not now" category
in [ROADMAP.md](/project/roadmap/). Raising them as issues will be closed with
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
