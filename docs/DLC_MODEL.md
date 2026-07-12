<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# DLC Model — Pack → Steam DLC Contract

> **Purpose:** Define the contract between premium scenario packs in this
> repository and their corresponding Steamworks DLC applications. This document
> specifies which packs qualify as premium DLC, the manifest fields the app
> loader uses to identify and gate DLC packs, how the app checks Steam DLC
> ownership at runtime, and how CI deploys DLC content depots.
>
> **Audience:** Platform team members, Outright Mental staff, and anyone adding
> a new premium pack to the DLC catalogue.
>
> **Authoritative ID mapping:** App ID ↔ pack ID ↔ depot ID is recorded in
> [`publishing/STEAM_DLC_REGISTRY.md`](../publishing/STEAM_DLC_REGISTRY.md).
> This document defines the _rules_; the registry records the _values_.

---

## Overview

Conversation Simulator uses Steam DLC as the distribution mechanism for premium
first-party scenario packs. Each premium pack is a Steamworks DLC App — a child
application of the base app — with its own store page, price, and a single
cross-platform content depot.

The app loader checks Steam DLC ownership at pack load time. A player who has
not purchased a DLC pack sees the pack listed (so they can discover and buy it)
but cannot start a session from it. The session start button is replaced with a
"Get on Steam" link to the DLC's store page.

Community packs and base-app-bundled packs are unaffected by this mechanism.

---

## Which packs are DLC

A pack is premium DLC if and only if its `manifest.yaml` contains a non-zero
`steam_dlc_app_id` field. Packs without this field (or with `steam_dlc_app_id:
0`) are treated as freely available to all players.

The four packs bundled with the base app — Job Interview Basics, Everyday
Negotiation, Difficult Conversations, and Language Café — do **not** carry a
`steam_dlc_app_id` and are always accessible after purchasing the base app.

The tutorial pack (`tutorial.first_words`) is also always accessible and never
gated.

---

## Manifest contract

To register a pack as premium DLC, add the following field to its
`manifest.yaml`:

```yaml
# Steamworks DLC App ID assigned by Valve for this pack.
# 0 or absent = freely accessible to all owners of the base app.
# Non-zero = requires DLC ownership check via Steam API.
steam_dlc_app_id: 0  # replace with the actual App ID from STEAM_DLC_REGISTRY.md
```

The value must match the DLC App ID recorded in
[`publishing/STEAM_DLC_REGISTRY.md`](../publishing/STEAM_DLC_REGISTRY.md).
Setting an incorrect App ID causes all players to see the pack as unpurchased.

### Full manifest example (premium DLC pack)

```yaml
schema_version: "0.1"
pack_id: official.dating_confidence_boundaries
name: Dating — Confidence & Boundaries
version: 1.0.0
description: >-
  Practice the social skills that make dating feel less daunting and more
  human: starting a conversation, asking someone out, accepting a no with
  grace, setting a clear boundary, and building genuine first-date connection.
author: Outright Mental
license: CC-BY-4.0
content_rating: PG-13
steam_dlc_app_id: 0  # replace with assigned DLC App ID
```

---

## App-side ownership check

The app loader (`packages/pack-loader`) calls
`SteamAPI_ISteamApps_BIsDlcInstalled(dlc_app_id)` from the Steamworks SDK
before allowing a session to start from any pack where
`steam_dlc_app_id > 0`.

Behaviour by context:

| Context | `steam_dlc_app_id` | Ownership check | Result |
|---------|-------------------|-----------------|--------|
| Running under Steam, DLC owned | non-zero | `BIsDlcInstalled` → `true` | Full access |
| Running under Steam, DLC not owned | non-zero | `BIsDlcInstalled` → `false` | Pack visible, session blocked, "Get on Steam" link shown |
| Running outside Steam (dev/CLI) | non-zero | Steam not initialised | Full access — DLC gate is a Steam-only control |
| Any pack | 0 or absent | Not called | Full access |

