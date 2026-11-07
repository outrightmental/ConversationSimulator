<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Installation guide

Conversation Simulator runs entirely on your computer — no cloud inference, no telemetry. You need a local model before any conversation can start; the app downloads it on first run and shows its size and license before you begin.

Two install paths are available:

- **Path A — build from source (free):** clone the repository at a release tag and build it yourself. This is the free path, and the only one served from GitHub.
- **Path B — Steam ($9.99):** the same software, packaged and ready to run — code-signed, notarized, auto-updating, with the AI engine bundled.

> **There are no installers to download from GitHub.** Steam is the only channel
> that ships prebuilt binaries. The GitHub releases page carries release notes and
> source tags only — no `.dmg`, `.exe`, `.msi`, `.deb`, or `AppImage`.

---

## System requirements

| Requirement | Minimum | Notes |
|---|---|---|
| OS | macOS 14+, Ubuntu 22.04+, Windows 10 (build 19041 or newer) | macOS 13 Ventura and earlier are not supported: the bundled AI engine needs macOS 14 |
| CPU | Any 64-bit x86 or Apple Silicon | On macOS, Apple Silicon is recommended: the AI engine uses Metal acceleration there. The Steam build for macOS is built for Apple Silicon only, so an Intel Mac needs a source build |
| RAM | 8 GB | 16 GB recommended for standard-tier models |
| GPU VRAM | 0 GB (CPU fallback available) | 4 GB+ for starter model; see [local-models.md](local-models.md) |
| Disk | 5 GB free | 20 GB recommended. Model weights take 3–15 GB depending on tier, plus app data |
| Python | 3.10 or newer | Path A only |
| Node.js | 18 LTS or newer | Path A only |

---

## Path A — developer install

### 0. Run the first-run check (optional)

Before installing anything, confirm your system meets the requirements:

**macOS / Linux:**

```bash
./scripts/first-run-check.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\first-run-check.ps1
```

The check reports OS version, CPU architecture, RAM, disk space, audio device
availability, and port conflicts. All items marked `FAIL` must be resolved
before the app will work; `WARN` items are advisory.

### 1. Install system dependencies

**Python 3.10+**

- macOS: `brew install python@3.11`
- Ubuntu/Debian: `sudo apt install python3.11 python3.11-venv`
- Windows: download from <https://www.python.org/downloads/>

**Node.js 18 LTS+**

- All platforms: download from <https://nodejs.org/>
- Or use a version manager: `nvm install 18` / `fnm install 18`

**pnpm (recommended) or npm**

pnpm is faster for a monorepo workspace. npm (bundled with Node.js) also works.

```bash
npm install -g pnpm
```

