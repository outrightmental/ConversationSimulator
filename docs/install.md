<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Installation guide

Conversation Simulator runs entirely on your computer — no cloud inference, no telemetry. You need a local model before any conversation can start; the app downloads it on first run after you accept its license.

Two install paths are available:

- **Path A — developer install:** clone the source and run the dev services locally. Suitable for contributors and users who want full control.
- **Path B — alpha app install:** download and run the pre-built desktop application (see below). Note that the alpha build wraps the web UI in a native window; the backend must still be started separately until the sidecar is bundled.

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

### 6. Install a local model

On first run the home screen shows a **"No model loaded"** banner. Click **Install model** or go to **Settings → Models**.

The in-app model manager lists curated models with license, size, and hardware requirements. You must accept the license before a download begins. The downloaded file is verified against its SHA-256 checksum before loading.

See [local-models.md](local-models.md) for model recommendations by hardware.

### 7. Verify the installation

Run the offline smoke test to confirm no service makes outbound network calls during play. The smoke test ships as the `convsim` CLI (`@convsim/cli`), which must be built once before first use:

```bash
pnpm --filter @convsim/cli build
npx convsim offline-smoke-test packs/official/job-interview-basic
```

The command exits 0 on success and prints an actionable error if any subsystem attempted an external connection during the scripted play session.

---

## Path B — alpha app install

When a release is published on the [GitHub releases page](https://github.com/outrightmental/ConversationSimulator/releases):

### 1. Pre-flight check

Run the first-run check before downloading anything:

```bash
./scripts/first-run-check.sh        # macOS / Linux
.\scripts\first-run-check.ps1       # Windows PowerShell
```

### 2. Download and verify

Download the installer for your platform:

| Platform | File |
|---|---|
| macOS (Apple Silicon) | `ConversationSimulator_<version>_aarch64.dmg` |
| macOS (Intel) | `ConversationSimulator_<version>_x64.dmg` |
| Linux (x86_64) | `conversation-simulator_<version>_amd64.AppImage` |
| Windows (x86_64) | `ConversationSimulator_<version>_x64-setup.exe` |

Verify the download against the `checksums-sha256.txt` file on the release page:

```bash
# macOS / Linux
shasum -a 256 ConversationSimulator_<version>_aarch64.dmg
```

```powershell
# Windows PowerShell
Get-FileHash "ConversationSimulator_<version>_x64-setup.exe" -Algorithm SHA256
```

### 3. Install and launch

- **macOS:** open the `.dmg` and drag the app to `/Applications`. On first
  launch, Gatekeeper may warn about an unidentified developer (alpha builds are
  unsigned). Right-click the app → **Open** → **Open** to proceed.
- **Windows:** run the `.exe` installer. SmartScreen may warn about an unrecognised
  publisher — click **More info → Run anyway**.
- **Linux:** `chmod +x *.AppImage` then run it directly. No installation needed.

### 4. Start the backend

> **Alpha limitation:** The desktop app wraps the browser UI but does not yet
> launch the backend automatically. You must start `convsim-core` in a separate
> terminal before using the app.

```bash
./scripts/dev.sh          # macOS / Linux
.\scripts\dev.ps1         # Windows PowerShell
```

Then open the desktop app. The backend sidecar will be bundled in a future
release, making this step unnecessary.

### 5. Install a local model

On first launch the app shows a **"No model loaded"** banner. Open **Settings →
Models**, accept a model license, and start the download. No model weights are
bundled with the installer.

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
