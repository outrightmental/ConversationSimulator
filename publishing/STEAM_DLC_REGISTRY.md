<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam DLC Registry

> **Purpose:** Authoritative mapping of Steamworks App IDs and depot IDs to
> premium scenario packs. Update this file immediately after registering a new
> DLC in the Steamworks partner portal. Never hardcode these IDs anywhere else
> — always reference this file.
>
> **Audience:** Platform team members and Outright Mental staff with Steamworks
> partner portal access.
>
> **See also:** [`docs/DLC_MODEL.md`](../docs/DLC_MODEL.md) — the full
> pack → DLC contract: manifest fields, ownership checks, and CI deployment.
> [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — base
> app registration and DLC registration steps.

---

## Base app

| Field | Value |
|-------|-------|
| **App ID** | *(pending Valve assignment — record here after registration)* |
| **GitHub variable** | `vars.STEAM_APP_ID` |
| **Base price** | $9.99 USD |
| **Package type** | Paid (Store) |
| **Package ID** | *(pending Valve assignment — record here after registration)* |

---

## Premium DLC packs

Each row below corresponds to one premium scenario pack registered as a
Steamworks DLC App. `steam_dlc_app_id` in the pack's `manifest.yaml` must
match the **DLC App ID** column exactly.

IDs marked `TBD` have not yet been assigned by Valve. Complete the
registration steps in
[`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md#dlc-registration)
and replace each `TBD` with the assigned value.

| Pack ID | Display Name | DLC App ID | Content Depot ID | Price (USD) | Status |
|---------|-------------|------------|-----------------|-------------|--------|
| `official.dating_confidence_boundaries` | Dating — Confidence & Boundaries | TBD | TBD | $4.99 | Pending registration |

---

## Column definitions

| Column | Description |
|--------|-------------|
| **Pack ID** | `pack_id` from the pack's `manifest.yaml`. Must be unique across all packs. |
| **Display Name** | `name` from the pack's `manifest.yaml`. Used as the DLC display name in Steamworks. |
| **DLC App ID** | Seven-digit App ID assigned by Valve when the DLC is registered in the Steamworks partner portal. Set as `steam_dlc_app_id` in `manifest.yaml`. |
| **Content Depot ID** | Depot ID assigned by Valve for the DLC's content depot. Store as `vars.STEAM_DLC_DEPOT_<PACK_SLUG>_ID` in GitHub repository variables. |
| **Price (USD)** | Base USD price set in Steamworks. Regional prices follow Valve's suggested tier for this price point. |
| **Status** | `Pending registration` → `Registered` → `Live` |

---

## How to add a new DLC

1. Follow the DLC registration steps in
   [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md#dlc-registration).
2. Record the assigned **DLC App ID** and **depot ID** in the table above.
3. Set `steam_dlc_app_id` in the pack's `manifest.yaml` to the assigned DLC
   App ID.
4. Update the **Status** column as the DLC progresses through registration
   and live deployment.

---

## Links

- [`docs/DLC_MODEL.md`](../docs/DLC_MODEL.md) — pack → DLC contract
- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — base app and DLC registration steps
- [`packs/official/dating-confidence-boundaries/manifest.yaml`](../packs/official/dating-confidence-boundaries/manifest.yaml) — first premium DLC pack manifest