### 2. Clone the repository

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
```

### 3. Run setup

**macOS / Linux:**

```bash
./scripts/setup.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\setup.ps1
```

The setup script:

- Confirms Python 3.10+ and Node.js 18+ are present.
- Installs frontend packages (`pnpm install` or `npm install`).
- Creates the Python virtual environment for `convsim-core` under `services/convsim-core/.venv/`.
- Creates local data directories under `~/.convsim/`.

It does **not** modify global state or download model files. No model weights are bundled.

### 4. Start local dev

**macOS / Linux:**

```bash
./scripts/dev.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\dev.ps1
```

This starts the browser UI and the API server and prints their URLs. If a port is already occupied the script reports which process is blocking it.

| Service | URL | Responsibility |
|---|---|---|
| convsim-ui | <http://127.0.0.1:7354> | Browser UI (dev mode) |
| convsim-core | <http://127.0.0.1:7355> | Main server, API, WebSocket |

Press **Ctrl-C** to stop everything cleanly. Logs are written to `~/.convsim/logs/`.

### 5. Open the app

Navigate to <http://127.0.0.1:7354> in your browser. On a fresh install the app opens the welcome screen (next step). After setup, the home screen shows whether the AI engine, the model and the voice services are ready.

### 6. Set up a local model (first run)

On first run the app shows the **welcome screen**. Click **Set me up**. The
app downloads and configures the recommended model automatically.

Alternatively, expand **Advanced: use Ollama or a local GGUF file** on the
welcome screen to use Ollama or a custom GGUF file. See [local-models.md](local-models.md) for model
recommendations by hardware and all runtime options.

### 7. Verify the installation

Run the offline smoke test to confirm no service makes outbound network calls during play. The smoke test ships as the `convsim` CLI (`@convsim/cli`). Build it once, together with the pack loader it depends on, then run it with `node`:

```bash
pnpm --filter @convsim/pack-loader build
pnpm --filter @convsim/cli build
node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic
```

The command exits 0 on success and prints an actionable error if any subsystem attempted an external connection during the scripted play session.

---

## Updates and rollback

**On Steam,** Steam handles updates; the Steam build has no in-app updater.
Pre-release builds go to the Steam **beta** branch first (opt in from the app's
Properties → Betas in your Steam library). If a release has to be withdrawn, we
set the previous build live again and Steam delivers it; there is nothing for
you to do.

There is no direct-download channel: no installers or beta builds are published
on GitHub, so the only prebuilt binaries come through Steam.

**From source,** update by checking out a newer release tag and rebuilding; roll
back by checking out an earlier one. Data created in a newer version is
forward-compatible with older versions at the same schema version (see
[schemas/VERSIONING.md](../schemas/VERSIONING.md)).

### SmartScreen and Gatekeeper warnings (source builds)

A build you make yourself is not code-signed, so macOS Gatekeeper and Windows
Defender SmartScreen warn about an unverified publisher. The signed builds are
the ones distributed through Steam.

**macOS:** do not double-click the app directly. Right-click (or Control-click)
the icon → **Open** → click **Open** in the dialog. Or, in **System Settings →
Privacy & Security → Security**, scroll down and click **Open Anyway** after the
first blocked launch.

**Windows:** if SmartScreen shows "Windows protected your PC", click **More
info**, then **Run anyway**.

**Linux:** no bypass needed. If you built the desktop app (see
[platform-notes.md](platform-notes.md)), Tauri writes the AppImage to
`apps/desktop/src-tauri/target/release/bundle/appimage/` and names it after the
product, with a space: `Conversation Simulator_<version>_amd64.AppImage`. Mark
it executable and run it:

```bash
cd apps/desktop/src-tauri/target/release/bundle/appimage
chmod +x "Conversation Simulator_"*.AppImage
./"Conversation Simulator_"*.AppImage
```

---

## Path B — Steam

Install **Conversation Simulator** from Steam on Windows, macOS (Apple Silicon),
Linux, or Steam Deck. Steam handles installation and updates; there is nothing to
download by hand and no checksum to verify.

The Steam build is Authenticode-signed on Windows, signed and notarised on macOS,
and bundles the llama.cpp AI engine, so there is nothing to install separately.

### Why there is no GitHub installer

Publishing prebuilt binaries on GitHub would mean shipping a second, unsigned
distribution channel that nobody pays for and nobody can auto-update. The project
serves the free path as *source you build* and the paid path as *binaries we sign
and support*. So:

- GitHub releases → release notes and a source tag. Nothing to download.
- Steam → the prebuilt, signed, standalone binaries.

The release workflow enforces this: it publishes no binary assets, and its build
output goes to the Steam depot.

---

> For platform-specific details (code signing, Gatekeeper, SmartScreen,
> WebView2, audio permissions), see [platform-notes.md](platform-notes.md).

---

## Data locations

The desktop app keeps its data under one folder in your platform's local
app-data location:

| Platform | Data folder |
|---|---|
| macOS | `~/Library/Application Support/com.outrightmental.convsim/` |
| Windows | `%LOCALAPPDATA%\com.outrightmental.convsim\` |
| Linux and Steam Deck | `~/.local/share/com.outrightmental.convsim/` (under `$XDG_DATA_HOME` if that is set) |

Inside it:

| Folder | Purpose |
|---|---|
| `db/` | Session database (SQLite) |
| `data/` | General app data. Raw microphone recordings go to `data/audio/` only while **Save raw audio recordings (advanced)** is turned on; the switch sits under **Show advanced** at the bottom of Settings |
| `logs/` | Runtime logs |
| `models/llm/` | Downloaded model weights |
| `packs/` | Installed scenario packs: copies of the official packs, packs you import, and the Creator Workbench's `local-dev/` packs |
| `exports/` | Created and listed in Settings, but nothing is written here yet: the **Export** button in Settings hands you the session as a download named `session-<id>.json` |
| `cache/` | Created and listed in Settings, but nothing is written here yet: the voice synthesis cache goes to `~/.convsim/tts_cache/` |
| `crashes/` | Crash bundles and diagnostics bundles |

**Settings → Local folders** lists all of these except `db/` (as Data, Logs,
Models, Packs, Exports, Cache and Crash bundles), shows the exact paths and
opens them. Move single folders with `CONVSIM_DB_DIR`, `CONVSIM_DATA_DIR`,
`CONVSIM_LOG_DIR`, `CONVSIM_MODELS_DIR`, `CONVSIM_PACKS_DIR`, `CONVSIM_EXPORTS_DIR`,
`CONVSIM_CACHE_DIR` and `CONVSIM_CRASH_BUNDLES_DIR`; the desktop shell passes them
through to convsim-core. `CONVSIM_DATA_ROOT` moves the whole tree, but only when
convsim-core runs without the desktop shell: the shell always sets it to the
folder above. If you run the services from source without the desktop shell
(Path A), convsim-core uses `%LOCALAPPDATA%\outrightmental\convsim\` on Windows
and `~/.local/share/convsim/` on Linux instead. Data from older builds that used
`~/.convsim/` is copied to the new folder on first launch; model weights are not,
so download the model again.

A few things still live under `~/.convsim/`: the AI engine that a source build
downloads on first run (`~/.convsim/bin/`; the Steam build has it bundled), the
voice input and voice activity detection models (`~/.convsim/models/stt/` and
`~/.convsim/models/vad/`, where the download scripts under `runtimes/` put them)
and the voice synthesis cache (`~/.convsim/tts_cache/`). When you run from source
with `scripts/dev.sh` or `scripts/dev.ps1`, logs go to `~/.convsim/logs/` as well
unless you set `CONVSIM_LOG_DIR`.

---

## Next steps

- [Quickstart](quickstart.md) — run your first conversation
- [Local models](local-models.md) — choose a model for your hardware
- [Troubleshooting](troubleshooting.md) — common setup problems
- [README](../README.md) — project overview
