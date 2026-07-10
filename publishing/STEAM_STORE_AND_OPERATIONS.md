<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Store and Operations

> **Purpose:** Single operational reference for everyone involved in launching
> and maintaining the Conversation Simulator Steam page. This document maps to
> the detail docs, defines the launch runbook, and owns the support triage
> routing that applies after public release.
>
> **Audience:** Publishing team, platform team, Outright Mental staff, and
> any contractor brought in to help with launch or support operations.
>
> **Scope:** Steam store page setup, free product configuration, asset
> production status, compliance sign-off, launch-day operations, and
> post-launch support triage. For SteamPipe build and depot operations see
> [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md).

---

## Document map

| Topic | Authoritative document |
|-------|------------------------|
| Store copy (short desc, long desc, feature bullets, system requirements) | [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) |
| Store assets (capsules, screenshots, trailer brief) | [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) |
| Free product and depot registration | [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) |
| Risk register and compliance checklists (SR-01 through SR-09) | [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) |
| Depot contents and exclusions | [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md) |
| SteamPipe build, CI deploy, and troubleshooting | [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) |
| Steam API integration and fallback behaviour | [`docs/STEAM_INTEGRATION.md`](../docs/STEAM_INTEGRATION.md) |
| macOS signing and notarisation | [`publishing/MACOS_SIGNING_AND_NOTARIZATION.md`](MACOS_SIGNING_AND_NOTARIZATION.md) |
| Windows Authenticode signing | [`publishing/WINDOWS_CODE_SIGNING.md`](WINDOWS_CODE_SIGNING.md) |
| Issue triage flow | [`docs/steam-triage.md`](../docs/steam-triage.md) |
| Release gates and MVP scope | [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) |
| Release principles and release train | [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) |

---

## Free product configuration

Conversation Simulator is a **free-to-play** title on Steam. This section
summarises the store-page and partner-portal settings that enforce that
commitment; the checklist item numbers refer to
[`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md).

### Key settings

| Setting | Required value |
|---------|---------------|
| App type | `Game` |
| Base price | `Free to Play` |
| Paid package | None — do not create |
| DLC or microtransaction package | None — do not create |
| Release state at registration | `Coming Soon` |

### Free-forever invariants

- No base purchase price is set now or in the future without an explicit
  Outright Mental decision recorded in a new document.
- No premium content tier or content unlock exists in any release branch.
- The free default package (created by Valve automatically for free-to-play
  apps) contains all three platform depots.
- All store copy, trailers, and screenshots must accurately represent the
  free nature of the product (risk SP-05 in the compliance register).

See [`publishing/STEAM_STORE_PAGE.md` — Free edition wording](STEAM_STORE_PAGE.md#free-edition-wording)
for the canonical approved copy to use wherever the free nature must be stated.

---

## Asset status and production schedule

Assets are tracked in detail in [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md).
This table shows the current status at a glance.

| Asset | Size spec | Status | Blocking stage |
|-------|-----------|--------|---------------|
| Header capsule | 460 × 215 px | Not started | Stage 3 (private beta) |
| Small capsule | 231 × 87 px | Not started | Stage 3 |
| Library capsule | 600 × 900 px | Not started | Stage 3 |
| Main capsule (library hero) | 3840 × 1240 px | Not started | Stage 4 (public release) |
| Page background | 1438 × 810 px (optional) | Not started | Stage 4 |
| Screenshots (minimum 5) | 1920 × 1080 px | Placeholder SVGs exist | Stage 3 — replace with real screenshots |
| Gameplay trailer | MP4, H.264, 30–120 s | Not started | Stage 4 |
| Achievement icons | 64 × 64 px and 32 × 32 px per achievement (×5) | Not started | Stage 4 |

All assets must be reviewed by Outright Mental before upload. See the sign-off
table in [`publishing/STEAM_STORE_PAGE.md` — Sign-off](STEAM_STORE_PAGE.md#sign-off)
for the approval workflow.

### Content constraints (all assets)

- No real human faces or voices.
- No sensitive data (transcripts, real names, credentials).
- All NPCs shown are fictional characters defined in official packs.
- UI shown in screenshots must match the current release build — update assets
  with each milestone that changes the UI meaningfully.

---

## Compliance sign-off

The compliance register in
[`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md)
tracks every risk that can block the Steam release. The status column in that
register is the single source of truth for whether a risk is open or closed.

### Compliance gates by stage

| Stage | Required compliance status |
|-------|--------------------------|
| Stage 2 — packaged desktop alpha | All privacy risks (PR-01, PR-02, PR-03) MITIGATED |
| Stage 3 — Steam private beta | All release-blocking risks MITIGATED or ACCEPTED; SR-01 through SR-08 passed (including SR-08 depot audit) and the SR-09 private beta sign-off completed |
| Stage 4 — public free release | All Stage 4 gates (G4-01 through G4-05 in [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md)) met; SR-08 depot audit re-run clean on the launch build |

