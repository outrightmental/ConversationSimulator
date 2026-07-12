<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# DLC Model Contract

> **Purpose:** Define what can and cannot be DLC, the depot layout for DLC
> packs, the build-time registry configuration, and the runtime ownership-gate
> API. This document is the authoritative reference for any issue or PR that
> touches premium scenario-pack DLC.
>
> **Audience:** Platform team, publishing team, and DLC pack authors working in
> the private [`ConversationSimulator-DLC`](https://github.com/outrightmental/ConversationSimulator-DLC)
> repo.

---

## The invariant

> **Nothing that ships free in the base app may ever be relocked as paid DLC.**

DLC is always additive. The four official packs included in the base app are
Apache-2.0 / CC BY 4.0 and remain so permanently. Community packs are free.
Premium DLC packs are new content, sourced from the private DLC repo, sold
only on Steam.

---

## What can be DLC

- First-party scenario packs authored in the private
  [`ConversationSimulator-DLC`](https://github.com/outrightmental/ConversationSimulator-DLC)
  repo.
- Each DLC pack is a standard scenario pack (same schema as
  [`schemas/pack.schema.json`](../schemas/pack.schema.json)) with a proprietary
  `LicenseRef-*` identifier (see #365) reflecting its non-open license.

## What can never be DLC

- Any pack or scenario already released in the base app or on GitHub.
- Engine features, bug fixes, or UI improvements — these ship in the base app.
- Community packs — they are always free.

---

## Concepts

| Term | Description |
|---|---|
| **Pack** | A directory of YAML scenario files identified by a `pack_id` string (e.g. `official.premium_conversations`). |
| **DLC App ID** | A Valve-assigned Steam Application ID for a DLC item tied to the base game. Distinct from the base game's own App ID. |
| **DLC registry** | The build-time mapping of `pack_id` → DLC App ID, encoded in `STEAM_DLC_APP_IDS` and baked into the desktop bundle. |

---

## Steamworks registration

Each premium pack is registered as a separate **DLC app** under the base
Conversation Simulator App ID in the Steamworks partner portal.

| Artifact | Location |
|----------|----------|
| DLC App IDs | `STEAM_DLC_APP_IDS` GitHub repository variable (comma-separated `pack_id:dlc_app_id` pairs) |
| DLC depot template | [`steam/depot_dlc.vdf.tpl`](../steam/depot_dlc.vdf.tpl) |
| Registration checklist | [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — DLC registration |
| Compliance gate | SP-05 in [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) |

### `STEAM_DLC_APP_IDS` variable format

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

---

## DLC depot layout

Each DLC pack ships in its own depot (one depot per DLC App ID). The depot
contains only the pack content — YAML scenario files, character assets, and
any audio/image assets used by the pack. Engine binaries and model weights are
never included.

The depot is built from the private DLC repo and deployed via its own Steam
deploy pipeline (outrightmental/ConversationSimulator-DLC#2).

When installed, Steam places the DLC content at:

```
<Steam install dir>/steamapps/common/Conversation Simulator/dlc/<dlc-app-id>/
```

The app discovers installed DLC packs by scanning that directory at startup.

---

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

---

## Runtime ownership gate

The app gates DLC pack playability by Steam ownership. A player who does not
own a DLC App ID sees the pack in the library as "Available on Steam" but
cannot launch a scenario from it.

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

### Rust: `SteamRuntime::is_dlc_installed`

```rust
// apps/desktop/src-tauri/src/steam.rs
runtime.is_dlc_installed(dlc_app_id: u32) -> bool
```

Returns `true` when the Steamworks SDK confirms the local user owns and has
installed the DLC with the given App ID. Returns `false` when Steam is
unavailable, the user does not own the DLC, or the DLC is not installed.

The Tauri command wrapper in `lib.rs`:

```rust
steam_is_dlc_installed(dlc_app_id: u32, state: tauri::State<SteamRuntimeState>) -> bool
```

### React hook: `useSteamDlc`

```typescript
// apps/web/src/hooks/useSteamDlc.ts
const { isDlcInstalled, isDlcInstalledForPack } = useSteamDlc()

// Option 1 — convenience wrapper (preferred):
const owned = await isDlcInstalledForPack('official.premium_conversations')

// Option 2 — explicit App ID:
const appId = DLC_REGISTRY['official.premium_conversations']
if (appId !== undefined) {
  const owned = await isDlcInstalled(appId)
}
```

Calls the `steam_is_dlc_installed` Tauri command. Degrades gracefully to
`false` in a browser context or when the `steam` Cargo feature is disabled.

### Pack schema: `dlc_app_id` field

A DLC pack's `manifest.yaml` carries an optional `dlc_app_id` field (integer).
When the field is present and non-zero, the app calls `isDlcInstalled` before
allowing a scenario from that pack to be launched.

```yaml
# packs/dlc/<pack-id>/manifest.yaml
dlc_app_id: 1234567   # Steam DLC App ID; omit for free packs
```

Packs without `dlc_app_id` (or with `dlc_app_id: 0`) are always playable.

---

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

---

## Pack library UI

See #364 for the pack library UI changes that show owned DLC as playable and
unowned DLC as available-to-buy (with a Steam store link).

---

## Adding a new DLC pack

1. Register a child DLC app in Steamworks App Admin (parent: the base game's
   App ID). Note the assigned DLC App ID.
2. Author the new pack in the private `ConversationSimulator-DLC` repo with a
   unique `pack_id` and `dlc_app_id` in its `manifest.yaml`.
3. Append `new_pack_id:dlc_app_id` to the `STEAM_DLC_APP_IDS` repository
   variable in GitHub Actions settings.
4. Update `STEAM_DLC_REGISTRY.md` in the private repo.
5. Trigger a new release build — the DLC registry is baked in at compile time.

---

## Links

- [`docs/STEAM_ROADMAP.md`](STEAM_ROADMAP.md) — release train, DLC stage (Stage 5)
- [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — DLC registration checklist
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — SP-05
- [`steam/depot_dlc.vdf.tpl`](../steam/depot_dlc.vdf.tpl) — DLC SteamPipe depot template
- [`apps/web/src/hooks/useSteamDlc.ts`](../apps/web/src/hooks/useSteamDlc.ts) — React ownership-gate hook
- [`apps/desktop/src-tauri/src/steam.rs`](../apps/desktop/src-tauri/src/steam.rs) — Rust ownership-gate method
- [outrightmental/ConversationSimulator-DLC](https://github.com/outrightmental/ConversationSimulator-DLC) — private DLC repo
