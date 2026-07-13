# DLC Model

Conversation Simulator uses Steam DLC to gate premium scenario packs behind a
one-time purchase. This document describes how DLC App IDs are configured,
how ownership is checked at runtime, and how the open-source / browser build
falls back gracefully when Steam is absent.

## Concepts

| Term | Description |
|---|---|
| **Pack** | A directory of YAML scenario files identified by a `pack_id` string (e.g. `official.premium_conversations`). |
| **DLC App ID** | A Valve-assigned Steam Application ID for a DLC item tied to the base game. Distinct from the base game's own App ID. |
| **DLC registry** | The build-time mapping of `pack_id` → DLC App ID, encoded in `STEAM_DLC_APP_IDS` and baked into the desktop bundle. |

## DLC App ID configuration

DLC App IDs are registered in the Steamworks App Admin portal (one child app per
premium pack). The full registry is maintained in the private
`STEAM_DLC_REGISTRY.md` and mirrored to the **`STEAM_DLC_APP_IDS` repository
variable** in GitHub Actions (Settings → Secrets and variables → Actions →
Variables).

### Variable format

```
STEAM_DLC_APP_IDS = pack_id:dlc_app_id[,pack_id:dlc_app_id …]
```

Example (hypothetical IDs):

```
official.premium_conversations:2123456,official.pro_scenarios:2123457
```

Rules:
- Each entry is `pack_id:dlc_app_id` — colon-separated, no spaces required (whitespace is trimmed).
- Multiple entries are comma-separated.
- DLC App IDs must be positive integers.
- Malformed entries are silently skipped at runtime; the build script (`build.rs`) fails loudly at compile time so typos are caught before release.

## How the build pipeline threads the registry in

At Tauri build time (`pnpm --filter @convsim/desktop build`), the CI step sets:

```yaml
VITE_STEAM_DLC_APP_IDS: ${{ vars.STEAM_DLC_APP_IDS }}
```

This env var is picked up in two places:

1. **`apps/desktop/src-tauri/build.rs`** — validates the format and emits
   `cargo:rerun-if-env-changed=VITE_STEAM_DLC_APP_IDS` so Cargo re-runs
   the build script when the variable changes.

2. **Vite frontend bundle** — Vite automatically bakes all `VITE_*` env vars
   into the JavaScript bundle as `import.meta.env.VITE_STEAM_DLC_APP_IDS`.
   The `DLC_REGISTRY` export in `useSteamDlc.ts` is parsed from this value at
   bundle load time.

The `tauri.conf.json` `beforeBuildCommand` re-runs `pnpm --filter @convsim/web build`
as part of `tauri build`, so both targets receive the env var in a single CI step.

## Runtime ownership check

```
pack_id  →  DLC_REGISTRY lookup  →  dlc_app_id
                                         │
                                         ▼
                               steam_is_dlc_installed (Tauri command)
                                         │
                                         ▼
                               SteamRuntime::is_dlc_installed
                                         │
                                         ▼
                               ISteamApps::IsDlcInstalled(appId)
```

### TypeScript (pack layer)

```typescript
import { useSteamDlc, DLC_REGISTRY } from '../hooks/useSteamDlc'

const { isDlcInstalled, isDlcInstalledForPack } = useSteamDlc()

// Option 1 — convenience wrapper (preferred):
const owned = await isDlcInstalledForPack('official.premium_conversations')

// Option 2 — explicit App ID:
const appId = DLC_REGISTRY['official.premium_conversations']
if (appId !== undefined) {
  const owned = await isDlcInstalled(appId)
}
```

### Rust (Tauri command, `lib.rs`)

```rust
steam_is_dlc_installed(dlc_app_id: u32, state: tauri::State<SteamRuntimeState>) -> bool
```

Delegates to `SteamRuntime::is_dlc_installed(dlc_app_id)`, which calls
`ISteamApps::IsDlcInstalled` via the `steamworks` crate.

## Open-source / browser build behavior

When `STEAM_DLC_APP_IDS` is not configured (open-source contributors, browser
builds, any non-Steam distribution):

- `VITE_STEAM_DLC_APP_IDS` is absent → `DLC_REGISTRY` is an empty object.
- `isDlcInstalledForPack(packId)` returns `false` for every pack ID
  (no DLC App ID to look up).
- `isDlcInstalled(appId)` returns `false` (no `window.__TAURI__` in a browser,
  or Steam is absent in the Tauri shell).

Premium packs are therefore treated as **not owned** in all non-Steam contexts.
The pack layer should gate premium content behind this check and surface an
appropriate upgrade prompt rather than showing an error.

## Adding a new DLC pack

1. Register a child DLC app in Steamworks App Admin (parent: the base game's
   App ID). Note the assigned DLC App ID.
2. Add the new pack manifest under `packs/` with a unique `pack_id`.
3. Append `new_pack_id:dlc_app_id` to the `STEAM_DLC_APP_IDS` repository
   variable in GitHub Actions settings.
4. Update `STEAM_DLC_REGISTRY.md` in the private repo.
5. Trigger a new release build — the DLC registry is baked in at compile time.
