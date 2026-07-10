<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Platform notes

Platform-specific differences for building, running, and distributing
Conversation Simulator on macOS and Windows.

---

## macOS

### Supported versions

macOS 12 Monterey or newer. Apple Silicon (M1+) and Intel are both supported
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

Tauri produces a `.dmg` disk image and a `.app.tar.gz` archive.
The `.dmg` is the primary distributable for macOS.

### Code signing and Gatekeeper

Alpha builds are **not code-signed**. macOS Gatekeeper will block unsigned
apps with "Apple cannot verify this app is free from malware." To open an
unsigned build:

1. Right-click (or Control-click) the `.app` → **Open** → **Open**.
2. Or: **System Settings → Privacy & Security** → scroll down → **Open Anyway**.

For distributable builds, sign with an Apple Developer ID certificate:

```bash
# Set these before running `tauri build`:
export APPLE_CERTIFICATE="Developer ID Application: Your Name (TEAMID)"
export APPLE_CERTIFICATE_PASSWORD="keychain-password"
export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="app-specific-password"
export APPLE_TEAM_ID="TEAMID"
```

Tauri's bundler handles signing and notarisation automatically when these
environment variables are present. See
[tauri.app/distribute/sign/macos](https://tauri.app/distribute/sign/macos).

### Microphone permission

The OS shows a standard permission dialog on first use of voice input.
If denied, re-enable in **System Settings → Privacy & Security → Microphone**.

### Data directories

The desktop app uses the macOS-native application support directory so that
user data follows standard macOS conventions (visible in Finder under
`~/Library/Application Support/`) without being swept into iCloud Drive or
Time Machine's application bundles.

```
~/Library/Application Support/com.outrightmental.convsim/db/       — SQLite session database
~/Library/Application Support/com.outrightmental.convsim/data/     — exports and pack cache
~/Library/Application Support/com.outrightmental.convsim/logs/     — runtime logs
~/Library/Application Support/com.outrightmental.convsim/models/   — downloaded model weights
~/Library/Application Support/com.outrightmental.convsim/exports/  — exported transcripts
~/Library/Application Support/com.outrightmental.convsim/data/audio/  — recorded audio clips (only when "save raw audio" is enabled; off by default)
~/Library/Application Support/com.outrightmental.convsim/crashes/  — crash bundles
```

The `CONVSIM_DATA_ROOT` environment variable overrides the entire root path.

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

### Code signing (SmartScreen)

Alpha builds are **not code-signed**. Windows Defender SmartScreen will warn
"Windows protected your PC" with an **unrecognised publisher** message.
To run an unsigned build:

1. Click **More info** in the SmartScreen dialog.
2. Click **Run anyway**.

For distributable and Steam release builds, sign with an Extended Validation
(EV) or standard OV code-signing certificate using Authenticode.

#### Authenticode signing in CI (Release workflow)

The release workflow (`release.yml`) signs Windows installers automatically
when two repository secrets are present:

| Secret | Contents |
|--------|----------|
| `WINDOWS_SIGN_CERT_PFX` | Base64-encoded PFX certificate file (cert + private key) |
| `WINDOWS_SIGN_CERT_PASSWORD` | Password for the PFX file |

When the secrets are absent the build continues and produces an unsigned
installer.  Unsigned installers are blocked by SmartScreen on end-user
machines; signing is **required** before the Stage 3 private beta gate
(G3-01 in `docs/steam-mvp-scope.md`).

**Obtaining a certificate:**

1. Purchase an EV or OV code-signing certificate from DigiCert, Sectigo,
   GlobalSign, or another trusted CA.
2. Export the private key and certificate chain as a `.pfx` file.
3. Base64-encode it: `certutil -encode cert.pfx cert.b64`
4. Add the contents of `cert.b64` as the `WINDOWS_SIGN_CERT_PFX` repository
   secret (Settings → Secrets and variables → Actions → Secrets).
5. Add the PFX password as `WINDOWS_SIGN_CERT_PASSWORD`.

**Local signing:**

```powershell
# Sign a specific installer with signtool.exe (included in the Windows SDK)
signtool.exe sign `
  /f path\to\cert.pfx `
  /p <password> `
  /tr http://timestamp.digicert.com `
  /td sha256 /fd sha256 /v `
  "apps\desktop\src-tauri\target\release\bundle\nsis\ConversationSimulator_*_x64-setup.exe"
```

See [tauri.app/distribute/sign/windows](https://tauri.app/distribute/sign/windows) for
additional options including HSM/EV token signing.

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

Ubuntu 22.04 LTS is the primary test target. Other glibc-based distros
(Fedora 38+, Debian 12+, Arch) should work but are not regularly tested.

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

### Installer format

Tauri produces:
- **`.AppImage`** — portable, runs on any x86_64 Linux without installation.
- **`.deb`** — Debian/Ubuntu package for system-wide installation.

### Microphone (PipeWire / PulseAudio)

WebKit on Linux may require `xdg-desktop-portal` and a running PipeWire or
PulseAudio session for the browser `getUserMedia` permission dialog to appear.
On headless or minimal desktop environments, microphone access may silently
fail; use text-only input mode in that case.

---

## Cross-platform differences summary

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Installer format | `.dmg` | `.exe` (NSIS), `.msi` | `.AppImage`, `.deb` |
| Code signing | Apple Developer ID | EV or OV certificate | Not applicable |
| Runtime warning | Gatekeeper dialog | SmartScreen dialog | None |
| WebView engine | WKWebView (Safari) | WebView2 (Chromium) | WebKitGTK |
| Microphone prompt | System Settings | Windows Security | `xdg-desktop-portal` |
| Data directory | `~/Library/Application Support/com.outrightmental.convsim` | `%LOCALAPPDATA%\outrightmental\convsim` | `~/.local/share/convsim` |
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
`llama-server` binary for the current platform. On Windows, use WSL2 to run
this script (the binary is the Linux x86_64 build) or build llama.cpp from
source using MSVC:

```powershell
# Windows — build from source
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release
```

See [runtimes/llama_cpp/README.md](../runtimes/llama_cpp/README.md) for more
details.
