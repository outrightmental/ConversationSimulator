<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Platform notes

Platform-specific differences for building, running, and distributing
Conversation Simulator on macOS and Windows.

---

## macOS

### Steam system requirements

These are the official minimum and recommended requirements recorded for the
Steam store page and the Stage 3/4 release gates.

| | Minimum | Recommended |
|---|---|---|
| **OS** | macOS 13 Ventura | macOS 14 Sonoma or newer |
| **Architecture** | Apple Silicon (arm64) or Intel (x86-64) | Apple Silicon (M2 or newer) |
| **CPU** | Apple M1 / Intel Core i5 (6th gen or newer) | Apple M2 or newer |
| **RAM** | 8 GB | 16 GB |
| **Storage** | 2 GB free (app) + 3 GB per downloaded model | 5 GB free |
| **GPU / ANE** | Integrated GPU | Apple Neural Engine (M1+) for fast inference |
| **Internet** | Required for first-time model download | — |

Notes:
- macOS 12 Monterey may work but is **not tested** and is excluded from QA coverage.
- A universal binary (arm64 + x86-64) is the target; separate arm64 and x86-64
  `.dmg` files are acceptable for Stage 3 private beta.
- As of late 2024, the GitHub-hosted `macos-13` Intel runner is deprecated; CI
  builds on `macos-latest` (Apple Silicon / arm64). Intel builds require a
  self-hosted runner or cross-compilation (`--target x86_64-apple-darwin`).

### Supported versions

macOS 13 Ventura or newer. Apple Silicon (M1+) and Intel are both supported
with separate installer builds (`.dmg` files differ by architecture).

### Build prerequisites

```bash
# Xcode Command Line Tools (provides clang, libtool, otool, etc.)
xcode-select --install

# Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Node.js 18+, pnpm, Python 3.10+ via Homebrew (recommended)
brew install node python@3.11
npm install -g pnpm
```

For cross-compilation (building Apple Silicon on an Intel Mac or vice versa):

```bash
rustup target add aarch64-apple-darwin   # build for Apple Silicon
rustup target add x86_64-apple-darwin    # build for Intel
pnpm --filter @convsim/desktop tauri build --target aarch64-apple-darwin
```

### Installer format

Tauri produces a `.dmg` disk image and a raw `.app` bundle. The `.dmg` is the
primary distributable for macOS. For the Steam depot, the release CI tarballs
the `.app` bundle into a `.app.tar.gz` (Steam ships the raw application, not the
installer); Tauri itself only emits `.app.tar.gz` when the updater is
configured, which this project does not use.

### Code signing and Gatekeeper

Alpha builds are **not code-signed**. macOS Gatekeeper will block unsigned
apps with "Apple cannot verify this app is free from malware." To open an
unsigned build:

1. Right-click (or Control-click) the `.app` → **Open** → **Open**.
2. Or: **System Settings → Privacy & Security** → scroll down → **Open Anyway**.

For distributable (Stage 3+) builds, sign and notarise with an Apple Developer
ID certificate. Set the following environment variables before running
`tauri build` (or let the CI release workflow set them from secrets):

```bash
# Base64-encoded Developer ID Application .p12 certificate
export APPLE_CERTIFICATE="<base64>"
export APPLE_CERTIFICATE_PASSWORD="<p12-passphrase>"
# Full identity string from the certificate
export APPLE_SIGNING_IDENTITY="Developer ID Application: Outright Mental (TEAMID)"
# Notarisation credentials
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="<app-specific-password>"
export APPLE_TEAM_ID="TEAMID"
```

Tauri's bundler reads these variables automatically, applies
`apps/desktop/src-tauri/entitlements.plist` (Hardened Runtime entitlements
required for Steamworks and sidecar compatibility — see the file for details),
signs the `.app` bundle with `codesign --options runtime`, and submits it to
Apple's notarisation service via `notarytool`.

