<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# macOS Code Signing and Notarization

> **Purpose:** Step-by-step runbook for signing and notarising the macOS
> Conversation Simulator build with an Apple Developer ID certificate so that
> Gatekeeper allows the app to run on a clean macOS install without any manual
> override.
>
> **Audience:** Platform team members who run the release CI pipeline and
> any maintainer performing a manual release build.
>
> **Gate:** A notarised macOS build is required before Stage 3 (Steam private
> beta). See gate G3-01 in [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md).

---

## Background

macOS Gatekeeper blocks apps that are not signed with an Apple Developer ID
Application certificate and notarised by Apple's notary service. An unsigned
or un-notarised build shows the error "Apple cannot verify this app is free
from malware" and requires manual intervention by the user.

The signing and notarisation process:

1. **Sign** — the `.app` bundle is code-signed with `codesign --options runtime`
   using the Developer ID Application certificate. This covers the main binary
   and all embedded binaries (including the `convsim-core` PyInstaller sidecar
   and the llama-server, whisper-cli, and sherpa-onnx sidecars).
2. **Notarise** — the signed bundle is submitted to Apple's notary service via
   `notarytool`. Apple scans it for malware and returns a ticket.
3. **Staple** — the notarisation ticket is stapled to the `.app` bundle so that
   Gatekeeper can verify it offline, without contacting Apple's servers.

Tauri's bundler automates all three steps when the environment variables
listed below are set.

---

## Certificate procurement

You need an **Apple Developer ID Application** certificate. This is distinct
from the distribution certificate used for App Store submissions.

### Steps to obtain the certificate

1. Enrol in the [Apple Developer Programme](https://developer.apple.com/programs/)
   under the Outright Mental organisation account.
2. In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/certificates/list),
   create a new **Developer ID Application** certificate.
3. Download the certificate and install it in your macOS Keychain.
4. Export the certificate and its private key as a `.p12` file:
   - Keychain Access → expand the certificate → right-click the private key →
     Export → choose `.p12` → set a strong passphrase.
5. Base64-encode the `.p12` for storage as a GitHub Actions secret:
   ```bash
   base64 -i DeveloperID.p12 -o DeveloperID.b64
   # On macOS, -i/-o flags are required; on Linux omit them and use redirect.
   ```

### Certificate identity string

The signing identity is the full subject string from the certificate. Retrieve
it after installation:

```bash
security find-identity -v -p codesigning
# Example output:
# 1) AABBCCDDEE "Developer ID Application: Outright Mental (TEAMID)"
```

The string in quotes is the `APPLE_SIGNING_IDENTITY` value.

---

## App Store Connect API key for notarisation (preferred)

The ASC API key is the **preferred** authentication method for notarytool.
It has no 2FA coupling, can be revoked without touching the Apple ID account,
and is scoped to the App Manager role — making it safer than an app-specific
password tied to the organisation's Apple ID.

### Minting an ASC API key

