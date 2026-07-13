---
title: "Developer install (run from source)"
description: "Clone the repository and run the full Conversation Simulator platform locally — for contributors and anyone who wants full control."
sidebar:
  order: 9
---

This is the contributor path: clone the source and run the dev services
locally. If you just want to use the app, follow the
[installation guide](/start/install/) instead.

---

## Extra requirements

In addition to the [system requirements](/start/install/#system-requirements):

| Requirement | Minimum |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 LTS or newer |

---

## 0. Run the first-run check (optional)

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

## 1. Install system dependencies

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

## 2. Clone the repository

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
```

## 3. Run setup

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

## 4. Start local dev

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

## 5. Open the app

Navigate to <http://127.0.0.1:7354> in your browser. The home screen shows the status of each service and whether a model is loaded.

## 6. Set up a local model

On first run the app shows the **welcome screen**. Click **Set me up** to
download and configure the recommended model, or expand **Advanced options**
to use Ollama or a custom GGUF file.

The model manager shows curated models with license, size, and hardware
requirements. You must accept the license before a download begins. Downloads
are verified against their SHA-256 checksum before loading.

See [Choosing how to run the AI](/play/ai-engine/) for model recommendations
by hardware and all runtime options.

## 7. Verify the installation

Run the offline smoke test to confirm no service makes outbound network calls during play. The smoke test ships as the `convsim` CLI (`@convsim/cli`), which must be built once before first use:

```bash
pnpm --filter @convsim/cli build
npx convsim offline-smoke-test packs/official/job-interview-basic
```

The command exits 0 on success and prints an actionable error if any subsystem attempted an external connection during the scripted play session.

---

## Next steps

- [Contributing](/project/contributing/) — contribution paths and the PR checklist
- [Architecture](/reference/architecture/) — how the services fit together
- [Offline smoke tests](/dev/offline-smoke-tests/) — the network-guard harness in depth
