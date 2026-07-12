<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Publishing and Deployment

> **Purpose:** End-to-end operational reference for building and uploading
> Conversation Simulator to Steam using SteamPipe. Covers concepts, depot
> configuration, CI deployment, manual fallback procedures, branch promotion,
> and troubleshooting.
>
> **Audience:** Platform team members with Steamworks partner portal access and
> write access to the `steam-release` GitHub Actions environment.
>
> **Prerequisites:** App IDs and depot IDs already registered in the Steamworks
> partner portal and set as GitHub repository variables. See
> [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) for
> the registration checklist and identifier table.

---

## SteamPipe concepts

SteamPipe is Valve's content delivery system. Understanding its object model
prevents mistakes that corrupt the live branch or leak forbidden files.

### Depots

A **depot** is the atomic unit of content Valve stores and distributes. Each
depot contains the application files for one platform. Conversation Simulator
uses exactly three depots — one per target platform:

| Depot variable | Platform | Content root |
|----------------|----------|--------------|
| `STEAM_DEPOT_WINDOWS_ID` | Windows 10 / 11 x86-64 | `steam-content/windows/` |
| `STEAM_DEPOT_MACOS_ID` | macOS 13+ (Apple Silicon + Intel) | `steam-content/macos/` |
| `STEAM_DEPOT_LINUX_ID` | Linux x86-64 + SteamOS 3.x | `steam-content/linux/` |

A depot ID is a non-secret number assigned by Valve at registration. It appears
in Steam store URLs and can be referenced in public tooling. Store depot IDs as
GitHub repository **variables** (not secrets).

What goes in each depot is defined in
[`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md).
What must never appear in any depot is enforced by both the VDF `FileExclusion`
patterns and the pre-upload audit script.

### Packages

A **package** bundles one or more depots and represents what a player "owns".
Conversation Simulator ships as a **paid app**: the base app is a one-time
**$9.99 USD** purchase, so it uses a normal **paid package** (the automatic
free default package Valve provisions for free-to-play apps does not apply).
This base package must contain all three platform depots.

For the base app: one paid package, three depots, no exceptions.

**Premium scenario-pack DLC is out of scope for this base-app pipeline.** Each
premium pack is a separate Steam DLC (its own App ID and content depot), built
and uploaded **separately** from the private `ConversationSimulator-DLC` repo
using [`steam/depot_dlc_scenariopacks.vdf.tpl`](../steam/depot_dlc_scenariopacks.vdf.tpl).
DLC content must **never** be staged into the base app depots — the depot audit
and `FileExclusion` patterns exist in part to enforce that boundary. See
[`docs/DLC_MODEL.md`](../docs/DLC_MODEL.md) and
[`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md).

### Branches

A **branch** determines which build version a player's Steam client downloads.

| Branch | Audience | Gate requirement |
|--------|----------|-----------------|
| `default` | All public players | Stage 4 gate fully passed |
| `beta` | Invited Stage 3 testers | Stage 3 gate passed |

Setting a branch live is a one-way operation that affects every player on that
branch immediately. Always stage the build without setting a branch live first
(dry run), then promote only after verification.

### VDF build scripts

SteamPipe is driven by VDF (Valve Data Format) files. The repository ships
templates in `steam/` that are filled in by `envsubst` in CI:

| Template | Purpose |
|----------|---------|
| [`steam/app_build.vdf.tpl`](../steam/app_build.vdf.tpl) | Top-level build manifest: app ID, depots to include, description, branch |
| [`steam/depot_windows.vdf.tpl`](../steam/depot_windows.vdf.tpl) | Windows depot content root and file exclusions |
| [`steam/depot_macos.vdf.tpl`](../steam/depot_macos.vdf.tpl) | macOS depot content root and file exclusions |
| [`steam/depot_linux.vdf.tpl`](../steam/depot_linux.vdf.tpl) | Linux/SteamOS depot content root and file exclusions |

Each template uses `$VARIABLE` placeholders that are substituted from
environment variables. Never commit a rendered VDF with real IDs to the
repository — the templates keep IDs out of source control, with actual values
living only in GitHub repository variables.

---

## CI deployment (primary path)

