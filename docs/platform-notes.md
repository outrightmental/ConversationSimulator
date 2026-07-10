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

Tauri produces a `.dmg` disk image and a `.app.tar.gz` archive.
The `.dmg` is the primary distributable for macOS.

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

See [tauri.app/distribute/sign/macos](https://tauri.app/distribute/sign/macos)
for more details on the Tauri signing process.

**Gate G3-01:** A notarised macOS build is required before Stage 3 (Steam
private beta). A Gatekeeper pass on a clean macOS install (without "Open
Anyway") is the acceptance criterion.

### Microphone permission

The OS shows a standard permission dialog on first use of voice input.
If denied, re-enable in **System Settings → Privacy & Security → Microphone**.

### Data directories

The platform data root is `~/Library/Application Support/com.outrightmental.convsim/`
(set by `convsim_core/paths.py`; passed to the sidecar as `CONVSIM_DATA_ROOT`
via the Tauri shell's `app_local_data_dir()`). Subdirectories:

```
~/Library/Application Support/com.outrightmental.convsim/
  db/       — SQLite session database
  data/     — exports and pack cache
  logs/     — runtime logs
  models/   — downloaded model weights
  exports/  — debrief exports
  crashes/  — crash bundles
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

### Code signing (SmartScreen)

Alpha builds are **not code-signed**. Windows Defender SmartScreen will warn
"Windows protected your PC" with an **unrecognised publisher** message.
To run an unsigned build:

1. Click **More info** in the SmartScreen dialog.
2. Click **Run anyway**.

For distributable builds, sign with an Extended Validation (EV) or standard
code-signing certificate. Set the Tauri signing environment variables before
building:

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY      = "path\to\private.key"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "key-password"
```

See [tauri.app/distribute/sign/windows](https://tauri.app/distribute/sign/windows).

### Antivirus false positives

Freshly compiled Rust/Tauri executables are occasionally flagged by antivirus
engines as suspicious (heuristic detection). If this happens:

1. Add the install directory to your antivirus exclusion list.
2. Submit the executable for false-positive review through your AV vendor's portal.

### Microphone permission

Windows Security prompts for microphone access on first use. Allow it when
prompted, or grant it in **Settings → Privacy & Security → Microphone**.

### Data directories

```
%USERPROFILE%\.convsim\db\      — SQLite session database
%USERPROFILE%\.convsim\data\    — exports and pack cache
%USERPROFILE%\.convsim\logs\    — runtime logs
%USERPROFILE%\.convsim\models\  — downloaded model weights
```

Override with environment variables: `CONVSIM_DB_DIR`, `CONVSIM_DATA_DIR`,
`CONVSIM_LOG_DIR`, `CONVSIM_MODELS_DIR`.

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
