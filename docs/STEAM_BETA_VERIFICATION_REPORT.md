<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Beta Verification Report

> **Purpose:** Signed-off aggregate report produced after completing the
> Steam beta client verification across all required platforms (Windows, macOS,
> Linux, Steam Deck).  One completed copy of this report must be attached to
> the release GitHub issue before the Stage 3 gate (G3-06) can be declared PASS,
> and before Valve's Steam Deck Verified review (G4-02) is requested.
>
> **When to use:** Complete this report after all four platform-specific
> checklists in `docs/release-checklist.md` (Parts E, G, H, I) are finished
> for the release candidate build.
>
> **How to file:** Copy this template, fill it in, and either attach it as a
> file to the release GitHub issue or paste it as a comment with the title
> "Steam beta verification report — vX.Y.Z".

---

## Report header

```
Build version         : vX.Y.Z  (or Steam build ID)
Steam branch verified : beta
Build date            : YYYY-MM-DD
Release issue         : https://github.com/outrightmental/ConversationSimulator/issues/NNN
Verification period   : YYYY-MM-DD to YYYY-MM-DD
Publishing owner      :
Report date           : YYYY-MM-DD
```

---

## Prerequisites

The following dependent issues must be resolved or have an accepted waiver
before this verification can proceed:

| Label | Issue | Status |
|-------|-------|--------|
| `ci-steam-beta-deploy` | [CI] Add SteamPipe deploy workflow to Steam beta branch | [ ] Closed / [ ] Waiver |
| `ci-signing-notarization-malware` | [CI] Add code signing, macOS notarization, and malware-scan hooks | [ ] Closed / [ ] Waiver |
| `steam-cloud-nonsensitive` | [Steamworks] Configure Steam Cloud for non-sensitive settings only | [ ] Closed / [ ] Waiver |
| `steam-achievements-stats-presence` | [Steamworks] Add achievements, stats, and rich presence | [ ] Closed / [ ] Waiver |
| `steam-store-assets-trailer` | [Steamworks] Prepare Steam store page copy, capsules, screenshots, and trailer | [ ] Closed / [ ] Waiver |
| `qa-automation-e2e` | [QA] Add packaged-app smoke tests and end-to-end scripted playthroughs | [ ] Closed / [ ] Waiver |

---

## Part 1 — Windows verification (release-checklist.md Part E)

**Tester:**
**Machine:**
**Date:**

| Step | Result |
|------|--------|
| E.1 Fresh install from Steam — no SmartScreen / AV warning on signed build | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.2 First-run model wizard | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.3 Text scenario and debrief | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.4 Log verification | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.5 Uninstall behavior | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.6 Reinstall behavior | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.7 Depot content audit | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.8 Offline play after model download | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.9 Privacy controls | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.10 Steam Cloud exclusions (Part B.11) | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.11 Support bundle flow | [ ] PASS / [ ] FAIL / [ ] SKIP |
| E.12 Achievements / stats / rich presence | [ ] PASS / [ ] FAIL / [ ] N/A |

**Windows platform result:**
- [ ] PASS — all required steps passed; no blocking issues
- [ ] PARTIAL — failures noted (see blockers below); maintainer waiver required
- [ ] FAIL — one or more blocking issues remain open

```
Hardware
  CPU  :
  RAM  :
  GPU  :
  OS   :  Windows 10 / 11 build NNNNN
  Model tested : Qwen3 4B Q4_K_M / other
  Hardware tier : [ ] Minimum  [ ] Starter  [ ] Recommended

First-token latency : ___ s   [ ] Within threshold  [ ] Exceeds threshold
Notes:
  -
```

---

## Part 2 — macOS verification (release-checklist.md Part G)

**Tester:**
**Machine:**
**Date:**

| Step | Result |
|------|--------|
| G.1 Gatekeeper / notarization — no dialog on clean install | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.2 Fresh install from Steam | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.3 First-run model wizard | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.4 Text scenario and debrief | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.5 Offline play after model download | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.6 Privacy controls | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.7 Steam Cloud exclusions (Part B.11) | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.8 Support bundle flow | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.9 Achievements / stats / rich presence | [ ] PASS / [ ] FAIL / [ ] N/A |
| G.10 Log verification | [ ] PASS / [ ] FAIL / [ ] SKIP |
| G.11 Uninstall and reinstall behavior | [ ] PASS / [ ] FAIL / [ ] SKIP |

