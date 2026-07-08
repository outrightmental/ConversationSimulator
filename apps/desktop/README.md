<!-- SPDX-License-Identifier: Apache-2.0 -->
# apps/desktop

Tauri v2 desktop wrapper for Conversation Simulator.

The desktop app wraps the `apps/web` React UI in a native OS window using
[Tauri](https://tauri.app). It does **not** bundle model weights or require
cloud services — it is a thin shell around the same local web experience.

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
Model weights are **never** included in the bundle.

The repo ships **placeholder** app icons in `src-tauri/icons/` so the app
compiles out of the box — Tauri embeds the window icon at compile time, so both
`tauri dev` and `tauri build` fail if the referenced icons are missing. Replace
them with real branding before shipping a distributable:

```bash
# Regenerate the full icon set from a 1024×1024 source PNG:
pnpm --filter @convsim/desktop tauri icon assets/icon.png
```

> **Alpha note:** `convsim-core` lifecycle is not yet managed by the desktop
> shell. Run it manually before launching the app (the dev script handles
> this automatically). A sidecar process will be added in a future milestone.
>
> **The production build cannot reach the backend yet.** The web UI calls the
> API via relative paths (`/api`, `/ws` — see `apps/web/src/api/client.ts`).
> In dev mode the Vite dev server proxies those to `convsim-core` on port 7355,
> but a `tauri build` bundle serves the frontend from `tauri://localhost` with
> no such proxy, so backend-dependent screens (Model Manager, Scenario Library,
> Conversation, Debrief, Settings) will fail to load data even if `convsim-core`
> is running. **Dev mode (`./scripts/dev-desktop.sh`) is the only supported
> alpha path.** Wiring the production bundle to the backend (sidecar + absolute
> API base or a Tauri-side proxy) is tracked as future work.

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
        └── lib.rs               # Tauri Builder with plugins
```

The `frontendDist` path in `tauri.conf.json` points to `../../web/dist`,
so the production build consumes the output of `pnpm --filter @convsim/web build`.

---

## Limitations (alpha)

- **convsim-core sidecar** is not yet bundled. The core server must be started
  separately. See `./scripts/dev-desktop.sh` for the reference flow.
- **Production builds cannot reach the backend.** The web UI uses relative
  `/api` and `/ws` requests that only the Vite dev proxy resolves; a `tauri
  build` bundle has no proxy, so only dev mode is functional in the alpha.
  See the alpha note under "Production build" above.
- **Auto-update** is not configured.
- **Code signing** is not configured — macOS Gatekeeper will warn on unsigned
  builds unless you sign with a Developer ID certificate.
- **App icons** are placeholders. Run `pnpm tauri icon <source.png>` to replace
  them with real branding before building a distributable.
