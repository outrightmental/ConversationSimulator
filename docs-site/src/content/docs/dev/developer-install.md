---
title: "Developer install (run from source)"
description: "Clone the repository and run the full Conversation Simulator platform locally — for contributors and anyone who wants full control."
sidebar:
  order: 9
verified_against: v0.4.0
---

This is the contributor path: clone the source and run the dev services
locally. If you just want to use the app, follow the
[installation guide](/start/install/) instead.

---

## Extra requirements

In addition to the [system requirements](/start/install/#system-requirements):

| Requirement | Minimum | Needed for |
|---|---|---|
| Python | 3.10 or newer | `convsim-core` |
| Node.js | 20 LTS or newer | the web UI, packages and scripts |
| pnpm | 9 or newer | installing the workspace |
| Rust | 1.80 or newer | the desktop app only |

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
availability, and port conflicts on the five service ports (7354 to 7358). It
also reports the installed Python and Node.js versions for the developer path
(the Node.js item passes on 18 or newer; see step 1).
All items marked `FAIL` must be resolved before the app will work; `WARN` items
are advisory.

## 1. Install system dependencies

**Python 3.10+**

- macOS: `brew install python@3.11`
- Ubuntu/Debian: `sudo apt install python3.11 python3.11-venv`
- Windows: download from <https://www.python.org/downloads/>

**Node.js 20 LTS+**

- All platforms: download from <https://nodejs.org/>
- Or use a version manager: `nvm install 20` / `fnm install 20`

The locked dependencies need Node.js 20 or newer. `better-sqlite3`, which the
pack loader and the `convsim` CLI load, lists Node 20.x and 22.x through 26.x
in its `engines` field, and the docs site depends on packages that need 20.19
or newer. CI runs Node 24. The first-run check and the setup scripts still
accept any Node.js 18 or newer. On 18 or 19, pnpm warns `Unsupported engine`
at the start of the install and carries on, but `better-sqlite3` has no
prebuilt binary for those versions, so the install then compiles it from source
with node-gyp. That needs Python and a C++ build toolchain, and without them
the install fails.

**pnpm 9 or newer**

The workspace needs pnpm; npm cannot install it. The packages refer to each
other with the `workspace:` protocol, which npm does not support, so
`npm install` stops at once with `EUNSUPPORTEDPROTOCOL`. CI installs with pnpm
too. The lockfile is pnpm 9 format, so use pnpm 9 or newer. npm, which comes
with Node.js, can install pnpm for you:

```bash
npm install -g pnpm
```

**Rust (desktop app only)**

The browser UI does not need Rust. To run the Tauri desktop shell, install the
toolchain with rustup (Rust 1.80 or newer) and the Tauri v2 system dependencies
for your platform. See [Desktop app](#desktop-app-optional) below.

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

- Confirms Python 3.10+ and Node.js are present. Its Node.js check only
  requires 18, not the 20 the workspace needs (see step 1).
- Installs frontend packages with `pnpm install`. If pnpm is not on your
  `PATH` it runs `npm install` instead, which fails on this workspace, so
  install pnpm first (step 1).
- Creates the Python virtual environment for `convsim-core` under
  `services/convsim-core/.venv/` and installs `convsim-core` with its test
  dependencies into it. On macOS and Linux it first installs
  `packages/prompt-composer`, which `convsim-core` depends on.
- Creates `~/.convsim/logs/`, `~/.convsim/data/` and `~/.convsim/db/`
  (see [Where data lives](#where-data-lives)).

It does **not** modify global state or download model files. No model weights are bundled.

**Windows note.** `setup.ps1` does not install `packages/prompt-composer`, and
pip cannot fetch it on its own because it is not on PyPI (`convsim-core`
requires it under the name `convsim-prompt`). pip reports
`No matching distribution found for convsim-prompt` and installs nothing, but
the script carries on and still prints `Setup complete.`, and `dev.ps1` then
stops with `uvicorn not found`. Install the package into the virtual
environment the script created, then rerun setup:

```powershell
.\services\convsim-core\.venv\Scripts\pip install -e packages\prompt-composer
.\scripts\setup.ps1
```

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

Press **Ctrl-C** to stop everything cleanly. Logs are written to
`~/.convsim/logs/` unless `CONVSIM_LOG_DIR` is set.

## 5. Open the app

Navigate to <http://127.0.0.1:7354> in your browser. On a fresh profile the app
opens on the welcome screen (step 6). Once a model is set up, the home screen
has a **Status** list with **AI engine**, **AI model** (the model's name once
one is installed, otherwise *Not installed*), **Voice input**, **Voice output**,
**Network required to play**, and **Packs**.

## 6. Set up a local model

On first run the app shows the **welcome screen**. Click **Set me up** to
download and load the recommended model. The card states the model's size and
license, and the download starts as soon as you click. To use something else,
expand **Advanced: use Ollama or a local GGUF file** and choose **Browse Ollama
models** or **Use a GGUF file**.

The model manager (**Set up your model**) offers the same three choices: the
recommended model with its name, size, license and VRAM requirement, **Use
existing Ollama model**, and **Use a local GGUF file**. Installing the
recommended model from there goes through a **Confirm model install** step
that also shows the SHA-256 checksum, and nothing downloads until you click
**Confirm & install**. That step's **Storage path** row still reads
`~/.convsim/models/llm/<id>.gguf`, but the file is written under the platform
data root described in [Where data lives](#where-data-lives). Every registry
download is checked against its SHA-256 checksum when it finishes; a file that
does not match is deleted.

See [Choosing how to run the AI](/play/ai-engine/) for model recommendations
by hardware and all runtime options.

## 7. Verify the installation

Run the offline smoke test to confirm that a scenario pack loads and plays
without any outbound network access. The smoke test ships as the `convsim` CLI
(`@convsim/cli`). Build it once, together with the pack loader it depends on,
then run it with `node`:

```bash
pnpm --filter @convsim/pack-loader build
pnpm --filter @convsim/cli build
node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic
```

Everything happens inside the CLI's own process. It blocks every outbound TCP
connection that process opens to anything other than localhost, loads the pack,
plays a short scripted session of its first scenario with the CLI's built-in
fake runtime and builds a local debrief. No model is loaded and the services
you started in step 4 are not contacted. The command exits 0 when nothing tried
to connect out. It exits 1 if a connection was blocked, naming the subsystem
and address, or if the pack failed to load.

To check that `convsim-core` itself makes no outbound calls during a session,
run the acceptance test in
[Offline smoke tests](/dev/offline-smoke-tests/#2-run-the-offline-smoke-test-against-the-live-server).

## 8. Run the tests

These are the local equivalents of the CI jobs you will reach for most:

```bash
# TypeScript: build the two shared packages first, then typecheck and test
pnpm --filter @convsim/shared-types build
pnpm --filter @convsim/scenario-schema build
pnpm test:types
pnpm --filter @convsim/web test
pnpm --filter @convsim/pack-loader test
pnpm --filter @convsim/cli test

# Python: the virtual environment from setup already has pytest
cd services/convsim-core && .venv/bin/python -m pytest
```

Two more Python suites live at the repository root and run with the same
virtual environment. The acceptance suite is a CI job. The onboarding e2e suite
is the release gate for the first-run flow: `release-smoke.yml` runs all of it,
and pull requests that touch that flow run a fast subset.

```bash
# from the repository root
services/convsim-core/.venv/bin/python -m pytest tests/acceptance/ -v
services/convsim-core/.venv/bin/python -m pytest e2e/onboarding/ -v
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python` in both
blocks. The smoke check, shell script linting, schema validation and pack validation
commands are in [Contributing](/project/contributing/#running-ci-locally).

---

## Where data lives

Of the `~/.convsim/` folders that setup creates, only `logs/` is used in dev:
`dev.sh` and `dev.ps1` start `convsim-core` with `CONVSIM_LOG_DIR` pointing at
`~/.convsim/logs/`. Everything else `convsim-core` writes (the session
database, settings, imported packs, downloaded models, exports, cache) goes
under the platform data directory:

| Platform | Data root |
|---|---|
| Linux / Steam Deck | `$XDG_DATA_HOME/convsim`, or `~/.local/share/convsim` when unset |
| macOS | `~/Library/Application Support/com.outrightmental.convsim` |
| Windows | `%LOCALAPPDATA%\outrightmental\convsim` |

Its subfolders are `db/`, `data/`, `packs/`, `models/llm/`, `exports/`,
`cache/`, `crashes/` and `logs/`.

`convsim-core` reads its settings from `CONVSIM_*` environment variables, or
from a `.env` file in `services/convsim-core/` (the directory the dev scripts
start it from). The one exception is `CONVSIM_DATA_ROOT`, which is resolved
before the settings load, so it only works as a real environment variable. The
ones a contributor reaches for:

| Variable | Effect |
|---|---|
| `CONVSIM_DATA_ROOT` | Move the whole data root somewhere else. Environment variable only, not `.env`. |
| `CONVSIM_LOG_DIR`, `CONVSIM_DATA_DIR`, `CONVSIM_DB_DIR` | Override one directory. The setup scripts create whichever of these you set. |
| `CONVSIM_DEV_DEBUG=true` | DEBUG-level logging. |
| `CONVSIM_EDITION=demo` | Run the demo edition (below). |

## Run the demo edition

The Steam demo is the same build narrowed to one model download and five
conversations. To see it locally, start the engine with `CONVSIM_EDITION=demo`.
The web UI adopts the engine's answer from `/api/health`, so no rebuild is
needed.

**macOS / Linux:**

```bash
CONVSIM_EDITION=demo ./scripts/dev.sh
```

**Windows (PowerShell):**

```powershell
$env:CONVSIM_EDITION = "demo"; .\scripts\dev.ps1
```

In the demo the welcome screen offers only **Set me up**, and the Library,
Logbook and Creator Workbench are hidden.

## Desktop app (optional)

The browser UI covers most contributor work. To run the Tauri desktop shell,
install Rust 1.80 or newer and the Tauri v2 system dependencies, finish setup,
then run:

**macOS / Linux:**

```bash
./scripts/dev-desktop.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\dev-desktop.ps1
```

The script starts `convsim-core` on port 7355, then runs `tauri dev`, which
starts the web dev server on port 7354 and opens the native window. Press
**Ctrl-C** to stop everything.

---

## Next steps

- [Contributing](/project/contributing/) — contribution paths and the PR checklist
- [Architecture](/reference/architecture/) — how the services fit together
- [Offline smoke tests](/dev/offline-smoke-tests/) — the network-guard harness in depth