The ownership check is non-blocking — the pack card renders immediately and the
check result updates the UI asynchronously. This prevents a slow or unavailable
Steam client from blocking the pack library from loading.

---

## Content depot layout

Each DLC App gets a single cross-platform content depot. The depot contains
only the pack directory for the corresponding `pack_id`:

```
<depot root>/
  packs/
    official/
      <pack-slug>/
        manifest.yaml
        scenarios/
        npcs/
        safety/
        assets/
```

The pack directory layout mirrors the layout in the repository's `packs/official/`
directory. The loader resolves DLC pack paths through Steam's
`ISteamApps::GetAppInstallDir()` on the DLC App ID, then appends the relative
pack path.

DLC depot VDF templates are not yet checked into the `steam/` directory. When
a new DLC is registered, add a `steam/depot_dlc_<pack-slug>.vdf.tpl` following
the same pattern as the existing platform depot templates, substituting the DLC
depot ID from `publishing/STEAM_DLC_REGISTRY.md`.

---

## CI deployment

The base-app deploy workflow (`.github/workflows/steam-deploy.yml`) deploys
only the three platform depots for the base app. DLC depots are deployed
separately by extending the workflow with a DLC depot push step.

For each registered DLC:

1. Add a `vars.STEAM_DLC_DEPOT_<PACK_SLUG>_ID` GitHub repository variable
   containing the DLC's depot ID from `publishing/STEAM_DLC_REGISTRY.md`.
2. Add a `steam/depot_dlc_<pack-slug>.vdf.tpl` depot VDF template that maps
   the depot to `packs/official/<pack-slug>/`.
3. Add the DLC depot to the `Depots` block in a DLC-specific app build VDF
   (`steam/app_build_dlc_<pack-slug>.vdf.tpl`), referencing the DLC App ID
   (not the base App ID).
4. Trigger a `steamcmd +run_app_build` for the DLC app build VDF after the base
   app build completes.

DLC builds are staged to the same `beta` / `default` branch strategy as the
base app. A DLC build must not be set live before the base app build that
contains the matching `steam_dlc_app_id` value in the pack manifest.

---

## Adding a new premium DLC pack — checklist

Follow these steps when promoting an existing pack to premium DLC status.

- [ ] Confirm the pack passes all content quality criteria
      ([`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md))
      and has an approved content rating.
- [ ] Register the DLC App ID and depot in Steamworks — see
      [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md#dlc-registration).
- [ ] Record the assigned App ID, depot ID, and price in
      [`publishing/STEAM_DLC_REGISTRY.md`](../publishing/STEAM_DLC_REGISTRY.md).
- [ ] Set `steam_dlc_app_id` in the pack's `manifest.yaml` to the assigned
      DLC App ID.
- [ ] Add the `vars.STEAM_DLC_DEPOT_<PACK_SLUG>_ID` GitHub repository variable.
- [ ] Add `steam/depot_dlc_<pack-slug>.vdf.tpl` and
      `steam/app_build_dlc_<pack-slug>.vdf.tpl`.
- [ ] Extend `.github/workflows/steam-deploy.yml` with the DLC depot push step.
- [ ] Verify the ownership gate in a local dev build (run without Steam to
      confirm `steam_dlc_app_id > 0` packs are fully accessible outside Steam).
- [ ] Verify the "Get on Steam" link in a test build running under the Steam
      client without the DLC owned.

---

## Links

- [`publishing/STEAM_DLC_REGISTRY.md`](../publishing/STEAM_DLC_REGISTRY.md) — authoritative App ID ↔ pack ID ↔ depot ID mapping
- [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — base app registration, pricing, and DLC registration steps
- [`docs/STEAM_ROADMAP.md`](STEAM_ROADMAP.md) — release principles and paid model rationale
- [`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md) — content quality criteria that any DLC pack must meet
- [`packs/official/`](../packs/official/) — official pack directory; DLC packs live here like any other pack
