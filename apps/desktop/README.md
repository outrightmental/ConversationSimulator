<!-- SPDX-License-Identifier: Apache-2.0 -->
# apps/desktop

Tauri v2 desktop wrapper for Conversation Simulator.

The desktop app wraps the `apps/web` React UI in a native OS window using
[Tauri](https://tauri.app). It manages the `convsim-core` backend as a
supervised child process and shows startup progress until the core is ready.
It does **not** bundle model weights or require cloud services — the application
is fully local.

---

## Quick start (dev mode)

```bash
# From repo root — starts convsim-core + Tauri dev window
./scripts/dev-desktop.sh          # macOS / Linux
.\scripts\dev-desktop.ps1         # Windows PowerShell
```

The script:
1. Starts `convsim-core` (Python, port 7355).
2. Runs `tauri dev`, which launches the Vite web dev server (port 7354) via
   `beforeDevCommand` and opens the native window pointed at it.

In dev mode the Vite proxy routes `/api` and `/ws` to the running core, so
the existing relative-URL client works as-is.

The browser path (`apps/web`) continues to work independently via
`./scripts/dev.sh`.

---

## Prerequisites

In addition to the base requirements from `./scripts/setup.sh` / `setup.ps1`:

- **Rust** 1.80+ (install via [rustup](https://rustup.rs/)); CI and release builds use stable
- **Tauri system dependencies** for your OS:
  - **macOS** — Xcode Command Line Tools (`xcode-select --install`)
  - **Linux** — `libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev`
    (exact package names vary by distro; see [Tauri Linux docs](https://tauri.app/start/prerequisites/))
  - **Windows** — Microsoft Visual Studio C++ Build Tools, WebView2 Runtime

After meeting the prerequisites, install npm dependencies from the repo root:

```bash
pnpm install   # installs @tauri-apps/cli into apps/desktop
```

---

## Production build

```bash
./scripts/build-core.sh                  # PyInstaller → resources/bin/convsim-core
pnpm --filter @convsim/desktop build
```

`build-core.sh` must run first: it writes the standalone `convsim-core` binary
into `src-tauri/resources/bin/`, which `bundle.resources` (`resources/**/*`)
packages into the installer. Without it the app builds but cannot start its
engine. The built installer is placed in
`apps/desktop/src-tauri/target/release/bundle/`.

In a production build the Tauri shell:
1. Locates the `convsim-core` executable (see "Executable resolution" below).
2. Spawns it bound to `127.0.0.1:7355`.
3. Sets `CONVSIM_BUNDLED_RUNTIME_DIR` to the `runtimes/` dir adjacent to the
   app bundle so sidecars (llama-server, whisper-cli, sherpa-onnx-offline-tts)
   can be found without a system PATH entry.
4. Shows a startup progress screen until the core answers `GET /api/health`,
   then loads the app.
5. Stops the core when the app window closes (see "Core sidecar lifecycle").

Model weights are **never** included in the bundle.

To verify a built core end-to-end without launching the window:

```bash
./scripts/packaged-core-smoke.sh
```

It starts the packaged binary against a throwaway data root and asserts health
readiness, loopback-only binding, official-pack seeding, an offline
`convsim offline-smoke-test` run against a pack the binary shipped, and both
teardown paths — closing the stdin pipe, and the SIGTERM the shell falls back
to — draining the FastAPI lifespan and releasing the port.
`release.yml` runs it on every non-Windows release build.

### Editions

The shell is compiled as one of two editions (issue #495):

| Edition | How it is built | What differs |
|---------|-----------------|--------------|
| `full` (default) | `tauri build` as above | The complete app. |
| `demo` | `VITE_CONVSIM_EDITION=demo` for the web build (Vite only exposes `VITE_`-prefixed variables), `CONVSIM_EDITION=demo` for `tauri build` (exactly that value — `build.rs` rejects anything else), plus `--config src-tauri/tauri.demo.conf.json` | The Steam Next Fest demo: product name "Conversation Simulator Demo", its own bundle identifier, its own icon set (below), and `CONVSIM_EDITION=demo` handed to `convsim-core` at launch so the engine narrows itself to one model and five conversations. |

`build.rs` rejects any other value. Whatever the edition, the shell keys the
per-user data directory (`CONVSIM_DATA_ROOT`) to the **full** app's bundle
identifier, so a model downloaded in the demo is reused by the full app. The
release workflow's `edition` input drives all of this in CI — see
[docs/steam-next-fest-demo.md](../../docs/steam-next-fest-demo.md).

The repo ships **placeholder** app icons in `src-tauri/icons/` so the app
compiles out of the box. Replace them before shipping a distributable:

```bash
# Regenerate the full icon set from a 1024×1024 source PNG:
pnpm --filter @convsim/desktop tauri icon assets/icon.png
```

The demo edition has its **own** icon set in `src-tauri/icons-demo/`, selected
by `bundle.icon` in `tauri.demo.conf.json`: the same speech-bubble mark on a
purple plate instead of the full app's teal, with a "DEMO" ribbon on the
frames large enough to read one. Without it the demo and the full game are
indistinguishable in the Steam client. Regenerate it — and the matching
Steamworks App Icon and Shortcut Icon under `publishing/assets/icons/` — with:

```bash
python3 publishing/assets/source/gen_icons.py
```

---

## Executable resolution

The Tauri shell finds `convsim-core` using this priority order (same convention
as the Python sidecar resolver — see [docs/sidecar-bundling.md](../../docs/sidecar-bundling.md)):

1. **`CONVSIM_CORE_EXECUTABLE`** env-var override — absolute path to the binary.
2. **`CONVSIM_BUNDLED_RUNTIME_DIR`** — a `convsim-core[.exe]` file inside the
   bundled runtime directory (Steam / packaged builds).
3. **Tauri resource directory** — `convsim-core[.exe]` or `bin/convsim-core`
   adjacent to the installed app bundle.
4. **PATH lookup** — `which convsim-core` / `where convsim-core` (dev builds).

---

## Core sidecar lifecycle

The shell owns the engine process from launch to teardown. The state machine
lives in `supervise_core` (`src-tauri/src/lib.rs`) and reports every transition
to the front-end as a `core-status` event.

**Readiness is `GET /api/health`, not an open port.** A TCP connect only answers
"something is on 7355", which is not the question the shell has. It used to
accept that as readiness, so *any* program holding the port made the shell
declare ready and mount the UI over a stranger's socket. The shell now sends a
real HTTP request and requires the body to look like a convsim-core health
response — which also tells it, in the same exchange, which edition is running.

Specifically: a 200 whose body carries a string `status`, a string `version` and
an object `database`. Not `status` alone — `{"status":"ok"}` is the most common
health-response shape there is and `/api/health` a common path, so that key by
itself identifies nothing and an occupant answering it would be adopted as our
engine. All three have been required fields of `HealthResponse` since the
service's first commit, so the test rejects nothing that has ever been a
convsim-core (`edition` has not, hence its `"full"` default). The front-end's
own health fast-path applies the same test, so it cannot bypass the startup
screen on an answer the shell would reject.

(For an engine the shell started itself an open port does track readiness closely:
`uvicorn.run()` binds its socket *after* the FastAPI lifespan completes, so the
two are about 40 ms apart. That is a property of how the engine happens to be
launched, not a contract — and it never distinguished our engine from anybody
else's.)

**Port already in use.** If something is on 7355 the shell asks it for
`/api/health`:

| Answer | What happens |
|---|---|
| A convsim-core of this edition | Attach to it; no second engine is started. In a release build the shell then re-checks it every 3 s and takes the port over if it goes away — see "Adopting an engine" below. |
| A convsim-core of the *other* edition | Error: the demo and the full app share the port and one data directory, so attaching would give the wrong library (issue #495). |
| Anything else, for 30 s | Error: `Port 7355 is already in use by another program.` The grace period exists because `/api/health` awaits the LLM, STT and TTS probes in sequence — the two that call sidecars over HTTP allow 5 s each, so one answer can take just over 10 s — and because the occupant may be an engine mid-restart. It is twice a single probe's budget on purpose, so one slow answer still leaves room for a second attempt. |

The port can also be taken *after* the shell finds it free, in the window its own
engine spends unpacking and migrating. The engine then exits because it cannot
bind, and the shell asks the port the same question again rather than reporting
an exit status the logs can only explain as "the port was taken". The answer
decides what the player is told, and the three cases need different advice:

| What won the race | What the player is told |
|---|---|
| The *other* edition's engine | Close the other one (same message as the attach path above). The demo and the full app are separate Steam apps and may be launched together. |
| A convsim-core of *this* edition | `Conversation Simulator is already running.` — a second copy of the app was launched while this one was starting. There is no single-instance plugin; Steam and macOS LaunchServices refuse a second launch themselves, but the installer `.exe` and the AppImage can both be run twice. |
| Anything else, for 30 s | `Port 7355 is already in use by another program.` |

The middle row is why it is not all one message: the port-conflict hint tells the
player to close whatever holds 7355, and there that is the engine serving the
window which *did* start.

The last row carries the same 30 s grace as the attach table above, and needs it
more. Reaching this point means the port was free when the attach loop asked and
our own child then died for failing to bind it, so whatever won the race is
almost certainly a convsim-core; taking one unidentified answer as proof of a
stranger would give the middle row's case the bottom row's advice.
`identify_port_occupant` is that grace, factored out of the attach loop for the
callers that cannot interleave their own progress messages.

The losing engine usually takes *longer* to exit than the winner takes to answer
`/api/health`, so the shell often meets the winner before its own child is gone.
Two more moments therefore ask the port the same question and report from the
same table:

- A readiness probe answered by the **other edition** is not readiness. The
  shell stops its own child and reports the error, because mounting this build
  over that engine gives the wrong library (issue #495) — the attach path's
  edition check, applied to the one path that could otherwise bypass it.
- A child that exits *after* readiness was reported, while a convsim-core is
  still serving 7355, was never the engine on the port. That is not a crash and
  no restart can fix it, so the shell says which window to use instead of
  flapping the UI through three attempts and settling on "keeps stopping".

**Adopting an engine.** An engine the shell did not start has no child handle,
so it cannot be supervised — but a release build re-checks the port every 3 s
(a bare TCP connect, so the adopted engine pays nothing for being watched) and
takes it over once nothing is listening. uvicorn closes its listening socket at
the *start* of its shutdown, so an engine on its way out stops accepting well
before it exits. That matters because teardown
drains the engine rather than killing it, and the drain can take as long as
`core_process::GRACE`: a player who quits and reopens the app inside that
window adopts an engine that is already on its way out, and without the re-check the UI would mount over a port that disappears a
moment later, with every request failing and nothing on screen to say why. Dev
builds do not re-check — `dev-desktop.sh` owns that engine and the developer has
its terminal.

**Crash restart.** After readiness the shell watches the child. An engine that
exits on its own is restarted up to three times with 1 s / 2 s / 4 s backoff,
announced to the UI as a `restarting` phase; the counter resets once an engine
has served for five minutes, and exhausting it shows the recovery card rather
than looping. A `shutting_down` flag separates a deliberate teardown from a
crash, so quitting the app cannot race the supervisor into spawning a
replacement engine that nothing will ever stop.

The front-end unmounts for the duration because nothing is serving 7355 until
the replacement binds, not because the session is lost: a session's flow state,
state variables and transcript live in the engine's SQLite database, so the
replacement reads them back and the remount resumes the conversation
(`Conversation`'s start call gets 409 `INVALID_TRANSITION` and rehydrates from
`/transcript`). The turn that was in flight is lost, and the state meters stay
blank until the next reply restates `visible_state`.

*Known limitation of the restart path:* a crash is by definition not a
lifespan shutdown, so the engine that died never ran `supervisor.stop_all()`
and its own sidecars survive it — llama-server keeps port 7356, the STT
worker 7357 and the TTS worker 7358. The replacement engine starts and serves,
and its `llama-server` autostart then fails with `Port 7356 … is already in use`
(`ensure_llama_sidecar_running`) — reported through `sidecar_diagnostics` in
`/api/health` and surfaced by the UI as "another application is using the
required port".

Conversations usually still work: `LlamaCppRuntime` talks to llama-server over
HTTP at `127.0.0.1:7356` and does not care which process started it, so both
`runtime.health()` and `/v1/chat/completions` land on the orphan, which is still
serving the same model. What breaks is *managing* it — switching models goes
through the same autostart and keeps hitting the conflict.

Nothing clears the orphan on its own, and in particular **relaunching does
not**: the replacement engine's `stop_all()` only stops sidecars it started a
process for, and the shell's teardown reaches the *replacement's* process group
(Unix) or process tree (Windows) — the orphan belongs to the group of the engine
that died, and its parent is that same dead engine, so it is in neither. It has
to be ended by hand.

**Clean shutdown.** Handled by `src-tauri/src/core_process.rs`, which both the
`RunEvent::Exit` handler and the managed state's `Drop` go through: the shell
closes the write end of the engine's stdin pipe, which `parent_watch` reads as
EOF and turns into a graceful uvicorn stop, and only kills the whole process
group (Unix) or tree (`taskkill /T`, Windows) if the engine is still up after
`GRACE`. The ask matters: a graceful stop is what lets uvicorn run the lifespan
shutdown, and that shutdown is where `supervisor.stop_all()` stops the engine's
*own* children. A bare `kill()` left llama-server and the voice workers running
after the window closed, holding ports 7356-7358 and several GB of RAM. See
[docs/sidecar-bundling.md](../../docs/sidecar-bundling.md#shutdown) for the full
process tree and why the handle the shell holds is only the bootloader.

## Startup progress and error handling

The web UI displays a startup screen (rendered by `CoreStartupGuard` in
`apps/web/src/screens/CoreStartup.tsx`) that:

- Shows live progress messages as the core service starts.
- Displays an actionable error card if the core executable is missing, the
  port is already in use, or the process crashes before becoming healthy.
- Reappears over the app while the engine is restarting, and remounts the app
  when the replacement reports ready — readiness tracks the shell's current
  phase rather than latching on the first success, so a crash mid-session cannot
  leave the UI mounted over a dead port.
- Passes through immediately in non-Tauri (browser) contexts.
- On a fast health check success (e.g. core already running in dev), the
  startup screen is bypassed entirely. That check applies the same test as the
  shell's probe — a 200 whose body is not a convsim-core health response does
  not count, so a stranger on 7355 cannot bypass the startup screen either.
  It also never overrules a phase the shell has already reported: the request is
  issued at once, but acted on only after `get_core_status` has answered, because
  the shell reports its fast failures (missing binary, port conflict, the other
  edition's engine) from `setup()` — before this webview exists, so they arrive
  through that snapshot rather than as events, two IPC round-trips behind a
  single local fetch.

---

## Permissions

| Feature | Mechanism |
|---|---|
| Microphone | Browser `getUserMedia` / Web API — OS prompt on first use |
| File open/save dialogs | `tauri-plugin-dialog` (`dialog:allow-open`, `dialog:allow-save`) |
| Open data folder | `tauri-plugin-shell` (`shell:allow-open`) |
| Local asset playback | WebView `<audio>`/`<video>` — no extra permission needed |
| Filesystem read/write | `tauri-plugin-fs` (`fs:allow-read-text-file`, `fs:allow-read-dir`, `fs:allow-write-text-file`) |

Capability definitions live in `src-tauri/capabilities/default.json`.

### Microphone notes

- **macOS**: The OS shows a standard permission dialog on first access.
  If denied, users must re-enable in System Settings → Privacy → Microphone.
- **Linux**: WebKit may require PipeWire / PulseAudio and the
  `xdg-desktop-portal` for permission mediation.
- **Windows**: Windows Security may prompt; WebView2 inherits the browser
  permission model.

---

## Architecture

```
apps/desktop/
├── package.json                 # @tauri-apps/cli + @tauri-apps/api
└── src-tauri/
    ├── Cargo.toml               # Rust crate manifest
    ├── build.rs                 # tauri-build hook
    ├── tauri.conf.json          # Product name, window, bundle settings
    ├── capabilities/
    │   └── default.json         # Window permission grants
    ├── icons/                   # Placeholder app icons (replace with `tauri icon`)
    ├── icons-demo/              # Demo-edition app icons (gen_icons.py)
    └── src/
        ├── main.rs              # OS entry point
        └── lib.rs               # Tauri Builder, core process management
```

The `frontendDist` path in `tauri.conf.json` points to `../../web/dist`,
so the production build consumes the output of `pnpm --filter @convsim/web build`.

In production, `apps/web/src/api/client.ts` detects the `tauri://localhost` (or
`https://tauri.localhost` on Windows) origin and switches the API base URL to
`http://127.0.0.1:7355/api` and the WebSocket base to `ws://127.0.0.1:7355/ws`.

---

## Tests

```bash
./scripts/desktop-smoke.sh   # cargo check (±steam) + cargo test
```

(`scripts/desktop-smoke.ps1` is the PowerShell twin.)

The crate's unit tests cover the sidecar state machine: HTTP/health parsing, the
port-conflict and foreign-edition guards, the executable resolution order, and
the restart backoff. The readiness probe is exercised against real loopback
sockets — a silent squatter, a 503, a stub engine, and an occupant that only
identifies itself on the second ask. The crash watcher is exercised against real
child processes: one that exits on its own (restart), one running under a
teardown already in progress (no restart), and a handle teardown has already
taken (no restart).

CI runs them on **both** Linux and Windows, because `core_process`'s teardown
has two separate implementations (`killpg` and `taskkill /T`) and the Linux job
cannot compile the Windows one. Those tests spawn a stand-in engine with a
stand-in sidecar grandchild and assert that neither survives teardown — the
failure they guard against is silent, because the hard-kill fallback still stops
the process the shell holds a handle on while the engine's own sidecars are
orphaned.

## Known limitations

- **Auto-update** is not configured.
- **Code signing** is not configured — macOS Gatekeeper will warn on unsigned
  builds unless you sign with a Developer ID certificate.
- **App icons** are placeholders. Run `pnpm tauri icon <source.png>` to replace
  them with real branding before building a distributable.
