<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Installation guide

Conversation Simulator runs entirely on your computer — no cloud inference, no telemetry. You need a local model before any conversation can start; the app downloads it on first run after you accept its license.

Two install paths are available:

- **Path A — developer install:** clone the source and run the dev services locally. Suitable for contributors and users who want full control.
- **Path B — alpha app install:** download and run the pre-built desktop application (planned for a future milestone; see below).

---

## System requirements

| Requirement | Minimum | Notes |
|---|---|---|
| OS | macOS 12+, Ubuntu 22.04+, Windows 10 | |
| CPU | Any 64-bit x86 or Apple Silicon | Apple Silicon recommended for CPU inference |
| RAM | 8 GB | 16 GB recommended for standard-tier models |
| GPU VRAM | 0 GB (CPU fallback available) | 4 GB+ for starter model; see [local-models.md](local-models.md) |
| Disk | 20 GB free | 3–15 GB for model weights plus app data |
| Python | 3.10 or newer | Path A only |
| Node.js | 18 LTS or newer | Path A only |

---

## Path A — developer install

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

Run the offline smoke test to confirm no service makes outbound network calls during play:

```bash
npx convsim offline-smoke-test packs/official/job-interview-basic
```

The command exits 0 on success and prints an actionable error if any subsystem attempted an external connection during the scripted play session.

---

## Path B — alpha app install

> **Status:** The packaged desktop application is planned for a future milestone. This section describes how to install it when it becomes available.

When a release is published on the [GitHub releases page](https://github.com/outrightmental/ConversationSimulator/releases):

1. Download the installer for your platform (`.dmg` on macOS, `.exe` on Windows, `.AppImage` on Linux).
2. Open the installer and follow the prompts.
3. Launch **Conversation Simulator** from your Applications folder or Start Menu.
4. On first launch the app prompts you to install a local model. No model weights are bundled with the installer.

To verify the installer download before running it:

```bash
# macOS / Linux — replace the filename and checksum with values from the release page
shasum -a 256 ConversationSimulator-1.0.0.dmg
```

```powershell
# Windows PowerShell
Get-FileHash "ConversationSimulator-1.0.0.exe" -Algorithm SHA256
```

The expected checksum is listed on the GitHub release page alongside each download.

---

## Data locations

| Path | Purpose |
|---|---|
| `~/.convsim/db/` | Session database (SQLite) |
| `~/.convsim/data/` | Exported data and pack cache |
| `~/.convsim/logs/` | Runtime logs |
| `~/.convsim/models/llm/` | Downloaded model weights |

Override any of these with environment variables: `CONVSIM_DB_DIR`, `CONVSIM_DATA_DIR`, `CONVSIM_LOG_DIR`.

---

## Next steps

- [Quickstart](quickstart.md) — run your first conversation
- [Local models](local-models.md) — choose a model for your hardware
- [Troubleshooting](troubleshooting.md) — common setup problems
- [README](../README.md) — project overview
