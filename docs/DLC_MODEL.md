<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# DLC Model Contract

> **Purpose:** Define what can and cannot be DLC, the depot layout for DLC
> packs, and the runtime ownership-gate API. This document is the authoritative
> reference for any issue or PR that touches premium scenario-pack DLC.
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

## Steamworks registration

Each premium pack is registered as a separate **DLC app** under the base
Conversation Simulator App ID in the Steamworks partner portal.

| Artifact | Location |
|----------|----------|
| DLC App IDs | `STEAM_DLC_APP_IDS` GitHub repository variable (comma-separated) |
| DLC depot template | [`steam/depot_dlc.vdf.tpl`](../steam/depot_dlc.vdf.tpl) |
| Registration checklist | [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — DLC registration |
| Compliance gate | SP-05 in [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) |

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

## Runtime ownership gate

The app gates DLC pack playability by Steam ownership. A player who does not
own a DLC App ID sees the pack in the library as "Available on Steam" but
cannot launch a scenario from it.

### Rust: `SteamRuntime::is_dlc_installed`

```rust
// apps/desktop/src-tauri/src/steam.rs
runtime.is_dlc_installed(dlc_app_id: u32) -> bool
```

Returns `true` when the Steamworks SDK confirms the local user owns and has
installed the DLC with the given App ID. Returns `false` when Steam is
unavailable, the user does not own the DLC, or the DLC is not installed.

### React hook: `useSteamDlc`

```typescript
// apps/web/src/hooks/useSteamDlc.ts
const { isDlcInstalled } = useSteamDlc()
isDlcInstalled(dlcAppId: number): Promise<boolean>
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

## Pack library UI

See #364 for the pack library UI changes that show owned DLC as playable and
unowned DLC as available-to-buy (with a Steam store link).

---

## Links

- [`docs/STEAM_ROADMAP.md`](STEAM_ROADMAP.md) — release train, DLC stage (Stage 5)
- [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — DLC registration checklist
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — SP-05
- [`steam/depot_dlc.vdf.tpl`](../steam/depot_dlc.vdf.tpl) — DLC SteamPipe depot template
- [`apps/web/src/hooks/useSteamDlc.ts`](../apps/web/src/hooks/useSteamDlc.ts) — React ownership-gate hook
- [`apps/desktop/src-tauri/src/steam.rs`](../apps/desktop/src-tauri/src/steam.rs) — Rust ownership-gate method
- [outrightmental/ConversationSimulator-DLC](https://github.com/outrightmental/ConversationSimulator-DLC) — private DLC repo