**macOS platform result:**
- [ ] PASS
- [ ] PARTIAL — failures noted; waiver required
- [ ] FAIL

```
Hardware
  CPU / chip  :  Apple M__ / Intel Core i__
  RAM         :
  OS          :  macOS 13 / 14 / 15
  Architecture:  arm64 / x86-64
  Model tested: Qwen3 4B Q4_K_M / other
  Hardware tier: [ ] Minimum  [ ] Starter  [ ] Recommended

spctl output  : accepted / rejected / error
codesign exit : 0 / non-zero
First-token latency : ___ s   [ ] Within threshold  [ ] Exceeds threshold
Notes:
  -
```

---

## Part 3 — Linux verification (release-checklist.md Part H)

**Tester:**
**Machine:**
**Date:**

| Step | Result |
|------|--------|
| H.1 Executable permissions and glibc ≥ 2.35 confirmed | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.2 Fresh install from Steam | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.3 First-run model wizard | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.4 Text scenario and debrief | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.5 Offline play after model download | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.6 Privacy controls | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.7 Steam Cloud exclusions (Part B.11) | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.8 Support bundle flow | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.9 Achievements / stats / rich presence | [ ] PASS / [ ] FAIL / [ ] N/A |
| H.10 Log verification | [ ] PASS / [ ] FAIL / [ ] SKIP |
| H.11 FUSE / AppImage notes documented | [ ] Done / [ ] N/A |

**Linux platform result:**
- [ ] PASS
- [ ] PARTIAL — failures noted; waiver required
- [ ] FAIL

```
Hardware
  CPU     :
  RAM     :
  GPU     :
  OS      :  Ubuntu 22.04 / 24.04 / Fedora 40 / other
  glibc   :  x.xx (output of `ldd --version`)
  Model tested: Qwen3 4B Q4_K_M / other
  Hardware tier: [ ] Minimum  [ ] Starter  [ ] Recommended

FUSE status :  FUSE 2 present / absent (used --appimage-extract-and-run)
First-token latency : ___ s   [ ] Within threshold  [ ] Exceeds threshold
Notes:
  -
```

---

## Part 4 — Steam Deck verification (release-checklist.md Part I)

**Tester:**
**Device:**  Steam Deck [ ] LCD / [ ] OLED
**SteamOS version:**
**Date:**

| Step | Result |
|------|--------|
| I.1 Install from Steam library in Gaming Mode | [ ] PASS / [ ] FAIL |
| I.2 First-run model wizard (controller-only) | [ ] PASS / [ ] FAIL |
| I.3 TC-11 controller-only full session (all 13 steps) | [ ] PASS / [ ] PARTIAL / [ ] FAIL |
| I.4 Offline play under SteamOS | [ ] PASS / [ ] FAIL |
| I.5 Privacy controls and support bundle (controller-only) | [ ] PASS / [ ] FAIL |
| I.6 Steam Cloud exclusions | [ ] PASS / [ ] FAIL |
| I.7 Achievements / stats / rich presence | [ ] PASS / [ ] FAIL / [ ] N/A |
| I.8 Battery impact documented (target < 15 W) | [ ] Done |
| I.9 All Steam Deck Verified sign-off items checked | [ ] PASS / [ ] FAIL |

**TC-11 detail (any FAIL steps):**

```
(list any TC-11 steps that failed, with description)
-
```

**Steam Deck platform result:**
- [ ] PASS — all required steps passed; Deck Verified criteria met
- [ ] PARTIAL — failures noted; waiver required before G4-02 request
- [ ] FAIL — Deck Verified cannot be requested until blockers resolved

```
Battery draw (observed)  : ___ W average
Fan behavior             : silent / intermittent / sustained
Model load time          : ___ s  (target ≤ 90 s)
First-token latency      : ___ s  (target ≤ 30 s)
Notes:
  -
```

