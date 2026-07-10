<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam App Registration

> **Purpose:** Record the Steamworks partner portal configuration for the free
> Outright Mental-sponsored edition of Conversation Simulator. This document is
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

### Free-to-play configuration

- [ ] Under **Pricing & Availability**, set the **Base price** to `Free to Play`.
- [ ] Do **not** set a purchase price or create a paid package. The base package is always free.
- [ ] Verify the app does **not** appear in the "Set up pricing" wizard with a price — it must be marked Free on Steam from the first configuration step.
- [ ] Confirm no DLC or microtransaction package is created during initial setup.
- [ ] Verify the free default package (automatically created by Valve for free-to-play apps) contains all three platform depots once they are created.

The Steam release is and will remain free to download and play. There is no
base purchase price, no subscription, and no pay-to-unlock core content.
See [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — Free on Steam,
sponsored by Outright Mental.

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
player owns. For a free-to-play title, Valve automatically creates a **free
default package** containing all depots.

- [ ] Verify the automatic free package exists and contains all three depots.
- [ ] Do **not** create a paid package or a retail activation package.
- [ ] Record the free package ID (assigned by Valve) in the [Identifiers](#identifiers) table.

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

| Identifier | GitHub repository variable | Description |
|-----------|---------------------------|-------------|
| App ID | `vars.STEAM_APP_ID` | Assigned by Valve at registration. Seven-digit format, e.g. `1234567`. |
| Windows depot ID | `vars.STEAM_DEPOT_WINDOWS_ID` | First depot created; Windows x86-64 content. Valve assigns depot IDs sequentially after the App ID. |
| macOS depot ID | `vars.STEAM_DEPOT_MACOS_ID` | Second depot created; macOS (Apple Silicon + Intel) content. |
| Linux/SteamOS depot ID | `vars.STEAM_DEPOT_LINUX_ID` | Third depot created; Linux x86-64 and Steam Deck content. |
| Free package ID | *(record here after registration)* | Automatically created by Valve for free-to-play apps. Not referenced in CI. |

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
   target release tag and, optionally, the `set_live_branch` input set to
   `beta` or `default`.
2. If `set_live_branch` is left empty, the build is staged in Steamworks but no
   branch is made live — use this for a dry run or when manual sign-off is
   required before going live.
3. For `default` (public release): the Stage 4 gate in
   [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) must be fully passed
   before this branch is set live.

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
Steamworks → Packages → [Free package] → Generate Steam Product Codes.

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