The `convsim-core` PyInstaller sidecar also reads `APPLE_SIGNING_IDENTITY`
at build time (see `convsim-core.spec`) and signs its embedded Python extensions
with the same entitlements before Tauri wraps them in the bundle.

> **These are environment-variable names, not secret names.** Tauri requires them
> verbatim, but the org secrets that feed them in CI are named differently
> (`MACOS_CODESIGN_CERT_BASE64` → `APPLE_CERTIFICATE`, `APPLE_ID_PASSWORD` →
> `APPLE_PASSWORD`). See [Apple secrets](#apple-secrets-macos-signing-and-notarisation)
> below for the full mapping. In CI, `APPLE_SIGNING_IDENTITY` is *derived* from the
> imported certificate rather than configured — you only set it by hand locally.

See [tauri.app/distribute/sign/macos](https://tauri.app/distribute/sign/macos)
for more details on the Tauri signing process.

**Gate G3-01:** A notarised macOS build is required before Stage 3 (Steam
private beta). A Gatekeeper pass on a clean macOS install (without "Open
Anyway") is the acceptance criterion.

### Microphone permission

The OS shows a standard permission dialog on first use of voice input.
If denied, re-enable in **System Settings → Privacy & Security → Microphone**.

The dialog text comes from `NSMicrophoneUsageDescription` in
`apps/desktop/src-tauri/Info.plist` (merged into the bundle by Tauri). This key
is mandatory under Hardened Runtime — without it macOS terminates the app
instead of prompting when voice input first requests the microphone.

### Data directories

The platform data root is `~/Library/Application Support/com.outrightmental.convsim/`
(set by `convsim_core/paths.py`; passed to the sidecar as `CONVSIM_DATA_ROOT`
via the Tauri shell's `app_local_data_dir()`). Subdirectories:

```
~/Library/Application Support/com.outrightmental.convsim/
  db/         — SQLite session database
  data/       — exports and pack cache
  logs/       — runtime logs
  models/     — downloaded model weights
  exports/    — exported transcripts
  data/audio/ — recorded audio clips (only when "save raw audio" is enabled; off by default)
  crashes/    — crash bundles
```

This directory is not synced to iCloud (it is outside `~/Library/Mobile Documents`)
and is explicitly excluded from Steam Cloud via `.nosteamcloudpath` sentinel files.

If you have data from an older build that used `~/.convsim/`, run the app once to
trigger the one-time migration (`convsim_core/data_migration.py` copies existing
data to the new location on first launch).

Override the entire data root with the `CONVSIM_DATA_ROOT` environment variable.

### Port conflicts

The app uses ports 7354–7358 (all bound to `127.0.0.1`). Find and stop
conflicting processes:

```bash
lsof -i :7354
lsof -i :7355
kill <PID>
```

---

## Windows

### Supported versions

Windows 10 (build 19041 / 20H1) or newer. Windows 11 is recommended.
64-bit x86 only (`x86_64-pc-windows-msvc`).

### Build prerequisites

1. **Microsoft Visual Studio C++ Build Tools** — required by the Rust MSVC toolchain.
   Install via [Build Tools for Visual Studio](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
   and select the **"Desktop development with C++"** workload.

2. **Rust toolchain** — install via [rustup.rs](https://rustup.rs/); the installer
   detects Windows and installs the MSVC toolchain automatically.

3. **WebView2 Runtime** — bundled with Windows 11 and Windows 10 21H2+. For older
   Windows 10 builds, install the Evergreen Bootstrapper from
   [developer.microsoft.com/en-us/microsoft-edge/webview2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).

4. **Node.js 18+ and pnpm** — download from [nodejs.org](https://nodejs.org/) and
   run `npm install -g pnpm` in a PowerShell terminal (as Administrator if needed).

5. **Python 3.10+** — download from [python.org](https://www.python.org/downloads/).
   During installation, check **"Add Python to PATH"**.

Run the setup script from PowerShell:

```powershell
.\scripts\setup.ps1
```

### Installer format

Tauri produces two Windows installers:

- **NSIS `.exe`** — a classic setup wizard; recommended for most users.
- **MSI (WiX)** — Microsoft Installer; better for enterprise/group-policy deployment.

Both installers are self-contained; no separate runtime installation is needed
(WebView2 is bundled with the NSIS installer if not already present).

### Code signing (SmartScreen) {#code-signing-smartscreen}

Alpha builds are **not code-signed**. Windows Defender SmartScreen will warn
"Windows protected your PC" with an **unrecognised publisher** message.
To run an unsigned build:

1. Click **More info** in the SmartScreen dialog.
2. Click **Run anyway**.

For distributable and Steam release builds, signing uses **Google Cloud KMS +
jsign** so the private key never resides on the build runner. The certificate
is issued against the KMS key (see the CSR flow in
[`publishing/WINDOWS_CODE_SIGNING.md`](../publishing/WINDOWS_CODE_SIGNING.md)).

#### Authenticode signing in CI (Release workflow)

Signing runs in two phases controlled by `scripts/jsign-sign.ps1`:

1. **Main executable** — `ConversationSimulator.exe` is signed by Tauri's
   `bundle.windows.signCommand` hook during `tauri build`.
2. **Resource binaries** — `convsim-core.exe` (and `llama-server.exe` on Steam
   builds) are bundled via `bundle.resources`, which `signCommand` does **not**
   cover, so the "Sign bundled resource binaries" step signs them before the
   Tauri build packages them into the installer.
3. **Outer installers** — the NSIS `.exe` and MSI are signed post-build by the
   "Sign Windows installers (Authenticode)" step.

Both phases share the same script and the same signing priority:

| Priority | Credential secrets | Notes |
|----------|--------------------|-------|
| 1. GCP KMS | `GCP_SA_KEY_JSON` + `GCP_KMS_KEY` + `WINDOWS_CODESIGN_CERT` | Org-level; key stays in Cloud HSM |
| 2. PFX fallback | `WINDOWS_SIGN_CERT_PFX` + `WINDOWS_SIGN_CERT_PASSWORD` | Legacy; key decoded to `RUNNER_TEMP` per build |
| 3. Skip | (neither set) | Fork-friendly; produces unsigned artifact |

Signing is **required** before the Stage 3 private beta gate (G3-01 in
`docs/steam-mvp-scope.md`).

#### Setting up KMS signing

See [`publishing/WINDOWS_CODE_SIGNING.md`](../publishing/WINDOWS_CODE_SIGNING.md)
for the full runbook including:
- Cloud KMS key ring and key creation
- CSR generation and CA submission
- Org-level secret configuration
- Key-version rotation procedure
- SmartScreen reputation notes

#### Local signing (manual / one-off)

```powershell
# Set environment variables (values from org-level secrets)
$env:GCP_SA_KEY_JSON       = Get-Content path\to\sa-key.json -Raw
$env:GCP_KMS_KEY           = 'projects/P/locations/global/keyRings/convsim-signing/cryptoKeys/windows-codesign'
$env:WINDOWS_CODESIGN_CERT = [Convert]::ToBase64String([IO.File]::ReadAllBytes('fullchain.pem'))

# Sign a specific binary
pwsh -File scripts\jsign-sign.ps1 -FilePath .\path\to\ConversationSimulator.exe

# Verify the signature
signtool.exe verify /pa /v .\path\to\ConversationSimulator.exe
```

### Antivirus false positives

Freshly compiled Rust/Tauri executables are occasionally flagged by antivirus
engines as suspicious (heuristic detection). If this happens:

1. Add the install directory to your antivirus exclusion list.
2. Submit the executable for false-positive review through your AV vendor's portal.

### Microphone permission

Windows Security prompts for microphone access on first use. Allow it when
prompted, or grant it in **Settings → Privacy & Security → Microphone**.

### Data directories

The desktop app stores all mutable user data under the platform-native
application data directory.  On Windows this is `%LOCALAPPDATA%`, which is
**not** synced by Windows Roaming Profiles or OneDrive by default, keeping
data local as required by the local-first privacy promise.

```
%LOCALAPPDATA%\outrightmental\convsim\db\       — SQLite session database
%LOCALAPPDATA%\outrightmental\convsim\data\     — exports and pack cache
%LOCALAPPDATA%\outrightmental\convsim\logs\     — runtime logs
%LOCALAPPDATA%\outrightmental\convsim\models\   — downloaded model weights
%LOCALAPPDATA%\outrightmental\convsim\exports\  — exported transcripts
%LOCALAPPDATA%\outrightmental\convsim\data\audio\  — recorded audio clips (only when "save raw audio" is enabled; off by default)
%LOCALAPPDATA%\outrightmental\convsim\crashes\  — crash bundles
```

The `CONVSIM_DATA_ROOT` environment variable overrides the entire root path.

> **Migration from earlier builds:** If `~\.convsim\` exists from a pre-1.0
> alpha install, `convsim-core` automatically copies sessions, packs, logs,
> exports, and the database to the new location on first launch.  Model weights
> are **not** migrated; re-download them via the Model Manager after migration.
> A `.convsim_migrated_to_platform_dir` marker is written when migration
> completes.

**Steam Cloud exclusion:** each data subdirectory contains a `.nosteamcloudpath`
file that tells the Steam client not to sync it.  Transcripts, session history,
audio, and model outputs never leave the player's machine via Steam Cloud.

### Windows system requirements for Steam

These requirements apply to the **installed desktop app** distributed via Steam.
They do not apply to source-checkout developer builds (which may need
additional tooling).

#### Minimum requirements

| Component | Minimum |
|-----------|---------|
| OS | Windows 10 (build 19041 / 20H1) 64-bit |
| CPU | 64-bit x86 processor, 2 cores, SSE4.2 |
| RAM | 8 GB |
| Disk (app install) | 500 MB |
| Disk (models, downloaded post-launch) | 4 GB free (for a single starter model) |
| GPU | Not required — CPU-only inference is supported |
| WebView2 | Microsoft Edge WebView2 Runtime (bundled by the NSIS installer on Windows 10 builds earlier than 21H2) |
| Internet | Required only for initial model download; **all play is offline** after the model is installed |

#### Recommended requirements

| Component | Recommended |
|-----------|-------------|
| OS | Windows 11 (any release) 64-bit |
| CPU | 64-bit x86 processor, 8+ cores (for faster CPU inference) |
| RAM | 16 GB |
| Disk | 20 GB free (for multiple models and session history) |
| GPU | NVIDIA GPU with 4+ GB VRAM (enables GPU-accelerated inference via llama.cpp's CUDA backend) |

> **Note on GPU acceleration:** GPU acceleration is not required and not
> automatically enabled.  If a supported NVIDIA GPU is present the player can
> opt in via the Model Manager.  CUDA toolkit is not required — the bundled
> `llama-server.exe` includes the CUDA runtime.

#### Verified Steam client version

The app has been tested against **Steam client 1.0.0.81** and newer.  The
minimum Steam client version to list on the store page is **Steam client
1.0.0.81**.

### Port conflicts

Find and stop conflicting processes on Windows:

```powershell
Get-NetTCPConnection -LocalPort 7354 | Select-Object OwningProcess
Stop-Process -Id <PID> -Force
```

### Paths with spaces

If your user directory contains spaces (e.g. `C:\Users\Jane Doe\`), ensure
that Python, Node.js, and Rust are installed in paths **without** spaces, or
that their paths are correctly quoted in the environment. The setup script
handles quoting automatically, but custom tool installations may not.

### PowerShell execution policy

To run `setup.ps1` and `dev.ps1`, the execution policy must allow local
scripts. Run once in an elevated PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Linux

### Supported distributions

Ubuntu 22.04 LTS is the primary test target and the CI build machine.
Other glibc-based distros (Fedora 38+, Debian 12+, Arch, SteamOS 3.x)
are compatible. See [linux-steamos-requirements.md](linux-steamos-requirements.md)
for the full distribution compatibility matrix and GLibC version details.

### Build prerequisites

```bash
# Tauri system dependencies (Ubuntu / Debian)
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev libgtk-3-dev \
  libayatana-appindicator3-dev librsvg2-dev

# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Node.js 18+ via NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install -g pnpm

# Python 3.10+
sudo apt-get install -y python3.11 python3.11-venv
```

Run setup and then the Linux build script:

```bash
./scripts/setup.sh
./scripts/build-linux.sh
```

### Installer format

Tauri produces:
- **`.AppImage`** — portable, runs on any x86_64 Linux with glibc ≥ 2.35
  without installation. This is the primary Steam depot artifact and the
  recommended format for Steam Deck / SteamOS installs.
- **`.deb`** — Debian/Ubuntu package for system-wide installation on
  Ubuntu 22.04+ and Debian 12+.

The AppImage bundles WebKitGTK, GTK 3, and most other user-space dependencies.
The `.deb` package declares them as `Depends:` and installs them via apt.

### Code signing

Linux builds are **not code-signed**. There is no Linux equivalent of macOS
Gatekeeper or Windows SmartScreen; no signature is required for distribution.
The AppImage and `.deb` are distributed with SHA-256 checksums listed in the
GitHub release and verified by the Steam depot audit before upload.

### Microphone (PipeWire / PulseAudio)

WebKit on Linux may require `xdg-desktop-portal` and a running PipeWire or
PulseAudio session for the browser `getUserMedia` permission dialog to appear.
On headless or minimal desktop environments, microphone access may silently
fail; use text-only input mode in that case.

```bash
# Install portal support on Ubuntu
sudo apt-get install -y xdg-desktop-portal xdg-desktop-portal-gtk
```

### Data directories

```
~/.local/share/convsim/db/       — SQLite session database
~/.local/share/convsim/data/     — general application data
~/.local/share/convsim/packs/    — installed scenario packs
~/.local/share/convsim/exports/  — exported transcripts
~/.local/share/convsim/logs/     — runtime logs
~/.local/share/convsim/cache/    — regenerable caches
~/.local/share/convsim/models/   — downloaded model weights
```

The root is `$XDG_DATA_HOME/convsim` when `XDG_DATA_HOME` is set, otherwise
`~/.local/share/convsim`. If `~/.convsim/` exists from a pre-release dev
install, the app migrates data on first launch. Every subdirectory can be
redirected via a `CONVSIM_*` environment variable — e.g. `CONVSIM_DB_DIR`,
`CONVSIM_DATA_DIR`, `CONVSIM_LOG_DIR`, `CONVSIM_MODELS_DIR` — or relocate the
whole tree at once with `CONVSIM_DATA_ROOT`.

### Port conflicts

The app binds ports 7354–7358 on `127.0.0.1`. Find and stop conflicting
processes:

```bash
ss -tlnp | grep -E '7354|7355|7356|7357|7358'
# or
fuser 7354/tcp 7355/tcp
kill <PID>
```

### Steam Deck / SteamOS 3.x

The AppImage runs on SteamOS 3.x (Arch-based, x86-64, glibc 2.37+) without
modification. Refer to
[linux-steamos-requirements.md](linux-steamos-requirements.md) for the
complete Steam Deck installation guide, controller navigation expectations,
and verification checklist required for the Steam Deck Verified tier.

---

## CI secrets and rotation procedures

All secrets live in **GitHub → Settings → Secrets and variables → Actions → Secrets**.
Variables (non-secret, visible in logs) live under **→ Variables**.

### Apple secrets (macOS signing and notarisation)

These are **org-level** secrets on `outrightmental`, shared across repos. Their
names deliberately differ from the environment variables Tauri reads: the org
names describe the *credential*, the env vars are dictated by the *tool*. The
release workflow maps one onto the other in its step `env:` blocks.

| Org secret | Env var it supplies | Contents | Expiry |
|------------|---------------------|----------|--------|
| `MACOS_CODESIGN_CERT_BASE64` | `APPLE_CERTIFICATE` | Base64-encoded Developer ID Application `.p12` certificate | Certificates expire after 5 years |
| `MACOS_CODESIGN_CERT_PASSWORD` | `APPLE_CERTIFICATE_PASSWORD` | Passphrase for the `.p12` file | No expiry |
| `APPLE_ID` | `APPLE_ID` | Apple ID email of the dedicated notarisation account | No expiry |
| `APPLE_ID_PASSWORD` | `APPLE_PASSWORD` | App-specific password for the Apple ID | Apple revokes app-specific passwords periodically; rotate when prompted |
| `APPLE_TEAM_ID` | `APPLE_TEAM_ID` | 10-character Apple Developer Team ID | Permanent (tied to the developer account) |

There is **no `APPLE_SIGNING_IDENTITY` secret.** The identity string
(`Developer ID Application: NAME (TEAMID)`) is a property of the certificate, so
CI reads it back out of the keychain with `security find-identity` after importing
the `.p12` and exports it via `GITHUB_ENV`. Keeping a second secret in sync with
the first only creates a way for them to disagree — and a typo'd identity is
invisible until Tauri fails with "no identity found". Set it by hand only for
**local** signing (see the `export` block earlier in this document).

**Obtaining a certificate:**

1. Log in to [developer.apple.com](https://developer.apple.com) as the team admin.
2. Navigate to **Certificates, Identifiers & Profiles → Certificates**.
3. Click **+** and choose **Developer ID Application**. (A Mac Development or
   Apple Distribution certificate will *not* notarise — CI rejects it.)
4. Generate a CSR with Keychain Access, upload it, and download the resulting `.cer` file.
5. Double-click the `.cer` to import it into Keychain Access.
6. In Keychain Access, find the imported certificate, right-click → **Export** → save as a `.p12` file with a strong passphrase.
7. Base64-encode it: `base64 -i certificate.p12 | pbcopy`
8. Store the result as the `MACOS_CODESIGN_CERT_BASE64` org secret.
9. Store the passphrase as `MACOS_CODESIGN_CERT_PASSWORD`.

**Obtaining an app-specific password:**

1. Sign in to [appleid.apple.com](https://appleid.apple.com).
2. Navigate to **Sign-In and Security → App-Specific Passwords**.
3. Click **+**, name it `convsim-notarise-ci`, and copy the generated password.
4. Store it as the `APPLE_ID_PASSWORD` org secret.

**Rotation procedure (certificate expiry):**

1. Generate a new Developer ID Application certificate on developer.apple.com (step above).
2. Update `MACOS_CODESIGN_CERT_BASE64` and `MACOS_CODESIGN_CERT_PASSWORD` in org secrets.
3. Nothing else to update — CI re-derives the signing identity from the new certificate.
4. Run the **Release preflight** workflow to confirm every credential is present,
   then trigger a build to confirm signing and notarisation succeed.
5. Document the rotation date in the compliance register (`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`).

**Rotation procedure (app-specific password revoked by Apple):**

1. Generate a new app-specific password on appleid.apple.com.
2. Update `APPLE_ID_PASSWORD` in org secrets.
3. Verify that a notarisation run in CI completes without authentication errors.

---

### Windows secrets (Authenticode signing)

Signing uses **Google Cloud KMS + jsign** (org-level secrets). The legacy PFX
secrets remain recognised as a fallback.

| Secret | Level | Contents | Expiry |
|--------|-------|----------|--------|
| `GCP_SA_KEY_JSON` | Org | GCP service-account key JSON with KMS signing permissions | Rotate on compromise or per org policy |
| `GCP_KMS_KEY` | Org | Fully-qualified Cloud KMS key resource path | Permanent (update on key rename) |
| `WINDOWS_CODESIGN_CERT` | Org | Base64-encoded PEM certificate chain (leaf first) | 1–3 years depending on CA and cert type |
| `WINDOWS_SIGN_CERT_PFX` | Repo | Base64-encoded PFX file (legacy fallback) | OV: 1–3 yr; EV: 1–2 yr |
| `WINDOWS_SIGN_CERT_PASSWORD` | Repo | PFX passphrase (legacy fallback) | No expiry |

**Setup and rotation:** See [`publishing/WINDOWS_CODE_SIGNING.md`](../publishing/WINDOWS_CODE_SIGNING.md)
for the full CSR flow, Cloud KMS configuration, and rotation runbook.

**Rotation procedure summary (KMS path):**

1. If the *certificate* expires but the *KMS key version* is unchanged: issue a new cert
   against the same key version, update `WINDOWS_CODESIGN_CERT`.
2. If the *KMS key version* is rotated: create a new key version, issue a new cert
   against it, update `WINDOWS_CODESIGN_CERT`. The key-version pinning logic in
   `scripts/jsign-sign.ps1` automatically selects the new version.
3. Trigger a dispatch build and confirm the "Verify Windows Authenticode signature" step passes.
4. Document the rotation date in the compliance register.

---

### Optional secrets

| Secret | Contents | Used by |
|--------|----------|---------|
| `VIRUSTOTAL_API_KEY` | VirusTotal Public API v3 key | Malware scan step in `release.yml` and `desktop-distro.yml` |

**VirusTotal setup:**

1. Create a free account at [virustotal.com](https://www.virustotal.com).
2. Navigate to your profile → **API Key**.
3. Copy the key and add it as `VIRUSTOTAL_API_KEY` in repository secrets.
4. Free tier: 4 file uploads/minute, 500/day.  The malware scan step is
   non-blocking — VirusTotal detections on freshly compiled Rust/Tauri
   binaries are often heuristic false positives.  Review results manually
   and submit false-positive reports through the VirusTotal partner portal
   or your AV vendor if detections appear on signed release builds.

**Rotation procedure:**

1. Go to your VirusTotal profile → **API Key** → **Regenerate**.
2. Update `VIRUSTOTAL_API_KEY` in repository secrets.

---

## Cross-platform differences summary

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Installer format | `.dmg` | `.exe` (NSIS), `.msi` | `.AppImage`, `.deb` |
| Code signing | Apple Developer ID | EV or OV certificate | Not required |
| Runtime warning | Gatekeeper dialog | SmartScreen dialog | None |
| WebView engine | WKWebView (Safari) | WebView2 (Chromium) | WebKitGTK |
| Microphone prompt | System Settings | Windows Security | `xdg-desktop-portal` |
| Data directory | `~/Library/Application Support/com.outrightmental.convsim/` | `%LOCALAPPDATA%\outrightmental\convsim\` | `$XDG_DATA_HOME/convsim/` |
| Dev script | `./scripts/dev.sh` | `.\scripts\dev.ps1` | `./scripts/dev.sh` |
| First-run check | `./scripts/first-run-check.sh` | `.\scripts\first-run-check.ps1` | `./scripts/first-run-check.sh` |

### WebKit differences

The WebView engine varies by platform, which can surface subtle rendering and
API differences:

- **macOS (WKWebView):** uses the Safari rendering engine. Ensure Web Audio API
  and `getUserMedia` behave as expected in Safari.
- **Windows (WebView2 / Chromium-based):** closest to Chrome. Most modern Web
  APIs work without polyfills.
- **Linux (WebKitGTK):** an older Chromium-adjacent engine; some newer Web APIs
  may be unavailable. Test voice input on real hardware.

### llama.cpp binary

The `runtimes/llama_cpp/download-runtime.sh` script downloads a pre-built
`llama-server` binary for the current platform. Release builds bundle a
native Windows x64 binary — no WSL2 or manual build step is needed for
end-user installs.

For contributor builds on Windows, run the PowerShell equivalent:

```powershell
.\runtimes\llama_cpp\download-runtime.ps1
```

See [runtimes/llama_cpp/README.md](../runtimes/llama_cpp/README.md) for more
details.