---

## Part 5 — Platform-specific blocker log

List every session-ending bug, data-loss bug, or privacy regression found during
Parts E, G, H, and I.  Each entry must have a corresponding GitHub issue with
the labels `beta-testing` and the appropriate `platform:*` label.

| # | Platform | Description | GitHub issue | Status |
|---|----------|-------------|-------------|--------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

> Add rows as needed.  "Status" values: `Open`, `Closed`, `Waived (see notes)`.

**All session-ending / data-loss / privacy-regression blockers resolved or waived:**
- [ ] Yes — gate G3-06 may be declared PASS
- [ ] No — gate blocked; see open issues above

---

## Part 6 — CI gate confirmation

All automated gates must be green on the build commit before this report is
filed.

| Gate | Workflow | Result |
|------|----------|--------|
| Part A CI gates | `ci.yml` | [ ] PASS / [ ] FAIL |
| Release smoke — Windows | `release-smoke.yml` | [ ] PASS / [ ] FAIL |
| Release smoke — macOS | `release-smoke.yml` | [ ] PASS / [ ] FAIL |
| Release smoke — Linux | `release-smoke.yml` | [ ] PASS / [ ] FAIL |
| Artifact inspection (all platforms) | `steam-deploy.yml` | [ ] PASS / [ ] FAIL |

CI run link: _______________________________________________

---

## Aggregate sign-off

```
=== Steam Beta Verification Report — Aggregate Sign-Off ===

Build version      : vX.Y.Z
Steam branch       : beta
Steam App ID       : ___________________________
Build submitted    : ___________________________  (SteamPipe build ID)
Verification date  : YYYY-MM-DD

--- Platform results ---
Windows            : [ ] PASS  [ ] PARTIAL  [ ] FAIL
macOS (Apple Si.)  : [ ] PASS  [ ] PARTIAL  [ ] FAIL
macOS (Intel)      : [ ] PASS  [ ] PARTIAL  [ ] FAIL
Linux (x86-64)     : [ ] PASS  [ ] PARTIAL  [ ] FAIL
Steam Deck         : [ ] PASS  [ ] PARTIAL  [ ] FAIL  [ ] Deferred to Stage 4

--- Blocker status ---
Open blocking issues (GitHub #):
  -
  -
All blockers resolved or waived: [ ] Yes  [ ] No

--- Gate outcomes ---
G3-06 (beta session verification)      : [ ] PASS  [ ] PARTIAL  [ ] FAIL
G4-02 (Steam Deck Verified — Stage 4)  : [ ] PASS  [ ] Pending Valve review  [ ] FAIL

--- Overall result ---
[ ] PASS — all required platforms passed; no unresolved blocking issues
[ ] PARTIAL — failures noted above; requires maintainer countersignature
[ ] FAIL — one or more blocking issues remain; gate cannot open

Signed: ___________________________ (tester / QA lead)

Countersigned: ___________________________ (publishing owner — required for
               PARTIAL or Stage 4 gate decisions)
Date: YYYY-MM-DD

Additional notes:
  -
```

---

## Links

- [`docs/release-checklist.md`](release-checklist.md) — Parts E (Windows),
  G (macOS), H (Linux/SteamOS), I (Steam Deck), and J (sign-off) contain the
  step-by-step platform checklists this report summarises
- [`docs/QA_STEAM_PLATFORM_MATRIX.md`](QA_STEAM_PLATFORM_MATRIX.md) — full QA
  test case matrix (TC-01 through TC-11) and per-platform hardware tiers
- [`docs/steam-mvp-scope.md`](steam-mvp-scope.md) — gate definitions G3-06 and
  G4-02
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md)
  — compliance checklists SR-01 through SR-08 and risk register
- [`docs/linux-steamos-requirements.md`](linux-steamos-requirements.md) —
  glibc requirements, SteamOS hardware profile, and performance targets
- [`docs/platform-notes.md`](platform-notes.md) — macOS signing, Gatekeeper,
  and system requirements
