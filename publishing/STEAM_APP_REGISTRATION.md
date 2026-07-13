<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam App Registration

> **Purpose:** Record the Steamworks partner portal configuration for the
> Outright Mental-published edition of Conversation Simulator. This document is
> the authoritative reference for app identity, depot layout, package
> configuration, branch strategy, and the location of CI credentials.
>
> **Audience:** Platform team members and Outright Mental staff with Steamworks
> partner portal access.
>
> **Sensitive data:** No secret credentials appear in this document. App IDs and
> depot IDs are non-secret identifiers assigned by Valve. Steam partner
> credentials are stored as GitHub Actions secrets — see
> [CI credentials](#ci-credentials).

---

## Publisher and developer identity

| Field | Value |
|-------|-------|
| **Partner account** | Outright Mental |
| **Publisher display name** | Outright Mental |
| **Developer display name** | Outright Mental |
| **Partner portal** | https://partner.steamgames.com/ |

The app is registered under the Outright Mental partner account. All Steamworks
permissions are managed through that account. Team members who need partner
access must be granted it by the account holder — see
[Partner permissions](#partner-permissions).

---

## App registration checklist

Steps to complete in the Steamworks partner portal when registering the app.
Mark each item when done and record the assigned identifiers in the
[Identifiers](#identifiers) table below.

### Basic setup

- [ ] Register new app under the Outright Mental partner account.
- [ ] Set **App type** to `Game`.
- [ ] Set **Developer** to `Outright Mental`.
- [ ] Set **Publisher** to `Outright Mental`.
- [ ] Enter the store page title: `Conversation Simulator`.
- [ ] Record the assigned **App ID** in the [Identifiers](#identifiers) table and set it as the `STEAM_APP_ID` repository variable.

### Pricing and DLC configuration

- [ ] Under **Pricing & Availability**, set the **Base price** to `$9.99 USD` — a normal paid app, **not** `Free to Play`.
- [ ] Create a normal **paid base package** and add all three platform depots to it once they are created (see [Packages](#packages)). Do **not** rely on Valve's auto-created free default package — that exists only for Free to Play titles.
- [ ] Confirm the app appears in the "Set up pricing" wizard as a paid title with the `$9.99` base price.
- [ ] Keep premium scenario-pack content **out** of the base package and its depots — DLC ships as separate DLC apps (see [Premium scenario-pack DLC](#premium-scenario-pack-dlc)).
- [ ] Record the paid base package ID in the [Identifiers](#identifiers) table once it is assigned.

The Steam release is a one-time `$9.99` purchase of the ready-to-run,
code-signed, notarised, auto-updating package — not a subscription. The full
source stays open source and free to build from GitHub; the paid Steam package
funds development and never relocks anything that ships free.
See [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — published by Outright
Mental.

#### Premium scenario-pack DLC

Premium scenario packs are sold as paid Steam DLC. Each pack is a separate Steam
application associated with this base app. Configure DLC only after the base app
is registered.

- [ ] Register each premium pack as its own **DLC app** under the base app, and record the assigned **DLC App ID**.
- [ ] Create one **content depot** per DLC app and associate it with the base app.
- [ ] Set an individual **price** for each DLC under **Pricing & Availability**.
- [ ] Build and upload each DLC's content from the **private** `ConversationSimulator-DLC` repository — never from this public repository. See [`docs/DLC_MODEL.md`](../docs/DLC_MODEL.md).
- [ ] Record every DLC App ID in the [Identifiers](#identifiers) table and mirror the non-secret DLC App IDs into the `STEAM_DLC_APP_IDS` repository variable.

DLC ownership is checked at runtime through Steamworks (`BIsDlcInstalled`); the
app unlocks only the packs a player owns. DLC content is authored in the private
repository and is not part of this open-source repository.

### Depots

Create exactly three depots — one per supported platform. Do not create a shared
data depot for the MVP. See [Depot layout](#depot-layout) for rationale and
content rules.

- [ ] Create depot **Windows x86-64** — record its ID as `STEAM_DEPOT_WINDOWS_ID`.
- [ ] Create depot **macOS (Universal)** — record its ID as `STEAM_DEPOT_MACOS_ID`.
- [ ] Create depot **Linux x86-64 / SteamOS** — record its ID as `STEAM_DEPOT_LINUX_ID`.
- [ ] Set repository variables `STEAM_DEPOT_WINDOWS_ID`, `STEAM_DEPOT_MACOS_ID`, and `STEAM_DEPOT_LINUX_ID` to the assigned depot IDs.

### Packages

A **package** in Steamworks bundles one or more depots and determines what a
player owns. For this paid title, create a normal **paid base package**
containing all three platform depots. Valve's auto-created free default package
does not apply — that mechanism exists only for Free to Play titles.

- [ ] Create a paid base package and add all three platform depots to it.
- [ ] Set the base package price to `$9.99 USD`.
- [ ] Keep DLC content out of the base package — premium scenario packs ship as separate DLC depots (see [Premium scenario-pack DLC](#premium-scenario-pack-dlc)).
- [ ] Record the paid base package ID (assigned by Valve) in the [Identifiers](#identifiers) table.

### Release state

- [ ] Set the **Release State** to `Coming Soon` during initial setup.
- [ ] Do **not** set the app live until Stage 3 (private beta) criteria are met. See [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) Stage 3 gate.

---

## Identifiers

These identifiers are assigned by Valve when the app is registered. They are
not secret — they appear in Steam store URLs and are visible to anyone with
access to the app. They are stored as GitHub repository **variables** (not
secrets) so that CI workflows can reference them without hardcoding values in
source files.

| Identifier | Value | GitHub repository variable | Description |
|-----------|-------|---------------------------|-------------|
| App ID | **4963030** | `vars.STEAM_APP_ID` | Assigned by Valve at registration. |
| Windows depot ID | *(assigned in partner portal — set as repo variable)* | `vars.STEAM_DEPOT_WINDOWS_ID` | First depot created; Windows x86-64 content. Valve assigns depot IDs sequentially after the App ID. |
| macOS depot ID | *(assigned in partner portal — set as repo variable)* | `vars.STEAM_DEPOT_MACOS_ID` | Second depot created; macOS (Apple Silicon + Intel) content. |
| Linux/SteamOS depot ID | *(assigned in partner portal — set as repo variable)* | `vars.STEAM_DEPOT_LINUX_ID` | Third depot created; Linux x86-64 and Steam Deck content. |
| Base package ID | *(record here after registration)* | *(not referenced in CI)* | The paid base package that grants the base app and its three platform depots. |
| DLC App IDs | *(record here per pack)* | `vars.STEAM_DLC_APP_IDS` | One Steam App ID per premium scenario-pack DLC (comma-separated). Non-secret. DLC content is built and uploaded from the private `ConversationSimulator-DLC` repo — see [`docs/DLC_MODEL.md`](../docs/DLC_MODEL.md). |

**To set a repository variable:** GitHub → repository Settings → Secrets and
variables → Actions → Variables tab → New repository variable.

---

## Depot layout

The MVP uses three depots — one per target platform. Each depot contains only
the binaries and resources for that platform.

| Depot variable | Platform | Content |
|----------------|----------|---------|
| `STEAM_DEPOT_WINDOWS_ID` | Windows 10 / 11 (x86-64) | Tauri application directory; no NSIS installer |
| `STEAM_DEPOT_MACOS_ID` | macOS 13+ (Apple Silicon + Intel) | Tauri `.app` bundle |
| `STEAM_DEPOT_LINUX_ID` | Linux x86-64 + SteamOS 3.x | Tauri binary and resources |

**No shared data depot in v1.** Scenario packs and model weights are distributed
separately:

- **Official packs** are bundled with the application binary and included in
  each platform depot.
- **Model weights** are never placed in any depot — they are downloaded
  explicitly through the Model Manager at the player's request. See risk MD-04
  in [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

### Depot content exclusions

The following file types must **never** appear in any Steam depot:

| Pattern | Reason |
|---------|--------|
| `*.gguf`, `*.bin`, `*.safetensors` | Model weight files — distribution via Steam would violate most model licenses and add gigabytes to the installer (see MD-04) |
| `*.pdb` | Windows debug symbols — not useful to players and may expose internal symbol names |
| `*.dSYM/` | macOS debug symbol bundles |
| `~/.convsim/` | Player data directories — must never be included in a depot |

These exclusions are enforced in the SteamPipe depot VDF templates:

- [`steam/depot_windows.vdf.tpl`](../steam/depot_windows.vdf.tpl)
- [`steam/depot_macos.vdf.tpl`](../steam/depot_macos.vdf.tpl)
- [`steam/depot_linux.vdf.tpl`](../steam/depot_linux.vdf.tpl)

A depot content audit is required before each Steam build submission — see
checklist item SR-08 in
[`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

---

## Steam Cloud configuration

Steam Cloud must be configured in the Steamworks partner portal before Stage 3
(private beta).  The configuration enforces the local-first promise by syncing
**only** the non-sensitive cloud settings file and excluding all directories
that contain private user data.

### What to configure

Navigate to **Steamworks App Admin → Steam Cloud** for the app.

#### Quota

| Setting | Value |
|---------|-------|
| Byte quota per user | 64 KB (the cloud settings file is under 1 KB; 64 KB provides ample headroom for future non-sensitive fields) |
| File count per user | 5 |

#### Root paths (per platform)

These root paths tell Steam Cloud where to look for files to sync.  Set them
to the same platform-specific data root that `convsim_core.paths.platform_data_root()`
resolves to, or use the `{Steam}` variable if Valve's remote storage paths match
the platform conventions below.

| Platform | Steamworks root path |
|----------|---------------------|
| Windows | `{localappdata}\outrightmental\convsim` |
| macOS | `{userhome}/Library/Application Support/com.outrightmental.convsim` |
| Linux / Steam Deck | `{userhome}/.local/share/convsim` |

#### Sync pattern — include (one entry)

| Pattern | Recursive | Description |
|---------|-----------|-------------|
| `steam_cloud_settings.json` | No | The only file Steam Cloud is allowed to sync |

#### Sync pattern — exclude (one entry per subdirectory)

These exclusions prevent Steam Cloud from touching any subdirectory.  The
`.nosteamcloudpath` markers placed by the app lifespan hook serve as an
additional defence, but the Steamworks portal exclusions are the authoritative
control.

| Pattern | Recursive | Reason |
|---------|-----------|--------|
| `db\*` / `db/*` | Yes | Conversation transcripts, session history, prompts |
| `logs\*` / `logs/*` | Yes | Application and service logs |
| `models\*` / `models/*` | Yes | LLM / STT / TTS model weight files |
| `packs\*` / `packs/*` | Yes | User-imported scenario packs (may be private) |
| `exports\*` / `exports/*` | Yes | Exported session JSON files |
| `cache\*` / `cache/*` | Yes | TTS audio cache and download cache |
| `crashes\*` / `crashes/*` | Yes | Crash report bundles |
| `data\*` / `data/*` | Yes | Miscellaneous application data directory |

> **Important:** Add both Windows (`\`) and POSIX (`/`) path separator variants
> if the Steamworks portal requires per-platform wildcard syntax.

### Verification

After configuring Steam Cloud in the Steamworks portal, verify the setup using
the **B.11 Steam Cloud sync verification** steps in
[`docs/release-checklist.md`](../docs/release-checklist.md).

---

## Branch strategy

Steam uses **branches** to control which build a player's Steam client
downloads. The following branches are used for Conversation Simulator.

| Branch | Audience | Set live by |
|--------|----------|------------|
| `default` | All public players | Platform team, only after Stage 4 gate passes |
| `beta` | Private beta testers (Stage 3) | Platform team, after Stage 3 gate passes |

**Do not create additional branches** without updating this document and the
deploy workflow.

### Setting a branch live

1. Trigger the deploy workflow (`.github/workflows/steam-deploy.yml`) with the
   target release tag. The `set_live_branch` input defaults to `beta` — the
   correct choice for a Stage 3 private beta upload.
2. Leave `set_live_branch` empty to stage the build without making any branch
   live — use this for a dry run or when manual sign-off is required first.
3. For `default` (public release): the Stage 4 gate in
   [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) must be fully passed
   before this branch is set live.

### Private beta verification procedure

After the deploy workflow completes with `set_live_branch = beta`, verify the
deployment before distributing Steam keys to testers.

**Step 1 — Confirm the build is staged**

Open the Steamworks partner portal → **App Admin → Builds**.

- The new build appears in the build list with the correct description.
- The build row shows three depot file counts (one per platform).
- The `beta` column shows `SET LIVE` next to the new build.

**Step 2 — Verify build version**

Click the build row → **View Manifest**. Confirm the version field matches the
GitHub release tag (e.g. `0.1.0` for tag `v0.1.0`).

**Step 3 — Confirm Stage 3 gate criteria**

Before sharing keys with testers, all Stage 3 gate criteria in
[`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) must be satisfied:

| Gate ID | Check |
|---------|-------|
| G3-01 | macOS `.app` is notarised; Windows installer is Authenticode-signed |
| G3-02 | Depot audit passed in CI — no model-weight files in any depot |
| G3-04 | All release-blocking risks in `STEAM_COMPLIANCE_AND_RISK_REGISTER.md` are MITIGATED, ACCEPTED, or DEFERRED |
| G3-05 | All SR-01 through SR-08 compliance checklist items are signed off |

**Step 4 — Generate beta tester keys**

Steamworks → **Packages → [paid base package] → Generate Steam Product Codes**.
Request one key batch per named tester group. Share keys only with named testers
— do not post them publicly.

**Step 5 — Beta session verification (G3-06)**

At least five testers (at least one on each of Windows, macOS, and Linux) must:

1. Activate the key and install via the Steam client.
2. Launch the app from the Steam Play button.
3. Complete a full text session and view the debrief screen.
4. Confirm the Steam overlay (Shift+Tab) opens without disrupting the session (G3-03).
5. Report any session-ending bugs, data-loss bugs, or privacy regressions.

Record tester sign-offs and platform coverage in [`docs/release-checklist.md`](../docs/release-checklist.md).

**Step 6 — Promote to `default` only after Stage 4 gate**

Do not trigger the deploy workflow with `set_live_branch = default` until the
full Stage 4 gate passes, including Valve review approval (G4-01) and Steam Deck
Verified tier (G4-02). See [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md).

---

## Partner permissions

Access to the Steamworks partner portal is managed through the Outright Mental
partner account.

| Role | Who | Permissions |
|------|-----|------------|
| **Account administrator** | Outright Mental account holder | Full access; manages partner permissions, financial settings, and legal agreements |
| **Developer** | Platform team members | Upload builds, manage depots, edit store page draft |
| **QA tester** | QA team, beta testers | Access private beta builds; no partner portal access |

**To add a team member:** Steamworks partner portal → Users & Permissions →
Manage Users → Add a user. Assign the Developer group. Do not assign the Admin
role to individuals who do not own the partner account.

**Beta tester access** is granted through a Steam key batch — not through
partner portal roles. Keys for Stage 3 private testers are generated in
Steamworks → Packages → [paid base package] → Generate Steam Product Codes.

---

## CI credentials

The Steam deploy workflow (`.github/workflows/steam-deploy.yml`) authenticates
to Steam using a **dedicated build account**, not the main Outright Mental
partner account. A separate account limits the blast radius of a compromised CI
credential.

### Required GitHub Actions secrets

| Secret name | Description | How to obtain |
|------------|-------------|---------------|
| `STEAM_USERNAME` | Steam username of the dedicated CI build account | Create a new Steam account for CI use; grant it Developer access in the Steamworks partner portal under Users & Permissions |
| `STEAM_CONFIG_VDF` | Base64-encoded `config.vdf` from an authenticated Steam session on the build account | Log in as the build account on a machine with Steam installed; complete the SteamGuard prompt; copy `~/.steam/steam/config/config.vdf`; encode it: `base64 -w0 ~/.steam/steam/config/config.vdf` |

**Why `STEAM_CONFIG_VDF` instead of a password:** Steam requires two-factor
authentication (SteamGuard). Storing a `config.vdf` from an already-authenticated
session bypasses the interactive 2FA prompt in headless CI environments. Treat
this file with the same confidentiality as a password — rotate it if the build
account is ever compromised.

**To set a GitHub Actions secret:** GitHub → repository Settings → Secrets and
variables → Actions → Secrets tab → New repository secret.

### Refreshing `STEAM_CONFIG_VDF`

The SteamGuard config expires after approximately one year of inactivity on the
build account. If the deploy workflow fails with a SteamGuard or authentication
error:

1. Log in as the build account on a local machine with Steam installed.
2. Complete the SteamGuard prompt.
3. Copy and re-encode the updated `config.vdf`.
4. Update the `STEAM_CONFIG_VDF` secret in GitHub.

---

## Links

- [`steam/app_build.vdf.tpl`](../steam/app_build.vdf.tpl) — SteamPipe app build VDF template
- [`steam/depot_windows.vdf.tpl`](../steam/depot_windows.vdf.tpl) — Windows depot VDF template
- [`steam/depot_macos.vdf.tpl`](../steam/depot_macos.vdf.tpl) — macOS depot VDF template
- [`steam/depot_linux.vdf.tpl`](../steam/depot_linux.vdf.tpl) — Linux/SteamOS depot VDF template
- [`.github/workflows/steam-deploy.yml`](../.github/workflows/steam-deploy.yml) — Steam deploy workflow
- [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — Release train and release principles
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — Stage gate criteria
- [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — Canonical store copy, system requirements, genres/tags, age disclosures, and store review checklist
- [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) — Capsule art, screenshot, and trailer production briefs
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — Risk register (MD-04, SR-08)