The Steam deploy workflow in
[`.github/workflows/steam-deploy.yml`](../.github/workflows/steam-deploy.yml)
is the primary and preferred deployment path. It enforces the depot audit, uses
scoped credentials, and requires a manual approval step before any secrets are
exposed.

### One-time setup

These steps are performed once and do not need to be repeated for each release.
See [`publishing/STEAM_APP_REGISTRATION.md` — CI credentials](STEAM_APP_REGISTRATION.md#ci-credentials)
for the detailed procedure to obtain each value.

**Repository variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `STEAM_APP_ID` | Valve-assigned App ID for Conversation Simulator |
| `STEAM_DEPOT_WINDOWS_ID` | Windows x86-64 depot ID |
| `STEAM_DEPOT_MACOS_ID` | macOS depot ID |
| `STEAM_DEPOT_LINUX_ID` | Linux / SteamOS depot ID |

**Repository secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Value |
|--------|-------|
| `STEAM_USERNAME` | Steam username of the dedicated CI build account |
| `STEAM_CONFIG_VDF` | Base64-encoded `config.vdf` from an authenticated Steam session on the build account |

**GitHub Actions environment:**

Create a `steam-release` environment under Settings → Environments. Add at
least one required reviewer so the workflow pauses for approval before secrets
are used. This prevents accidental or unauthorised deployments.

### Triggering a deployment

The workflow is triggered manually under Actions → Steam Deploy → Run workflow.

| Input | Required | Description |
|-------|----------|-------------|
| `release_tag` | Yes | The GitHub release tag to upload (e.g. `v0.3.0`). The release must already exist and its build artifacts must be published. |
| `build_description` | No | Human-readable description shown in Steamworks. Defaults to `Conversation Simulator <tag>`. |
| `set_live_branch` | No | **Defaults to `beta`** (Stage 3 promotion). Clear the field for a staged (dry-run) upload that sets no branch live. Use `default` only for the public release — all Stage 4 gate items must be checked first. |

### Workflow steps

1. **Resolve build description** — fills in the default description from the
   tag if `build_description` was left empty.
2. **Download release artifacts** — pulls the platform artifacts from the
   specified GitHub release using `gh release download`.
3. **Organise depot content** — copies artifacts into `steam-content/<platform>/`
   directories. macOS depots receive the `.app` bundle extracted from the
   `.app.tar.gz` artifact, not the `.dmg` installer.
4. **Audit depot content** — runs `./scripts/depot-audit.sh` against each
   `steam-content/<platform>` directory. Exits non-zero if any model weight
   file, developer artefact, secret file, debug symbol, or test fixture is
   present. The workflow fails and no upload occurs.
5. **Generate SteamPipe VDF files** — runs `envsubst` to fill in the VDF
   templates with the repository variables.
6. **Install steamcmd** — installs the Steam command-line tool on the
   ubuntu-latest runner.
7. **Restore Steam config** — decodes `STEAM_CONFIG_VDF` from base64 to
   `~/.steam/steam/config/config.vdf` to bypass the interactive SteamGuard
   prompt.
8. **Upload build to Steam** — runs `steamcmd +login ... +run_app_build ...`.
9. **Show steamcmd build output** — logs the output files regardless of success
   or failure, useful for diagnosing upload errors.

### Verifying a staged build

After a successful run with `set_live_branch` left empty:

1. Open the Steamworks partner portal → App Admin → Builds.
2. Confirm a new build appears with all three depots and the correct description.
3. Install the build on each required platform using a Steam beta key to verify
   the depot layout before promoting to any branch.

---

## Manual upload procedure (fallback)

Use the manual procedure only when CI is unavailable or when a hotfix must be
deployed outside the standard release pipeline.

### Requirements

- `steamcmd` installed locally (see [Valve docs](https://developer.valvesoftware.com/wiki/SteamCMD)).
- Steamworks credentials for the build account or a partner account member with
  Developer access.
- SteamGuard 2FA code ready (interactive prompt if `config.vdf` is not cached).

### Steps

```bash
# 1. Build and sign the release artifacts for all three platforms.
#    (See the signing docs for platform-specific steps.)

# 2. Organise artifacts into per-platform content directories.
mkdir -p steam-content/windows steam-content/macos steam-content/linux
# Copy platform files into the appropriate directories.

# 3. Run the depot audit.
./scripts/depot-audit.sh steam-content/windows
./scripts/depot-audit.sh steam-content/macos
./scripts/depot-audit.sh steam-content/linux
# If any exit with code 1, resolve violations before continuing.

# 4. Generate VDF files from templates.
export STEAM_APP_ID="<app-id>"
export STEAM_DEPOT_WINDOWS_ID="<windows-depot-id>"
export STEAM_DEPOT_MACOS_ID="<macos-depot-id>"
export STEAM_DEPOT_LINUX_ID="<linux-depot-id>"
export STEAM_BUILD_DESCRIPTION="Conversation Simulator v0.x.y (manual)"
export STEAM_SET_LIVE_BRANCH=""   # leave empty for staged upload
mkdir -p steam-build/output
envsubst < steam/app_build.vdf.tpl     > steam-build/app_build.vdf
envsubst < steam/depot_windows.vdf.tpl > steam-build/depot_windows.vdf
envsubst < steam/depot_macos.vdf.tpl   > steam-build/depot_macos.vdf
envsubst < steam/depot_linux.vdf.tpl   > steam-build/depot_linux.vdf

# 5. Upload.
steamcmd \
  +login <build-account-username> \
  +run_app_build "$(pwd)/steam-build/app_build.vdf" \
  +quit
```

Steam will prompt for the SteamGuard code interactively. Enter it when
prompted. The upload proceeds after authentication.

After the upload, verify the build appears in Steamworks before promoting
any branch.

---

## Branch promotion

Promoting a build to a branch makes it immediately available to all players on
that branch. Always follow the staged-then-promote pattern.

### Stage 3 → beta branch

1. Confirm all Stage 3 gate criteria in
   [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) are met.
2. Trigger the deploy workflow with the Stage 3 release tag and
   `set_live_branch: beta`.
3. Provide beta testers with Steam keys (generated in Steamworks → Packages →
   the base app package → Generate Steam Product Codes).
4. Document the promoted build version and date in the release notes.

### Stage 4 → default branch (public release)

1. Confirm **all** Stage 4 gate criteria in
   [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) are met, including
   Valve store page approval and Steam Deck Verified status.
2. **If the build is already staged or live on `beta`**, run the dedicated
   promotion workflow (`.github/workflows/steam-promote.yml`) with the Build ID
   from Steamworks, the release tag, and the previous default Build ID (for
   rollback reference).  The workflow enforces the go/no-go gate and captures
   the provenance record; it does **not** re-upload depot content (the build is
   already on Valve's CDN).  Steam does not allow CI to set the `default` branch
   of a released app live — that change requires an interactive Steam Mobile
   Authenticator (or SMS) authorization — so a human then sets the build live on
   `default` in Steamworks → App Admin → Builds, following the instructions the
   workflow prints.  Record the resulting promotion entry in
   [`publishing/STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md).
   **If the build has not been staged yet**, trigger `steam-deploy.yml` to
   upload the depot content first, then set it live on `default` in App Admin.
3. The `default` branch immediately serves all new installs and updates.
4. Monitor the Steamworks App Admin → Reviews and the GitHub issue queue for
   the first 72 hours. Follow the launch monitoring checklist in
   [`publishing/STEAM_STORE_AND_OPERATIONS.md`](STEAM_STORE_AND_OPERATIONS.md#launch-day).

### Rolling back a branch

If a critical defect is found after setting a branch live:

1. In Steamworks App Admin → Builds, find the previous known-good build.
2. Set that build live on the affected branch.
3. Open a `severity:critical` GitHub issue with the `steam` and `platform-bug`
   labels; link it to the rollback action.
4. Do not re-promote the broken build until the defect is fixed and the depot
   audit passes on the fixed build.

---

## Troubleshooting

### Authentication errors

**Symptom:** `steamcmd` exits with `Login Failure: Account Logon Denied` or
`SteamGuard code required`.

**Cause:** The `config.vdf` has expired (SteamGuard session is approximately
one year). The build account may also have been locked or had its password
reset.

**Fix:**
1. Log in to the build account on a local machine with Steam installed.
2. Complete the SteamGuard prompt.
3. Copy and re-encode the updated `config.vdf`:
   ```bash
   base64 -w0 ~/.steam/steam/config/config.vdf
   ```
4. Update the `STEAM_CONFIG_VDF` repository secret with the new value.

---

### Depot audit failure

**Symptom:** The workflow fails at the `Audit depot content` step with output
such as `[weights] found: model.gguf` or `[secrets] found: config.vdf`.

**Fix:** Investigate where the forbidden file came from in the release artifact
or the artifact organisation step. Remove it and re-trigger the workflow. Do
not bypass the audit — it exists to prevent a private-data leak or a model
weight distribution policy violation (risk MD-04 in the compliance register).

---

### Build appears in Steamworks but depot is empty

**Symptom:** The build is listed in App Admin → Builds but the depot size shows
zero bytes or the install fails immediately.

**Cause:** Usually caused by a path mismatch between the VDF `ContentRoot`
setting and the actual `steam-content/<platform>/` directory layout.

**Fix:**
1. Run the workflow with `set_live_branch` empty to re-generate a staged build.
2. Check the generated VDF files in the workflow logs to confirm `ContentRoot`
   points to a directory that actually contains files.
3. Confirm the `Organise depot content` step ran without errors and that
   `find steam-content -type f | sort` shows the expected files.

---

### SteamPipe error: `ERROR! BuildOutput/App_<id>.log`

**Symptom:** `steamcmd` exits non-zero and refers to an output log file.

**Fix:** The `Show steamcmd build output` step always runs (even on failure)
and dumps the log. Read the full log for the root cause — common causes are
authentication errors, network timeouts, or a missing content directory.

---

### macOS depot fails Gatekeeper after install

**Symptom:** Players on macOS report "Apple cannot verify this app is free
from malware" after installing via Steam.

**Cause:** The `.app` bundle in the depot is not notarised, or was not
stapled before upload.

**Fix:** See [`publishing/MACOS_SIGNING_AND_NOTARIZATION.md`](MACOS_SIGNING_AND_NOTARIZATION.md)
for the full signing and notarisation runbook. In short:
1. Re-run the release workflow to produce a freshly signed and notarised bundle.
2. Confirm `spctl --assess --type execute ConversationSimulator.app` exits 0.
3. Re-upload the corrected depot.

---

### Windows SmartScreen blocks installer

**Symptom:** Players on Windows see "Windows protected your PC" and cannot run
the installer without clicking "More info → Run anyway".

**Cause:** The installer is unsigned or the certificate has not yet built
SmartScreen reputation.

**Fix:** See [`publishing/WINDOWS_CODE_SIGNING.md`](WINDOWS_CODE_SIGNING.md)
for the full Authenticode signing runbook. For the immediate issue, advise
testers to use "More info → Run anyway" during the Stage 3 private beta
(before reputation is established) and ensure the Stage 4 public release uses
a signed build.

---

## Links

- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — app IDs, depot IDs, CI credentials, branch strategy
- [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md) — depot layout, exclusions, approved binary payload list
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register; see MD-04, SR-08
- [`publishing/STEAM_STORE_AND_OPERATIONS.md`](STEAM_STORE_AND_OPERATIONS.md) — store operations, launch runbook, support triage
- [`publishing/STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md) — log of every default-branch promotion (Build IDs, artifact hashes, release notes)
- [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md) — launch-day sequence including Step 3 (promotion) and Step 4 (CDN verification)
- [`publishing/MACOS_SIGNING_AND_NOTARIZATION.md`](MACOS_SIGNING_AND_NOTARIZATION.md) — macOS signing and notarisation
- [`publishing/WINDOWS_CODE_SIGNING.md`](WINDOWS_CODE_SIGNING.md) — Windows Authenticode signing
- [`.github/workflows/steam-promote.yml`](../.github/workflows/steam-promote.yml) — CI workflow for promoting a staged build to default (no re-upload)
- [`.github/workflows/steam-deploy.yml`](../.github/workflows/steam-deploy.yml) — CI workflow for uploading content and optionally setting a branch live
- [`steam/`](../steam/) — SteamPipe VDF templates
- [`scripts/depot-audit.sh`](../scripts/depot-audit.sh) — depot content audit (Linux / macOS)
- [`scripts/depot-audit.ps1`](../scripts/depot-audit.ps1) — depot content audit (Windows PowerShell)
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — stage gate criteria
- [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — release principles and release train
