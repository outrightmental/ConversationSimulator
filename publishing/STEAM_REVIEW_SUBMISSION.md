<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Review Submission Runbook

> **Purpose:** Step-by-step instructions for preparing and submitting
> Conversation Simulator to Valve for store review. Covers all Steamworks portal
> configuration that must be complete before submission: store page, assets,
> system requirements, depots, packages, pricing and DLC settings, content survey
> (IARC), and release date settings.
>
> **Audience:** Platform team member or Outright Mental staff with Steamworks
> partner portal Developer access. The account holder must approve store copy and
> content ratings before submission.
>
> **Prerequisite:** All Stage 4 release gates in
> [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) and all compliance
> checklist items SR-01 through SR-09 in
> [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md)
> must be complete before proceeding.

---

## Pre-submission gate check

Confirm **all** of the following before opening the Steamworks submission form.
No single item may be skipped.

| Gate | Reference | Status |
|------|-----------|--------|
| G4-01: Valve store page approval pending (this runbook completes this gate) | [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) | Proceed |
| G4-02: Steam Deck Verified tier submitted to Valve | [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) | |
| G4-03: Full release checklist run and passed on all four platforms | [`docs/release-checklist.md`](../docs/release-checklist.md) | |
| G4-04: Store page accuracy confirmed (no therapy/diagnosis/legal claims; no implied marketplace) | [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) | |
| G4-05: Voice smoke test on all platforms passes | [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) | |
| SR-09: Private beta sign-off complete (≥5 testers, all SR-01–SR-08 items passed) | [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) | |
| Beta verification report signed off for the launch build | [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md) | |
| All release-blocking risks MITIGATED, ACCEPTED, or DEFERRED | [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) | |
| Launch build staged in Steamworks (not yet live on `default`) | [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) | |

---

## 1. Store page copy

Navigate to **Steamworks App Admin → Store Page → Basic Info**.

### 1.1 App name and developer fields

- [ ] App name: `Conversation Simulator` (no version suffix).
- [ ] Developer field: `Outright Mental`.
- [ ] Publisher field: `Outright Mental`.
- [ ] Franchise field: leave empty.

### 1.2 Short description

