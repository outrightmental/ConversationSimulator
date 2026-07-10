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

## App-specific password for notarisation

The notary service authenticates with an Apple ID and an **app-specific
password** (not the Apple ID login password).

1. Sign in to [appleid.apple.com](https://appleid.apple.com).
2. Under Security → App-Specific Passwords, generate a new password.
3. Label it `convsim-notarytool` or similar for traceability.
4. Copy the password — it is shown only once.

---

## CI setup (GitHub Actions secrets)

Store the following as **GitHub Actions secrets** (Settings → Secrets and
variables → Actions → Secrets):

| Secret name | Contents |
|-------------|----------|
| `APPLE_CERTIFICATE` | Base64-encoded `.p12` file (the output of the `base64` command above) |
| `APPLE_CERTIFICATE_PASSWORD` | Passphrase for the `.p12` file |
| `APPLE_SIGNING_IDENTITY` | Full identity string: `Developer ID Application: Outright Mental (TEAMID)` |
| `APPLE_ID` | Apple ID email used for notarisation |
| `APPLE_PASSWORD` | App-specific password generated above |
| `APPLE_TEAM_ID` | Ten-character Outright Mental team ID (visible in the Apple Developer portal) |

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
3. Update the `APPLE_CERTIFICATE` and `APPLE_CERTIFICATE_PASSWORD` GitHub
   Actions secrets.
4. Update the `APPLE_SIGNING_IDENTITY` secret if the team ID or name changed.
5. Rebuild and re-notarise the latest release to confirm the new certificate
   works end to end.
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

- [`apps/desktop/src-tauri/entitlements.plist`](../apps/desktop/src-tauri/entitlements.plist) — Hardened Runtime entitlements
- [`apps/desktop/src-tauri/tauri.conf.json`](../apps/desktop/src-tauri/tauri.conf.json) — Tauri bundle configuration
- [`docs/platform-notes.md` — macOS section](../docs/platform-notes.md#macos) — system requirements, supported versions, build prerequisites
- [`docs/steam-mvp-scope.md` — G3-01](../docs/steam-mvp-scope.md) — Stage 3 gate: notarised macOS build required
- [`publishing/STEAM_DEPOT_CONTENTS.md` — macOS depot](STEAM_DEPOT_CONTENTS.md#macos-depot-depot_macosvdftpl) — macOS depot layout and notarisation requirement
- [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — Steam deploy workflow and troubleshooting
- [Tauri macOS signing docs](https://tauri.app/distribute/sign/macos) — upstream reference for `tauri build` signing variables
- [Apple Developer — Developer ID](https://developer.apple.com/developer-id/) — official certificate documentation
- [Apple — notarytool man page](https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool) — notarytool migration guide
