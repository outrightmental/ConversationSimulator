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

- **Rust** 1.77.2+ (install via [rustup](https://rustup.rs/))
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
pnpm --filter @convsim/desktop build
```

The built installer is placed in `apps/desktop/src-tauri/target/release/bundle/`.

In a production build the Tauri shell:
1. Locates the `convsim-core` executable (see "Executable resolution" below).
2. Spawns it bound to `127.0.0.1:7355`.
3. Sets `CONVSIM_BUNDLED_RUNTIME_DIR` to the `runtimes/` dir adjacent to the
   app bundle so sidecars (llama-server, whisper-cli, sherpa-onnx-offline-tts)
   can be found without a system PATH entry.
4. Shows a startup progress screen until the core is healthy, then loads the app.
5. Kills the core process when the app window closes.

Model weights are **never** included in the bundle.

The repo ships **placeholder** app icons in `src-tauri/icons/` so the app
compiles out of the box. Replace them before shipping a distributable:

```bash
# Regenerate the full icon set from a 1024×1024 source PNG:
pnpm --filter @convsim/desktop tauri icon assets/icon.png
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

## Startup progress and error handling

The web UI displays a startup screen (rendered by `CoreStartupGuard` in
`apps/web/src/screens/CoreStartup.tsx`) that:

- Shows live progress messages as the core service starts.
- Displays an actionable error card if the core executable is missing, the
  port is already in use, or the process crashes before becoming healthy.
- Passes through immediately in non-Tauri (browser) contexts.
- On a fast health check success (e.g. core already running in dev), the
  startup screen is bypassed entirely.

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

## Known limitations

- **Auto-update** is not configured.
- **Code signing** is not configured — macOS Gatekeeper will warn on unsigned
  builds unless you sign with a Developer ID certificate.
- **App icons** are placeholders. Run `pnpm tauri icon <source.png>` to replace
  them with real branding before building a distributable.