Enter the approved short description exactly as written in
[`publishing/STEAM_STORE_PAGE.md` — Short description](STEAM_STORE_PAGE.md#short-description).
Limit is 300 characters. Do not truncate or paraphrase the approved copy.

- [ ] Short description entered, ≤ 300 characters.
- [ ] No language claiming therapy, diagnosis, or legal advice.
- [ ] No implied in-app marketplace or microtransactions.

### 1.3 Long description

Enter the approved HTML long description from
[`publishing/STEAM_STORE_PAGE.md` — Long description](STEAM_STORE_PAGE.md#long-description)
using the Steamworks rich text editor.

- [ ] Long description entered in HTML format.
- [ ] All section headers, bullet lists, and privacy statement text preserved.
- [ ] Pricing and open-source wording block included verbatim.
- [ ] Outright Mental publisher and pricing statement ($9.99, one-time) included.
- [ ] Store page reviewed in Steamworks preview mode for formatting errors.

### 1.4 System requirements

Enter minimum and recommended system requirements exactly as specified in
[`publishing/STEAM_STORE_PAGE.md` — System requirements](STEAM_STORE_PAGE.md#system-requirements).

**Windows:**

- [ ] Minimum: OS, CPU, RAM, storage, and notes entered.
- [ ] Recommended: OS, CPU, RAM, storage, and notes entered.

**macOS:**

- [ ] Minimum: OS version, CPU, RAM, storage, and Apple Silicon note entered.
- [ ] Recommended: OS version, CPU, RAM, storage entered.

**Linux / Steam Deck:**

- [ ] Minimum: OS/glibc version, CPU, RAM, storage entered.
- [ ] Recommended: OS, CPU, RAM, storage entered.
- [ ] Steam Deck note about USB microphone requirement entered.

### 1.5 Genres and tags

- [ ] Primary genre set to: **Simulation**.
- [ ] Secondary genre set to: **Casual**.
- [ ] User-defined tags applied: `Simulation`, `Casual`, `Education`,
      `Singleplayer`, `Local Only` (or nearest available equivalent).
- [ ] No genres or tags imply multiplayer or online features.

### 1.6 Languages

- [ ] Supported languages set to English (interface, full audio, subtitles).
- [ ] Do not claim support for additional languages unless the pack content and
      UI have been verified in those languages for the launch build.

### 1.7 Age disclosures and content warnings

Enter the age disclosure and content warning text from
[`publishing/STEAM_STORE_PAGE.md` — Age and content disclosures](STEAM_STORE_PAGE.md#age-and-content-disclosures).

- [ ] Age disclosure text entered in the appropriate Steamworks field.
- [ ] Content warning text entered.
- [ ] No content is rated more restrictively than the approved copy warrants.

---

## 2. Store assets

Navigate to **Steamworks App Admin → Store Page → Graphical Assets**.

All assets must have been reviewed and approved by Outright Mental before upload.
Specifications for each asset are in
[`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md).

### 2.1 Capsule art (required for submission)

- [ ] Header capsule (460 × 215 px) uploaded. No blurry upscale; no real human faces.
- [ ] Small capsule (231 × 87 px) uploaded.
- [ ] Library capsule (600 × 900 px) uploaded.
- [ ] Main capsule / library hero (3840 × 1240 px) uploaded.

### 2.2 Screenshots (minimum 5 required)

- [ ] At least 5 screenshots uploaded at 1920 × 1080 px.
- [ ] At least 3 of the 5 screenshots show actual in-app gameplay from the current launch build (not an earlier alpha).
- [ ] Screenshots do not show real player data, real transcripts, or real names.
- [ ] Screenshots do not show placeholder or development UI elements.
- [ ] All NPCs visible in screenshots are fictional characters from official packs.

### 2.3 Gameplay trailer

- [ ] Gameplay trailer uploaded (MP4, H.264, 30–120 seconds).
- [ ] Trailer reviewed and approved by Outright Mental.
- [ ] Trailer audio does not contain real player voice recordings.
- [ ] Trailer does not imply features not present in the launch build.

### 2.4 Page background (optional)

- [ ] If a background is uploaded, it is 1438 × 810 px and approved by Outright Mental.

### 2.5 Achievement icons

- [ ] Achievement icons (64 × 64 px and 32 × 32 px, one pair per achievement)
      uploaded for all five achievements defined in
      [`docs/steam-achievements-stats-rich-presence.md`](../docs/steam-achievements-stats-rich-presence.md).

---

## 3. Pricing and DLC configuration

Navigate to **Steamworks App Admin → Pricing & Availability**.

- [ ] Base price is set to **$9.99 USD** — a one-time purchase, **not** `Free to
      Play`. A numeric price appears on the store page.
- [ ] Regional pricing is generated from the USD base price and reviewed: Steam's
      suggested regional prices are applied (or intentionally overridden) for all
      territories, with no missing, zero, or unconverted-currency regions.
- [ ] A single paid base package exists under this App ID, priced at $9.99 USD.
- [ ] Premium scenario-pack DLC, if launching alongside the base app, is listed as
      separate Steam DLC — each with its own Steam App ID and its own price — per
      [`docs/DLC_MODEL.md`](../docs/DLC_MODEL.md). If no DLC ships in this
      submission, no DLC package appears under this App ID yet.
- [ ] The paid base package is visible in **Steamworks → Packages** and contains
      all three platform depots: Windows, macOS, and Linux.
- [ ] The base package depots exclude all premium DLC content (DLC ships from its
      own separate content depots and App IDs).
- [ ] Confirm the base app is configured with its $9.99 USD price — the "Set up
      pricing" step is complete and the app is **not** left as Free to Play.

---

## 4. Depots and packages

Navigate to **Steamworks App Admin → SteamPipe → Depots**.

- [ ] Three depots exist: Windows x86-64, macOS (Universal), Linux x86-64 / SteamOS.
- [ ] Depot IDs match the values in
      [`publishing/STEAM_APP_REGISTRATION.md` — Identifiers](STEAM_APP_REGISTRATION.md#identifiers)
      and the GitHub repository variables `STEAM_DEPOT_WINDOWS_ID`,
      `STEAM_DEPOT_MACOS_ID`, `STEAM_DEPOT_LINUX_ID`.
- [ ] Each depot's platform filter is set correctly (Windows / macOS / Linux).
- [ ] No fourth depot has been created (no shared-data depot in v1).
- [ ] The launch build is staged and visible in **App Admin → Builds** with all
      three depots present. The staged build must not yet be set live on
      `default`.
- [ ] Depot audit has been run on the staged build: all three platform directories
      passed `scripts/depot-audit.sh` with exit code 0 (SR-08).

Navigate to **Steamworks → Packages**.

- [ ] The paid base package contains all three platform depots.
- [ ] Base package ID is recorded in
      [`publishing/STEAM_APP_REGISTRATION.md` — Identifiers](STEAM_APP_REGISTRATION.md#identifiers).

---

## 5. Steam Cloud

Navigate to **Steamworks App Admin → Steam Cloud**.

- [ ] Byte quota per user: 64 KB.
- [ ] File count per user: 5.
- [ ] Include pattern `steam_cloud_settings.json` (non-recursive) is configured.
- [ ] All eight exclusion patterns are configured as specified in
      [`publishing/STEAM_APP_REGISTRATION.md` — Steam Cloud configuration](STEAM_APP_REGISTRATION.md#steam-cloud-configuration).
- [ ] Steam Cloud verification (B.11) in
      [`docs/release-checklist.md`](../docs/release-checklist.md) has been completed on the staged build.

---

## 6. Content survey (IARC questionnaire)

Navigate to **Steamworks App Admin → Store Page → Content Survey**.

The IARC (International Age Rating Coalition) questionnaire determines the age
rating labels shown on the store page. Answers must accurately reflect the
content of the launch build. Do not understate content to obtain a more
favourable rating.

### 6.1 Questionnaire answers

Answer all IARC questions based on the content present in the v1 launch build:

| Question category | Answer for Conversation Simulator |
|-------------------|-----------------------------------|
| Violence | **No** — no combat, no graphic violence, no blood. |
| Language | **Mild language** — NPC dialogue may contain occasional mild profanity in authentic conversational contexts (e.g. a frustrated manager NPC). No severe profanity in official packs. |
| Sexual content | **None** — no sexual or romantic content. Dating-confidence scenario content is social and conversational only, capped at PG-13, and ships in a later pack. |
| Fear / horror | **None** — no horror elements. |
| Gambling | **None** — no gambling, no simulated gambling. |
| Drug / alcohol | **None** — no drug or alcohol depictions in official packs. |
| Online features | **None** — no online multiplayer, no user-generated content submission, no online purchases. The app runs offline. |
| In-app purchases | **No in-app purchase UI** — there is no in-app payment UI or Steam Wallet microtransaction system inside the app. The base app is a one-time $9.99 USD purchase and premium scenario-pack DLC is sold separately through Steam's DLC storefront, so IARC **real-money purchases is answered Yes** (paid base app + optional DLC). |
| User interaction | **None** — no user-to-user interaction; all AI characters are local. |

### 6.2 Expected IARC rating

Because the official packs contain mild language for workplace and social
conflict scenarios, the answers above are expected to produce a rating in the
**ESRB E10+ / Teen** and **PEGI 7 / 12** range (or the equivalent regional
ratings) — see the expected rating outcome table in
[`publishing/STEAM_STORE_PAGE.md` — IARC / Steam content questionnaire answers](STEAM_STORE_PAGE.md#iarc--steam-content-questionnaire-answers).
An 18+ age gate is **not** expected and must not be requested. If Valve assigns
a rating higher than **PEGI 12 / ESRB T**, review whether the answers match the
actual content and consult Outright Mental before accepting the rating.

- [ ] IARC questionnaire completed.
- [ ] Resulting content descriptors reviewed and approved by Outright Mental.
- [ ] Content descriptors applied to the store page (displayed below the app title).
- [ ] Rating labels do not conflict with the approved store page copy.

---

## 7. Release date settings

Navigate to **Steamworks App Admin → Store Page → Basic Info**.

- [ ] Release date field is set. Options:
  - Use a specific date (e.g. `16 July 2026`) if the date has been confirmed by
    Outright Mental and Valve approval is expected before that date.
  - Use `Coming Soon` until the exact date is confirmed with Valve.
  - Use `Q3 2026` (or the appropriate quarter) if the month is known but the day
    is not confirmed.
- [ ] The release date shown on the store page has been approved by Outright Mental.
- [ ] If `Coming Soon` is showing, confirm the release date setting will be updated
      to the exact date once the Valve review is approved.
- [ ] Release state is set to `Released` in Steamworks only **after** the store
      page has received Valve approval and the `default` branch is set live.

> **Note:** Setting the release date to a specific date before Valve approval
> creates a commitment that may not be honoured if review takes longer than
> expected. Coordinate with Outright Mental before committing to a date.

---

## 8. Achievements and stats

Navigate to **Steamworks App Admin → Stats & Achievements**.

- [ ] Five achievements defined as specified in
      [`docs/steam-achievements-stats-rich-presence.md`](../docs/steam-achievements-stats-rich-presence.md).
- [ ] Achievement icons uploaded (64 × 64 px and 32 × 32 px for each).
- [ ] Achievement names and descriptions match approved copy.
- [ ] Stats API data verified working on the beta build (achievement unlock tested in-game).

---

## 9. Store page review checklist (pre-submission)

Run the full store page review checklist in
[`publishing/STEAM_STORE_PAGE.md` — Store page review checklist](STEAM_STORE_PAGE.md#store-page-review-checklist)
before submitting to Valve.

- [ ] Store page review checklist in `STEAM_STORE_PAGE.md` completed.
- [ ] All sign-off rows in the sign-off table at the bottom of `STEAM_STORE_PAGE.md`
      are completed with reviewer name and date.

---

## 10. Submit for Valve review

Navigate to **Steamworks App Admin → Publish → Review and Publish**.

- [ ] All sections above are complete. No placeholder copy, missing assets, or
      unanswered content survey questions remain.
- [ ] Click **Submit for Review**. Valve will review within 3–5 business days
      (typical for first-time submissions; may take longer).
- [ ] Record the submission date in the sign-off block below.
- [ ] Notify Outright Mental that the app has been submitted.

### What to expect from Valve

| Outcome | Action |
|---------|--------|
| Valve approves the store page | Proceed to the launch-day runbook in [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md). |
| Valve requests changes to store copy | Update the copy in `STEAM_STORE_PAGE.md` (with Outright Mental approval), apply the changes in Steamworks, and resubmit. |
| Valve requests changes to assets | Produce updated assets per `STEAM_ASSETS_SPEC.md`, apply, and resubmit. |
| Valve rejects for content policy reasons | Log the rejection as risk SP-01 progressing in the compliance register; engage with Valve developer support; do not resubmit without resolving the stated concern. |

---

## Submission sign-off

| Item | Owner | Date | Notes |
|------|-------|------|-------|
| Pre-submission gate check complete | | | |
| Store copy entered and approved | | | |
| All capsule assets uploaded | | | |
| All screenshots uploaded | | | |
| Gameplay trailer uploaded | | | |
| System requirements entered | | | |
| Genres and tags confirmed | | | |
| Pricing and DLC configuration verified | | | |
| Depots and packages confirmed | | | |
| Steam Cloud configuration confirmed | | | |
| IARC content survey complete | | | |
| Release date setting confirmed | | | |
| Achievements configured | | | |
| Store page review checklist complete | | | |
| Submitted to Valve for review | | | |

---

## Links

- [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — canonical store copy and store page review checklist
- [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) — capsule art, screenshots, and trailer brief
- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — depot IDs, package configuration, Steam Cloud
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register (SR-09, SP-01)
- [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md) — what to do after Valve approves
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — Stage 4 gate criteria
- [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md) — signed beta verification report (SR-09 deliverable)
- [`docs/steam-achievements-stats-rich-presence.md`](../docs/steam-achievements-stats-rich-presence.md) — achievements and stats portal setup
