<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# How the App Unlocks Owned DLC

This document describes the ownership model for premium DLC packs and how the
Scenario Library UI surfaces them to players.

---

## Pack categories

| Category | Pack ID prefix | Always playable? |
|----------|---------------|-----------------|
| **Official** | `official.` | Yes — free and bundled. |
| **Premium DLC** | `premium.` | Only when owned on Steam. |
| **Workshop** | _(any other prefix)_ | Yes — player-imported content. |

---

## Official packs (always free)

The four bundled official packs are unconditionally playable for all players.
They require no DLC purchase and are never hidden or gated:

- `official.first_words`
- `official.difficult_conversations`
- `official.language_cafe`
- `official.job_interview_basic`

If an official pack is missing (e.g. the user deleted it), the Scenario Library
offers a **Restore official packs** button that re-seeds them from the bundled
source.

---

## Premium DLC packs

Premium packs are distributed as Steam DLC. Each DLC has its own Steam AppID
separate from the base game. Ownership is determined via the Steamworks
`ISteamApps::BIsDlcInstalled` API, which the desktop shell exposes as the
`steam_is_dlc_installed` Tauri command.

### DLC catalog

The authoritative catalog is declared in
`apps/web/src/hooks/useSteamDlc.ts` (`DLC_CATALOG`). Each entry stores:

| Field | Description |
|-------|-------------|
| `pack_id` | Stable identifier matching the pack manifest |
| `name` | Display name shown in the Scenario Library |
| `description` | Short marketing copy shown on the "Available to buy" card |
| `steam_dlc_app_id` | Steam AppID of the DLC (unique per DLC title) |
| `store_url` | Steam store page URL for the DLC |

### Install path convention

When a player owns a DLC and Steam installs it, the content lands at:

```
dlc/<steam_dlc_app_id>/
```

relative to the Steam DLC install root for the base game. The `convsim-core`
backend discovers pack manifests at this path and serves the scenarios through
the `/api/scenarios` endpoint exactly like any other installed pack.

### Ownership check flow

```
On Scenario Library mount
  │
  ├── Query /api/scenarios  →  list of installed packs
  │
  └── For each entry in DLC_CATALOG:
        invoke steam_is_dlc_installed(entry.steam_dlc_app_id)
            │
            ├─ true   →  DLC is owned; show scenarios as playable if installed
            └─ false  →  DLC is not owned; show "Available on Steam" card
```

---

## UI rules

1. **Never hide premium packs.** Every entry in the DLC catalog is always
   shown in the Scenario Library — either as a playable pack (owned) or as an
   "Available on Steam" card (not owned).

2. **Owned DLC = playable.** When `steam_is_dlc_installed` returns `true` and
   the pack's scenarios are in the API response, each scenario has a **Launch**
   button that routes to `/setup/<scenario_id>`.

3. **Unowned DLC = available to buy.** When a DLC catalog entry is not in the
   installed scenarios list (or the DLC is confirmed not owned), the library
   shows a locked card with the pack name, a short description, and a
   **Get on Steam** button.

4. **Steam overlay for purchases.** The **Get on Steam** button invokes
   `steam_open_dlc_store_overlay` which opens the Steam overlay to the DLC
   store page. Outside of Steam (e.g. dev / browser), it falls back to opening
   the `store_url` in the system browser.

5. **Graceful non-Steam fallback.** When Steam is unavailable (not running,
   or the `steam` Cargo feature is disabled), installed packs are assumed
   owned and shown as playable. Unowned DLC cards still appear (using browser
   fallback for the store link) so the catalog is always visible.

---

## Adding a new premium DLC pack

1. Register the DLC in the Steamworks partner portal and obtain its AppID.
2. Create the pack manifest under `packs/premium/<pack-slug>/`.
3. Add an entry to `DLC_CATALOG` in `apps/web/src/hooks/useSteamDlc.ts`
   with the confirmed `steam_dlc_app_id` and `store_url`.
4. Update the depot VDF in `steam/` to include the DLC content path.
5. Bump the DLC AppID placeholder comment in this document.

---

## References

- `apps/web/src/hooks/useSteamDlc.ts` — `DLC_CATALOG`, `useSteamDlc`, `useSteamDlcOwned`, `useSteamDlcStore`
- `apps/web/src/screens/ScenarioLibrary.tsx` — Scenario Library UI
- `apps/desktop/src-tauri/src/steam.rs` — `SteamRuntime::is_dlc_installed`, `SteamRuntime::open_dlc_store_overlay`
- `apps/desktop/src-tauri/src/lib.rs` — `steam_is_dlc_installed`, `steam_open_dlc_store_overlay` Tauri commands
- `docs/STEAM_ROADMAP.md` — Release principles and stage requirements
