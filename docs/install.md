<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Installation guide

Conversation Simulator runs entirely on your computer — no cloud inference, no telemetry. You need a local model before any conversation can start; the app downloads it on first run after you accept its license.

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
| OS | macOS 13+, Ubuntu 22.04+, Windows 10 | macOS 12 Monterey is no longer supported (app minimum is macOS 13) |
| CPU | Any 64-bit x86 or Apple Silicon | Apple Silicon recommended for CPU inference |
| RAM | 8 GB | 16 GB recommended for standard-tier models |
| GPU VRAM | 0 GB (CPU fallback available) | 4 GB+ for starter model; see [local-models.md](local-models.md) |
| Disk | 20 GB free | 3–15 GB for model weights plus app data |
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

Navigate to <http://127.0.0.1:7354> in your browser. The home screen shows the status of each service and whether a model is loaded.

### 6. Set up a local model (first run)

On first run the app shows the **welcome screen**. Click **Set me up**. The
app downloads and configures the recommended model automatically.

Alternatively, expand **Advanced** (*use Ollama or a local GGUF file*) on the
welcome screen to use Ollama or a custom GGUF file. See [local-models.md](local-models.md) for model
recommendations by hardware and all runtime options.

### 7. Verify the installation

Run the offline smoke test to confirm no service makes outbound network calls during play. The smoke test ships as the `convsim` CLI (`@convsim/cli`), which must be built once before first use:

```bash
pnpm --filter @convsim/cli build
npx convsim offline-smoke-test packs/official/job-interview-basic
```

The command exits 0 on success and prints an actionable error if any subsystem attempted an external connection during the scripted play session.

---

## Beta builds — direct-download channel

Beta builds are published to GitHub Releases as versioned pre-releases (e.g.
`v0.1.0-beta.1`).  They are distinct from the Steam beta branch (covered by
the Steam depot workflow).

### In-app update notice

The desktop app checks for a new beta on launch and shows a non-intrusive
banner on the home screen when one is found.  The banner never appears during
an active conversation session.  Click **View notes** to open the release page,
or **Install** to open it and download the new build.  The check is skipped
silently when you are offline.

### SmartScreen and Gatekeeper warnings (beta builds before signing certs land)

Beta builds may be unsigned until code-signing certificates are provisioned
(tracked in [#235](https://github.com/outrightmental/ConversationSimulator/issues/235)).
Both macOS Gatekeeper and Windows Defender SmartScreen will warn about unverified
publishers.  Once #235 ships, these warnings disappear automatically.

**macOS — Gatekeeper bypass for unsigned beta builds:**

1. Download the `.dmg` and open it.
2. Drag **Conversation Simulator** to `/Applications`.
3. Do **not** double-click the app directly — right-click (or Control-click)
   the icon → **Open** → click **Open** in the dialog.
4. Alternatively, in **System Settings → Privacy & Security → Security**
   scroll down and click **Open Anyway** after the first blocked launch.

Once signed and notarised (#235), the app opens normally without any bypass.

**Windows — SmartScreen bypass for unsigned beta builds:**

1. Run the `.exe` installer.
2. If SmartScreen shows "Windows protected your PC", click **More info**.
3. Click **Run anyway**.

Once signed with an EV code-signing certificate (#235), SmartScreen displays
the verified publisher name instead of this warning.

**Linux — no bypass needed:**

The `.AppImage` is not code-signed at the OS level.  Mark it executable and
run it directly:

```bash
chmod +x conversation-simulator_<version>_amd64.AppImage
./conversation-simulator_<version>_amd64.AppImage
```

### Rollback

Every beta release remains permanently downloadable from its versioned release
page (e.g., `releases/tag/v0.1.0-beta.1`).  To roll back:

1. Download the installer from the previous versioned release page.
2. Install over the current version — the NSIS installer and macOS DMG both
   support in-place downgrades.
3. Data created in a newer beta is forward-compatible with older betas at the
   same schema version (see [schemas/VERSIONING.md](../schemas/VERSIONING.md)).

---

## Path B — Steam

Install **Conversation Simulator** from Steam on Windows, macOS, Linux, or Steam
Deck. Steam handles installation and updates; there is nothing to download by hand
and no checksum to verify.

The Steam build is Authenticode-signed on Windows, signed and notarised on macOS,
and bundles the llama.cpp AI engine, so the app is standalone — your first
conversation can start while the model is still downloading.

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

| Path | Purpose |
|---|---|
| `~/.convsim/db/` | Session database (SQLite) |
| `~/.convsim/data/` | Exported data and pack cache |
| `~/.convsim/logs/` | Runtime logs |
| `~/.convsim/models/llm/` | Downloaded model weights |

Override any of these with environment variables: `CONVSIM_DB_DIR`, `CONVSIM_DATA_DIR`, `CONVSIM_LOG_DIR`, `CONVSIM_MODELS_DIR`.

---

## Next steps

- [Quickstart](quickstart.md) — run your first conversation
- [Local models](local-models.md) — choose a model for your hardware
- [Troubleshooting](troubleshooting.md) — common setup problems
- [README](../README.md) — project overview