Run the store-page review checklist in
[`publishing/STEAM_STORE_PAGE.md` — Store page review checklist](STEAM_STORE_PAGE.md#store-page-review-checklist)
before submitting to Valve.

---

## Launch operations

### Pre-launch checklist (Stage 4 gate)

Complete these steps in the order listed. Do not set the `default` branch live
until every item is checked.

#### Build and deployment

- [ ] The release build for the launch tag is signed and notarised on all three
      platforms (see signing docs in this folder).
- [ ] The depot audit passes for all three platform depots — exit code 0 from
      `./scripts/depot-audit.sh` on each `steam-content/<platform>` directory.
- [ ] The Steam deploy workflow has run successfully for the launch tag with
      `set_live_branch` left empty (staged build, not yet live).
- [ ] The staged build was verified in the Steamworks partner portal: build
      appears in the App Admin → Builds section with all three depots.

#### Store page

- [ ] All store copy (short description, long description, feature bullets,
      system requirements) has been reviewed and matches the text in
      [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md).
- [ ] At least five screenshots uploaded (including at least three that show
      actual in-app gameplay from the current build).
- [ ] Gameplay trailer uploaded and approved.
- [ ] All capsule art uploaded: header, small, library, main.
- [ ] Genres and tags set correctly (primary: Simulation; secondary: Casual).
- [ ] IARC questionnaire complete; content descriptors applied (Mild Language only).
- [ ] Store page has been submitted to Valve and received approval.

#### Platform and QA

- [ ] Smoke matrix from [`docs/release-checklist.md`](../docs/release-checklist.md)
      has been run and passed on Windows 10/11, macOS 13+, Linux x86-64, and
      Steam Deck.
- [ ] Steam Deck Verified tier checklist from
      [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md#steam-deck-verification-checklist)
      has been submitted to Valve and verified.
- [ ] Offline smoke test passes from the Steam-installed build (not source
      checkout) on all required platforms.

#### Legal and publishing

- [ ] Outright Mental has read and approved all store copy.
- [ ] Legal has confirmed no claims of clinical authority or regulated advice in
      any store-facing text.
- [ ] `NOTICE` file in the depot is up to date with all bundled runtime licences
      (see [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md#third-party-licence-notices-notice)).

### Launch day

1. **Set the beta branch live first** (if not already done at Stage 3):
   trigger the deploy workflow with `set_live_branch: beta`.
2. Confirm beta builds install correctly on at least one machine per platform
   via a fresh Steam install (log out, remove game, reinstall).
3. **Set the default branch live:**
   trigger the deploy workflow with `set_live_branch: default` and the launch tag.
4. Wait 10–15 minutes for Steam CDN propagation.
5. Verify the app is publicly visible on its store page and that the install
   button is active and set to `Free`.
6. Install from a fresh account (not the partner account) on each required
   platform to confirm end-to-end installation.
7. Confirm all Stage 4 gates (G4-01 through G4-05 in
   [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md)) remain satisfied on
   the shipped build, then begin the post-launch monitoring below.

### Post-launch monitoring

During the first 72 hours after public launch, monitor the following:

| Signal | Where to check | Escalation threshold |
|--------|---------------|---------------------|
| Steam review sentiment | Steamworks App Admin → Reviews | Any review mentioning unexpected network activity or privacy concern — escalate immediately |
| GitHub Steam issue queue | GitHub → Issues, filter `label:steam` | Any `severity:critical` — 24-hour response SLA |
| Crash rate | Steamworks App Admin → Stats (if crash reporting is configured in future) | Baseline comparison against private beta |
| Store refund rate | Steamworks App Admin → Financials | Not applicable (free game, no purchase price) |

See [`docs/steam-triage.md`](../docs/steam-triage.md) for the full triage
routing and SLA policy.

---

## Support triage overview

This section is an operational summary. The full triage procedure, escalation
rules, privacy handling requirements, and SLA targets are in
[`docs/steam-triage.md`](../docs/steam-triage.md).

### Issue routing at a glance

| Reporter describes | Route to |
|--------------------|----------|
| App does not launch, Steam overlay broken, controller broken, Steam Deck crash | `steam` + `platform-bug` |
| Model download fails, checksum mismatch, model not loading | `steam` + `model-install` |
| NPC gives wrong response, scoring incorrect, scenario loop broken | `steam` + `pack-bug` |
| App sent data somewhere, unexpected network activity, privacy concern | `steam` + `privacy` + `safety` — fast-path escalation to lead maintainer |
| Creator Workbench crash, pack import fails, YAML editor broken | `steam` + `creator-workbench` |

### Privacy fast-path (mandatory)

Any issue containing the words "transcripts", "sent my data", "network",
"uploaded", "privacy", or "recording" must be escalated immediately to the
lead maintainer — outside the standard triage cadence — regardless of the
filed severity label.

Never ask reporters to paste conversation transcripts in GitHub issues.
See [`docs/steam-triage.md`](../docs/steam-triage.md#privacy-handling-for-all-stages)
for the full policy.

---

## Links

- [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — canonical store copy, system requirements, genres/tags, age disclosures, store review checklist, sign-off table
- [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) — capsule art, screenshot, and trailer production briefs
- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — app identity, depot IDs, CI credentials, branch strategy, partner permissions
- [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md) — depot layout, exclusions, approved binary payload list, third-party licence notices
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register (SR-01 through SR-09, MD-04, PR-01 through PR-03)
- [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — SteamPipe concepts, CI deployment, manual upload, branch promotion, troubleshooting
- [`publishing/MACOS_SIGNING_AND_NOTARIZATION.md`](MACOS_SIGNING_AND_NOTARIZATION.md) — macOS Apple Developer ID signing and notarisation
- [`publishing/WINDOWS_CODE_SIGNING.md`](WINDOWS_CODE_SIGNING.md) — Windows Authenticode signing
- [`docs/STEAM_INTEGRATION.md`](../docs/STEAM_INTEGRATION.md) — Steam API bridge, Steam Cloud, achievements/stats/rich presence, fallback
- [`docs/steam-triage.md`](../docs/steam-triage.md) — issue triage flow, SLA targets, privacy handling
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — feature requirements and pass/fail release gates
- [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — release principles and release train
- [`docs/release-checklist.md`](../docs/release-checklist.md) — platform smoke matrix