1. Sign in to [App Store Connect](https://appstoreconnect.apple.com) as an
   Admin under the Outright Mental team.
2. Navigate to **Users and Access → Integrations → App Store Connect API**.
3. Under **Team Keys**, click **+** to generate a new key.
   - **Name:** `convsim-notarytool` (or include the date for rotation traceability)
   - **Access:** `App Manager`
4. Download the generated `.p8` private key file — it can only be downloaded
   **once**.  Store it securely before leaving this page.
5. Note the **Key ID** (alphanumeric, e.g. `ABCDE12345`) and the **Issuer ID**
   (UUID shown at the top of the Integrations page).

### Storing as org-level secrets

Base64-encode the `.p8` file for secret storage:

```bash
base64 -i AuthKey_ABCDE12345.p8 -o AuthKey_ABCDE12345.b64
# On Linux (no -i/-o flags required):
base64 AuthKey_ABCDE12345.p8 > AuthKey_ABCDE12345.b64
```

Add the three secrets at the org level:

```bash
# Key ID (short alphanumeric, not the full filename):
gh secret set APPLE_API_KEY \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt

# Issuer UUID from the App Store Connect Integrations page:
gh secret set APPLE_API_ISSUER \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt

# Base64-encoded .p8 file content:
gh secret set APPLE_API_KEY_PATH \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt
```

The release workflow decodes `APPLE_API_KEY_PATH` to a temp file at runtime,
sets `APPLE_API_KEY_PATH` in the environment to that file path (the variable
name Tauri expects), and deletes the file the moment the Tauri build completes.

### Apple ID fallback

If the ASC API key is not configured, the workflow falls back to Apple ID
authentication using the `APPLE_ID`, `APPLE_ID_PASSWORD`, and `APPLE_TEAM_ID`
org secrets. (`APPLE_ID_PASSWORD` supplies the env var Tauri calls
`APPLE_PASSWORD` — the workflow maps the name.)

1. Sign in to [appleid.apple.com](https://appleid.apple.com).
2. Under Security → App-Specific Passwords, generate a new password.
3. Label it `convsim-notarytool` or similar for traceability.
4. Copy the password — it is shown only once.

Add the three secrets:

```bash
gh secret set APPLE_ID --org outrightmental \
  --visibility selected --repos ConversationSimulator,FeverTilt
gh secret set APPLE_ID_PASSWORD --org outrightmental \
  --visibility selected --repos ConversationSimulator,FeverTilt
gh secret set APPLE_TEAM_ID --org outrightmental \
  --visibility selected --repos ConversationSimulator,FeverTilt
```

---

## Release enforcement (REQUIRE_SIGNED_MACOS)

The release workflow sets `REQUIRE_SIGNED_MACOS=true` for any workflow run
triggered by a `v*` tag (push or workflow_dispatch).  When this flag is true:

- **Missing `MACOS_CODESIGN_CERT_BASE64`** → the verify step fails with an
  actionable error and the build is rejected before any artifact is uploaded.
- **Missing notarisation credentials** → the verify step fails (even if the
  build was signed) with a message listing both the preferred ASC API key and
  the Apple ID fallback.

This turns gate G3-01 from a checklist item into CI law.  Contributor forks
and PR builds are unaffected — they never carry a `v*` tag and the enforcement
block is never reached.

### Testing enforcement

Do **not** test this by removing a live org secret. Run the **Release preflight**
workflow instead (`.github/workflows/release-preflight.yml`): it reports exactly
which required credentials are present or missing without cutting a release, and
it runs automatically on every push to `main`.

If enforcement does trip on a real tag, the verify step exits non-zero with:

```
ERROR: MACOS_CODESIGN_CERT_BASE64 is not configured but a signed macOS build
       is required for this release tag.
```

---

## CI setup (GitHub Actions secrets)

These secrets are stored at the **outrightmental organisation level**, scoped to
`ConversationSimulator` and `FeverTilt`. They are entered once and rotated in one
place — all scoped repositories pick up the change automatically.

**Code-signing secrets (required for all signed builds):**

Org secret names describe the credential; the environment variables Tauri reads
are named differently and the release workflow maps between them.

| Org secret name | Env var it supplies | Contents | Source |
|-----------------|---------------------|----------|--------|
| `MACOS_CODESIGN_CERT_BASE64` | `APPLE_CERTIFICATE` | Base64-encoded `.p12` file | Export from Keychain, then `base64 -i DeveloperID.p12` |
| `MACOS_CODESIGN_CERT_PASSWORD` | `APPLE_CERTIFICATE_PASSWORD` | Passphrase for the `.p12` file | Set when exporting the `.p12` |

There is **no `APPLE_SIGNING_IDENTITY` secret.** CI derives the identity from the
imported certificate (`security find-identity -v -p codesigning`) and publishes it
via `GITHUB_ENV`, so it cannot drift out of sync with the certificate it describes.

**Notarisation secrets — ASC API key (preferred, see above for minting):**

| Secret name | Contents | Source |
|-------------|----------|--------|
| `APPLE_API_KEY` | Key ID (e.g. `ABCDE12345`) | App Store Connect → Users and Access → Integrations → Key ID |
| `APPLE_API_ISSUER` | Issuer UUID | App Store Connect → Users and Access → Integrations → Issuer ID |
| `APPLE_API_KEY_PATH` | Base64-encoded `.p8` private key content | `base64 -i AuthKey_ABCDE12345.p8` |
| `APPLE_TEAM_ID` | Ten-character Outright Mental team ID | Apple Developer portal (required for both auth paths) |

**Notarisation secrets — Apple ID fallback (used when ASC API key is absent):**

| Secret name | Contents | Source |
|-------------|----------|--------|
| `APPLE_ID` | Apple ID email used for notarisation | Outright Mental Apple Developer account |
| `APPLE_ID_PASSWORD` | App-specific password for notarytool (supplies Tauri's `APPLE_PASSWORD`) | appleid.apple.com → Security → App-Specific Passwords |

**To set or rotate** (values supplied interactively, never committed):

```bash
gh secret set MACOS_CODESIGN_CERT_BASE64 \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt
# repeat for each secret in the tables above
```

Or use the org Settings UI: GitHub → outrightmental org **Settings → Secrets
and variables → Actions → Secrets → New organisation secret**, then set
**Repository access** to *Selected repositories: ConversationSimulator, FeverTilt*.

**Rotation:** Rotating any secret at org level updates it for all scoped
repositories simultaneously. Run `gh secret list --org outrightmental` to
confirm the inventory after any change.

Tauri's bundler reads these environment variables from the CI environment
automatically. The release workflow (`release.yml`) passes them through
`env:` blocks. See
[`docs/platform-notes.md` — Code signing and Gatekeeper](../docs/platform-notes.md#code-signing-and-gatekeeper)
for the exact variable names used by Tauri.

---

## Entitlements

The Hardened Runtime is required for notarisation. The entitlements file at
`apps/desktop/src-tauri/entitlements.plist` grants the capabilities the app
needs under Hardened Runtime.

The file must include the following entitlements at minimum (these match the
committed `entitlements.plist`):

| Entitlement key | Value | Reason |
|-----------------|-------|--------|
| `com.apple.security.cs.allow-jit` | `true` | WKWebView (Tauri's embedded browser) requires JIT to run JavaScript under Hardened Runtime |
| `com.apple.security.cs.disable-library-validation` | `true` | Load vendor-signed third-party dylibs (Steamworks SDK, llama.cpp runtime) |
| `com.apple.security.device.audio-input` | `true` | Microphone access for optional Whisper STT |
| `com.apple.security.network.client` | `true` | Model download and loopback to the convsim-core sidecar (user-initiated) |
| `com.apple.security.files.user-selected.read-write` | `true` | Read/write files chosen via the system open/save dialog (pack import, debrief export) |

The App Sandbox is intentionally **not** enabled — Steam apps require direct
IPC for the overlay and achievement reporting, which the App Sandbox forbids.
Hardened Runtime (codesign's `runtime` option) is separate from the App Sandbox
and is the feature Apple's notary service requires.

Review the entitlements file before each Stage 3 submission. Entitlements that
are not needed must be removed — Apple's notary service flags unnecessary
entitlements.

---

## Signing the sidecar binaries

All binaries embedded in the `.app` bundle must be individually signed before
the bundle itself is signed. Tauri handles this automatically when
`APPLE_SIGNING_IDENTITY` is set — it calls `codesign` on each file in
`Contents/MacOS/`, `Contents/Resources/bin/`, and `Contents/Resources/runtimes/`
before signing the outer `.app`.

The `convsim-core` PyInstaller bundle also reads `APPLE_SIGNING_IDENTITY`
at build time (see `convsim-core.spec`) to sign the embedded Python C extensions
before Tauri wraps them. Verify this is happening by inspecting the PyInstaller
build log for `codesign` invocations.

If a sidecar binary is updated independently of the Tauri build:

```bash
codesign \
  --sign "Developer ID Application: Outright Mental (TEAMID)" \
  --options runtime \
  --entitlements apps/desktop/src-tauri/entitlements.plist \
  --force \
  --timestamp \
  path/to/sidecar-binary
```

---

## Manual signing and notarisation

Use this procedure for local testing of the signing and notarisation flow
before the CI pipeline is fully configured.

### Prerequisites

```bash
# Xcode Command Line Tools (provides codesign, spctl, notarytool, stapler)
xcode-select --install

# Confirm notarytool is available (requires Xcode 13+ or macOS 12+)
xcrun notarytool --version
```

### Step 1 — Build the app bundle

```bash
# From the repo root:
export APPLE_CERTIFICATE="<base64-p12>"
export APPLE_CERTIFICATE_PASSWORD="<p12-passphrase>"
export APPLE_SIGNING_IDENTITY="Developer ID Application: Outright Mental (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="<app-specific-password>"
export APPLE_TEAM_ID="TEAMID"

pnpm --filter @convsim/desktop build
# The signed .app bundle is produced in:
#   apps/desktop/src-tauri/target/release/bundle/macos/ConversationSimulator.app
```

### Step 2 — Verify the signature

```bash
codesign --verify --verbose=2 \
  apps/desktop/src-tauri/target/release/bundle/macos/ConversationSimulator.app

# Also verify the main binary directly:
codesign -dv --verbose=4 \
  apps/desktop/src-tauri/target/release/bundle/macos/ConversationSimulator.app/Contents/MacOS/ConversationSimulator
```

The output should include `authority=Developer ID Application: Outright Mental`.
The `--timestamp` seal confirms the signature is timestamped.

### Step 3 — Notarise

Tauri submits the bundle to the notary service automatically as part of
`tauri build` when the environment variables are set. To notarise manually:

```bash
# Create a zip of the .app (notarytool requires zip or dmg input)
ditto -c -k --keepParent \
  apps/desktop/src-tauri/target/release/bundle/macos/ConversationSimulator.app \
  ConversationSimulator.zip

xcrun notarytool submit ConversationSimulator.zip \
  --apple-id "$APPLE_ID" \
  --password "$APPLE_PASSWORD" \
  --team-id "$APPLE_TEAM_ID" \
  --wait
```

`--wait` polls until notarisation completes (typically 1–10 minutes). The
command prints the submission ID and the final status.

If notarisation fails, retrieve the detailed log:

```bash
xcrun notarytool log <submission-id> \
  --apple-id "$APPLE_ID" \
  --password "$APPLE_PASSWORD" \
  --team-id "$APPLE_TEAM_ID"
```

### Step 4 — Staple the ticket

```bash
xcrun stapler staple \
  apps/desktop/src-tauri/target/release/bundle/macos/ConversationSimulator.app
```

### Step 5 — Verify Gatekeeper acceptance

```bash
# Run on a separate machine that has not seen this app before, or:
spctl --assess --type execute --verbose \
  apps/desktop/src-tauri/target/release/bundle/macos/ConversationSimulator.app
# Expected output:
# ConversationSimulator.app: accepted
# source=Notarized Developer ID
```

A result of `accepted` with `source=Notarized Developer ID` satisfies gate
G3-01.

---

## Steam depot preparation

The Steam depot requires the raw `.app` bundle, not the `.dmg` installer.
The release CI workflow tarballs the notarised, stapled `.app` into a
`.app.tar.gz` artifact. The Steam deploy workflow then extracts it into
`steam-content/macos/` before uploading.

```bash
# If producing the tarball manually:
tar -czf ConversationSimulator.app.tar.gz \
  -C apps/desktop/src-tauri/target/release/bundle/macos \
  ConversationSimulator.app
```

Do **not** upload the `.dmg` to the Steam depot. The `.dmg` is an installer
disk image, not application files. SteamPipe requires the application directory
structure directly.

---

## Rotating the certificate

Apple Developer ID certificates expire after five years. When the certificate
approaches expiry:

1. Generate a new Developer ID Application certificate in the Apple Developer
   portal.
2. Export as `.p12` and base64-encode as described above.
3. Update the org-level `MACOS_CODESIGN_CERT_BASE64` and
   `MACOS_CODESIGN_CERT_PASSWORD` secrets (see
   [CI setup](#ci-setup-github-actions-secrets) for the `gh secret set` command).
   All scoped repositories pick up the new certificate automatically.
4. Nothing else to update: CI re-derives the signing identity from the new
   certificate, so there is no second secret to keep in sync.
5. Run the **Release preflight** workflow, then rebuild and re-notarise the latest
   release to confirm the new certificate works end to end.
6. Existing installed copies signed with the old certificate continue to work —
   the stapled notarisation ticket is valid permanently.

---

## Troubleshooting

### "Apple cannot verify this app is free from malware"

The app is not notarised or the stapled ticket was lost. Verify with:

```bash
spctl --assess --type execute --verbose path/to/ConversationSimulator.app
```

If the result is `rejected`, re-run Steps 3–4 (notarise and staple). If
the ticket was already stapled but Gatekeeper still rejects, confirm the
staple with:

```bash
xcrun stapler validate ConversationSimulator.app
```

### Notarisation rejected — "OBJC_CLASS$_SomeClass not found"

A dynamically linked library was not signed with `--options runtime`. Run
`codesign -dv --verbose=4` on the `.app` and on each embedded binary to
confirm all carry the Hardened Runtime flag.

### "invalid signature" on embedded sidecar

The PyInstaller-bundled `convsim-core` or a sidecar runtime binary was not
signed. Re-run the `convsim-core` build with `APPLE_SIGNING_IDENTITY` set
(see the `convsim-core.spec` spec file for the codesign hook), then rebuild
the Tauri bundle.

### Notarisation timeout

Apple's notary service occasionally experiences delays. Resubmit with the
same command; the submission ID changes but the content is identical. Check
[developer.apple.com/system-status](https://developer.apple.com/system-status/)
for notary service outages.

---

## Links

- [`apps/desktop/src-tauri/entitlements.plist`](../apps/desktop/src-tauri/entitlements.plist) — Hardened Runtime entitlements (with rationale for each)
- [`apps/desktop/src-tauri/tauri.conf.json`](../apps/desktop/src-tauri/tauri.conf.json) — Tauri bundle configuration
- [`docs/platform-notes.md` — macOS section](../docs/platform-notes.md#macos) — system requirements, supported versions, build prerequisites
- [`docs/steam-mvp-scope.md` — G3-01](../docs/steam-mvp-scope.md) — Stage 3 gate: notarised macOS build required
- [`docs/release-checklist.md` — Part G](../docs/release-checklist.md#part-g--macos-steam-beta-install-verification) — macOS Steam beta install checklist including `.app.tar.gz` round-trip verification
- [`docs/steam-achievements-stats-rich-presence.md`](../docs/steam-achievements-stats-rich-presence.md) — Steamworks SDK integration context (relevant to `disable-library-validation` entitlement)
- [`publishing/STEAM_DEPOT_CONTENTS.md` — macOS depot](STEAM_DEPOT_CONTENTS.md#macos-depot-depot_macosvdftpl) — macOS depot layout and notarisation requirement
- [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — Steam deploy workflow and troubleshooting
- [Tauri macOS signing docs](https://tauri.app/distribute/sign/macos) — upstream reference for `tauri build` signing variables
- [Apple Developer — Developer ID](https://developer.apple.com/developer-id/) — official certificate documentation
- [Apple — App Store Connect API](https://developer.apple.com/documentation/appstoreconnectapi) — ASC API key management
- [Apple — notarytool man page](https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool) — notarytool migration guide
